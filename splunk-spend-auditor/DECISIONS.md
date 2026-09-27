# DECISIONS.md

Registro de decisiones de arquitectura y producto, con la razón detrás de cada
una, para no volver a discutirlas desde cero en sesiones futuras.

---

## D020 — Idioma de mensajes operacionales de la CLI: inglés, consistente con el resto del producto; precisión de "read-only" en docs/security.md

**Contexto:** Fase 4A (evaluación de solo lectura de onboarding para
testers externos) encontró, ejecutando los comandos reales, que los
mensajes de error operacionales de la CLI (`_collect_from_source`,
`_resolve_token`, y cada rama de `_describe_rest_error` en
`rest_collector.py` -- connection refused, timeouts, 401/403/404/429/5xx,
JSON malformado) estaban en español, mientras `--help`, el contenido de
los reportes y los mensajes de éxito ya estaban en inglés. Para un tester
externo angloparlante (el público objetivo, ver `docs/product-spec.md`),
esto es fricción justo en el punto donde más necesita claridad: el primer
intento fallido de conexión REST.

**Decisión:** todos los mensajes que la CLI muestra por defecto (sin
`--verbose`) -- validación de argumentos, errores de lectura de CSV, y las
12 ramas de `_describe_rest_error` -- están ahora en inglés. **No** se
tradujeron los `logger.debug()` internos (solo visibles con `--verbose`)
ni los comentarios/docstrings del código: ambos son consistentes con el
resto del código base (en español) y no son parte de la experiencia por
defecto de un tester -- traducirlos habría sido alcance innecesario para
una "iteración corta y dirigida".

**Precisión adicional en `docs/security.md`:** el texto original decía que
el modo REST "solo ejecuta GET/búsquedas de lectura", lo cual es
técnicamente impreciso -- también usa `POST /services/search/jobs` en modo
`oneshot` (así funciona la API de búsqueda de Splunk incluso para queries
de solo lectura; `oneshot` ni siquiera deja un job persistente). Se
corrigió a "operacionalmente read-only": ningún endpoint de
escritura/borrado de configuración o datos se llama nunca (verificado por
inspección directa de todos los métodos HTTP usados en
`rest_collector.py` -- solo `GET` y ese único `POST` de búsqueda), pero
"read-only" no es sinónimo de "solo HTTP GET".

**Sin cambio de semántica de error handling:** mismas ramas de excepción,
mismos códigos de salida, mismo comportamiento de `--verbose` -- solo
cambió el texto mostrado.

**Tests:** `tests/test_cli.py::TestCLIOperationalMessagesAreEnglish` (3,
nuevo), `tests/test_rest_collector.py::TestDescribeRestErrorIsAlwaysEnglish`
(12, nuevo, parametrizado sobre las 12 ramas de `_describe_rest_error`,
verifica ausencia de caracteres acentuados/eñe como guarda de regresión
simple y robusta sin mantener una lista de palabras en español). 4 tests
existentes de `TestMandatoryIngestFailureBecomesRestCollectionError`
actualizados de aserciones en español a inglés (mismo comportamiento
verificado, distinto idioma esperado).

**Validación contra el laboratorio real:** connection refused (puerto
incorrecto) y 401 (token inválido) contra `splunk-lab` real -- ambos
mensajes en inglés, claros, sin stack trace por defecto.

---

## D019 — Consistencia final de outputs: contador de señales, etiqueta de confianza, quickscan y tier

**Contexto:** Fase 3C.2, revisión dirigida sobre los artefactos finales de
Fase 3C.1. Cinco inconsistencias detectadas al inspeccionar el reporte y
el quickscan como producto (no como código), todas corregidas sin tocar
`scoring/rules.py` -- se verificó explícitamente que ninguna era un bug de
clasificación antes de tocar nada.

**1. "Signals available: 6 of 6" contradecía a Methodology.** El
denominador de `sources_available_display | rejectattr("degraded")`
contaba `NOT_APPLICABLE` como "no degradado" y por lo tanto como
"disponible" -- mientras la sección Methodology, en el mismo reporte,
listaba `dashboards_used`/`protected_overrides` como "not applicable for
this run". Dos secciones del mismo documento afirmando cosas distintas
sobre la misma señal. Corregido: `reports/render.py` ahora calcula
`available_signal_count`/`applicable_signal_count` excluyendo
`NOT_APPLICABLE` del denominador (`4 of 4 applicable to this run` en vez
de `6 of 6`), y agrega una fila "Signals not applicable" explícita en
Current Environment, consistente con Methodology.

**2. Columna "Confidence" ambigua junto a POSSIBLE_WASTE.**
`lsa_waste:app:verbose_debug` mostraba `Confidence: UNKNOWN` en la misma
fila que se clasifica `POSSIBLE_WASTE`, leíble como si el motor no
estuviera seguro de la clasificación. Verificado por inspección directa
de `scoring/rules.py` (ya hecho una vez en D018 para `last_seen`, repetido
aquí para `parser_confidence`): **ningún** uso de `parser_confidence`
existe en `classify()` ni en `data_value_score()` -- la columna es
puramente confianza de evidencia de búsqueda/parsing SPL (docs/scoring.md
sección 3), un concepto completamente distinto de la clasificación final.
No había bug de lógica que corregir -- solo se renombró el encabezado a
"Search evidence confidence" en ambos templates.

**3. quickscan mezclaba POSSIBLE_WASTE y REVIEW sin peso.** `quickscan`
sumaba ambas categorías en una sola cifra ("Review candidates (possible
waste): 2 datasets, 879 KB/day, 64.7%"), mientras el full audit
(`compute_savings()`) pesa REVIEW a `REVIEW_WEIGHT=0.5` y nunca los trata
como equivalentes -- los dos comandos daban números distintos (879 KB/64.7%
vs. 877 KB/64.6%) para "lo mismo". Corregido: `quickscan` ahora lista
POSSIBLE_WASTE y REVIEW como bloques separados (con su volumen real, sin
peso, para cada uno) y reutiliza literalmente `savings.candidate_gb_day` /
`savings.potential_reduction_pct` -- el mismo objeto `SavingsEstimate` que
`_run_pipeline()` ya calculaba -- para la única cifra "comparable a full
audit", en vez de una suma paralela hecha a mano en `cli.py`. Por
construcción, ambos comandos no pueden volver a divergir en ese número.

**4. quickscan en modo REST sugería `audit --from-csv ...`.** El CTA final
de `quickscan` estaba hardcodeado a `--from-csv`, incluso corriendo contra
Splunk real vía REST. Corregido: el CTA ahora usa `--host`/`--port` cuando
la corrida fue REST, `--from-csv <dir>` cuando fue CSV -- refleja el
origen real de esta ejecución (`cli.py` ya tenía `host`/`from_csv`
disponibles en el mismo scope, no se agregó estado nuevo).

**5. "(PRO)" en el reporte.** Free/Pro es una hipótesis de producto sin
validar (ver `docs/product-spec.md`, pendiente de Fase 3C.1/PROJECT_STATUS.md
"Pendientes reales"). Mostrar "(PRO)" en el subtítulo del reporte lo
presentaba como un hecho de producto ya decidido. Se eliminó el label de
ambos templates -- el sistema de tiers en sí (qué contenido trunca `tier`)
no cambió, solo se dejó de nombrarlo en el reporte visible.

**Alcance deliberadamente NO tocado:** `scoring/rules.py` (confirmado sin
bug en ninguno de los 5 puntos); la lógica de truncamiento free/pro;
cualquier decisión de clasificación de fases anteriores.

**Tests:** `tests/test_cli.py` (nuevo, 4 tests: separación
POSSIBLE_WASTE/REVIEW, cifra comparable idéntica a `compute_savings()`,
CTA por modo CSV/REST), `tests/test_report_render.py::TestSignalAvailableCounterExcludesNotApplicable`
(2), `TestConfidenceColumnLabelIsUnambiguous` (2),
`TestNoProductTierLabelInReport` (2).

**Validación:** regenerado quickscan + audit reales contra `splunk-lab`
(mismos 7 datasets, modo REST, token admin) -- confirmado en
`/tmp/fase3c2_outputs/`: `Signals available: 4 of 4 applicable to this
run` + `Signals not applicable: dashboards_used, protected_overrides`;
"Search evidence confidence" como encabezado; quickscan separa "Possible
waste: 1 dataset, 876 KB/day" de "Review (...): 1 dataset, 3 KB/day" y
reporta "877 KB/day (64.6%)" -- idéntico al full audit; CTA
`audit --host localhost --port 8089`; sin "(PRO)" en ningún archivo.

---

## D018 — Honestidad de lenguaje para `dashboards_used`; `last_seen` renombrado; procedencia del annual spend explícita

**Contexto:** Fase 3C.1, revisión dirigida sobre el reporte de Fase 3C
(veredicto MODIFY). Se pidió investigar tres "inconsistencias semánticas"
concretas antes de cualquier validación externa.

**1. `dashboards_used` se presentaba como certeza que no existía.**
`Dataset.used_in_dashboards` es un `bool` que por diseño defaultea a
`False` cuando la fuente nunca se evaluó (modo REST: siempre
`NOT_APPLICABLE`, ver `collector/rest_collector.py` -- "fuente manual por
diseño en AMBOS collectors", D002; modo CSV: `UNAVAILABLE` si no se exportó
`dashboards_used.csv`). El reporte mostraba `Dashboards: No` y la
explicación de `POSSIBLE_WASTE` afirmaba *"was not found in alerts,
dashboards, or scheduled saved searches"* incluso cuando esa señal nunca
se consultó -- una violación del principio "missing visibility != zero
usage" en el TEXTO del reporte, no solo en la clasificación.

Investigado el flujo completo (`models`, `scoring/rules.py`,
`scoring/classify_all.py`, `reports/render.py`): el valor SÍ participa en
clasificación (Regla 3 HIGH_VALUE, componente `has_zero_usage` de Regla 4
POSSIBLE_WASTE) y en `data_value_score()` (bonus aditivo de +15 si es
`True`). Como es **puramente aditivo** (nunca resta, nunca convierte un
"no se sabe" en evidencia negativa) y como excluir `dashboards_used` de
`SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE` (D013) fue una decisión
deliberada y ya documentada en Fase 3B (agregarlo ahí bloquearía
`POSSIBLE_WASTE` en casi todos los entornos reales, dado que la fuente es
manual/opcional para prácticamente todos los usuarios) **no se revirtió esa
decisión de clasificación**. Lo que sí era un bug real -- y se corrigió --
es el LENGUAJE: `classify()` ahora recibe `dashboards_signal_available:
bool` (calculado en `classify_all()` a partir de
`sources_available["dashboards_used"] == SignalAvailability.AVAILABLE`,
mismo criterio que D013/D014 para las demás fuentes) y solo afirma "no
encontrado en dashboards" cuando la señal realmente se evaluó. El reporte
(`reports/render.py` + templates) ahora muestra `Dashboards: Not evaluated`
en vez de `No` cuando la fuente no está `AVAILABLE`, en lugar de inferir un
"No" que nunca se confirmó.

**2. `last_seen` estaba correctamente implementado, mal etiquetado.**
Se verificó `queries/metadata_last_seen.spl` (usa `recentTime` de
`metadata type=sourcetypes` -- tiempo de indexación del evento más
reciente, actividad de DATOS, no de búsqueda), el modelo (`Dataset.
last_seen_days_ago`, ya comentado como "Actividad de ingest") y el scoring
(`scoring/rules.py`: **no lo usa en absoluto**, ni en `classify()` ni en
`data_value_score()` -- confirmado por grep, es un campo puramente
informativo). La semántica siempre fue correcta de punta a punta; el único
bug real era la ETIQUETA visible: "Last observed: N days ago" en la misma
línea que "Searches 90d: 0" se leía como si "observed" significara
"buscado/consultado por un humano". Renombrado a "Last data observed" en
ambos templates (HTML y Markdown) y en `docs/report-design.md`. No hay
regresión de scoring que corregir porque nunca existió.

**3. Procedencia del `annual_spend` no era lo bastante explícita.**
Investigado: `$94,200` no es un default ni un valor hardcoded del
producto (`cli.py`: `annual_spend: Optional[float] = typer.Option(None,
...)` -- default `None`, `compute_savings(annual_spend=None)` ya deja
`potential_annual_saving=None` de forma segura). El monto provino
exclusivamente de pasar `--annual-spend 94200` al correr el audit real
contra el laboratorio (siguiendo el ejemplo del propio README, que a su
vez cita `docs/product-spec.md` como fuente de investigación de mercado,
nunca un precio inferido). El cálculo (`annual_spend *
potential_reduction_pct`) es puramente proporcional al % de volumen
optimizable -- no asume ningún $/GB, por lo que es matemáticamente
correcto sin importar cuán pequeño sea el volumen real medido (1.3 MB/día
en el laboratorio vs. $94,200/año es una combinación válida, no un bug).
El problema era de CLARIDAD: nada dejaba inequívoco, en el texto que ve el
usuario, que ese monto es un input que la persona proporcionó, no algo que
la herramienta "sabe" o midió. Ambos templates ahora dicen explícitamente
*"(as provided for this audit, not measured or inferred by this tool)"* en
el Executive Summary y *"(user-provided input, not measured by this
tool)"* en la tabla "Current Spend".

**Alcance deliberadamente NO tocado:** `SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE`
sigue sin incluir `dashboards_used` (ver razón arriba); el bonus de
`data_value_score()` para dashboards sigue siendo aditivo sin gating por
disponibilidad (seguro por ser solo positivo); la fórmula de
`compute_savings()` no cambió.

**Tests:** `tests/test_rules.py::TestDashboardsSignalHonesty` (3),
`tests/test_report_render.py::TestDashboardsSignalPresentation` (3),
`tests/test_report_render.py::TestAnnualSpendProvenance` (2),
`tests/test_report_render.py::TestLastSeenLabelDoesNotImplySearchActivity` (1).

**Validación:** regenerado el audit real contra el laboratorio Splunk
(mismos 7 datasets, token admin) -- confirmado en `/tmp/fase3c1_outputs/
report.md`: `Dashboards: Not evaluated` en las 7 filas, explicación de
`lsa_waste` sin afirmar "not found in ... dashboards", "Last data
observed: 0.8 days ago", y ambas menciones de `$94,200` con su procedencia
explícita.

---

## D016 — Precisión de volumen (GB/día) elevada a 8 decimales; formateo auto-escalado

**Contexto:** Fase 3C ("Verificar los números"). Al correr el audit real
contra el laboratorio Splunk, varios datasets de bajo volumen real
(p.ej. `lsa_alert_only`, 920 bytes/día) se mostraban como `0.0 GB/day` en
el CLI, el reporte y el propio texto de explicación de cada candidato --
indistinguible de "no ingiere nada". Investigado y encontrado en **tres
puntos distintos** de la cadena, cada uno redondeando independientemente:
1. `queries/ingest_by_index_sourcetype.spl` (y las 3 queries de ingest
   informativas): `round(bytes/1024/1024/1024, 4)` -- 4 decimales de GB
   (~100 KB de resolución) truncaba a 0 cualquier dataset por debajo de
   ese umbral.
2. `analysis/build_datasets.py`: `round(float(row["mean"]), 4)` -- mismo
   problema, en Python, incluso después de corregir la query.
3. `scoring/savings.py`: los 4 campos de volumen de `SavingsEstimate`
   también se redondeaban a 2 decimales de GB (~5 MB de resolución) --
   afectaba especialmente entornos pequeños completos, no solo un dataset
   individual (`current_ingest_gb_day` de un laboratorio de prueba
   mostraba "0 GB/day" con datos reales presentes).

**Decisión:** los tres puntos ahora usan 8 decimales de GB (~10 bytes de
resolución) en vez de 2-4. Además, se agregó `formatting.format_gb_per_day()`
(módulo nuevo, fuera de `reports/` para que `scoring/rules.py` -- los
textos de explicación de cada candidato -- pueda usarlo sin que `scoring`
dependa de `reports`) que auto-escala el valor a KB/MB/GB según
corresponda, en vez de mostrar siempre "X.X GB/day" con un número que
puede leer como cero. Se usa en el CLI, el reporte (HTML/MD) y los textos
de explicación de `scoring/rules.py` -- un solo punto de formateo,
consistente en toda la herramienta.

**Razón:** este no es un problema exclusivo del laboratorio de prueba --
cualquier dataset real de bajo volumen (p.ej. un heartbeat/healthcheck
poco frecuente, exactamente el tipo de dataset de bajo volumen que este
producto también audita, ver docs/scoring.md) puede caer en el mismo
rango. Mostrar "0.0 GB/day" para un dataset con volumen real y corriente
(y potencialmente un candidato a revisión real) es engañoso y socava la
credibilidad del reporte frente a un Splunk Admin/FinOps que sepa leer
`license_usage.log` directamente.

**Validación:** confirmado contra el laboratorio real -- antes del fix,
`lsa_alert_only`/`lsa_protected`/`lsa_review` mostraban "0 GB/day" pese a
tener bytes reales confirmados vía `license_usage.log`; después, muestran
"1 KB/day"/"4 KB/day"/"3 KB/day" respectivamente. Tests de regresión:
`tests/test_build_datasets.py`, `tests/test_savings.py::test_low_volume_datasets_are_not_rounded_away_to_zero`,
`tests/test_report_render.py::TestFormatGbPerDay`.

---

## D017 — El reporte excluye índices internos de Splunk (`_`-prefijo) de las tablas de datos

**Contexto:** Fase 3C ("HTML quality review"). Contra el laboratorio real
(con ruido residual de D010 y de las propias búsquedas de validación de
sesiones anteriores), el reporte mostraba filas como `_internal:splunkd` y
`_audit:audittrail` en "Ingestion Breakdown", "Usage Analysis" y el
detalle completo -- con `0 GB/día` garantizado (esos índices nunca
aparecen en `license_usage.log`, no están sujetos a licencia) y nombres
que un Splunk Admin reconocería como "no es mi dato de negocio", pero que
un manager/FinOps leyendo el mismo reporte no sabría interpretar.

**Decisión:** `reports/render.py::build_report_context()` filtra cualquier
`Dataset` cuyo `key.index` empiece con `_` antes de construir cualquier
tabla, conteo o cifra del reporte (incluyendo `total_datasets`, que ahora
se calcula como `len(datasets)` post-filtro en vez de
`summary.total_datasets`, que se computó antes del filtro). El filtro es
puramente de presentación: vive en la capa de reporte, no en
`build_datasets`/`classify_all`/`compute_savings` -- esos módulos siguen
viendo (y pueden seguir clasificando/auditando internamente) estos
datasets si en algún momento hiciera falta, solo no se los muestra al
lector final del reporte. No cambia ningún número de ahorro (estos
datasets siempre aportan 0 GB).

**Razón:** estos datasets nunca son parte del "spend" que el producto
audita (D004/D010 ya establecían que el análisis es sobre el `spend` real
del cliente); mostrarlos es ruido puro, nunca información accionable.

**Tests:** `tests/test_report_render.py::TestReportOmitsInternalSplunkIndexes`.

**Addendum (Fase 3C.1):** la revisión de 3C.1 pidió verificar explícitamente
que ocultar estas filas nunca pudiera dejar un total ejecutivo sin poder
reconciliarse con las tablas visibles ("Executive total != suma explicable
de resultados visibles"). Verificado empíricamente contra el laboratorio
real (`index=_internal source=*license_usage.log type="Usage"`): ningún
índice interno aparece jamás en `license_usage.log` en esta instancia de
Splunk Enterprise -- confirma que el supuesto "0 GB garantizado" del
párrafo de arriba es cierto en la práctica, no solo en teoría. Aun así, el
filtro se endureció para no depender de esa suposición: ahora solo oculta
un índice `_`-prefijo cuando `ingest_gb_per_day == 0.0` exactamente
(`d.key.index.startswith("_") and d.ingest_gb_per_day == 0.0`). Si algún
día un índice interno SÍ trajera volumen real (p.ej. un CSV manual mal
formado en modo CSV, o una versión de Splunk que sí mida uso interno),
seguiría siendo visible -- así la garantía "nunca se oculta dinero" es por
construcción del código, no por una suposición sobre los datos de origen.
Test: `tests/test_report_render.py::TestInternalIndexFilterNeverHidesRealVolume`.

---

## D013 — Modelo de disponibilidad de señales (`SignalAvailability`)

**Contexto:** Fase 3B. `RawCollection.sources_available` (y
`EnvironmentSummary.sources_available`) eran `dict[str, bool]` desde Fase 2 --
solo podían distinguir "presente" de "ausente". Esto no alcanza para
representar la diferencia entre "se consultó la fuente y el resultado es 0"
(confirmado) y "no fue posible obtener la señal" (403, timeout, endpoint
inaccesible, archivo no exportado) -- exactamente la ambigüedad que el brief
de Fase 3B identificó como riesgo central.

**Decisión:** se agregó `models.SignalAvailability` (enum: `AVAILABLE`,
`UNAVAILABLE`, `PARTIAL`, `ERROR`, `NOT_APPLICABLE`) y se cambió el tipo de
`sources_available` en ambos collectors y en `EnvironmentSummary`. Semántica:
- `AVAILABLE`: se consultó con éxito; el resultado (incluso 0 filas) es una
  respuesta real, usable como "confirmado ausente".
- `UNAVAILABLE`: nunca se intentó (archivo CSV ausente, o el collector no
  implementa esa fuente para este modo).
- `PARTIAL`: se consultó pero la cobertura puede estar incompleta (p.ej.
  límite `maxsearches` de `| map` alcanzado en `metadata_last_seen.spl`).
- `ERROR`: se intentó y Splunk/la red devolvió un error explícito.
- `NOT_APPLICABLE`: no es un resultado de query en este contexto (p.ej.
  `dashboards_used`/`protected_overrides`, fuentes manuales opcionales por
  diseño desde Fase 2, no una regresión de Fase 3B).

**Razón:** es la pieza mínima de arquitectura necesaria para que
`scoring/rules.py` pueda negarse a tratar un `0` como evidencia cuando la
fuente que lo produjo no es confiable -- ver D014. Se evaluó (y descartó)
agregar un campo separado por señal dentro de `Dataset` (p.ej.
`audit_searches_available: bool`); se prefirió mantener la disponibilidad a
nivel de FUENTE/ENTORNO (como ya lo era en Fase 2), no de dataset individual,
porque así es como realmente falla una fuente REST (todo el endpoint
falla o no, no un dataset a la vez) -- añadir granularidad por dataset habría
sido una abstracción sin un caso real que la justifique.

---

## D014 — La pérdida de una señal nunca puede producir una clasificación más agresiva

**Contexto:** Fase 3B. Se encontró y reprodujo un bug real (antes de este
fix) en `scoring/rules.py::classify()`: un `Dataset` con
`interactive_searches_90d=0`, `is_scheduled=False`, `has_alert_action=False`
llegaba a `POSSIBLE_WASTE` exactamente igual sin importar si esos ceros
estaban CONFIRMADOS (la fuente respondió y no hay uso) o eran simplemente el
valor default de un campo que nunca se pudo poblar porque `audit_searches`/
`saved_searches` fallaron (403, timeout, endpoint inaccesible). El código no
consultaba `sources_available` en ningún punto de la clasificación -- a pesar
de que `docs/architecture.md` ya documentaba desde Fase 2 el principio
contrario ("nunca se asume 0 uso por ausencia de la fuente completa").

**Decisión:** `classify()` recibe un nuevo parámetro,
`unavailable_signals: frozenset[str]` (calculado por
`classify_all.unavailable_signals_from(sources_available)`). Si
`audit_searches` o `saved_searches` no están `AVAILABLE`, la regla
`POSSIBLE_WASTE` NUNCA puede aplicarse -- el dataset se degrada a `REVIEW`
(peso 0.5 en `compute_savings`, contra 1.0 de `POSSIBLE_WASTE`) con una
explicación que nombra la fuente faltante. Deliberadamente **NO** se incluye
`dashboards_used` en el conjunto de fuentes bloqueantes: su ausencia es una
limitación estructural aceptada desde Fase 2
(`docs/splunk-data-sources.md` sección 7 ya documentaba que omitirla, como
máximo, subestima `HIGH_VALUE` -- nunca produce un falso `POSSIBLE_WASTE`).
Incluirla habría bloqueado `POSSIBLE_WASTE` en casi todos los entornos reales
(la mayoría de usuarios no exportan ese CSV opcional), un cambio de
comportamiento no pedido y contrario al valor central del producto.

**Validación:** además de los tests unitarios
(`tests/test_rules.py::TestSignalAvailabilityGating`,
`tests/test_savings.py::test_losing_visibility_never_increases_potential_savings`),
se reprodujo el efecto extremo a extremo contra `sample-data/case_mixed`
real: quitando `audit_searches.csv`, el ahorro potencial estimado cayó de
36.3% ($34,211) a 21.6% ($20,296) -- nunca subió -- y `app:verbose_debug`/
`windows:eventlog_raw` pasaron de `POSSIBLE_WASTE` a `REVIEW` con una
explicación honesta. También se confirmó contra el laboratorio Splunk real de
Fase 3A (ver PROJECT_STATUS.md).

**Razón:** es exactamente la propiedad de seguridad pedida explícitamente
para Fase 3B: "la pérdida de una señal nunca puede aumentar artificialmente
la clasificación de desperdicio ni los potential savings". `REVIEW` en vez de
`UNKNOWN` porque la fuente que falta es específica (audit/saved searches), no
una falla generalizada del parser SPL en todo el entorno (eso sigue siendo
D009, un eje ortogonal) -- `REVIEW` sigue exigiendo revisión manual sin
descartar por completo la señal parcial que sí existe (p.ej. el propio
ingest alto).

**Limitación real encontrada durante la validación contra el laboratorio,
NO resuelta en Fase 3B (ver D015):** este mecanismo depende de que la fuente
falle con un error EXPLÍCITO (HTTP 4xx/5xx, timeout). Se confirmó contra el
laboratorio que un usuario Splunk con `srchIndexesAllowed` restringido (sin
`_audit` en la lista) NO recibe un 403 al consultar `_audit` -- la búsqueda
devuelve HTTP 200 con `results: []`, indistinguible de "no hay búsquedas".
Con un token así, `lsa_high_value` (HIGH_VALUE real, 12 búsquedas) se
reclasificó como `POSSIBLE_WASTE` porque el mecanismo de esta decisión no
tiene ninguna señal de error que capturar. Ver D015.

---

## D015 — RESUELTO: preflight de acceso efectivo a `_audit` antes de confiar en un resultado vacío

**Estado:** resuelto en la iteración dirigida a D015 (posterior a Fase 3B).
La versión anterior de esta decisión (que documentaba la limitación como
NO resuelta) queda reemplazada por lo siguiente.

**Contexto original (Fase 3B):** se creó un rol Splunk real (`lsa_restricted`)
con `srchIndexesAllowed=["_internal", "lsa_*"]` (sin `_audit`) y un token
para un usuario con ese rol. La query `audit_interactive_searches.spl`
contra `index=_audit` con ese token devuelve `HTTP 200`, `messages: []`,
`results: []` -- Splunk aplica el scope de índices del rol en silencio, sin
ningún error ni warning en la respuesta. Con ese token, `lsa_high_value`
(HIGH_VALUE real, confirmado con el token admin) se reclasificaba como
`POSSIBLE_WASTE` -- D014 (que bloquea `POSSIBLE_WASTE` cuando
`sources_available` marca una fuente como no-`AVAILABLE`) no cubría este
caso porque, desde la perspectiva del collector, la fuente había respondido
"exitosamente".

**Investigación del modelo de autorización real de Splunk (empírica, contra
el laboratorio, no solo documentación):**
1. `/services/authorization/roles/<rol>` expone, además de los campos
   propios (`srchIndexesAllowed`/`srchIndexesDisallowed`), los campos
   `imported_srchIndexesAllowed`/`imported_srchIndexesDisallowed` -- Splunk
   mismo resuelve ahí la herencia de TODA la cadena de `imported_roles`,
   confirmado con una cadena de 3 niveles de roles importados y con una
   búsqueda real exitosa contra `_audit` usando un token cuyo único camino
   de acceso era heredado transitivamente. No hace falta caminar el grafo
   de roles a mano.
2. Un patrón `"*"` (bare wildcard) en `srchIndexesAllowed`/
   `imported_srchIndexesAllowed` **no** concede acceso a índices internos
   (`_audit`, `_internal`, etc.) -- confirmado porque el rol base `"user"`
   (heredado por `lsa_restricted`) tiene `srchIndexesAllowed=["*"]` y NO
   otorgaba acceso a `_audit`, mientras que el rol `admin` de Splunk agrega
   explícitamente `"_*"` ADEMÁS de `"*"` en su propio `srchIndexesAllowed`.
3. `srchIndexesDisallowed` siempre gana sobre `srchIndexesAllowed`, sin
   importar cuán amplio sea el allow -- confirmado con un rol
   `srchIndexesAllowed=["*","_*"]` + `srchIndexesDisallowed=["_audit"]` que
   seguía sin poder buscar `_audit`.
4. El acceso efectivo de un usuario es la UNIÓN de TODOS sus roles propios
   (no solo `imported_roles` dentro de un rol) -- confirmado dándole a un
   usuario dos roles, uno sin `_audit` y otro con `_audit`, y verificando
   acceso real.

**Decisión:** `rest_collector.py` agrega un preflight determinista (NO
heurístico) antes de confiar en un resultado vacío de
`audit_interactive_searches.spl`:
- Si la query devuelve **alguna fila**, es evidencia positiva inequívoca --
  se usa directamente, sin ningún preflight (ahorra las llamadas extra en
  el caso común).
- Si devuelve **cero filas**, se resuelve `_probe_index_access()`: obtiene
  los roles del usuario actual (`/services/authentication/current-context`)
  y, para cada uno, el conjunto efectivo allow/disallow (propio + heredado,
  vía los campos `imported_*`). Devuelve `CONFIRMED` / `DENIED` /
  `UNDETERMINED`.
  - `CONFIRMED` → el resultado vacío es un cero real, `AVAILABLE`.
  - `DENIED` o `UNDETERMINED` → `UNAVAILABLE`, con una razón legible
    específica en `RawCollection.diagnostics["audit_searches"]` (nunca
    "cero búsquedas").
- **Fail-safe explícito:** si CUALQUIER rol del usuario no se puede leer
  con confianza (red, permisos, respuesta inesperada), todo el resultado es
  `UNDETERMINED` -- nunca se declara `CONFIRMED` con información parcial.

**Segundo hallazgo durante la implementación -- refinamiento necesario de
D014, no solo de D015:** el primer intento de esta corrección (degradar a
`REVIEW`, igual que D014) todavía violaba el invariante de que "perder
visibilidad nunca puede aumentar el ahorro potencial estimado": un dataset
que sería `HIGH_VALUE` (peso 0 en `compute_savings`) pasaba a `REVIEW`
(peso 0.5) al perder `_audit` -- el ahorro potencial subía de $0 a un
número positivo, exactamente en la dirección prohibida, aunque la
*clasificación* nominal (REVIEW, no POSSIBLE_WASTE) pareciera segura. Se
agregó `Dataset.excluded_from_savings_estimate: bool` (ver
`models/__init__.py`, `scoring/rules.py`, `scoring/savings.py`): cuando
D014 degrada a `REVIEW` específicamente porque la señal faltante también
podría haber confirmado `HIGH_VALUE` (rule 3), ese `REVIEW` no contribuye
NADA al cálculo de ahorro (ni el peso 0.5 normal) -- solo un `REVIEW`
respaldado por evidencia real y disponible conserva el peso 0.5. Esto NO es
scope creep de D015: es una corrección necesaria para que la propiedad de
seguridad que D014 pretendía garantizar sea cierta en todos los casos, no
solo en el caso `POSSIBLE_WASTE` directo.

**Validado con datos reales de `sample-data/case_mixed`:** quitando
`audit_searches.csv`, el ahorro potencial estimado ahora es **0.0% / $0**
(antes de este refinamiento, Fase 3B reportaba 21.6% / $20,296 -- ese
número queda superado/corregido por este hallazgo, ver PROJECT_STATUS.md).
$0 es la respuesta conservadora correcta: sin `audit_searches`, ningún
candidato puede confirmarse con evidencia suficiente.

**Validado contra el laboratorio Splunk real (no solo mocks):** con el
token admin (acceso completo), `lsa_high_value` clasifica `HIGH_VALUE`. Con
el token `lsa_restricted` (sin `_audit`), el mismo dataset clasifica
`REVIEW` (nunca `POSSIBLE_WASTE`), el CLI muestra el aviso de confianza
reducida con la razón específica ("current credentials do not have
confirmed access to _audit..."), y "Optimization candidates: 0.0 GB/day".

**Limitación conocida y aceptada (no bloqueante):** el preflight cubre
específicamente `_audit` (alcance de esta iteración). El riesgo análogo
para `saved_searches`/capability `list_settings` (mencionado en la versión
original de D015) sigue sin un preflight equivalente -- permanece como
recomendación operativa (token con `list_settings`), no como corrección de
código. También queda fuera de alcance el caso, estructuralmente
indetectable vía esta API, de que una query de referencia a un campo que no
existe en la versión del cliente devuelva `200`/`[]` sin error (schema
drift) -- no relacionado con permisos de índice.

**Tests:** `tests/test_rest_collector.py::TestIndexPatternMatching`,
`TestD015AuditIndexAccessProbe` (7 tests: acceso confirmado, denegado,
indeterminado, un rol ilegible entre varios, disallow gana sobre allow
amplio, acceso solo vía rol heredado, acceso vía un segundo rol propio) y
`TestD015SafetyInvariantEndToEnd` (reproduce el caso real HIGH_VALUE →
POSSIBLE_WASTE y demuestra que ya no ocurre, más los invariantes de
clasificación y ahorro). `tests/test_rules.py` agrega verificación directa
de `excluded_from_savings_estimate`.

---

## D001 — Nombre provisional: "Log Spend Auditor"

**Estado:** provisional, pendiente de investigación de trademark (Tarea 18 del
brief original). No bloquea el desarrollo del MVP: el código usa el paquete
Python `splunk_spend_auditor`, que es fácil de renombrar después.

---

## D002 — Arquitectura: CLI con dos collectors (REST API + CSV), no SaaS

**Decisión:** el producto es un CLI Python que corre en la máquina del cliente.
Soporta dos modos de obtención de datos:

- **Modo REST** (`--host`, `--token`): se conecta directamente a la API REST de
  Splunk y ejecuta las queries.
- **Modo CSV** (`--from-csv`): el usuario exporta los resultados de las queries
  SPL manualmente (o vía un botón "Export" de un dashboard) y el CLI analiza
  los CSV localmente, sin necesidad de credenciales de Splunk en absoluto.

**Razón:** la Tarea 10 del brief pedía evaluar Opción A (CLI+REST), Opción B
(CSV) u Opción C (ambas). Se eligió **Opción C** porque:
1. El modo CSV tiene fricción de adopción cero y cero riesgo de seguridad
   (el usuario nunca comparte credenciales con nuestra herramienta) — ideal
   para el Quickscan gratuito de validación de mercado.
2. El modo REST es necesario para el producto Pro (automatización recurrente,
   sin pasos manuales) y es el que finalmente escala.
3. Compartir el mismo motor de análisis (`analysis/`, `scoring/`) entre ambos
   modos significa que construir el modo CSV primero no es trabajo perdido:
   es el mismo pipeline con una fuente de datos distinta.

**Alternativa descartada:** SaaS hospedado (subir datos a un backend nuestro).
Descartada explícitamente por el principio LOCAL-FIRST del brief y porque
introduce una superficie de ataque y un costo de infraestructura que no
necesitamos para validar si alguien paga por esto.

---

## D003 — Stack técnico: Python + Typer + pandas + Jinja2

**Decisión:** Python 3.11+, Typer (CLI), `httpx` (REST), `pandas` (no `polars`),
Jinja2 (reportes HTML/Markdown), `pytest`.

**Razón:**
- Python es el lenguaje con más overlap con el ecosistema Splunk (el propio
  Splunk SDK oficial es Python) y con la experiencia de Alvaro.
- `pandas` en vez de `polars`: los volúmenes de datos de este producto son
  metadata (miles de filas `index x sourcetype`, no eventos crudos), no datasets
  de gigabytes. `polars` no aporta ventaja de rendimiento relevante aquí y
  `pandas` tiene más ejemplos/soporte para quien mantenga esto después.
- Typer sobre `argparse`/`click` puro: genera `--help` legible con poco código,
  bueno para un CLI que se distribuye a terceros.
- Jinja2 para generar tanto el HTML como el Markdown desde las mismas
  plantillas de datos evita mantener dos generadores de reporte distintos.

---

## D004 — Unidad de análisis: `(index, sourcetype)`, no host ni source

**Decisión:** la unidad mínima de clasificación y scoring es el par
`(index, sourcetype)`. Host y source se muestran como información adicional
"best-effort" cuando están disponibles, pero **nunca** son la base de una
clasificación `POSSIBLE_WASTE`.

**Razón (hecho verificado):** `license_usage.log` aplica *squashing*: cuando el
número de tuplas distintas `(source, sourcetype, host, index)` supera
`squash_threshold`, Splunk descarta los valores de `host` y `source` en esos
eventos y solo reporta por `(sourcetype, index)`. Solo el desglose por
`sourcetype` e `index` está garantizado como completo (no pierde bytes); el
desglose por host o por source puede subestimar sistemáticamente el volumen
real en entornos con muchas fuentes distintas. Ver
`docs/splunk-data-sources.md`, fuente 1.

Diseñar el producto alrededor de una unidad que se degrada silenciosamente
(host/source) habría generado números de ahorro potencial poco confiables
justo en los entornos grandes donde más importa que sean correctos.

---

## D009 — `UNKNOWN` se decide por la cobertura del ENTORNO, no del dataset

**Decisión:** un dataset sin evidencia HIGH propia (nunca mencionado
literalmente en ninguna búsqueda) **no** se clasifica automáticamente como
`UNKNOWN`. Solo cae en `UNKNOWN` cuando el `partial_or_unknown_ratio` del
**entorno completo** supera `UNKNOWN_ENVIRONMENT_RATIO_THRESHOLD` (50% por
defecto). Si el entorno tiene buena cobertura de parsing en general, el
silencio de un dataset específico se trata como evidencia real de falta de
uso y sigue evaluándose por las reglas 3-6 normales (`HIGH_VALUE`,
`POSSIBLE_WASTE`, `REVIEW`, `NORMAL`).

**Por qué se corrigió (bug real encontrado en la validación de Fase 2):** la
primera implementación gateaba la regla `UNKNOWN` con
`dataset.parser_confidence != HIGH`, un campo que por diseño empieza en
`UNKNOWN` para *cualquier* dataset que nunca aparece mencionado literalmente
en una búsqueda — que es exactamente el perfil del caso más común e
importante que el producto existe para encontrar: un dataset caro que nadie
busca nunca. Con la regla original, ese caso (`app:verbose_debug` en
`sample-data/case_mixed`, 38 GB/día y cero búsquedas) se clasificaba
`UNKNOWN` en vez de `POSSIBLE_WASTE`, y datasets usados solo por dashboard
(`sales:pos_transactions`, que nunca pasan por el parser de SPL en absoluto)
también quedaban atrapados en `UNKNOWN` antes de llegar a la regla de
`HIGH_VALUE`. Se detectó ejecutando el prototipo end-to-end contra los datos
sintéticos (ver `PROJECT_STATUS.md`) y se corrigió cambiando la señal de
"¿confío en el silencio de este dataset?" de una propiedad del dataset a una
propiedad del entorno — que es, además, exactamente lo que ya decía
`docs/scoring.md` sección 3 ("Regla dura") desde la Fase 2 original: el
código no coincidía con su propia documentación.

**Limitación conocida y aceptada (no es un bug):** esto significa que un
dataset de bajo volumen cuya única mención en el entorno es a través de una
macro no resuelta (`integration:partner_feed` en los datos sintéticos, Caso
9) **no** queda automáticamente protegido solo por esa macro, si el resto
del entorno tiene buena cobertura — cae en `REVIEW` o `POSSIBLE_WASTE` según
su volumen, igual que cualquier otro dataset silencioso. No hay forma
honesta de atribuir una macro no resuelta a un dataset específico (ver
DECISIONS.md D006); la protección para ese caso es el mecanismo manual de
`protected_overrides.txt`, igual que para el Caso 6 (dataset crítico de baja
frecuencia). Ver `sample-data/README.md`, nota sobre el Caso 9, para el
detalle completo con números reales.

---

## D005 — Nunca clasificar automáticamente como "eliminar"

**Decisión:** las categorías de salida son `HIGH_VALUE`, `NORMAL`, `REVIEW`,
`POSSIBLE_WASTE`, `PROTECTED`, `UNKNOWN`. Nunca `DELETE` ni nada que implique
una acción irreversible tomada por la herramienta o sugerida como automática.

**Razón:** cumple la Tarea 7 del brief (prevenir falsos positivos) y protege al
producto de daño reputacional: si un dataset marcado "para eliminar" resulta ser
crítico para compliance o una investigación de seguridad, el costo de haberse
equivocado es mucho mayor que el valor del ahorro sugerido. El lenguaje siempre
es de "candidato a revisión manual". Ver `docs/scoring.md`.

---

## D006 — El parser de SPL no intenta cubrir el 100% del lenguaje

**Decisión:** el motor de detección de uso clasifica cada búsqueda/saved search
en tres niveles de confianza: `HIGH` (index/sourcetype extraídos con certeza de
`index=X sourcetype=Y` explícitos), `PARTIAL` (se detectó una macro, eventtype,
data model o subsearch pero no se resolvió su contenido) y `UNKNOWN` (no se pudo
determinar nada). Un dataset que solo aparece en búsquedas `PARTIAL` o
`UNKNOWN` **nunca** se clasifica como `POSSIBLE_WASTE` — como máximo `REVIEW`.

**Razón:** intentar resolver macros anidadas, `eventtypes`, subsearches y
`tstats` sobre data models con 100% de exactitud es un problema abierto (en la
práctica, ni Splunk mismo lo resuelve de forma trivial fuera de Enterprise
Security). Es preferible ser conservador y marcar `UNKNOWN` que arriesgar un
falso positivo. Ver `docs/scoring.md`, sección "Confianza del parser", y
`docs/product-spec.md` Tarea 4.

---

## D007 — Distinguir "sin búsquedas manuales" de "sin uso"

**Decisión:** el motor consulta tres fuentes de uso, no solo `_audit`:
(1) búsquedas interactivas en `_audit` (filtrando `search_id=scheduler*`),
(2) saved searches / scheduled searches vía `/saved/searches` y
`/saved/searches/{name}/history`, y (3) opcionalmente una lista de
dashboards/paneles que el usuario puede exportar y pasar como CSV adicional
(el descubrimiento automático de qué panel usa qué dataset queda fuera del
MVP — ver `docs/product-spec.md`).

**Razón:** el propio brief señala el caso crítico: un sourcetype sin búsquedas
manuales puede alimentar una alerta crítica. Confundir ambas cosas sería el
peor tipo de falso positivo posible para este producto.

---

## D010 — Filtrar saved searches instaladas por Splunk mismo (`owner="nobody"`)

**Contexto:** validado en Fase 3A contra una instancia Splunk Enterprise
10.4.3 real (Docker, Trial license — ver PROJECT_STATUS.md). Sin ningún dato
ni configuración del cliente todavía, `/servicesNS/-/-/saved/searches`
devolvió **176 saved searches**, de las cuales **172 eran contenido
instalado por Splunk mismo** (apps `splunk_instrumentation` [117],
`SplunkDeploymentServerConfig` [29], `splunk_monitoring_console` [13],
`splunk_rapid_diag`, `audit_trail`, `splunk-rolling-upgrade`, más 10 reportes
por defecto de la app `search`) y solo 4 eran contenido real (2 creadas para
la prueba, 2 de `audit_trail` con `owner=admin`).

**Decisión:** el collector REST filtra las entries de
`/servicesNS/-/-/saved/searches` cuyo `eai:acl.owner == "nobody"` antes de
construir el DataFrame de saved searches, y por lo tanto antes de que
lleguen a `build_datasets`/`classify_all`.

**Razón:** sin este filtro, dos problemas concretos y confirmados:
1. Genera datasets fantasma sobre índices internos de Splunk (`_internal`,
   `_introspection`, `_telemetry`, ...) que el cliente no administra ni le
   interesa auditar — ruido visible en el reporte final.
2. Muchas de esas saved searches de sistema usan `tstats`/data models
   (confianza `PARTIAL` del parser SPL — ver D006), lo que infla
   `partial_or_unknown_ratio` del entorno completo. En la prueba, esto subió
   el ratio de ~46% a ~71%, cruzando el umbral de 50% de D009 y forzando
   `UNKNOWN` sobre `lsa_waste` (300 eventos, 0 búsquedas, exactamente el caso
   que el producto existe para encontrar) en vez de `POSSIBLE_WASTE`. Con el
   filtro aplicado, el ratio bajó a 46% y `lsa_waste` clasificó
   correctamente. Este no es un caso hipotético: es el comportamiento real
   de una instancia Splunk apenas instalada.

**Señal usada:** `owner == "nobody"` es la convención estándar de Splunk
para objetos sin dueño humano (instalados por una app en tiempo de
instalación), a diferencia de objetos creados por un usuario real, cuyo
`owner` sigue siendo ese usuario incluso si se comparten a nivel app/global
(`sharing=app`/`global` no cambia el `owner`).

**Limitación conocida y aceptada (no es un bug):** la señal no es 100%
precisa. En la validación, la app `audit_trail` registra su contenido con
`owner="admin"` en vez de `"nobody"`, y 2 de sus 2 saved searches
sobrevivieron al filtro. Se descartó filtrar por nombre de app (deny-list)
porque la app `search` mezcla contenido de sistema (10 reportes por defecto)
con contenido real del cliente (ahí es donde la mayoría de clientes crean
sus propios reportes/alertas) — un deny-list por app habría descartado
también contenido real. El impacto de este residual es mínimo: esas saved
searches sobrevivientes generan como máximo un dataset fantasma con 0 GB/día
(nunca aparecen en `license_usage.log`), invisible en la práctica en
cualquier reporte con datos reales de cliente.

**Tests de regresión:** `tests/test_rest_collector.py::test_saved_searches_excludes_splunk_bundled_content_owned_by_nobody`.

---

## D011 — `metadata type=sourcetypes` no tiene dimensión `index`; corregido con `map`

**Contexto:** validado en Fase 3A contra Splunk Enterprise 10.4.3 real. La
query `queries/metadata_last_seen.spl` de Fase 2 asumía
`| metadata type=sourcetypes index=*` devolvía un campo `index` (de ahí
`| eval index=split(index, "~")`, un patrón visto en foros de Splunk para
separar valores concatenados con `~` cuando SÍ hay desglose por índice en
otros comandos). **Esto es incorrecto para `metadata type=sourcetypes`:**
sus únicos campos de salida son `sourcetype`, `firstTime`, `lastTime`,
`recentTime`, `totalCount`, `type` — nunca `index`. El parámetro `index=`
solo filtra qué índices entran al cómputo; no es una dimensión de
agrupación. Con la query original, la columna `index` del resultado quedaba
vacía en el 100% de los casos, **sin ningún error ni warning** — el tipo de
falla silenciosa más peligroso para este producto, porque un CSV exportado
así habría roto el join por `(index, sourcetype)` de `build_datasets.py` sin
que nadie lo notara hasta revisar el reporte final a mano.

**Decisión:** `queries/metadata_last_seen.spl` ahora obtiene la lista de
índices con `| eventcount summarize=false index=* | dedup index`, y ejecuta
`metadata type=sourcetypes` una vez POR ÍNDICE vía `| map`, inyectando el
valor real del índice con `eval index="$index$"` dentro de la subbúsqueda.
Verificado end-to-end contra los 7 índices del laboratorio de Fase 3A.

**Razón:** es el único patrón que permite atribuir `last_seen_days_ago` al
`(index, sourcetype)` correcto cuando el mismo `sourcetype` aparece en más de
un índice — que es precisamente el escenario en el que la query original
fallaba en silencio.

**Limitación conocida y aceptada:** `map` tiene un límite `maxsearches`
(puesto en 100); entornos con más de 100 índices distintos necesitan subir
ese límite explícitamente o paginar. El collector REST (`rest_collector.py`)
todavía **no** ejecuta esta query — `sources_available["last_seen"]` sigue
en `False` (ver docstring del módulo); wire-up queda para Fase 3B junto con
el resto del hardening del collector real.

---

## D008 — Fase 2 no incluye pruebas contra un Splunk real

**Decisión:** toda la validación técnica de Fase 2 se hace contra datos
sintéticos (`sample-data/`), no contra una instancia Splunk real.

**Razón:** el objetivo de Fase 2 es validar que el diseño del scoring, la
clasificación y el cálculo de ahorro son correctos y deterministas — algo que
se puede probar completamente con CSVs sintéticos y `pytest`. Probar el
collector REST contra un Splunk real requiere credenciales/acceso que son una
decisión explícita del usuario (ver PROJECT_STATUS.md, "Decisiones pendientes").
El modo CSV, que no requiere esa decisión, queda completamente validado en
esta fase.

**Superado en Fase 3A:** el collector REST se validó contra una instancia
Splunk Enterprise 10.4.3 real (Docker, Trial license de 60 días — decisión
de laboratorio, no de producción, tomada dentro de esta sesión). Ver D010,
D011 y D012 para los bugs reales encontrados y corregidos, y
PROJECT_STATUS.md para el resumen completo.

---

## D012 — Coerción numérica de resultados REST (la API de Splunk serializa todo como string)

**Contexto:** validado en Fase 3A. Al ejecutar `queries/ingest_by_index_sourcetype.spl`
vía `/services/search/jobs?output_mode=json` contra Splunk real y pasar el
resultado a `build_datasets()`, el pipeline falló con
`TypeError: dtype 'str' does not support operation 'mean'` en el
`.groupby(...).agg(["mean", "count"])` de la columna `gb`.

**Causa:** la REST API de Splunk serializa **todos** los valores de
`results` como string en `output_mode=json`, incluso los numéricos (`"gb":
"0.0004"`, no `"gb": 0.0004`). El modo CSV nunca tuvo este problema porque
`pandas.read_csv` infiere tipos automáticamente; `pd.DataFrame(results)`
sobre JSON crudo no lo hace. Este bug no podía haberse encontrado en Fase 2
(datos 100% CSV) — es exactamente el tipo de gap que Fase 3A existe para
encontrar.

**Decisión:** `_run_oneshot_search()` en `rest_collector.py` convierte a
numérico cada columna del DataFrame resultante cuando el 100% de sus valores
son convertibles (`pd.to_numeric` sin ningún `NaN` resultante); columnas de
texto (p.ej. `index`, `sourcetype`) quedan intactas porque no son 100%
numéricas.

**Alternativa descartada:** convertir columnas por nombre conocido (p.ej.
"si la columna se llama 'gb', convertir siempre"). Se descartó porque acopla
el collector a los nombres de columna de una query específica; la conversión
"si el 100% de los valores son numéricos" es genérica y funciona para
cualquier query futura sin cambios en el collector.

**Tests de regresión:** `tests/test_rest_collector.py::test_oneshot_search_coerces_fully_numeric_columns_to_numeric`
y `::test_oneshot_search_leaves_mixed_columns_as_text`.
