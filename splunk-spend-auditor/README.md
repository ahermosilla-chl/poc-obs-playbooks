# Log Spend Auditor

**¿Qué datos estás pagando por ingerir en Splunk pero casi nunca usas?**

Log Spend Auditor es una herramienta de solo lectura y local-first que cruza
el volumen de ingest de tu entorno Splunk (`license_usage.log`) con señales
reales de uso (búsquedas interactivas, saved searches/alertas programadas,
dashboards) y clasifica cada `(index, sourcetype)` en una categoría
explicable, con un ahorro potencial estimado en dólares.

Operacionalmente de solo lectura: nunca modifica configuración ni datos
persistentes de Splunk, y nunca envía tus datos a un servidor externo —
todo corre en tu propia máquina. (El modo REST sí usa `POST
/services/search/jobs` en modo `oneshot` para ejecutar búsquedas -- así
funciona la API de búsqueda de Splunk incluso para queries de solo
lectura; nunca se llama a un endpoint que cree, modifique o borre
configuración/datos. Ver `docs/security.md` para el detalle completo.)

> **Estado del proyecto:** Fase 2, 3A, 3B, 3C, 3C.1, 3C.2 y 4A.1
> completadas -- MVP funcional, validado contra Splunk Enterprise real
> (Fase 3A, instancia 10.4.3) y endurecido contra pérdida de
> señales/errores REST (Fase 3B/D015). Preparado para testers externos
> controlados (Fase 4A.1). Ver `PROJECT_STATUS.md` para el detalle exacto
> de qué está hecho y qué falta.

## Por qué existe

Las organizaciones pagan por licencia de Splunk según el volumen de datos
ingeridos, y una parte de ese volumen suele tener muy poco uso real. Hoy no
existe una herramienta de autoservicio (sin consultoría, sin plataforma de
pipeline cara) que responda esa pregunta con evidencia concreta. Ver
`docs/product-spec.md` para el contexto completo.

## Instalación

Requiere **Python 3.10 o superior** (`pyproject.toml`,
`requires-python = ">=3.10"`).

**Para usar la herramienta (tester/usuario final):**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verificado (Fase 4A.1): esta instalación mínima, sin `[dev]`, es
suficiente para `--help`, `quickscan`, `audit` y la generación de
HTML/Markdown -- probado en un venv limpio.

**Para desarrollo (correr los tests):**

```bash
pip install -e ".[dev]"
```

`[dev]` agrega `pytest` y está reservado para quienes van a modificar el
código, no para un tester que solo va a ejecutar auditorías.

**Sistema operativo:** sin restricción conocida a nivel de código (no hay
dependencias específicas de plataforma). **Validado en Linux.** Se espera
que funcione en macOS (Python puro, sin llamadas a `subprocess` ni paths
específicos de SO) pero no fue probado ahí. No probado en Windows -- no
asumas que funciona sin verificarlo vos mismo primero.

## Try the demo

Sin Splunk, sin credenciales y sin internet:

```bash
splunk-spend-auditor demo
```

Corre el pipeline real de análisis y reporte sobre un entorno Splunk
**sintético** (datos ficticios y deterministas incluidos en el paquete: 9
índices, 12 sourcetypes, ~267 GB/día, con candidatos de optimización
visibles). No se conecta a Splunk ni a ninguna red. El reporte queda en
`./demo-output/report.html` (y `report.md`); usá `--output-dir <ruta>` para
cambiarlo. El demo no inventa cifras en dólares: muestra GB/día y % del
ingest observado.

## Uso rápido (con los datos sintéticos incluidos)

```bash
# Versión gratuita, resumen en terminal (no escribe ningún archivo)
splunk-spend-auditor quickscan --from-csv sample-data/case_mixed

# Auditoría completa con reporte HTML + Markdown
splunk-spend-auditor audit --from-csv sample-data/case_mixed \
    --output-dir ./output --annual-spend 94200
```

Esto genera `output/report.html` y `output/report.md` — ábrelos para ver el
formato completo del informe (Executive Summary, desglose de ingest,
candidatos de optimización con explicación, ahorro potencial, riesgos y
metodología). Es el **único** lugar donde la herramienta escribe algo a
disco -- para borrar todo lo generado, `rm -rf ./output` (o el directorio
que hayas pasado en `--output-dir`), no queda ningún otro estado local.

`--annual-spend` es **opcional**. Sin él, el reporte solo muestra el
porcentaje de volumen marcado como candidato a optimización -- nunca
inventa una cifra en dólares. Si lo pasás, el reporte deja explícito que
ese monto es un input que vos diste, no algo que la herramienta midió o
infirió (ver `docs/controlled-validation.md`).

## Uso contra tu propio entorno Splunk

**Modo CSV (sin credenciales):**
1. Corre las queries de `src/splunk_spend_auditor/queries/*.spl` en Splunk Search.
2. Exporta cada resultado a CSV con el nombre esperado (ver
   `sample-data/schema/` para el esquema exacto de cada archivo).
3. Corre `splunk-spend-auditor audit --from-csv <tu-directorio>`.

Ninguna credencial de Splunk es necesaria en este flujo — nunca compartes
acceso a tu instancia con esta herramienta.

**Modo REST — validado contra Splunk Enterprise real (instancia 10.4.3, vía
Docker, Fase 3A/3B/D015). Splunk Cloud NO ha sido validado todavía** (ver
`docs/splunk-permissions.md` para la salvedad conocida de acceso a
`_internal`/`_audit` en Cloud):

```bash
export SPLUNK_TOKEN=<tu token de Splunk>   # o se pide de forma interactiva
splunk-spend-auditor audit --host <tu-splunk> --port 8089
```

La verificación TLS está **activada por defecto** (`--verify-ssl`). Usá
`--no-verify-ssl` únicamente si tu instancia usa un certificado
self-signed o de otra forma no confiable en un entorno controlado (un
lab, por ejemplo) -- nunca contra una instancia de producción real sin
entender la implicancia.

El token nunca se pasa como argumento de línea de comandos ni se escribe a
disco (ver `docs/security.md`). **No uses un token `admin` para un tester**
-- ver `docs/splunk-permissions.md` para la lista exacta de permisos
Required/Recommended/Optional, con qué pasa si falta cada uno (nunca se
asume "cero uso" por un permiso faltante — se degrada de forma
conservadora, ver D013/D014/D015 en `DECISIONS.md`).

## Standalone distribution (distribución para usuarios finales)

> **Estado:** el workflow de build nativo fue ejecutado y verificado en
> Linux x86_64, Windows x86_64 y macOS arm64 (artifacts internos de GitHub
> Actions, sin firmar). **Todavía no hay binarios públicos.**

El objetivo es un ejecutable portable (sin Python, pip ni repositorio):
`./splunk-spend-auditor demo` (Windows: `splunk-spend-auditor.exe demo`).
Los desarrolladores lo construyen con PyInstaller (`--onefile`); PyInstaller
**no cross-compila**, así que cada plataforma se construye en su propio SO:

```bash
pip install -e ".[build]"
make build            # o: python scripts/build.py
python scripts/smoke_test.py dist/<artefacto>
```

El workflow manual `.github/workflows/release-build.yml` (GitHub Actions,
`workflow_dispatch`) construye y prueba cada plataforma en un runner nativo
y sube los binarios como *artifacts* internos (no publica nada).

Genera `dist/splunk-spend-auditor-<version>-<os>-<arch>[.exe]` más su
`.sha256` (`dist/` está en `.gitignore`). Plataformas previstas:
`linux-x86_64`, `macos-arm64`, `windows-x86_64.exe`. La instalación con
`pip install -e .` descrita arriba sigue siendo la vía para desarrollo.
`splunk-spend-auditor --version` muestra la versión.

## Estructura del repositorio

```
docs/                   Especificación completa (arquitectura, scoring,
                         seguridad, diseño del reporte, fuentes de datos de
                         Splunk, permisos Splunk, guía de validación
                         controlada para testers)
src/.../queries/        Queries SPL comentadas y listas para exportar a CSV
sample-data/            Escenario sintético reproducible (10+ casos) y
                         esquemas de referencia
src/splunk_spend_auditor/
    models/             Entidades de dominio (Dataset, Classification, ...)
    collector/           Modo CSV y modo REST -- ambos validados contra
                         datos reales (CSV: sample-data/case_mixed; REST:
                         Splunk Enterprise real, ver Fase 3A/3B/D015)
    analysis/           Parser de SPL + motor de cruce de fuentes
    scoring/            Reglas de clasificación, score, cálculo de ahorro
    reports/            Generación de reportes HTML/Markdown (Jinja2)
    cli.py              CLI (Typer): `quickscan` y `audit`
src/.../templates/      Plantillas Jinja2 de los reportes
tests/                  Suite pytest (192 tests) -- incluye un test de
                         integración end-to-end contra sample-data/case_mixed
PROJECT_STATUS.md       Estado exacto del proyecto, para retomar sin perder contexto
DECISIONS.md            Registro de decisiones de arquitectura/producto
```

## Ejecutar los tests

Requiere `pip install -e ".[dev]"` (ver "Instalación" arriba) -- no
disponible en la instalación mínima.

```bash
python3 -m pytest tests/ -v
```

## Documentación

Empezar por `docs/product-spec.md` (qué hace y qué no hace) y
`docs/architecture.md` (cómo está construido). `docs/scoring.md` documenta
cada regla de clasificación con su razonamiento — el código en
`src/splunk_spend_auditor/scoring/rules.py` es una traducción directa de ese
documento, línea por línea.

**Para preparar o correr una validación con un tester externo:**
`docs/splunk-permissions.md` (ficha de permisos para darle a un Splunk
Admin) y `docs/controlled-validation.md` (guía práctica para el tester,
de instalación a reporte).

## Licencia

Pendiente de definir antes de publicación pública (ver
`docs/product-spec.md`, sección Naming, para las tareas pendientes antes de
publicar en GitHub con nombre y licencia definitivos).
