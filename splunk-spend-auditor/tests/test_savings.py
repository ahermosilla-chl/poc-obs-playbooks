"""Tests del cálculo de ahorro potencial (docs/scoring.md sección 8)."""

from splunk_spend_auditor.models import Classification, Dataset, DatasetKey
from splunk_spend_auditor.scoring.savings import compute_savings


def _ds(gb: float, classification: Classification) -> Dataset:
    ds = Dataset(key=DatasetKey(index="i", sourcetype=str(id(object()))))
    ds.ingest_gb_per_day = gb
    ds.classification = classification
    return ds


def test_possible_waste_counts_fully_review_counts_at_half_weight():
    datasets = [
        _ds(100.0, Classification.NORMAL),
        _ds(20.0, Classification.POSSIBLE_WASTE),
        _ds(10.0, Classification.REVIEW),
    ]
    result = compute_savings(datasets)
    assert result.current_ingest_gb_day == 130.0
    assert result.possible_waste_gb_day == 20.0
    assert result.review_gb_day == 10.0
    # 20 (waste, peso 1.0) + 10*0.5 (review, peso 0.5) = 25.0
    assert result.candidate_gb_day == 25.0
    assert result.potential_reduction_pct == round(25.0 / 130.0, 4)


def test_protected_and_unknown_never_contribute_to_savings():
    datasets = [
        _ds(1000.0, Classification.PROTECTED),
        _ds(1000.0, Classification.UNKNOWN),
        _ds(10.0, Classification.POSSIBLE_WASTE),
    ]
    result = compute_savings(datasets)
    assert result.candidate_gb_day == 10.0


def test_annual_spend_input_produces_dollar_estimate():
    datasets = [_ds(100.0, Classification.NORMAL), _ds(20.0, Classification.POSSIBLE_WASTE)]
    result = compute_savings(datasets, annual_spend=120_000)
    expected_pct = 20.0 / 120.0
    assert result.potential_annual_saving == round(120_000 * expected_pct, 2)


def test_cost_per_gb_day_input_produces_dollar_estimate():
    datasets = [_ds(100.0, Classification.NORMAL), _ds(20.0, Classification.POSSIBLE_WASTE)]
    result = compute_savings(datasets, cost_per_gb_day=5.0)
    assert result.potential_annual_saving == round(20.0 * 5.0 * 365, 2)


def test_no_spend_input_leaves_dollar_estimate_as_none():
    """El reporte solo muestra % si no se dio ninguna base de costo -- nunca
    inventa un número en dólares."""
    datasets = [_ds(100.0, Classification.NORMAL)]
    result = compute_savings(datasets)
    assert result.potential_annual_saving is None


def test_empty_environment_does_not_divide_by_zero():
    result = compute_savings([])
    assert result.current_ingest_gb_day == 0.0
    assert result.potential_reduction_pct == 0.0
