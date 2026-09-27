"""Tests de analysis/build_datasets.py."""

import pandas as pd

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import RawCollection


def test_low_volume_ingest_is_not_rounded_away_to_zero():
    """Bug real (Fase 3C): build_datasets redondeaba ingest_gb_per_day a
    4 decimales -- un dataset real de bajo volumen (p.ej. 920 bytes/día,
    confirmado contra el laboratorio Splunk real) quedaba en
    ingest_gb_per_day=0.0, indistinguible de "no ingiere nada" para el
    resto del pipeline (clasificación, ahorro, reporte). Con 8 decimales
    la resolución mínima es ~10 bytes, suficiente para cualquier volumen
    real."""

    ingest = pd.DataFrame(
        [
            {"date": "2026-09-01", "index": "lsa_alert_only", "sourcetype": "monitoring:heartbeat", "gb": 0.00000086},
        ]
    )
    collection = RawCollection(ingest=ingest)
    datasets, _ = build_datasets(collection)

    assert len(datasets) == 1
    assert datasets[0].ingest_gb_per_day > 0
    assert datasets[0].ingest_gb_per_day == 0.00000086
