"""Collector para el modo REST (D002) -- conexión directa y de solo lectura
a una instancia Splunk real.

ESTADO: implementado según la documentación oficial de Splunk (ver
docs/splunk-data-sources.md), pero NO EJERCITADO CONTRA UN SPLUNK REAL en
Fase 2 (ver PROJECT_STATUS.md, "Próximos pasos" -- requiere credenciales que
son una decisión explícita del usuario). No tiene tests de integración
todavía; sí se puede -- y se recomienda -- revisar su lógica de forma
estática.

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


def _client(config: RestConfig) -> httpx.Client:
    return httpx.Client(
        base_url=f"https://{config.host}:{config.port}",
        headers={"Authorization": f"Bearer {config.token}"},
        verify=config.verify_ssl,
        timeout=60.0,
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
    return pd.DataFrame(results)


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
