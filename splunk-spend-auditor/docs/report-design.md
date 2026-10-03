# Diseño del informe — Log Spend Auditor

Formatos generados: `report.html` (para enviar a manager/FinOps/Splunk admin) y
`report.md` (para pegar en un ticket/wiki). Ambos se generan desde el mismo
contexto de datos vía Jinja2 (ver `src/splunk_spend_auditor/templates/`).

## Secciones (en orden)

### 1. Executive Summary
3-4 líneas en lenguaje no técnico: ingest total, spend estimado, % de
reducción potencial y ahorro anual potencial. Ejemplo real generado por el
prototipo (caso sintético `case_mixed`, ver sección de validación):

```
Your Splunk environment ingests 243.0 GB/day across 12 (index, sourcetype)
datasets. Of that, 41.3 GB/day (17.0%) are flagged as optimization candidates
with low or no observed usage. Based on an estimated annual spend of
$94,200, this represents a potential annual saving of around $16,014.
This is a potential saving, not a guaranteed one — see "Risk Considerations".
```

### 2. Current Spend
Tabla: ingest total GB/día, spend anual estimado (input del usuario o
`--cost-per-gb-day`), método de cálculo usado.

### 3. Ingestion Breakdown
Tabla ordenada por `ingest_gb_per_day` descendente: index, sourcetype, GB/día,
% del total. Top N configurable (`--top`, por defecto 20 en el reporte Free,
50 en el Pro — ver Tarea 13).

### 4. Usage Analysis
Tabla: dataset, búsquedas interactivas 30d/90d, programado (sí/no), alertas
(sí/no), dashboards (sí/no), usuarios únicos, última vez visto, confianza del
parser.

### 5. Top Optimization Candidates
Los datasets `POSSIBLE_WASTE` y `REVIEW`, ordenados por
`ingest_gb_per_day` descendente, cada uno con:
- nombre (index / sourcetype)
- GB/día
- la frase explicativa obligatoria (docs/scoring.md sección 7)
- clasificación
- recomendación en lenguaje no imperativo:
  `"Optimization candidate — review ingestion/filtering policy"` para
  `POSSIBLE_WASTE`, `"Review candidate — manual validation recommended"` para
  `REVIEW`.

### 6. Indexes / Sourcetypes (detalle completo)
Tabla completa de todos los datasets con su categoría — para quien quiera ver
el detalle más allá del Top N.

### 7. Potential Savings
Desglose de la fórmula de `docs/scoring.md` sección 8, con los números
concretos usados (no solo el resultado).

### 8. Risk Considerations
Texto fijo, siempre presente, que incluye:
- que las cifras son estimaciones basadas en metadata, no una auditoría
  financiera;
- que los datasets `PROTECTED` fueron excluidos deliberadamente;
- que los datasets `UNKNOWN` no se incluyen en el cálculo de ahorro;
- una nota sobre squashing si el entorno analizado muestra señales de alta
  cardinalidad de host/source (ver `docs/splunk-data-sources.md`);
- que ninguna acción debe tomarse sin validación manual de un administrador
  de Splunk.

### 9. Recommendations
Lista corta (3-5 puntos) de próximos pasos sugeridos en lenguaje de proceso,
no de producto: "validar con el equipo dueño del dato", "considerar
`INGEST_EVAL`/filtrado en el forwarder", "reconsiderar el tier de
retención" — nunca instrucciones SPL de borrado.

### 10. Methodology
- Rango de fechas analizado.
- Fuentes de datos disponibles vs. no disponibles en esta corrida (ver
  `docs/architecture.md`, "Manejo de errores y datos parciales").
- `partial_unknown_ratio` del entorno (docs/scoring.md sección 3).
- Versión de la herramienta y fecha de generación.

## Ejemplo de bloque de candidato (formato usado literalmente en la plantilla)

```
proxy_debug

Ingest: 17.0 GB/day
Interactive searches (30d): 0
Interactive searches (90d): 0
Scheduled searches: 0
Alerts: 0
Dashboards: Not evaluated
Last data observed: 83 days ago
Classification: POSSIBLE WASTE

This dataset appears as a candidate because it ingests 17.0 GB/day, has no
interactive searches in the last 90 days, and was not found in alerts or
scheduled saved searches (dashboard usage was not evaluated in this run --
see Methodology).
```

Nota (Fase 3C.1/D018): "Dashboards" solo muestra "Yes"/"No" cuando
`dashboards_used` fue evaluado de verdad en este run (el usuario exportó
`dashboards_used.csv`) -- de lo contrario muestra "Not evaluated" y la
explicación del candidato NO afirma "no encontrado en dashboards" (eso
sería una certeza falsa sobre una señal nunca consultada). Ver
DECISIONS.md D018. Además, "Last observed" se renombró a "Last data
observed": la señal viene de `metadata type=sourcetypes` (actividad de
ingest/datos, `recentTime`), NUNCA de actividad de búsqueda interactiva --
el nombre anterior podía leerse, junto a las columnas "Searches 30d/90d",
como si también fuera sobre uso humano.

Recommendation: Review ingestion/filtering policy.
```

## Free vs. Pro (Tarea 13)

| Sección | Free (Quickscan) | Pro |
|---|---|---|
| Executive Summary | Sí | Sí |
| Current Spend | Solo total | Total + tendencia 30d |
| Ingestion Breakdown | Top 5 | Top 50 / completo |
| Usage Analysis | No (solo se menciona que existe) | Completo |
| Top Optimization Candidates | Top 3 | Completo |
| Potential Savings | Estimación simple | Desglose completo + por categoría |
| CSV export | No | Sí |
| Markdown export | Sí (para poder compartirlo igual) | Sí |
| Risk Considerations / Methodology | Sí (siempre, sin excepción) | Sí |

**Regla de diseño:** las secciones de riesgo/metodología nunca se recortan en
la versión Free — la herramienta debe ser honesta sobre sus límites incluso
en el gancho gratuito.
