"""Collector para el modo REST (D002) -- conexión directa y de solo lectura
a una instancia Splunk real.

ESTADO: validado en Fase 3A contra una instancia Splunk Enterprise 10.4.3
real (Trial license, laboratorio Docker) -- ver PROJECT_STATUS.md y
DECISIONS.md D010/D011. Dos bugs reales se encontraron y corrigieron durante
esa validación (ninguno detectable solo con CSVs sintéticos):

1. La REST API de Splunk serializa TODOS los valores de resultados como
   string, incluso los numéricos -- `_run_oneshot_search` ahora convierte a
   numérico las columnas que sean 100% convertibles.
2. `/servicesNS/-/-/saved/searches` devuelve también el contenido instalado
   por Splunk mismo (cientos de saved searches de sistema en una instancia
   recién instalada) -- se filtra por `eai:acl.owner == "nobody"` antes de
   construir el DataFrame. Ver D010 para la limitación conocida de este
   filtro (no captura el 100% de los casos).

Ver `tests/test_rest_collector.py` para los tests de regresión de ambos
bugs (usan `httpx.MockTransport`, no requieren una instancia Splunk real).

Principios de seguridad aplicados aquí (ver docs/security.md):
- Solo se llama a endpoints de lectura (GET) y a /search/jobs con las
  queries de solo lectura de queries/*.spl -- nunca se escribe/borra nada.
- El token nunca se escribe a disco por este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pandas as pd

from splunk_spend_auditor.collector.csv_collector import RawCollection

_SEARCH_JOBS_ENDPOINT = "/services/search/jobs"
# Wildcard de user/app -- ver docs/splunk-data-sources.md sección 3, "gotcha
# de scoping": sin esto se pierden saved searches de otros usuarios/apps.
_SAVED_SEARCHES_ENDPOINT = "/servicesNS/-/-/saved/searches"


@dataclass
class RestConfig:
    host: str
    token: str
    port: int = 8089
    verify_ssl: bool = True
    lookback_days: int = 90
    transport: httpx.BaseTransport | None = None  # solo para tests (httpx.MockTransport)


def _client(config: RestConfig) -> httpx.Client:
    return httpx.Client(
        base_url=f"https://{config.host}:{config.port}",
        headers={"Authorization": f"Bearer {config.token}"},
        verify=config.verify_ssl,
        timeout=60.0,
        transport=config.transport,
    )


def _run_oneshot_search(client: httpx.Client, spl: str) -> pd.DataFrame:
    """Ejecuta una búsqueda en modo 'oneshot' (bloqueante, resultado directo)
    contra /services/search/jobs y devuelve un DataFrame. Modo de solo
    lectura -- nunca se llama a /control con acciones de escritura."""

    response = client.post(
        _SEARCH_JOBS_ENDPOINT,
        data={
            "search": spl if spl.strip().startswith("|") else f"search {spl}",
            "exec_mode": "oneshot",
            "output_mode": "json",
        },
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results", [])
    df = pd.DataFrame(results)
    # La REST API de Splunk serializa TODOS los valores de resultados como
    # string (confirmado empíricamente en Fase 3A contra Splunk 10.4.3 real
    # -- a diferencia de pandas.read_csv, que infiere tipos automáticamente
    # en el modo CSV). Sin esto, columnas numéricas como "gb" llegan como
    # texto y build_datasets.py falla con TypeError al hacer .agg(["mean"]).
    # Solo se convierte una columna si el 100% de sus valores son numéricos,
    # para no corromper columnas de texto (p.ej. "index") que por casualidad
    # tengan algunos valores numéricos.
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().all():
            df[col] = converted
    return df


def collect(config: RestConfig, queries_dir: str) -> RawCollection:
    """Punto de entrada del modo REST. Ejecuta las mismas queries
    documentadas en queries/*.spl contra un Splunk real.

    NOTA: implementación de referencia, pendiente de validar contra una
    instancia real (ver docstring del módulo). El CLI actual (Fase 2) solo
    expone el modo CSV como camino probado; este módulo queda listo para
    activarse en Fase 3 sin rediseño.
    """

    from pathlib import Path

    queries_path = Path(queries_dir)

    def _load_query(filename: str) -> str:
        text = (queries_path / filename).read_text()
        # Las queries en queries/*.spl empiezan con un bloque de comentario
        # ``` ... ``` explicativo -- se descarta antes de ejecutar.
        if text.startswith("```"):
            end = text.index("```", 3)
            text = text[end + 3 :]
        return text.strip()

    collection = RawCollection()
    with _client(config) as client:
        collection.ingest = _run_oneshot_search(
            client, _load_query("ingest_by_index_sourcetype.spl")
        )
        collection.sources_available["ingest"] = True

        try:
            collection.audit_searches = _run_oneshot_search(
                client, _load_query("audit_interactive_searches.spl")
            )
            collection.sources_available["audit_searches"] = True
        except httpx.HTTPStatusError:
            # Sin acceso a _audit (rol restringido) -- se degrada, no falla
            # (ver docs/architecture.md, "Manejo de errores").
            collection.sources_available["audit_searches"] = False

        try:
            saved = client.get(
                _SAVED_SEARCHES_ENDPOINT, params={"output_mode": "json", "count": 0}
            )
            saved.raise_for_status()
            entries = saved.json().get("entry", [])
            # Filtra contenido instalado por Splunk mismo (apps del sistema:
            # splunk_instrumentation, monitoring console, deployment server,
            # etc.), NUNCA saved searches reales del cliente -- confirmado
            # empíricamente en Fase 3A contra Splunk 10.4.3 real: en una
            # instancia recién instalada, /servicesNS/-/-/saved/searches
            # devuelve ~170 saved searches del propio Splunk junto a las del
            # cliente. Sin este filtro: (1) contaminan build_datasets con
            # datasets fantasma sobre índices internos (_internal,
            # _introspection, _telemetry, ...) que el cliente no puede ni
            # necesita auditar, y (2) muchas de ellas usan tstats/data models
            # (PARTIAL) y disparan el mecanismo de protección de D009
            # (UNKNOWN a nivel de entorno) aunque el entorno real del cliente
            # esté bien cubierto -- ver DECISIONS.md D010.
            # Señal usada: `eai:acl.owner == "nobody"` es la convención de
            # Splunk para contenido instalado por una app (sin dueño humano),
            # a diferencia del contenido creado por un usuario real (owner=
            # username), incluso si luego se comparte a nivel app/global.
            # Limitación conocida y aceptada: no es 100% exacta -- algunas
            # apps del sistema (p.ej. audit_trail) registran su contenido con
            # owner="admin" en vez de "nobody"; en la validación de Fase 3A
            # esto dejó pasar 2 de 176 saved searches de sistema (ver
            # PROJECT_STATUS.md). Filtrar por nombre de app en vez de owner
            # se descartó porque la app "search" mezcla contenido de sistema
            # y contenido real del cliente.
            entries = [
                e for e in entries if e.get("acl", {}).get("owner") != "nobody"
            ]
            collection.saved_searches = pd.DataFrame(
                [
                    {
                        "name": e.get("name"),
                        "search_text": e.get("content", {}).get("search", ""),
                        "is_scheduled": e.get("content", {}).get(
                            "is_scheduled", False
                        ),
                        "cron_schedule": e.get("content", {}).get(
                            "cron_schedule", ""
                        ),
                        "has_alert_action": bool(
                            e.get("content", {}).get("actions", "")
                        ),
                        "next_scheduled_time": e.get("content", {}).get(
                            "next_scheduled_time", ""
                        ),
                    }
                    for e in entries
                ]
            )
            collection.sources_available["saved_searches"] = True
        except httpx.HTTPStatusError:
            collection.sources_available["saved_searches"] = False

        collection.sources_available["dashboards_used"] = False  # manual, MVP
        collection.sources_available["last_seen"] = False

    return collection
