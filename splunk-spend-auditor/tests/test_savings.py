"""Tests del cálculo de ahorro potencial (docs/scoring.md sección 8)."""

from splunk_spend_auditor.models import (
    Classification,
    Dataset,
    DatasetKey,
    ParserConfidence,
    SignalAvailability,
)
from splunk_spend_auditor.scoring.classify_all import classify_all
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


def _high_waste_candidate_environment() -> list[Dataset]:
    """Un entorno pequeño donde un dataset con alto ingest y cero uso
    calificaría para POSSIBLE_WASTE si toda la evidencia estuviera
    confirmada disponible -- usado para la propiedad de seguridad de Fase
    3B (D013/D014): perder visibilidad nunca puede aumentar el ahorro
    potencial estimado."""

    return [
        Dataset(
            key=DatasetKey(index="idx_a", sourcetype="st_a"),
            ingest_gb_per_day=1.0,
            interactive_searches_30d=15,
            interactive_searches_90d=15,
            parser_confidence=ParserConfidence.HIGH,
        ),
        Dataset(
            key=DatasetKey(index="idx_b", sourcetype="st_b"),
            ingest_gb_per_day=50.0,
            interactive_searches_90d=0,
            is_scheduled=False,
            has_alert_action=False,
            parser_confidence=ParserConfidence.HIGH,
        ),
    ]


def test_losing_visibility_never_increases_potential_savings():
    """Regla de seguridad crítica pedida explícitamente en Fase 3B:
    "missing visibility cannot increase waste classification / potential
    savings". Mismo entorno, mismos números de ingest -- la única
    diferencia es si audit_searches/saved_searches estaban disponibles.
    Perder esas fuentes SOLO puede mantener o reducir candidate_gb_day y
    potential_annual_saving, nunca aumentarlos."""

    full_visibility = classify_all(
        _high_waste_candidate_environment(),
        environment_partial_unknown_ratio=0.0,
        sources_available={
            "audit_searches": SignalAvailability.AVAILABLE,
            "saved_searches": SignalAvailability.AVAILABLE,
        },
    )
    degraded_visibility = classify_all(
        _high_waste_candidate_environment(),
        environment_partial_unknown_ratio=0.0,
        sources_available={
            "audit_searches": SignalAvailability.ERROR,
            "saved_searches": SignalAvailability.ERROR,
        },
    )

    savings_full = compute_savings(full_visibility, annual_spend=100_000)
    savings_degraded = compute_savings(degraded_visibility, annual_spend=100_000)

    idx_b_full = next(d for d in full_visibility if d.key.index == "idx_b")
    idx_b_degraded = next(d for d in degraded_visibility if d.key.index == "idx_b")
    assert idx_b_full.classification == Classification.POSSIBLE_WASTE
    assert idx_b_degraded.classification == Classification.REVIEW

    assert savings_degraded.candidate_gb_day <= savings_full.candidate_gb_day
    assert savings_degraded.potential_annual_saving <= savings_full.potential_annual_saving
    # No es solo "<=" por casualidad de redondeo -- en este caso concreto
    # debe ser estrictamente menor (REVIEW pesa 0.5 contra 1.0 de
    # POSSIBLE_WASTE, ver REVIEW_WEIGHT en scoring/rules.py).
    assert savings_degraded.candidate_gb_day < savings_full.candidate_gb_day


def test_low_volume_datasets_are_not_rounded_away_to_zero():
    """Bug real (Fase 3C): compute_savings redondeaba los totales de GB/día
    a 2 decimales -- un entorno de bajo volumen real (p.ej. varios
    datasets por debajo de 1 MB/día, confirmado contra el laboratorio
    Splunk real) terminaba mostrando "0 GB/day" en el CLI y el reporte
    aunque hubiera volumen real y candidatos reales. Con 8 decimales, la
    resolución mínima es sub-KB, suficiente para no perder esta señal."""

    datasets = [
        _ds(0.0004, Classification.POSSIBLE_WASTE),  # ~420 KB/día
        _ds(0.0001, Classification.NORMAL),  # ~100 KB/día
    ]
    result = compute_savings(datasets, annual_spend=94_200)
    assert result.current_ingest_gb_day > 0
    assert result.candidate_gb_day > 0
    assert result.potential_annual_saving > 0
