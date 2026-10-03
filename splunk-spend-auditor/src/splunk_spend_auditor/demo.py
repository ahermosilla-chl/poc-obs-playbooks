"""Offline demo (Fase 5A): un entorno Splunk SINTÉTICO y determinista que se
inyecta como `RawCollection` en el pipeline real (build_datasets ->
classify_all -> compute_savings -> render). No hay red, credenciales ni
archivos de entrada: los datos se construyen en memoria con fórmulas fijas
(sin RNG, sin reloj), así cada corrida produce exactamente el mismo reporte.

Todo nombre es ficticio -- ningún cliente, empresa, usuario ni credencial
real. Este módulo es el único adaptador entre el fixture y los modelos."""

from __future__ import annotations

import pandas as pd

from splunk_spend_auditor.collector.csv_collector import RawCollection
from splunk_spend_auditor.models import SignalAvailability

DEMO_SOURCE_LABEL = "Synthetic demo dataset (offline, no Splunk connection)"

_AS_OF = pd.Timestamp("2026-09-30")
_DAYS = 28
# Suma cero en 7 días -> el promedio de 28 días es exactamente el base.
_WOBBLE = [0.0, 0.5, 1.0, 0.25, -0.5, -1.0, -0.25]

# (index, sourcetype, GB/día promedio, búsquedas últimos 30d, búsquedas 31-85d,
#  usuarios distintos)
_WORKLOADS = [
    ("web", "nginx_access", 42.0, 26, 40, 6),
    ("cdn", "edge_access", 30.0, 14, 22, 4),
    ("payments", "txn_events", 16.0, 18, 30, 5),
    ("app", "orders_service", 22.0, 4, 6, 2),
    ("infra", "syslog", 18.0, 3, 4, 2),
    ("infra", "snmp_traps", 3.0, 11, 9, 3),
    ("infra", "windows_perfmon", 24.0, 0, 1, 1),
    ("legacy", "app_2019", 1.2, 0, 0, 0),
    ("app", "debug_verbose", 38.0, 0, 0, 0),
    ("k8s", "kube_container_logs", 61.0, 0, 0, 0),
    ("security", "ids_alerts", 9.0, 0, 0, 0),
    ("auth", "sso_events", 3.0, 0, 0, 0),
]

_SAVED_SEARCHES = [
    {
        "name": "Orders Latency Daily Report",
        "search_text": "index=app sourcetype=orders_service | stats p95(latency_ms) by route",
        "is_scheduled": "true",
        "cron_schedule": "0 6 * * *",
        "has_alert_action": "false",
        "next_scheduled_time": "2026-10-01T06:00:00",
    },
    {
        "name": "CDN 5xx Spike Alert",
        "search_text": "index=cdn sourcetype=edge_access status>=500 | stats count by pop",
        "is_scheduled": "true",
        "cron_schedule": "*/15 * * * *",
        "has_alert_action": "true",
        "next_scheduled_time": "2026-10-01T00:15:00",
    },
]

# Búsquedas que el parser no puede atribuir con certeza (macros / sin index=)
# -- realismo: ningún entorno real parsea el 100% de sus búsquedas.
_UNRESOLVED_SEARCHES = [
    "`web_base` | stats count by status",
    "`web_base` | timechart span=1h count",
    "`k8s_namespace_filter` | top pod",
    "| makeresults | eval x=1",
]


def _ingest() -> pd.DataFrame:
    rows = []
    for index, sourcetype, base, *_ in _WORKLOADS:
        for day in range(_DAYS):
            date = _AS_OF - pd.Timedelta(days=_DAYS - 1 - day)
            gb = base * (1 + 0.08 * _WOBBLE[day % 7])
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "index": index,
                    "sourcetype": sourcetype,
                    "gb": round(gb, 6),
                }
            )
    return pd.DataFrame(rows)


def _audit_searches() -> pd.DataFrame:
    rows = []
    seq = 0

    def _add(date: pd.Timestamp, user: str, text: str, scheduled: bool = False) -> None:
        nonlocal seq
        seq += 1
        rows.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "user": user,
                "search_id": f"{'scheduler_' if scheduled else ''}demo-{seq:04d}",
                "is_scheduled": "true" if scheduled else "false",
                "search_text": text,
            }
        )

    for index, sourcetype, _gb, recent, older, users in _WORKLOADS:
        text = f"index={index} sourcetype={sourcetype} | stats count"
        for i in range(recent):
            _add(_AS_OF - pd.Timedelta(days=(i * 3) % 28), f"analyst_{i % users + 1:02d}", text)
        for i in range(older):
            _add(_AS_OF - pd.Timedelta(days=35 + (i * 5) % 50), f"analyst_{i % users + 1:02d}", text)

    for i, text in enumerate(_UNRESOLVED_SEARCHES):
        _add(_AS_OF - pd.Timedelta(days=2 + i), "analyst_01", text)

    # Una ejecución del scheduler: debe excluirse del conteo interactivo.
    _add(
        _AS_OF - pd.Timedelta(days=1),
        "splunk-system-user",
        "index=app sourcetype=debug_verbose | stats count",
        scheduled=True,
    )
    return pd.DataFrame(rows)


def _last_seen() -> pd.DataFrame:
    rows = []
    for i, (index, sourcetype, *_rest) in enumerate(_WORKLOADS):
        days = 41.0 if index == "legacy" else round(0.1 + 0.2 * (i % 6), 1)
        rows.append({"index": index, "sourcetype": sourcetype, "last_seen_days_ago": days})
    return pd.DataFrame(rows)


def build_demo_collection() -> RawCollection:
    """El entorno sintético completo, listo para el pipeline real."""

    return RawCollection(
        ingest=_ingest(),
        audit_searches=_audit_searches(),
        saved_searches=pd.DataFrame(_SAVED_SEARCHES),
        last_seen=_last_seen(),
        sources_available={
            "ingest": SignalAvailability.AVAILABLE,
            "audit_searches": SignalAvailability.AVAILABLE,
            "saved_searches": SignalAvailability.AVAILABLE,
            "last_seen": SignalAvailability.AVAILABLE,
            "dashboards_used": SignalAvailability.NOT_APPLICABLE,
            "protected_overrides": SignalAvailability.NOT_APPLICABLE,
        },
    )
