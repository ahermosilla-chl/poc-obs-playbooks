"""Tests del generador de reportes: que el contexto y el render no
revienten, que free vs. pro recorten lo que deben, y que nunca se filtre
lenguaje de 'guaranteed saving' (docs/report-design.md)."""

from pathlib import Path

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import load_from_directory
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
