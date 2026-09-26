# DECISIONS.md

Registro de decisiones de arquitectura y producto, con la razón detrás de cada
una, para no volver a discutirlas desde cero en sesiones futuras.

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
