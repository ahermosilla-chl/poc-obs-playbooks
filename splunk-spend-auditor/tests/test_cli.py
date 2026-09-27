"""Tests de la CLI (Typer). Fase 3C.2 (D019): quickscan mezclaba
POSSIBLE_WASTE y REVIEW en una sola cifra sin peso (distinta del full
audit, que sí pesa REVIEW) y siempre sugería `audit --from-csv ...` como
próximo paso, incluso en una corrida REST real -- ambos bugs reales
descubiertos al revisar los artefactos de Fase 3C.1/3C.2."""

from __future__ import annotations

import pandas as pd
import pytest
from typer.testing import CliRunner

from splunk_spend_auditor.cli import app
from splunk_spend_auditor.collector.csv_collector import RawCollection
from splunk_spend_auditor.models import SignalAvailability

runner = CliRunner()


def _mixed_waste_and_review_collection() -> RawCollection:
    """Un dataset POSSIBLE_WASTE (alto ingest, cero uso confirmado) y uno
    REVIEW (bajo ingest, cero uso) -- exactamente el escenario donde
    mezclarlos sin peso produce un número distinto al del full audit."""

    ingest = pd.DataFrame(
        [
            {"date": "2026-09-01", "index": "idx_waste", "sourcetype": "st_waste", "gb": 50.0},
            {"date": "2026-09-01", "index": "idx_review", "sourcetype": "st_review", "gb": 0.3},
            {"date": "2026-09-01", "index": "idx_normal", "sourcetype": "st_normal", "gb": 5.0},
        ]
    )
    audit_searches = pd.DataFrame(
        [
            {
                "date": "2026-09-01",
                "search_id": "s1",
                "search_text": "index=idx_normal sourcetype=st_normal",
                "user": "alice",
                "is_scheduled": "false",
            }
        ]
    )
    return RawCollection(
        ingest=ingest,
        audit_searches=audit_searches,
        saved_searches=pd.DataFrame(columns=["date", "savedsearch_name", "search_text", "actions", "cron_schedule"]),
        sources_available={
            "ingest": SignalAvailability.AVAILABLE,
            "audit_searches": SignalAvailability.AVAILABLE,
            "saved_searches": SignalAvailability.AVAILABLE,
            "last_seen": SignalAvailability.UNAVAILABLE,
            "dashboards_used": SignalAvailability.UNAVAILABLE,
            "protected_overrides": SignalAvailability.NOT_APPLICABLE,
        },
    )


class TestQuickscanDoesNotMixWasteAndReview:
    def test_possible_waste_and_review_are_reported_separately(self, tmp_path, monkeypatch):
        collection = _mixed_waste_and_review_collection()
        monkeypatch.setattr(
            "splunk_spend_auditor.cli.load_from_directory", lambda _dir: collection
        )
        result = runner.invoke(app, ["quickscan", "--from-csv", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "Possible waste:" in result.output
        assert "Review (manual validation recommended):" in result.output
        # Nunca la etiqueta vieja que mezclaba ambas categorías bajo un
        # solo total sin peso.
        assert "Review candidates (possible waste)" not in result.output

    def test_optimization_candidate_volume_matches_full_audit_calculation(self, tmp_path, monkeypatch):
        """La única cifra "comparable a full audit" en quickscan debe ser
        EXACTAMENTE savings.candidate_gb_day/potential_reduction_pct --
        no una suma paralela sin peso de REVIEW."""

        collection = _mixed_waste_and_review_collection()
        monkeypatch.setattr(
            "splunk_spend_auditor.cli.load_from_directory", lambda _dir: collection
        )

        from splunk_spend_auditor.analysis.build_datasets import build_datasets
        from splunk_spend_auditor.formatting import format_gb_per_day
        from splunk_spend_auditor.scoring.classify_all import classify_all
        from splunk_spend_auditor.scoring.savings import compute_savings

        datasets, summary = build_datasets(collection)
        datasets = classify_all(
            datasets,
            environment_partial_unknown_ratio=summary.partial_or_unknown_ratio,
            sources_available=summary.sources_available,
        )
        expected_savings = compute_savings(datasets)

        result = runner.invoke(app, ["quickscan", "--from-csv", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert format_gb_per_day(expected_savings.candidate_gb_day) in result.output
        pct_text = f"{expected_savings.potential_reduction_pct * 100:.1f}%"
        assert pct_text in result.output


class TestQuickscanCTAReflectsActualSource:
    def test_csv_mode_cta_suggests_from_csv(self, tmp_path, monkeypatch):
        collection = _mixed_waste_and_review_collection()
        monkeypatch.setattr(
            "splunk_spend_auditor.cli.load_from_directory", lambda _dir: collection
        )
        result = runner.invoke(app, ["quickscan", "--from-csv", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "--from-csv" in result.output
        assert "--host" not in result.output.split("Generate Full Spend Audit")[-1]

    def test_rest_mode_cta_never_suggests_from_csv(self, monkeypatch):
        """Bug real (Fase 3C.2): una corrida REST terminaba recomendando
        `audit --from-csv ...` como si los datos vinieran de un CSV."""

        collection = _mixed_waste_and_review_collection()
        monkeypatch.setattr(
            "splunk_spend_auditor.cli.collect_rest", lambda config, queries_dir: collection
        )
        monkeypatch.setenv("SPLUNK_TOKEN", "fake-token-for-test")
        result = runner.invoke(
            app, ["quickscan", "--host", "lab.example.com", "--port", "8089"]
        )
        assert result.exit_code == 0, result.output
        assert "--from-csv" not in result.output
        assert "--host lab.example.com --port 8089" in result.output
