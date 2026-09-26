# sample-data/

Datasets sintéticos para validar el motor de análisis/scoring sin necesitar
una instancia Splunk real (ver `DECISIONS.md` D008).

- `schema/` — un CSV mínimo de 1-2 filas por archivo, documentando el esquema
  exacto que produce cada query de `queries/*.spl` y que espera el
  `CSVCollector`. Sirve como referencia rápida, no como escenario de prueba.
- `case_mixed/` — un escenario único y coherente de 12 datasets que cubre los
  10 casos pedidos en el brief (ver tabla abajo). Se generó de forma
  reproducible con `generate_sample_data.py` (semilla fija). Es el escenario
  que usan los tests (`tests/`) y el prototipo end-to-end.

## Mapeo de los 10 casos pedidos → dataset en `case_mixed`

| # | Caso pedido | Dataset (index:sourcetype) | Categoría esperada |
|---|---|---|---|
| 1 | Mucho volumen + mucho uso | `cdn:edge_access` | `HIGH_VALUE` |
| 2 | Mucho volumen + cero uso | `app:verbose_debug` | `POSSIBLE_WASTE` |
| 3 | Poco volumen + mucho uso | `app:login_events` | `HIGH_VALUE` |
| 4 | Sin búsquedas manuales, usado por alerta | `network:snmp_traps` | `HIGH_VALUE` |
| 5 | Utilizado únicamente por dashboards | `sales:pos_transactions` | `HIGH_VALUE` |
| 6 | Uso infrecuente pero crítico (protegido manualmente) | `dr:heartbeat_check` | `PROTECTED` (vía `protected_overrides.txt`) |
| 7 | Datos aparentemente duplicados | `windows:eventlog` (mantener) vs `windows:eventlog_raw` (duplicado) | `HIGH_VALUE` / `POSSIBLE_WASTE` |
| 8 | Datos antiguos | `legacy:app_2019` | `REVIEW` (ingest bajo, no alcanza el percentil de "waste") |
| 9 | Dataset donde no podemos determinar uso | `integration:partner_feed` | `REVIEW` — ver nota abajo, no `UNKNOWN` |
| 10 | Dataset de seguridad/compliance | `compliance:pci_audit_log` | `PROTECTED` (patrón `*compliance*`/`*audit*`) |
| — | Baseline normal (no pedido explícitamente, para contraste) | `infra:syslog` | `NORMAL` |

### Nota sobre el Caso 9 (por qué termina en `REVIEW`, no en `UNKNOWN`)

`integration:partner_feed` solo aparece en el entorno a través de una macro
(`` `partner_feed_search` ``), que el parser marca `PARTIAL` a nivel de esa
búsqueda — pero **la evidencia `PARTIAL` no se puede atribuir a un dataset
concreto** (no sabemos qué índice/sourcetype resuelve la macro). Por diseño
(ver `docs/scoring.md` sección 3 y `DECISIONS.md` D009), la clasificación
`UNKNOWN` de un dataset solo se activa cuando el entorno **completo** tiene
mala cobertura de parsing (`partial_or_unknown_ratio` alto) — no existe un
mecanismo para proteger automáticamente un dataset individual solo porque
*alguna* búsqueda en el entorno usa una macro no resuelta, ya que no hay
forma de saber si esa macro tiene algo que ver con este dataset en
particular. En este escenario el entorno tiene buena cobertura global
(`partial_or_unknown_ratio` = 6.25%), así que el "silencio" de
`integration:partner_feed` se trata como señal real y cae en `REVIEW` (por
volumen bajo, no llega al umbral de `POSSIBLE_WASTE`). Un admin que sepa que
esa macro sí cubre este dataset puede protegerlo manualmente con
`protected_overrides.txt`, igual que el Caso 6. El comportamiento genuino de
`UNKNOWN` por mala cobertura del entorno está cubierto por un test dedicado
en `tests/test_rules.py`, con un entorno sintético separado donde
`partial_or_unknown_ratio` es deliberadamente alto.

Regenerar los datos: `python sample-data/generate_sample_data.py`
(determinista — misma salida siempre, semilla fija en el script).
