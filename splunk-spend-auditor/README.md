# Log Spend Auditor

**¿Qué datos estás pagando por ingerir en Splunk pero casi nunca usas?**

Log Spend Auditor es una herramienta de solo lectura y local-first que cruza
el volumen de ingest de tu entorno Splunk (`license_usage.log`) con señales
reales de uso (búsquedas interactivas, saved searches/alertas programadas,
dashboards) y clasifica cada `(index, sourcetype)` en una categoría
explicable, con un ahorro potencial estimado en dólares.

Nunca modifica ni borra nada en Splunk. Nunca envía tus datos a un servidor
externo — todo corre en tu propia máquina.

> **Estado del proyecto:** Fase 2, 3A y 3B completadas -- MVP funcional,
> validado contra Splunk real (Fase 3A) y endurecido contra pérdida de
> señales/errores REST (Fase 3B). Ver `PROJECT_STATUS.md` para el detalle
> exacto de qué está hecho y qué falta.

## Por qué existe

Las organizaciones pagan por licencia de Splunk según el volumen de datos
ingeridos, y una parte de ese volumen suele tener muy poco uso real. Hoy no
existe una herramienta de autoservicio (sin consultoría, sin plataforma de
pipeline cara) que responda esa pregunta con evidencia concreta. Ver
`docs/product-spec.md` para el contexto completo.

## Instalación (desarrollo)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso rápido (con los datos sintéticos incluidos)

```bash
# Versión gratuita, resumen en terminal
splunk-spend-auditor quickscan --from-csv sample-data/case_mixed

# Auditoría completa con reporte HTML + Markdown
splunk-spend-auditor audit --from-csv sample-data/case_mixed \
    --output-dir ./output --annual-spend 94200
```

Esto genera `output/report.html` y `output/report.md` — ábrelos para ver el
formato completo del informe (Executive Summary, desglose de ingest,
candidatos de optimización con explicación, ahorro potencial, riesgos y
metodología).

## Uso contra tu propio entorno Splunk

**Modo CSV (sin credenciales):**
1. Corre las queries de `queries/*.spl` en Splunk Search.
2. Exporta cada resultado a CSV con el nombre esperado (ver
   `sample-data/schema/` para el esquema exacto de cada archivo).
3. Corre `splunk-spend-auditor audit --from-csv <tu-directorio>`.

Ninguna credencial de Splunk es necesaria en este flujo — nunca compartes
acceso a tu instancia con esta herramienta.

**Modo REST (validado contra Splunk Enterprise real en Fase 3A/3B):**

```bash
export SPLUNK_TOKEN=<tu token de Splunk>   # o se pide de forma interactiva
splunk-spend-auditor audit --host <tu-splunk> --port 8089
```

El token nunca se pasa como argumento de línea de comandos ni se escribe a
disco (ver `docs/security.md`). Requiere que el rol del token tenga acceso a
`_internal`. Si no tiene acceso a `_audit`, el CLI lo detecta automáticamente
(no asume "cero búsquedas") y degrada la clasificación de forma conservadora
en vez de arriesgar un falso `POSSIBLE_WASTE` — ver `DECISIONS.md` D015. Para
resultados con máxima cobertura, el token debería tener también acceso a
`_audit` y la capability `list_settings`.

## Estructura del repositorio

```
docs/                   Especificación completa (arquitectura, scoring,
                         seguridad, diseño del reporte, plan de validación,
                         fuentes de datos de Splunk)
queries/                Queries SPL comentadas y listas para exportar a CSV
sample-data/            Escenario sintético reproducible (10+ casos) y
                         esquemas de referencia
src/splunk_spend_auditor/
    models/             Entidades de dominio (Dataset, Classification, ...)
    collector/           Modo CSV (probado) y modo REST (implementado, sin
                         probar contra Splunk real)
    analysis/           Parser de SPL + motor de cruce de fuentes
    scoring/            Reglas de clasificación, score, cálculo de ahorro
    reports/            Generación de reportes HTML/Markdown (Jinja2)
    cli.py              CLI (Typer): `quickscan` y `audit`
templates/              Plantillas Jinja2 de los reportes
tests/                  Suite pytest (69 tests) -- incluye un test de
                         integración end-to-end contra sample-data/case_mixed
PROJECT_STATUS.md       Estado exacto del proyecto, para retomar sin perder contexto
DECISIONS.md            Registro de decisiones de arquitectura/producto
```

## Ejecutar los tests

```bash
python3 -m pytest tests/ -v
```

## Documentación

Empezar por `docs/product-spec.md` (qué hace y qué no hace) y
`docs/architecture.md` (cómo está construido). `docs/scoring.md` documenta
cada regla de clasificación con su razonamiento — el código en
`src/splunk_spend_auditor/scoring/rules.py` es una traducción directa de ese
documento, línea por línea.

## Licencia

Pendiente de definir antes de publicación pública (ver
`docs/product-spec.md`, sección Naming, para las tareas pendientes antes de
publicar en GitHub con nombre y licencia definitivos).
