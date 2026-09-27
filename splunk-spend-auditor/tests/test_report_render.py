"""Tests del generador de reportes: que el contexto y el render no
revienten, que free vs. pro recorten lo que deben, y que nunca se filtre
lenguaje de 'guaranteed saving' (docs/report-design.md)."""

from pathlib import Path

import pytest

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import load_from_directory
from splunk_spend_auditor.formatting import format_gb_per_day
from splunk_spend_auditor.models import Classification, Dataset, DatasetKey
from splunk_spend_auditor.reports.render import build_report_context, render_report
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.savings import compute_savings

CASE_MIXED_DIR = Path(__file__).parent.parent / "sample-data" / "case_mixed"


def _classified():
    collection = load_from_directory(CASE_MIXED_DIR)
    datasets, summary = build_datasets(collection)
    datasets = classify_all(
        datasets, environment_partial_unknown_ratio=summary.partial_or_unknown_ratio
    )
    savings = compute_savings(datasets, annual_spend=94_200)
    return datasets, summary, savings


def test_free_tier_truncates_to_top_5_ingestion_and_top_3_candidates():
    datasets, summary, savings = _classified()
    context = build_report_context(datasets, summary, savings, tier="free")
    assert len(context["ingestion_breakdown"]) <= 5
    assert len(context["top_candidates"]) <= 3
    assert context["usage_analysis"] == []
    assert context["all_datasets_detail"] == []


def test_pro_tier_includes_full_detail():
    datasets, summary, savings = _classified()
    context = build_report_context(datasets, summary, savings, tier="pro")
    assert len(context["all_datasets_detail"]) == len(datasets)
    assert len(context["usage_analysis"]) == len(datasets)


def test_never_uses_guaranteed_saving_language():
    datasets, summary, savings = _classified()
    context = build_report_context(datasets, summary, savings, tier="pro")
    written = None
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        written = render_report(context, tmp, ["html", "md"])
        for path in written.values():
            text = path.read_text().lower()
            assert "guaranteed saving" not in text
            assert "delete this data" not in text
            assert "potential saving" in text


def test_redact_names_replaces_dataset_names(tmp_path):
    datasets, summary, savings = _classified()
    context = build_report_context(
        datasets, summary, savings, tier="pro", redact_names=True
    )
    names = [row["name"] for row in context["ingestion_breakdown"]]
    assert all(name.startswith("dataset_") for name in names)


def test_render_report_writes_requested_formats_only(tmp_path):
    datasets, summary, savings = _classified()
    context = build_report_context(datasets, summary, savings, tier="pro")
    written = render_report(context, tmp_path, ["md"])
    assert "md" in written
    assert "html" not in written
    assert written["md"].exists()
    assert not (tmp_path / "report.html").exists()


class TestFormatGbPerDay:
    """Fase 3C: bug real -- un valor pequeño (p.ej. 0.0004 GB/día, ~420 KB)
    redondeaba a "0.0 GB/day" en todo el reporte y la terminal, se leía
    como "nada" en vez de "muy poco". format_gb_per_day auto-escala a la
    unidad más legible."""

    def test_zero_is_zero_gb(self):
        assert format_gb_per_day(0) == "0 GB"

    def test_sub_kb_value_shown_in_kb_not_rounded_to_zero(self):
        # 920 bytes/día, el caso real encontrado contra el laboratorio.
        value = 920 / (1024**3)
        assert format_gb_per_day(value) != "0.0 GB"
        assert "KB" in format_gb_per_day(value)

    def test_sub_gb_value_shown_in_mb(self):
        assert format_gb_per_day(0.5) == "512.0 MB"

    def test_gb_scale_value_shown_in_gb(self):
        assert format_gb_per_day(45.2) == "45.2 GB"

    def test_negative_treated_as_zero(self):
        assert format_gb_per_day(-1) == "0 GB"


class TestReportOmitsInternalSplunkIndexes:
    """Fase 3C ("HTML quality review"): índices internos de Splunk
    (_internal, _audit, ...) nunca aparecen en license_usage.log -- si
    aparecen como "dataset" es solo ruido de saved searches de sistema
    residuales (D010), nunca datos reales del cliente. No deben aparecer
    en las tablas del reporte ni contarse en los totales."""

    def _dataset(self, index: str, classification: Classification) -> Dataset:
        ds = Dataset(key=DatasetKey(index=index, sourcetype="st"))
        ds.ingest_gb_per_day = 0.0
        ds.classification = classification
        ds.explanation = "test"
        ds.data_value_score = 0
        return ds

    def test_internal_index_datasets_excluded_from_report_context(self):
        datasets, summary, savings = _classified()
        datasets = list(datasets) + [
            self._dataset("_internal", Classification.HIGH_VALUE),
            self._dataset("_audit", Classification.PROTECTED),
        ]
        context = build_report_context(datasets, summary, savings, tier="pro")

        all_names = [row["name"] for row in context["all_datasets_detail"]]
        assert not any(name.startswith("_internal") or name.startswith("_audit") for name in all_names)
        assert context["total_datasets"] == len(datasets) - 2


class TestProtectedHighValueSection:
    def test_recognized_datasets_includes_protected_and_high_value_only(self):
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="pro")
        classifications = {row["classification"] for row in context["recognized_datasets"]}
        assert classifications <= {"PROTECTED", "HIGH_VALUE"}
        assert context["protected_count"] >= 1
        assert context["high_value_count"] >= 1


class TestCountsSummaryLine:
    @pytest.mark.parametrize("count,expected_fragment", [(0, "0 reviews"), (1, "1 review"), (2, "2 reviews")])
    def test_review_count_is_pluralized_correctly(self, count, expected_fragment):
        datasets, summary, savings = _classified()
        # Fuerza un conteo conocido de REVIEW sin depender del dataset exacto.
        for d in datasets:
            if d.classification == Classification.REVIEW:
                d.classification = Classification.NORMAL
        for d in datasets[:count]:
            d.classification = Classification.REVIEW
        context = build_report_context(datasets, summary, savings, tier="pro")
        assert expected_fragment in context["counts_summary_line"]
