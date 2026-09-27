"""Tests de analysis/build_datasets.py."""

import pandas as pd
import pytest

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


class TestMalformedIngestValuesDoNotPoisonTheReport:
    """Fase 4B (vulnerabilidad CONFIRMED, corregida): un valor `gb` no
    finito (NaN/Infinity, que json.loads acepta por defecto para una
    respuesta REST técnicamente malformada) o negativo envenenaba
    silenciosamente el promedio del dataset -- `nan` contamina cualquier
    suma/media que lo incluya -- y de ahí compute_savings() completo. El
    reporte final llegaba a mostrar literalmente "nan KB/day". Ahora se
    descartan filas con `gb` no numérico/no finito/negativo ANTES de
    agregar (un ingest no puede ser negativo ni infinito por definición)."""

    @pytest.mark.parametrize(
        "bad_value",
        [float("nan"), float("inf"), float("-inf"), -50.0, "not-a-number"],
    )
    def test_malformed_gb_row_is_excluded_not_propagated(self, bad_value):
        ingest = pd.DataFrame(
            [
                {"date": "2026-09-01", "index": "idx_bad", "sourcetype": "st", "gb": bad_value},
                {"date": "2026-09-01", "index": "idx_good", "sourcetype": "st", "gb": 5.0},
            ]
        )
        collection = RawCollection(ingest=ingest)
        datasets, _ = build_datasets(collection)

        names = {str(d.key) for d in datasets}
        assert "idx_bad:st" not in names
        assert "idx_good:st" in names
        good = next(d for d in datasets if str(d.key) == "idx_good:st")
        assert good.ingest_gb_per_day == 5.0

    def test_malformed_gb_never_produces_nan_in_downstream_savings(self):
        import math

        from splunk_spend_auditor.scoring.classify_all import classify_all
        from splunk_spend_auditor.scoring.savings import compute_savings

        ingest = pd.DataFrame(
            [
                {"date": "2026-09-01", "index": "idx_nan", "sourcetype": "st", "gb": float("nan")},
                {"date": "2026-09-01", "index": "idx_inf", "sourcetype": "st", "gb": float("inf")},
                {"date": "2026-09-01", "index": "idx_normal", "sourcetype": "st", "gb": 5.0},
            ]
        )
        collection = RawCollection(ingest=ingest)
        datasets, summary = build_datasets(collection)
        datasets = classify_all(
            datasets, environment_partial_unknown_ratio=0.0, sources_available={}
        )
        savings = compute_savings(datasets, annual_spend=94_200)

        assert not math.isnan(savings.current_ingest_gb_day)
        assert not math.isinf(savings.current_ingest_gb_day)
        assert not math.isnan(savings.candidate_gb_day)
        assert savings.potential_annual_saving is not None
        assert not math.isnan(savings.potential_annual_saving)
        assert 0 <= savings.potential_annual_saving <= 94_200


class TestMalformedDateDoesNotCrashTheAudit:
    """Fase 4B (vulnerabilidad CONFIRMED, corregida): un valor `date` no
    parseable (`pd.to_datetime()` sin `errors="coerce"`) levantaba
    `DateParseError` sin manejar -- crash de todo el audit ante un solo
    valor de fecha corrupto en la respuesta de Splunk, confirmado con
    fuzzing adversarial. Ahora la fila con fecha inválida se excluye de
    las ventanas de tiempo (ingest) en vez de abortar todo el pipeline."""

    def test_malformed_date_in_ingest_does_not_crash(self):
        ingest = pd.DataFrame(
            [
                {"date": "not-a-date-at-all", "index": "idx_bad", "sourcetype": "st", "gb": 5.0},
                {"date": "2026-09-01", "index": "idx_good", "sourcetype": "st", "gb": 3.0},
            ]
        )
        collection = RawCollection(ingest=ingest)
        datasets, summary = build_datasets(collection)
        names = {str(d.key): d.ingest_gb_per_day for d in datasets}
        assert names.get("idx_bad:st") == 5.0
        assert names.get("idx_good:st") == 3.0

    def test_malformed_date_in_audit_searches_does_not_crash(self):
        ingest = pd.DataFrame(
            [{"date": "2026-09-01", "index": "idx_a", "sourcetype": "st", "gb": 5.0}]
        )
        audit_searches = pd.DataFrame(
            [
                {
                    "date": "definitely-not-a-timestamp",
                    "user": "alice",
                    "search_id": "s1",
                    "is_scheduled": "false",
                    "search_text": "index=idx_a sourcetype=st",
                }
            ]
        )
        collection = RawCollection(ingest=ingest, audit_searches=audit_searches)
        datasets, summary = build_datasets(collection)
        assert len(datasets) == 1
        # La búsqueda con fecha inválida no cuenta para ninguna ventana --
        # no crashea, y no se cuenta como evidencia de uso confirmada.
        assert datasets[0].interactive_searches_30d == 0
        assert datasets[0].interactive_searches_90d == 0
