"""Genera el escenario sintético `case_mixed/` de forma determinista.

Ver sample-data/README.md para el mapeo de los 10 casos pedidos en el brief
a los datasets generados aquí. Ejecutar:

    python sample-data/generate_sample_data.py

Es determinista (semilla fija) — regenerar produce exactamente los mismos
archivos, para que los tests que dependen de estos CSV sean reproducibles.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(20260926)  # fecha de referencia del proyecto, arbitraria pero fija

OUT_DIR = Path(__file__).parent / "case_mixed"
OUT_DIR.mkdir(exist_ok=True)

TODAY = date(2026, 9, 26)
DAYS_OF_INGEST = 30  # ventana de ingest generada (el motor soporta hasta 90d)


# Cada dataset: (index, sourcetype, gb_per_day_promedio, variacion)
DATASETS = [
    ("cdn", "edge_access", 45.0, 3.0),  # Caso 1
    ("app", "verbose_debug", 38.0, 2.0),  # Caso 2
    ("app", "login_events", 2.8, 0.3),  # Caso 3
    ("network", "snmp_traps", 12.0, 1.0),  # Caso 4
    ("sales", "pos_transactions", 8.0, 0.5),  # Caso 5
    ("dr", "heartbeat_check", 20.0, 0.5),  # Caso 6
    ("windows", "eventlog", 15.0, 1.0),  # Caso 7 (mantener)
    ("windows", "eventlog_raw", 30.0, 2.0),  # Caso 7 (duplicado)
    ("legacy", "app_2019", 0.3, 0.05),  # Caso 8
    ("integration", "partner_feed", 9.0, 0.8),  # Caso 9
    ("compliance", "pci_audit_log", 14.0, 1.0),  # Caso 10
    ("infra", "syslog", 6.0, 0.5),  # baseline NORMAL
]


def write_ingest() -> None:
    rows = []
    for idx, st, mean_gb, spread in DATASETS:
        for day_offset in range(DAYS_OF_INGEST):
            d = TODAY - timedelta(days=day_offset)
            gb = max(0.01, round(random.gauss(mean_gb, spread), 4))
            rows.append((d.isoformat(), idx, st, gb))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(OUT_DIR / "ingest_by_index_sourcetype.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "index", "sourcetype", "gb"])
        w.writerows(rows)


def search_id(day_offset: int, n: int, scheduled: bool) -> str:
    ts = int((TODAY - timedelta(days=day_offset)).strftime("%s")) if hasattr(
        date, "strftime"
    ) else 0
    prefix = "scheduler_alert_" if scheduled else ""
    return f"{prefix}{1758000000 + day_offset * 100 + n}"


def write_audit_searches() -> None:
    """Búsquedas INTERACTIVAS (_audit). search_id con prefijo scheduler_ se
    excluye por el propio parser (ver docs/scoring.md sección 3) — aquí solo
    se agregan además unas pocas filas scheduler_* para probar que el parser
    las excluye correctamente de interactive_searches."""
    rows = []

    # Caso 1: cdn:edge_access — mucho uso interactivo, HIGH confidence
    for day_offset in range(0, 30, 2):  # ~15 búsquedas en 30 días
        rows.append(
            (
                (TODAY - timedelta(days=day_offset)).isoformat(),
                "alice",
                f"175800{day_offset:04d}.001",
                "false",
                "index=cdn sourcetype=edge_access action=blocked | stats count by dest_ip",
            )
        )

    # Caso 3: app:login_events — poco volumen pero MUCHO uso (>=10 en 30d)
    for day_offset in range(0, 30, 2):  # 15 búsquedas
        rows.append(
            (
                (TODAY - timedelta(days=day_offset)).isoformat(),
                "bob",
                f"175800{day_offset:04d}.002",
                "false",
                "index=app sourcetype=login_events | stats count by user",
            )
        )

    # Caso 2 (app:verbose_debug): CERO búsquedas — no se agregan filas.

    # Caso 4 (network:snmp_traps): CERO búsquedas interactivas — solo alerta
    # programada (ver write_saved_searches). No se agregan filas de _audit.

    # Caso 6 (dr:heartbeat_check): uso INFRECUENTE — 1 sola búsqueda en 90d
    rows.append(
        (
            (TODAY - timedelta(days=60)).isoformat(),
            "oncall_engineer",
            "1758000099.900",
            "false",
            "index=dr sourcetype=heartbeat_check | stats count",
        )
    )

    # Caso 7a (windows:eventlog): uso normal moderado
    for day_offset in range(0, 30, 5):
        rows.append(
            (
                (TODAY - timedelta(days=day_offset)).isoformat(),
                "carol",
                f"175800{day_offset:04d}.003",
                "false",
                "index=windows sourcetype=eventlog EventCode=4625",
            )
        )

    # Caso 7b (windows:eventlog_raw): CERO búsquedas — es el duplicado sin uso.

    # Caso 9 (integration:partner_feed): aparece SOLO vía macro -> PARTIAL,
    # nunca se resuelve a index=/sourcetype= literal, por diseño (ver
    # docs/scoring.md sección 3 y DECISIONS.md D006).
    for day_offset in range(0, 30, 10):
        rows.append(
            (
                (TODAY - timedelta(days=day_offset)).isoformat(),
                "dave",
                f"175800{day_offset:04d}.004",
                "false",
                "`partner_feed_search` | stats count by status",
            )
        )

    # Caso 10 (compliance:pci_audit_log): CERO búsquedas interactivas (nadie
    # lo busca a mano — es protegido de todas formas por patrón).

    # Baseline (infra:syslog): uso normal bajo
    for day_offset in range(0, 30, 7):
        rows.append(
            (
                (TODAY - timedelta(days=day_offset)).isoformat(),
                "erin",
                f"175800{day_offset:04d}.005",
                "false",
                "index=infra sourcetype=syslog | timechart count",
            )
        )

    # Filas de scheduler que el parser DEBE excluir de interactive_searches
    # (existen en _audit pero con search_id=scheduler_*)
    rows.append(
        (
            (TODAY - timedelta(days=1)).isoformat(),
            "system",
            "scheduler_edge_access_daily_1758000000",
            "true",
            "index=cdn sourcetype=edge_access | stats count",
        )
    )

    rows.sort(key=lambda r: r[0])
    with open(OUT_DIR / "audit_searches.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "user", "search_id", "is_scheduled", "search_text"])
        w.writerows(rows)


def write_saved_searches() -> None:
    rows = [
        # Caso 4: network:snmp_traps — SIN búsquedas interactivas, pero
        # programada Y con alerta -> HIGH_VALUE
        (
            "SNMP Trap Storm Alert",
            "index=network sourcetype=snmp_traps | stats count by trap_oid | where count > 100",
            "true",
            "*/10 * * * *",
            "true",
            "2026-09-26T12:10:00",
        ),
        # Caso 1: cdn:edge_access también tiene un reporte programado
        # (sin alerta) además del uso interactivo
        (
            "Daily Firewall Traffic Report",
            "index=cdn sourcetype=edge_access | stats count by action",
            "true",
            "0 6 * * *",
            "false",
            "2026-09-27T06:00:00",
        ),
        # Caso 7a: windows:eventlog con reporte programado (refuerza HIGH_VALUE)
        (
            "Failed Logon Report",
            "index=windows sourcetype=eventlog EventCode=4625 | stats count by user",
            "true",
            "0 7 * * *",
            "false",
            "2026-09-27T07:00:00",
        ),
    ]
    with open(OUT_DIR / "saved_searches.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "name",
                "search_text",
                "is_scheduled",
                "cron_schedule",
                "has_alert_action",
                "next_scheduled_time",
            ]
        )
        w.writerows(rows)


def write_dashboards_used() -> None:
    # Caso 5: sales:pos_transactions -- utilizado ÚNICAMENTE por dashboards
    rows = [("sales", "pos_transactions")]
    with open(OUT_DIR / "dashboards_used.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "sourcetype"])
        w.writerows(rows)


def write_last_seen() -> None:
    rows = []
    for idx, st, _, _ in DATASETS:
        if (idx, st) == ("legacy", "app_2019"):
            days_ago = 412.0  # Caso 8: datos antiguos, sin eventos recientes
        else:
            days_ago = round(random.uniform(0.1, 2.0), 1)
        rows.append((idx, st, days_ago))
    with open(OUT_DIR / "last_seen.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "sourcetype", "last_seen_days_ago"])
        w.writerows(rows)


def write_protected_overrides() -> None:
    # Caso 6: dr:heartbeat_check -- uso infrecuente pero CRÍTICO. No cumple
    # ninguna regla automática de PROTECTED (no matchea *audit*/*security*/
    # etc.), así que un admin humano lo agrega manualmente. Esto demuestra
    # el mecanismo de override manual (docs/scoring.md sección 6).
    content = (
        "# protected_overrides.txt\n"
        "# Un patrón por línea (index:sourcetype). Estos datasets nunca se\n"
        "# clasifican como POSSIBLE_WASTE sin importar sus señales de uso.\n"
        "dr:heartbeat_check\n"
    )
    with open(OUT_DIR / "protected_overrides.txt", "w") as f:
        f.write(content)


def main() -> None:
    write_ingest()
    write_audit_searches()
    write_saved_searches()
    write_dashboards_used()
    write_last_seen()
    write_protected_overrides()
    print(f"Generado escenario sintético en {OUT_DIR}")


if __name__ == "__main__":
    main()
