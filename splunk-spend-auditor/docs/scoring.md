# Scoring y clasificación — Log Spend Auditor

Principio rector (del brief original): **nunca un "AI score = 72" sin
explicación.** Cada resultado debe poder justificarse en una frase con los
números concretos que lo generaron.

## 1. Unidad de análisis

`Dataset = (index, sourcetype)`. Ver `DECISIONS.md` D004 para por qué no se usa
host ni source como unidad (squashing de `license_usage.log`).

## 2. Señales que alimentan el score

Para cada `Dataset` se recopilan, con su fuente:

| Señal | Fuente | Tipo |
|---|---|---|
| `ingest_gb_per_day` | `license_usage.log` | volumen |
| `interactive_searches_30d` | `_audit` (excluyendo `search_id=scheduler*`) | uso |
| `interactive_searches_90d` | `_audit` | uso |
| `unique_users_30d` | `_audit` | uso |
| `is_scheduled` | `/saved/searches` | uso |
| `scheduled_search_count` | `/saved/searches` | uso |
| `has_alert_action` | `/saved/searches` (`actions` no vacío) | uso |
| `used_in_dashboards` | CSV manual opcional | uso |
| `last_seen_days_ago` | `| metadata type=sourcetypes` | actividad |
| `parser_confidence` | motor de parsing SPL | confianza |
| `is_protected` | lista de patrones + override manual del usuario | protección |

## 3. Confianza del parser (Tarea 4 / D006)

Cada búsqueda (interactiva o saved search) se analiza para determinar qué
`(index, sourcetype)` toca, con tres niveles:

- **HIGH** — el texto SPL contiene `index=<valor literal>` y/o
  `sourcetype=<valor literal>` explícitos, sin macros ni wildcards ambiguos.
  Ejemplo: `index=main sourcetype=nginx`. También cubre el caso
  `(index=web OR index=proxy)` — múltiples valores literales unidos por
  OR/paréntesis se resuelven con HIGH.
- **PARTIAL** — se detecta el uso de una macro (`` `nombre_macro` ``), un
  `eventtype=`, una subsearch (`[ search ... ]`), o `| tstats ... from
  datamodel=`, pero no se resuelve su contenido. Se registra que existe
  actividad de búsqueda, pero **no se atribuye con certeza a ningún dataset
  específico**.
- **UNKNOWN** — no se pudo extraer ningún `index=`/`sourcetype=` literal ni
  patrón reconocido (ej. `| history`, `| rest`, búsquedas puramente sobre
  índices de metadatos, o SPL vacío/roto).

**Regla dura:** un `Dataset` cuya única evidencia de "no tiene uso" proviene de
una cobertura `PARTIAL`/`UNKNOWN` generalizada del entorno (es decir, gran
parte del tráfico de búsqueda del entorno es PARTIAL/UNKNOWN) **no puede
alcanzar `POSSIBLE_WASTE`** — como máximo `REVIEW`. Esto se controla con el
parámetro agregado `partial_unknown_ratio` del entorno completo, reportado en
la sección "Methodology" del informe.

## 4. Data Value Score

Un score de 0 a 100, **enteramente derivado de reglas explícitas** (no ML), que
ordena los datasets dentro de una misma categoría para priorizar la revisión.
No determina la categoría por sí solo — la categoría depende de reglas
discretas (sección 5); el score solo ordena.

```
score = 0
score += min(interactive_searches_30d, 30)        # tope 30 puntos
score += 25 if is_scheduled else 0
score += 20 if has_alert_action else 0
score += 15 if used_in_dashboards else 0
score += 10 if unique_users_30d >= 3 else (5 if unique_users_30d >= 1 else 0)
score = min(score, 100)
```

Es intencionalmente una suma simple y auditable: cualquiera puede recalcularla
a mano con los números que aparecen en el reporte.

## 5. Reglas de clasificación (Tarea 8)

Se evalúan en este orden; la primera regla que aplica gana:

1. **`PROTECTED`** — el dataset coincide con un patrón protegido por defecto
   (ver sección 6) o el usuario lo marcó manualmente como protegido en un
   archivo de overrides. **Nunca se reclasifica automáticamente**, sin
   importar sus otras señales.

2. **`UNKNOWN`** — el dataset no tiene evidencia HIGH propia **Y** el
   `partial_or_unknown_ratio` del entorno completo supera un umbral (por
   defecto 50%, `UNKNOWN_ENVIRONMENT_RATIO_THRESHOLD` en código). Es una
   salvaguarda a nivel de **entorno**, no de dataset individual: si el
   entorno en general tiene buena cobertura de parsing (ratio bajo), el
   silencio de un dataset específico sin evidencia propia se trata como
   señal real en las reglas 3-6, no como `UNKNOWN` — no existe forma de
   saber si una búsqueda `PARTIAL` en otra parte del entorno (una macro no
   resuelta, por ejemplo) tiene algo que ver con este dataset en particular,
   así que no se le puede dar el beneficio de la duda de forma individual.
   Ver `DECISIONS.md` D009.

3. **`HIGH_VALUE`** — `is_scheduled` o `has_alert_action` es verdadero, O
   `interactive_searches_30d >= 10`, O `used_in_dashboards` es verdadero.

4. **`POSSIBLE_WASTE`** — se cumplen **todas**: `ingest_gb_per_day` está en el
   percentil superior configurable (por defecto, top 25% del entorno) **Y**
   `interactive_searches_90d == 0` **Y** `is_scheduled == False` **Y**
   `has_alert_action == False` **Y** `used_in_dashboards == False` **Y**
   `parser_confidence` para ese dataset específico es `HIGH` en al menos una
   fuente que lo evaluó (es decir, sabemos con certeza que no aparece, no que
   "no pudimos verlo").

5. **`REVIEW`** — no cumple con certeza ninguna de las anteriores: por ejemplo,
   ingest medio-alto con pocas búsquedas, o cero búsquedas pero con
   `parser_confidence` mixta.

6. **`NORMAL`** — cualquier otro caso (ingest bajo, algo de uso, sin señales de
   alarma ni de alto valor).

## 6. Datasets protegidos por defecto (Tarea 7)

Patrones de `sourcetype`/`index` que **nunca** se auto-clasifican como
`POSSIBLE_WASTE`, incluso si técnicamente cumplieran la regla 4, y que en su
lugar caen directamente en `PROTECTED`:

- Índices/sourcetypes que coincidan (case-insensitive) con:
  `*audit*`, `*compliance*`, `*security*`, `*firewall*`, `*ids*`, `*ips*`,
  `*auth*`, `*forensic*`, `*_audit`, `*siem*`, `*edr*`, `*dlp*`.
- El índice interno `_audit` mismo (si por algún motivo apareciera como
  dataset analizable).
- Cualquier dataset que el usuario liste explícitamente en un archivo
  `protected_overrides.txt` que el CLI acepta con `--protect-file`.

Esta lista es deliberadamente amplia (prefiere falsos negativos de "esto
podría no ser sensible" sobre falsos positivos de "recomendé revisar algo que
era de seguridad"). Es configurable, nunca hardcoded sin posibilidad de
extenderla.

## 7. Texto explicativo obligatorio

Cada `Dataset` clasificado como `POSSIBLE_WASTE` o `REVIEW` debe generar una
frase con esta plantilla exacta (ver `docs/report-design.md`):

```
Este dataset aparece como candidato porque ingiere {ingest_gb_per_day:.1f}
GB/día, no registra consultas interactivas en {lookback_days} días, y no fue
encontrado en alertas, dashboards ni saved searches programadas.
```

Nunca se muestra una categoría sin esta explicación adjunta.

## 8. Cálculo de ahorro potencial (Tarea 9)

```
current_ingest_gb_day = sum(ingest_gb_per_day for todos los datasets)
candidate_gb_day = sum(ingest_gb_per_day for datasets en POSSIBLE_WASTE)
                  + 0.5 * sum(ingest_gb_per_day for datasets en REVIEW)
potential_reduction_pct = candidate_gb_day / current_ingest_gb_day

Si el usuario da --annual-spend X:
    potential_annual_saving = X * potential_reduction_pct

Si el usuario da --cost-per-gb-day Y:
    potential_annual_saving = candidate_gb_day * Y * 365
```

El factor `0.5` para `REVIEW` refleja que son candidatos con más incertidumbre
que `POSSIBLE_WASTE` — se cuentan a mitad de peso para no inflar la cifra de
ahorro. Este factor es una constante nombrada y documentada
(`REVIEW_WEIGHT = 0.5`), fácil de ajustar si la validación con usuarios reales
sugiere otro valor (hipótesis a validar, no un hecho).

**El reporte siempre usa la palabra "Potential saving", nunca "Guaranteed
saving"** (requisito explícito del brief) y siempre incluye la fórmula usada
en la sección "Methodology".
