# PROJECT_STATUS.md

Última actualización: cierre de Fase 2 (validación técnica + MVP funcional)

## Estado actual

**Fase 2 completada.** El MVP técnico está construido, probado y validado
end-to-end contra un escenario sintético que cubre los 10 casos pedidos en
el brief original, más 2 adicionales descubiertos durante la propia
validación. No se ha probado todavía contra un Splunk real ni se ha
publicado nada — eso es Fase 3, y no ha empezado.

## Resumen ejecutivo (para retomar el contexto en una nueva sesión)

Log Spend Auditor es una herramienta de solo lectura, local-first, que analiza un
entorno Splunk y responde: **"¿qué datos estoy pagando por ingerir pero casi nunca
utilizo?"**. Cruza volumen de ingest (`license_usage.log`) con señales de uso real
(búsquedas interactivas en `_audit`, saved searches, alertas, dashboards vía REST
API) para clasificar cada `(index, sourcetype)` en una categoría explicable y
estimar un ahorro potencial en dólares. Nunca borra ni modifica nada en Splunk, y
nunca envía datos del cliente a un servidor externo.

## Tareas completadas

- [x] Estructura base del repositorio.
- [x] `PROJECT_STATUS.md` y `DECISIONS.md` (9 decisiones registradas, D001-D009).
- [x] Investigación de fuentes de datos Splunk (`license_usage.log`, `_audit`,
      `_internal`, REST API `/saved/searches`, `/search/jobs`), con hechos
      verificados vía documentación oficial y Splunk Community — incluyendo el
      hallazgo del *squashing* de host/source en `license_usage.log`, que fue lo
      que motivó usar `(index, sourcetype)` como unidad de análisis (D004).
- [x] `docs/splunk-data-sources.md` — 8 fuentes documentadas con permisos,
      compatibilidad Enterprise/Cloud, riesgos y alternativas.
- [x] `docs/architecture.md` — CLI con **dos modos de collector** (REST API en
      vivo y CSV exportado) sobre un motor de análisis/scoring compartido.
- [x] `docs/scoring.md` — algoritmo de clasificación 100% explicable (sin ML,
      sin "AI score" opaco), actualizado tras el fix de D009.
- [x] `docs/security.md` — modelo de amenazas y principios read-only/local-first.
- [x] `docs/report-design.md` — diseño del informe HTML/Markdown.
- [x] `docs/validation-plan.md` — plan de Quickscan gratuito + umbrales de éxito.
- [x] `docs/product-spec.md` — especificación funcional completa.
- [x] 8 queries SPL documentadas y comentadas en `queries/`.
- [x] Escenario sintético reproducible en `sample-data/case_mixed/` (generado por
      `sample-data/generate_sample_data.py`, semilla fija) cubriendo los 10 casos
      pedidos + 2 adicionales (ver `sample-data/README.md` para el mapeo completo).
- [x] Motor completo en Python (`src/splunk_spend_auditor/`): modelos de dominio,
      collector CSV (probado), collector REST (implementado, sin probar contra un
      Splunk real), parser de SPL, motor de análisis, motor de scoring/clasificación,
      cálculo de ahorro potencial, generador de reportes HTML/Markdown (Jinja2), CLI
      (Typer: `quickscan` y `audit`).
- [x] Suite de **69 tests con pytest**, todos en verde: parser SPL (10 tests),
      reglas de clasificación y protección (20 tests), cálculo de ahorro (6 tests),
      collector CSV / manejo de archivos faltantes (4 tests), generación de reportes
      free vs. pro (5 tests), y un **test de integración end-to-end** que valida las
      12 clasificaciones esperadas del escenario sintético completo de una sola vez.
- [x] `audit` y `quickscan` ejecutados de punta a punta contra
      `sample-data/case_mixed/`: generan `report.html` y `report.md` coherentes,
      con HTML balanceado (tags verificados) y sin glitches de formato.
- [x] README.md del repositorio.

## Bugs reales encontrados y corregidos durante la validación

Vale la pena dejarlos explícitos porque cambian el comportamiento respecto a
la especificación original de `docs/scoring.md`:

1. **Parser de listas OR con campo repetido.** `(index=a OR index=b)` (el
   estilo que la mayoría de la gente escribe en SPL) se parseaba mal y
   generaba un `DatasetKey` espurio con `index='index'`. Corregido; cubierto
   por `tests/test_spl_parser.py::test_grouped_or_list_style_b_repeated_field_keyword`.
2. **La regla de `UNKNOWN` estaba atada al dataset, no al entorno (D009).**
   La primera implementación clasificaba `UNKNOWN` cualquier dataset sin
   evidencia HIGH propia — que es exactamente el perfil del caso más
   importante que el producto existe para encontrar (un dataset caro que
   nadie busca nunca). Corregido para que `UNKNOWN` dependa del
   `partial_or_unknown_ratio` del **entorno completo**, no del dataset
   individual — que es lo que `docs/scoring.md` sección 3 ya especificaba
   desde el principio; el código no coincidía con su propia documentación.
   Ver `DECISIONS.md` D009 para el detalle completo, incluyendo la
   limitación conocida y aceptada que esto deja (Caso 9 del escenario
   sintético termina en `REVIEW`, no en `UNKNOWN`, y por qué eso es correcto).
3. Colisión de nombres en los datos sintéticos: el dataset del Caso 1
   (mucho volumen + mucho uso) se llamaba originalmente `firewall:pan_traffic`,
   que matcheaba el patrón protegido por defecto `*firewall*` y salía
   `PROTECTED` en vez de `HIGH_VALUE`. Renombrado a `cdn:edge_access`.

## Riesgo principal

El parsing de SPL para determinar qué `(index, sourcetype)` toca una búsqueda
es inherentemente incompleto (macros anidadas, `eventtypes`, subsearches,
`tstats` sobre data models, lookups). Mitigado por diseño: nada que no se
resuelva con alta confianza se clasifica como `POSSIBLE_WASTE`, y la
protección contra ambientes con mala cobertura de parsing es ahora correcta a
nivel de entorno (ver bug #2 arriba). El riesgo residual documentado y
aceptado es que un dataset individual detrás de una macro no resuelta, en un
entorno por lo demás bien cubierto, no queda protegido automáticamente — se
resuelve con el mecanismo manual de `protected_overrides.txt`.

## Hipótesis todavía sin validar

1. Que un Splunk admin real esté dispuesto a pagar $149-$299 por el reporte
   completo sin haber hablado con nadie del equipo (hipótesis de negocio, no
   técnica — se valida en Fase 3 con el Quickscan público).
2. Que el volumen de "squashing" de `license_usage.log` (ver
   `docs/splunk-data-sources.md`) no invalide el desglose por host/source en
   entornos reales grandes — en la Fase 2 solo se validó con datos sintéticos.
3. Que el modo REST API en vivo funcione sin fricción en un Splunk Cloud real
   con roles restringidos — no se ha probado contra una instancia real
   todavía (se necesita acceso, ver "Próximos pasos").

## Próximos pasos (Fase 3 — no iniciada)

1. Conseguir acceso a una instancia Splunk real (Splunk Free/Developer instance
   local, o instancia de prueba) para validar el collector REST contra datos
   reales, no solo CSV sintético. **Requiere decisión/acceso del usuario.**
2. Publicar el Quickscan gratuito según `docs/validation-plan.md`.
3. Preparar el repositorio para GitHub (público, con licencia, sin credenciales
   ni datos de ejemplo sensibles — los `sample-data/case_mixed/*.csv` actuales
   son 100% sintéticos y no tienen ningún problema para publicarse tal cual).
4. Medir señales de interés (estrellas, descargas, preventas) antes de construir
   el motor completo de reportes Pro.

## Decisiones pendientes que requieren al usuario

- Nombre final del producto (ver `docs/product-spec.md`, sección "Naming" —
  quedó pendiente de investigación de trademark).
- Precio final de lanzamiento del Quickscan/reporte Pro (hay un rango propuesto
  en `docs/product-spec.md`, pero el precio final es una decisión de negocio).
- Si se usará una cuenta de Splunk real del propio Alvaro para las pruebas de
  Fase 3, o una instancia de desarrollo separada.

## Recomendación de cierre de Fase 2

**GO.** No hay nada en el diseño ni en la validación técnica que bloquee
avanzar a Fase 3. El siguiente paso natural es la decisión pendiente #3 de
arriba (acceso a un Splunk real) para poder ejercitar el collector REST, y en
paralelo, publicar el Quickscan gratuito para empezar a medir interés real.
