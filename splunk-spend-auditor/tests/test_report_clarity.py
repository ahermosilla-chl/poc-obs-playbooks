"""Fase 5B.2: transparencia aritmética y terminología del reporte. No cambia
el análisis: solo cómo se presenta."""

from __future__ import annotations

import pytest

from splunk_spend_auditor.cli import _run_pipeline
from splunk_spend_auditor.demo import DEMO_SOURCE_LABEL, build_demo_collection
from splunk_spend_auditor.models import Classification, Dataset, DatasetKey
from splunk_spend_auditor.reports.render import build_report_context, render_report
from splunk_spend_auditor.scoring.rules import data_value_score


def _render(tmp_path, annual_spend=None):
    datasets, summary, savings = _run_pipeline(build_demo_collection(), 90, annual_spend, None)
    context = build_report_context(datasets, summary, savings, source_label=DEMO_SOURCE_LABEL)
    written = render_report(context, tmp_path, ["html", "md"])
    return datasets, savings, context, {k: v.read_text(encoding="utf-8") for k, v in written.items()}


def test_demo_values_are_unchanged(tmp_path):
    _, savings, context, _ = _render(tmp_path)
    assert savings.current_ingest_gb_day == pytest.approx(267.2, abs=1e-3)
    assert savings.possible_waste_gb_day == pytest.approx(99.0, abs=1e-3)
    assert savings.review_gb_day == pytest.approx(25.2, abs=1e-3)
    assert savings.candidate_gb_day == pytest.approx(111.6, abs=1e-3)
    assert round(savings.potential_reduction_pct * 100, 1) == 41.8
    assert context["savings_display"]["review_weighted_gb_day"] == "12.6 GB"


def test_review_raw_and_weighted_are_shown_separately_with_correct_arithmetic(tmp_path):
    _, savings, _, out = _render(tmp_path)
    for text in out.values():
        assert "raw volume" in text and "25.2 GB" in text
        assert "Weighted review contribution" in text and "12.6 GB" in text
        assert "Weighted optimization estimate" in text and "111.6 GB" in text
        # El viejo rótulo engañoso (25.2 etiquetado como ponderado) no vuelve.
        assert "Review candidates (weighted" not in text
    assert 99.0 + 25.2 * 0.5 == pytest.approx(savings.candidate_gb_day, abs=1e-3)


def test_executive_summary_distinguishes_direct_candidates_from_review(tmp_path):
    _, _, _, out = _render(tmp_path)
    md = " ".join(out["md"].split("## Current Environment")[0].split())
    assert "99.0 GB/day** of direct optimization candidates (possible waste)" in md
    assert "25.2 GB/day** of datasets requiring manual review" in md
    assert "conservative weighting model" in md
    assert "111.6 GB/day** (41.8% of observed ingest)" in md
    assert "flagged as optimization candidates" not in md


def test_no_monetary_claims_without_spend(tmp_path):
    _, _, context, out = _render(tmp_path)
    assert context["has_financial_estimate"] is False
    for text in out.values():
        assert "Potential Optimization" in text
        assert "Potential Savings" not in text
        assert "potential saving" not in text.lower()
        assert "$" not in text


def test_financial_heading_preserved_when_spend_is_provided(tmp_path):
    _, savings, _, out = _render(tmp_path, annual_spend=94_200)
    assert savings.potential_annual_saving is not None
    for text in out.values():
        assert "Potential Savings" in text
        assert "potential annual saving" in text.lower()


def test_classifications_are_unchanged(tmp_path):
    datasets, _, _, _ = _render(tmp_path)
    got = {str(d.key): d.classification for d in datasets}
    assert got["k8s:kube_container_logs"] == Classification.POSSIBLE_WASTE
    assert got["app:debug_verbose"] == Classification.POSSIBLE_WASTE
    assert got["infra:windows_perfmon"] == Classification.REVIEW
    assert got["legacy:app_2019"] == Classification.REVIEW
    assert got["security:ids_alerts"] == Classification.PROTECTED
    assert sum(c == Classification.HIGH_VALUE for c in got.values()) == 5


def test_data_value_score_explanation_matches_implementation(tmp_path):
    _, _, _, out = _render(tmp_path)
    for text in out.values():
        assert "Data Value Score" in text
        assert "financial measure" in text
        assert "capped at 100" in text
    # La explicación cita exactamente los pesos reales del código.
    ds = Dataset(key=DatasetKey("i", "s"), interactive_searches_30d=100, is_scheduled=True,
                 has_alert_action=True, used_in_dashboards=True, unique_users_30d=5)
    assert data_value_score(ds) == 100  # tope real
    only = lambda **kw: data_value_score(Dataset(key=DatasetKey("i", "s"), **kw))
    assert only(interactive_searches_30d=100) == 30
    assert only(is_scheduled=True) == 25
    assert only(has_alert_action=True) == 20
    assert only(used_in_dashboards=True) == 15
    assert only(unique_users_30d=2) == 5 and only(unique_users_30d=3) == 10


def test_excluded_review_volume_is_disclosed_not_hidden():
    from splunk_spend_auditor.models import EnvironmentSummary
    from splunk_spend_auditor.scoring.savings import compute_savings

    a = Dataset(key=DatasetKey("a", "s"), ingest_gb_per_day=10.0, classification=Classification.REVIEW)
    b = Dataset(key=DatasetKey("b", "s"), ingest_gb_per_day=4.0, classification=Classification.REVIEW,
                excluded_from_savings_estimate=True)
    for d in (a, b):
        d.explanation, d.data_value_score = "x", 0
    savings = compute_savings([a, b])
    ctx = build_report_context([a, b], EnvironmentSummary(), savings)
    assert ctx["has_review_excluded"] is True
    assert ctx["savings_display"]["review_gb_day"] == "14.0 GB"
    assert ctx["savings_display"]["review_weighted_gb_day"] == "5.0 GB"
    assert ctx["savings_display"]["review_excluded_gb_day"] == "4.0 GB"
