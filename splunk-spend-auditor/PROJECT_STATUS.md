# PROJECT_STATUS.md

Última actualización: cierre de Fase 3B (MVP reliability & graceful degradation)

## Estado actual

**Fase 2 completada. Fase 3A completada. Fase 3B completada — GO condicional
(ver "Pendientes" abajo).** El MVP técnico (Fase 2) está construido, probado
y validado end-to-end contra un escenario sintético. Fase 3A validó ese mismo
diseño contra una instancia Splunk Enterprise real y encontró y corrigió 3
bugs reales (D010/D011/D012). Fase 3B endureció el pipeline completo contra
pérdida de señales, errores REST reales, y encontró y corrigió un bug de
seguridad crítico (D014) más una limitación real no resuelta (D015) -- ver
sección "Fase 3B" abajo. Fase 3C (reporte con datos reales) es el próximo
paso y todavía no empezó.

## Fase 3B — MVP Reliability & Graceful Degradation (COMPLETADA)

**Objetivo:** convertir el MVP validado en Fase 3A en un sistema robusto
ante permisos parciales, señales no disponibles, errores REST y timeouts --
sin agregar funcionalidad comercial nueva. Principio rector: la pérdida de
visibilidad nunca puede aumentar artificialmente una clasificación de
desperdicio ni el ahorro potencial estimado.

**Baseline confirmado antes de modificar nada:** 72 tests passing (exacto,
como se esperaba desde el cierre de Fase 3A).

**Cambios de arquitectura:**
- `models.SignalAvailability` (D013): reemplaza `dict[str, bool]` por un
  enum de 5 estados (`AVAILABLE`/`UNAVAILABLE`/`PARTIAL`/`ERROR`/
  `NOT_APPLICABLE`) para poder distinguir "consultado, resultado 0" de "no
  se pudo consultar" en cada fuente (ingest, audit_searches, saved_searches,
  dashboards_used, last_seen, protected_overrides).
- `scoring/rules.py::classify()` y `scoring/classify_all.py` (D014): la
  regla `POSSIBLE_WASTE` ahora exige que `audit_searches` y `saved_searches`
  estén `AVAILABLE` -- si no, degrada a `REVIEW` con una explicación
  explícita nombrando la fuente faltante. `dashboards_used` deliberadamente
  NO bloquea (limitación ya aceptada desde Fase 2).
- `collector/rest_collector.py`: reescrito con manejo de errores explícito
  (`httpx.HTTPStatusError`/`httpx.RequestError` distinguidos, mensajes
  legibles por código HTTP), una fuente obligatoria (`ingest`, igual que el
  modo CSV) que levanta `RestCollectionError` en vez de dejar escapar la
  excepción cruda de httpx, y wiring end-to-end de `metadata_last_seen.spl`
  (corregida en Fase 3A/D011, NO reescrita en Fase 3B) con detección de
  cobertura parcial y filtrado de índices por defecto de Splunk (`main`,
  `history`, `summary`) que `eventcount index=*` sí recorre.
- `cli.py`: ahora expone el modo REST (`--host`/`--port`/`--no-verify-ssl`,
  token leído de `SPLUNK_TOKEN` o `getpass`, nunca como argumento de línea
  de comandos -- ver docs/security.md) además del modo `--from-csv` ya
  existente. Errores operacionales muestran un mensaje breve y accionable
  por defecto; `--verbose` habilita logging técnico completo (`logging`
  estándar, sin framework nuevo).
- `templates/report.*.j2` + `reports/render.py`: la sección Methodology
  muestra un aviso "Analysis completed with reduced confidence" con las
  fuentes degradadas nombradas, y el estado de cada fuente en lenguaje claro
  en vez de solo "available"/"NOT available".

**Bugs reales encontrados y corregidos:**
1. **(D014, el más importante de esta fase)** Un dataset con evidencia de
   uso perdida por completo por un fallo de fuente (403/timeout en
   `audit_searches`/`saved_searches`) llegaba a `POSSIBLE_WASTE` exactamente
   igual que uno con evidencia confirmada de cero uso -- el código nunca
   consultaba `sources_available` al clasificar, a pesar de que
   `docs/architecture.md` documentaba lo contrario desde Fase 2. Reproducido
   antes del fix, corregido, validado con tests unitarios Y contra
   `sample-data/case_mixed` real (ver D014) Y contra el laboratorio Splunk
   real de Fase 3A.
2. El collector REST nunca ejecutaba `metadata_last_seen.spl` --
   `sources_available["last_seen"]` estaba hardcodeado en `False`/
   `UNAVAILABLE` sin intentarlo. Ahora se ejecuta, con detección de
   cobertura parcial y filtrado de ruido (índices por defecto de Splunk).
3. Cualquier fallo de red (`httpx.RequestError`: connection refused,
   timeout, TLS) en la fuente obligatoria (`ingest`) dejaba escapar la
   excepción cruda de httpx hasta el CLI -- ningún manejo, stack trace
   completo mostrado al usuario por defecto. Ahora se envuelve en
   `RestCollectionError` con mensaje accionable.

**Limitación real encontrada, NO resuelta (D015):** un token con
`srchIndexesAllowed` restringido (sin `_audit`) recibe `HTTP 200` con
`results: []` al consultar `_audit` -- indistinguible de "cero búsquedas
reales" a nivel de API. Confirmado contra el laboratorio real: con un token
así, un dataset `HIGH_VALUE` confirmado (12 búsquedas reales con el token
admin) se reclasificó como `POSSIBLE_WASTE`. El mecanismo de D014 no cubre
este caso porque no hay ningún error que capturar. Ver D015 para el análisis
completo y por qué no se implementó una corrección automática esta fase.

**Tests:** 95 passing (72 baseline + 23 nuevos: 6 de
`TestSignalAvailabilityGating`, 1 de `test_losing_visibility_never_increases_potential_savings`,
2 de `test_protected_overrides_availability...`, 14 de hardening del
collector REST en `tests/test_rest_collector.py`, 2 de
`tests/test_architecture_boundaries.py`). Todos con `httpx.MockTransport` --
ninguno depende de red/Docker/Splunk real. Cero regresiones sobre el
baseline de 72.

**Validado contra Splunk real (laboratorio de Fase 3A, sigue vivo):**
- `audit --host localhost --port 8089` end-to-end contra el laboratorio: las
  7 clasificaciones coinciden con lo esperado, incluyendo `last_seen` ahora
  disponible (antes nunca se intentaba).
- Token inválido (401) real contra el laboratorio -> mensaje limpio, exit
  code 1, sin stack trace (con `--verbose` sí se ve el detalle técnico).
- Host inaccesible / connection refused (real, no mockeado) -> mismo
  comportamiento.
- Rol Splunk real con `srchIndexesAllowed` restringido (sin `_audit`) creado
  específicamente para esta validación -> encontró D015 (arriba).
- Todo lo demás (401/403/404/429/5xx, timeouts de red, JSON malformado,
  query con mensaje FATAL) está cubierto por `httpx.MockTransport`, no
  reproducido contra el laboratorio real (no todos esos escenarios son
  seguros/prácticos de forzar contra una instancia real compartida).

## Pendientes de Fase 3B (reales, no triviales)

1. **D015** -- permisos de índice restringidos que devuelven `200`/`[]` en
   vez de un error no se detectan. Recomendación concreta para cuando se
   aborde: sondear `current-context.roles` +
   `authorization/roles/<rol>.srchIndexesAllowed` con `fnmatch`, limitado a
   roles directos (sin resolver `imported_roles` recursivamente), como
   heurístico best-effort explícitamente etiquetado como tal.
2. `protected_overrides` no tiene forma de proveerse en modo REST (solo
   existe como archivo dentro del directorio `--from-csv`). Gap menor, no
   bloqueante.
3. El residual conocido desde D010 (2 saved searches de sistema de la app
   `audit_trail` con `owner=admin` que sobreviven el filtro) sigue
   presente -- en la validación de Fase 3B contra el laboratorio aparece
   como `_audit:audittrail`, correctamente clasificado `PROTECTED` por el
   patrón de nombre, impacto nulo confirmado.
4. No se validó el modo REST contra Splunk Cloud (solo Enterprise vía
   Docker) ni a escala de producción -- mismo alcance que Fase 3A.

## Fase 3A — Validación contra Splunk real de laboratorio (COMPLETADA)

**Entorno usado:** Splunk Enterprise 10.4.3, imagen Docker oficial
(`splunk/splunk:latest`, `docker.io`), corriendo bajo **Trial license** de
60 días (no Free — Free deshabilita alerting y autenticación por completo,
lo cual habría impedido probar exactamente lo que había que probar). Es un
laboratorio efímero dentro de este entorno de desarrollo, no una instancia
persistente ni de producción.

**Escenario de laboratorio:** 7 índices (`lsa_high_value`, `lsa_waste`,
`lsa_protected`, `lsa_normal`, `lsa_review`, `lsa_scheduled_only`,
`lsa_alert_only`) con volumen de ingest distinto por índice (vía
`splunk add oneshot`), 15 búsquedas interactivas reales (12 sobre
`lsa_high_value`, 3 sobre `lsa_normal`) para poblar `_audit`, una saved
search programada real (`lsa-scheduled-billing-report`) y una alerta real
con acción de email (`lsa-alert-heartbeat-missing`) creadas vía REST API con
un token Bearer generado en la propia instancia.

**Resultado de las 8 queries `.spl`:** 8/8 ejecutan sin error contra Splunk
real; 7/8 se comportan exactamente como se documentó en Fase 2;
`metadata_last_seen.spl` tenía un bug de diseño (ver D011) y se corrigió.

**Resultado del collector REST (`rest_collector.py`):** se ejecutó
`collect()` end-to-end (no simulado) contra la instancia real, seguido del
pipeline completo (`build_datasets` → `classify_all`). Encontró 2 bugs reales
adicionales (D010, D012), ambos corregidos con tests de regresión. Tras las
3 correcciones, las 7 clasificaciones del escenario de laboratorio
coincidieron exactamente con lo esperado: `lsa_high_value`→`HIGH_VALUE`
(interactivo), `lsa_scheduled_only`→`HIGH_VALUE` (programada),
`lsa_alert_only`→`HIGH_VALUE` (alerta), `lsa_normal`→`NORMAL`,
`lsa_protected`→`PROTECTED` (patrón), `lsa_review`→`REVIEW`,
`lsa_waste`→`POSSIBLE_WASTE` — el caso central que el producto existe para
encontrar, funcionando de punta a punta con datos 100% reales de Splunk.

**Bugs reales encontrados y corregidos (ninguno detectable solo con CSVs
sintéticos):**
1. **D012** — la REST API de Splunk serializa todos los resultados como
   string; `build_datasets` fallaba con `TypeError` al esperar `gb` numérico.
2. **D010** — `/servicesNS/-/-/saved/searches` devuelve también ~170 saved
   searches instaladas por Splunk mismo, que sin filtrar contaminan el
   listado de datasets y disparan incorrectamente la regla `UNKNOWN` de
   entorno de D009 (el ratio de partial/unknown subió de ~46% a ~71% solo
   por ruido de sistema). Corregido filtrando `owner == "nobody"`.
3. **D011** — `metadata type=sourcetypes` no tiene dimensión `index`; la
   query de Fase 2 asumía que sí y producía una columna vacía en silencio.
   Corregido con `| map` (una ejecución por índice).

**Hipótesis de Fase 2 confirmadas (no invalidadas):**
- `license_usage.log` desglosado por `(index, sourcetype)` es preciso y
  aparece disponible en minutos, no horas — confirmado con bytes reales.
- El wildcard `servicesNS/-/-/saved/searches` es necesario y funciona (D002,
  fuente 3 de `splunk-data-sources.md`).
- La autenticación Bearer token funciona exactamente como documentado (tras
  habilitar token auth, que está deshabilitado por defecto — no es un
  problema del producto, es un paso de setup del admin de Splunk, ya
  documentado implícitamente en D002).
- El principio D009 (UNKNOWN a nivel de entorno) funciona correctamente una
  vez quitado el ruido de D010 — de hecho la validación demostró
  exactamente el escenario que D009 fue diseñado para prevenir, y cómo
  falla si no se filtra el ruido de contenido de sistema.

**No probado en Fase 3A (fuera de alcance, requiere producción o Splunk
Cloud):** squashing de host/source con alta cardinalidad real (el
laboratorio es un solo container/host), diferencias específicas de permisos
de Splunk Cloud, volumen a escala de producción (GB/TB reales).

**Tests:** 72 passing (69 de Fase 2 + 3 nuevos de regresión en
`tests/test_rest_collector.py`, con `httpx.MockTransport`, sin dependencia
de Docker/red para correr en CI).

**Recomendación de cierre de Fase 3A: GO.** El diseño central del producto
(unidad `(index, sourcetype)`, D002 dos collectors, D009 UNKNOWN a nivel de
entorno) sobrevivió la validación contra Splunk real sin cambios de fondo.
Los 3 bugs encontrados eran de implementación, no de diseño, y ya están
corregidos con tests. Fase 3B (hardening: timeouts, manejo de errores,
permisos insuficientes, mensajes CLI) y Fase 3C (reporte real desde estos
datos de laboratorio) son los próximos pasos naturales.

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

## Próximos pasos

**Fase 3C (reporte real) — no iniciada:**
1. Generar quickscan + audit completo (HTML/Markdown) usando datos del
   laboratorio de Fase 3A/3B.
2. Revisión manual del HTML para un Splunk Admin/Platform Engineer/manager/FinOps.

**Fase 3B, pendiente real no bloqueante (ver D015 y "Pendientes de Fase
3B" arriba):**
- Heurístico best-effort para detectar permisos de índice restringidos que
  devuelven `200`/`[]` en vez de un error explícito.

**Más adelante:**
- Publicar el Quickscan gratuito según `docs/validation-plan.md`.
- Preparar el repositorio para GitHub público (licencia, sin credenciales).
- Medir señales de interés antes de construir el motor completo Pro.
- Validar contra Splunk Cloud real y a escala de producción (fuera de
  alcance del laboratorio Docker de Fase 3A/3B — ver esas secciones arriba).

## Decisiones pendientes que requieren al usuario

- Nombre final del producto (ver `docs/product-spec.md`, sección "Naming" —
  quedó pendiente de investigación de trademark).
- Precio final de lanzamiento del Quickscan/reporte Pro (hay un rango propuesto
  en `docs/product-spec.md`, pero el precio final es una decisión de negocio).
- Si se usará una cuenta de Splunk real de producción para pruebas futuras, o
  se sigue trabajando contra laboratorios efímeros como el de Fase 3A/3B.
- Si D015 (permisos restringidos que simulan "cero" sin error) se aborda con
  el heurístico best-effort propuesto, o se documenta solo como
  recomendación operativa (token con acceso amplio) indefinidamente.

## Recomendación de cierre de Fase 3B

Ver el informe estructurado entregado al usuario al cierre de esta fase
(sección L, "Recomendación") para el detalle completo. Resumen: el diseño
central (D002, D004, D009) sigue sin necesitar cambios de fondo; Fase 3B
corrigió un bug de seguridad real (D014) y encontró una limitación real no
resuelta (D015) que no bloquea avanzar pero debe quedar visible antes de
Fase 3C.
