"""Test de integración end-to-end contra el escenario sintético completo
(sample-data/case_mixed/), generado por sample-data/generate_sample_data.py
con semilla fija -- determinista. Este es el test que valida los 10 casos
pedidos en el brief de una sola vez. Ver sample-data/README.md para el
mapeo completo y las notas de diseño (en particular, el Caso 9)."""

from pathlib import Path

import pytest

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import load_from_directory
from splunk_spend_auditor.models import Classification
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.savings import compute_savings

CASE_MIXED_DIR = Path(__file__).parent.parent / "sample-data" / "case_mixed"

# (index:sourcetype) -> categoría esperada, ver sample-data/README.md
EXPECTED_CLASSIFICATIONS = {
    "cdn:edge_access": Classification.HIGH_VALUE,
    "app:verbose_debug": Classification.POSSIBLE_WASTE,
    "app:login_events": Classification.HIGH_VALUE,
    "network:snmp_traps": Classification.HIGH_VALUE,
    "sales:pos_transactions": Classification.HIGH_VALUE,
    "dr:heartbeat_check": Classification.PROTECTED,
    "windows:eventlog": Classification.HIGH_VALUE,
    "windows:eventlog_raw": Classification.POSSIBLE_WASTE,
    "legacy:app_2019": Classification.REVIEW,
    "integration:partner_feed": Classification.REVIEW,
    "compliance:pci_audit_log": Classification.PROTECTED,
    "infra:syslog": Classification.NORMAL,
}


@pytest.fixture(scope="module")
def classified_datasets():
    collection = load_from_directory(CASE_MIXED_DIR)
    datasets, summary = build_datasets(collection)
    datasets = classify_all(
        datasets, environment_partial_unknown_ratio=summary.partial_or_unknown_ratio
    )
    return {str(d.key): d for d in datasets}, summary


def test_all_twelve_datasets_are_present(classified_datasets):
    by_key, _ = classified_datasets
    assert set(by_key.keys()) == set(EXPECTED_CLASSIFICATIONS.keys())


@pytest.mark.parametrize("key,expected", EXPECTED_CLASSIFICATIONS.items())
def test_expected_classification(classified_datasets, key, expected):
    by_key, _ = classified_datasets
    dataset = by_key[key]
    assert dataset.classification == expected, (
        f"{key}: esperado {expected}, obtenido {dataset.classification} "
        f"-- {dataset.explanation}"
    )


def test_every_classified_dataset_has_a_non_empty_explanation(classified_datasets):
    by_key, _ = classified_datasets
    for key, dataset in by_key.items():
        assert dataset.explanation, f"{key} no tiene explicación"


def test_environment_search_coverage_is_good_in_this_scenario(classified_datasets):
    """El escenario case_mixed representa un entorno bien cubierto -- por
    eso los datasets sin evidencia HIGH propia no quedan UNKNOWN (ver
    DECISIONS.md D009)."""
    _, summary = classified_datasets
    assert summary.partial_or_unknown_ratio < 0.5


def test_scheduler_searches_are_excluded_from_interactive_counts(classified_datasets):
    """audit_searches.csv incluye una fila scheduler_edge_access_daily_* que
    NO debe contarse como búsqueda interactiva de cdn:edge_access."""
    by_key, _ = classified_datasets
    cdn = by_key["cdn:edge_access"]
    # 15 búsquedas interactivas reales (una cada 2 días en 30 días) -- la
    # fila scheduler_* adicional NO debe sumar una 16ª.
    assert cdn.interactive_searches_30d == 15


def test_savings_calculation_runs_end_to_end(classified_datasets):
    by_key, _ = classified_datasets
    savings = compute_savings(list(by_key.values()), annual_spend=94_200)
    assert savings.current_ingest_gb_day > 0
    assert savings.candidate_gb_day > 0
    assert 0 < savings.potential_reduction_pct < 1
    assert savings.potential_annual_saving is not None
    assert savings.potential_annual_saving < 94_200  # nunca más que el spend total
