# Arquitectura — Log Spend Auditor

Ver `DECISIONS.md` D002 y D003 para la justificación de estas elecciones.

## Vista general

```
                    ┌─────────────────────┐
                    │   CLI (Typer)        │
                    │  splunk-spend-auditor │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴──────────────┐
                 │                             │
        ┌────────▼────────┐          ┌────────▼────────┐
        │  REST Collector   │          │  CSV Collector   │
        │  (httpx + token)  │          │  (pandas.read_csv)│
        └────────┬────────┘          └────────┬────────┘
                 │                             │
                 └─────────────┬───────────────┘
                               │
                   ┌───────────▼────────────┐
                   │  Modelos de dominio      │
                   │  (dataclasses, models/)  │
                   │  - IngestRecord           │
                   │  - UsageRecord            │
                   │  - Dataset                │
                   └───────────┬────────────┘
                               │
                   ┌───────────▼────────────┐
                   │  Analysis engine          │
                   │  (analysis/)              │
                   │  - join ingest + uso       │
                   │  - confianza del parser    │
                   └───────────┬────────────┘
                               │
                   ┌───────────▼────────────┐
                   │  Scoring engine           │
                   │  (scoring/)               │
                   │  - Data Value Score        │
                   │  - clasificación           │
                   │  - protected datasets      │
                   │  - cálculo de ahorro       │
                   └───────────┬────────────┘
                               │
                   ┌───────────▼────────────┐
                   │  Report generator         │
                   │  (reports/ + Jinja2)      │
                   │  - report.html            │
                   │  - report.md              │
                   │  - report.csv (export)    │
                   └────────────────────────┘
```

## Por qué esta forma

- **Un único motor de análisis y scoring, dos collectors.** El CLI decide, según
  los flags (`--host`/`--token` vs `--from-csv`), cuál collector instanciar,
  pero ambos producen los mismos `IngestRecord`/`UsageRecord` normalizados.
  Todo lo que viene después (join, scoring, reportes) es idéntico. Esto es lo
  que permite validar el 100% de la lógica de negocio (Fase 2, esta fase) sin
  necesitar una instancia Splunk real: el collector CSV consume
  `sample-data/*.csv` con exactamente el mismo esquema que produciría la query
  SPL real contra un Splunk de verdad.

- **Modelos de dominio explícitos (`models/`)** en vez de pasar `DataFrame`s de
  pandas "a pelo" entre módulos. Un `Dataset` (par index+sourcetype) es una
  entidad de primera clase con sus propios campos (`ingest_gb_per_day`,
  `searches_30d`, `is_scheduled`, `has_alert`, `has_dashboard`,
  `parser_confidence`, `last_seen_days_ago`). Esto hace el scoring testeable
  unitariamente sin pandas de por medio.

- **Separación análisis vs. scoring.** `analysis/` responde "¿qué sabemos de
  este dataset y con qué confianza?" (join de fuentes + nivel de confianza del
  parser SPL). `scoring/` responde "dado lo que sabemos, ¿qué categoría le
  asignamos y cuánto ahorro potencial representa?". Separar estas dos
  preguntas permite testear las reglas de clasificación (Tarea 8) de forma
  aislada de la complejidad de parsear SPL (Tarea 4).

- **Reportes desde plantillas Jinja2 compartidas.** El mismo contexto de datos
  (lista de `ScoredDataset` + resumen ejecutivo + metadata de ahorro) alimenta
  tanto `report.html.j2` como `report.md.j2`. Evita mantener dos
  implementaciones de "cómo se ve un reporte".

## Flujo de ejecución (modo CSV, el validado en Fase 2)

```
splunk-spend-auditor audit --from-csv sample-data/case_mixed/ --annual-spend 94200
      │
      ▼
1. CSVCollector.load()
   → lee ingest_by_index_sourcetype.csv, audit_searches.csv,
     saved_searches.csv, dashboards.csv (opcional)
      │
      ▼
2. build_datasets()  (analysis/)
   → agrupa por (index, sourcetype)
   → adjunta señales de uso con su nivel de confianza
      │
      ▼
3. score_datasets()  (scoring/)
   → aplica reglas de docs/scoring.md
   → asigna categoría + Data Value Score + razón textual
      │
      ▼
4. compute_savings()  (scoring/)
   → suma GB/día de POSSIBLE_WASTE + REVIEW (ponderado)
   → aplica --annual-spend o --cost-per-gb-day
      │
      ▼
5. render_report()  (reports/)
   → report.html, report.md
```

## Manejo de errores y datos parciales

El principio es **degradar, nunca fallar en silencio ni inventar datos**:

- Si falta la fuente de `_audit` (uso interactivo): el reporte lo indica
  explícitamente en la sección "Methodology" y todos los datasets que
  dependían solo de esa fuente para su señal de uso quedan con confianza
  reducida (nunca se asume "0 uso" por ausencia de la fuente completa; se
  asume "uso desconocido por esa vía").
- Si falta `saved_searches.csv`/history: mismo principio.
- Si un dataset no aparece en ninguna fuente de uso: se clasifica `UNKNOWN`,
  no `POSSIBLE_WASTE` — ver `docs/scoring.md`.

## Lo que NO se construye en el MVP (recordatorio del brief)

SaaS, login, cuentas, backend en la nube, billing/Stripe, dashboards web
complejos, agentes instalados, despliegue en Kubernetes, asistente de IA,
base de datos multi-tenant. El CLI es un binario/paquete que corre
enteramente en la máquina del usuario.
