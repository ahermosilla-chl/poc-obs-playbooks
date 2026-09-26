"""Tests de las reglas de clasificación (docs/scoring.md sección 5) y de
scoring (sección 4). Estos tests construyen Dataset directamente -- sin
pasar por CSV -- para aislar la lógica de negocio de la de collectors."""

import pytest

from splunk_spend_auditor.models import Classification, Dataset, DatasetKey, ParserConfidence
from splunk_spend_auditor.scoring.rules import (
    UNKNOWN_ENVIRONMENT_RATIO_THRESHOLD,
    classify,
    data_value_score,
    matches_default_protected_pattern,
)

HIGH_INGEST_THRESHOLD = 20.0  # umbral fijo para tests, no calculado por percentil
LOW_PARTIAL_RATIO = 0.05  # entorno con buena cobertura
HIGH_PARTIAL_RATIO = 0.8  # entorno con mala cobertura


def _ds(**kwargs) -> Dataset:
    defaults = dict(key=DatasetKey(index="idx", sourcetype="st"))
    defaults.update(kwargs)
    return Dataset(**defaults)


class TestProtectedPatterns:
    @pytest.mark.parametrize(
        "index,sourcetype",
        [
            ("compliance", "pci_audit_log"),
            ("security", "ids_alerts"),
            ("app", "auth_events"),  # "auth" es substring de "auth_events"
            ("firewall", "traffic"),
        ],
    )
    def test_matches_protected_pattern(self, index, sourcetype):
        ds = _ds(key=DatasetKey(index=index, sourcetype=sourcetype))
        assert matches_default_protected_pattern(ds) is True

    @pytest.mark.parametrize(
        "index,sourcetype",
        [
            ("cdn", "edge_access"),
            ("app", "login_events"),
            ("sales", "pos_transactions"),
        ],
    )
    def test_does_not_match_protected_pattern(self, index, sourcetype):
        ds = _ds(key=DatasetKey(index=index, sourcetype=sourcetype))
        assert matches_default_protected_pattern(ds) is False

    def test_protected_pattern_takes_precedence_over_everything_else(self):
        """Incluso un dataset con evidencia HIGH y mucho uso queda PROTECTED
        si matchea el patrón -- docs/scoring.md sección 5, regla 1 es la
        primera que se evalúa."""
        ds = _ds(
            key=DatasetKey(index="compliance", sourcetype="pci_audit_log"),
            ingest_gb_per_day=100.0,
            interactive_searches_30d=50,
            parser_confidence=ParserConfidence.HIGH,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.PROTECTED

    def test_manual_override_also_produces_protected(self):
        ds = _ds(is_protected=True, protection_reason="manual override test")
        classification, explanation = classify(
            ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO
        )
        assert classification == Classification.PROTECTED
        assert "manual override test" in explanation


class TestUnknownIsEnvironmentLevel:
    """DECISIONS.md D009: UNKNOWN se decide por la cobertura del ENTORNO, no
    por si este dataset específico tiene evidencia HIGH."""

    def test_zero_evidence_dataset_in_well_covered_environment_is_not_unknown(self):
        """Este es el caso más importante del producto: un dataset caro que
        nadie busca nunca, en un entorno donde el parser SÍ ve bien la
        mayoría de las búsquedas. NO debe quedar UNKNOWN -- debe llegar a
        POSSIBLE_WASTE (o REVIEW/NORMAL según ingest)."""
        ds = _ds(ingest_gb_per_day=50.0, parser_confidence=ParserConfidence.UNKNOWN)
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification != Classification.UNKNOWN

    def test_zero_evidence_dataset_in_poorly_covered_environment_is_unknown(self):
        """El mismo dataset, en un entorno donde la mayoría de las búsquedas
        no se pudieron resolver (muchas macros/eventtypes), SÍ debe quedar
        UNKNOWN -- no podemos confiar en el silencio."""
        ds = _ds(ingest_gb_per_day=50.0, parser_confidence=ParserConfidence.UNKNOWN)
        classification, explanation = classify(
            ds, HIGH_INGEST_THRESHOLD, HIGH_PARTIAL_RATIO
        )
        assert classification == Classification.UNKNOWN
        assert "partial/unknown" in explanation

    def test_threshold_boundary_is_exclusive(self):
        """Justo en el umbral, NO se activa UNKNOWN (la comparación es '>',
        no '>=') -- ver rules.py."""
        ds = _ds(ingest_gb_per_day=50.0, parser_confidence=ParserConfidence.UNKNOWN)
        classification, _ = classify(
            ds, HIGH_INGEST_THRESHOLD, UNKNOWN_ENVIRONMENT_RATIO_THRESHOLD
        )
        assert classification != Classification.UNKNOWN

    def test_dataset_with_own_high_evidence_is_never_unknown_regardless_of_environment(self):
        ds = _ds(
            ingest_gb_per_day=5.0,
            parser_confidence=ParserConfidence.HIGH,
            interactive_searches_30d=1,
            interactive_searches_90d=1,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, HIGH_PARTIAL_RATIO)
        assert classification != Classification.UNKNOWN


class TestHighValue:
    def test_scheduled_search_is_high_value(self):
        ds = _ds(is_scheduled=True, parser_confidence=ParserConfidence.HIGH)
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.HIGH_VALUE

    def test_alert_action_is_high_value(self):
        ds = _ds(has_alert_action=True, parser_confidence=ParserConfidence.HIGH)
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.HIGH_VALUE

    def test_dashboard_usage_is_high_value_even_without_any_search_evidence(self):
        """sales:pos_transactions en sample-data/case_mixed: nunca pasa por
        el parser de SPL (viene de un CSV manual), pero SÍ debe ser
        HIGH_VALUE."""
        ds = _ds(used_in_dashboards=True, parser_confidence=ParserConfidence.UNKNOWN)
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.HIGH_VALUE

    def test_ten_or_more_interactive_searches_is_high_value(self):
        ds = _ds(
            interactive_searches_30d=10,
            parser_confidence=ParserConfidence.HIGH,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.HIGH_VALUE

    def test_nine_interactive_searches_is_not_enough_alone(self):
        ds = _ds(
            interactive_searches_30d=9,
            interactive_searches_90d=9,
            ingest_gb_per_day=1.0,
            parser_confidence=ParserConfidence.HIGH,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification != Classification.HIGH_VALUE


class TestPossibleWaste:
    def test_high_ingest_and_zero_usage_is_possible_waste(self):
        ds = _ds(
            ingest_gb_per_day=50.0,
            interactive_searches_90d=0,
            parser_confidence=ParserConfidence.UNKNOWN,
        )
        classification, explanation = classify(
            ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO
        )
        assert classification == Classification.POSSIBLE_WASTE
        assert "50.0 GB/day" in explanation

    def test_never_uses_delete_language(self):
        """Requisito explícito del brief: nunca 'DELETE THIS DATA'."""
        ds = _ds(ingest_gb_per_day=50.0, parser_confidence=ParserConfidence.UNKNOWN)
        _, explanation = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert "delete" not in explanation.lower()

    def test_low_ingest_with_zero_usage_is_review_not_waste(self):
        """legacy:app_2019: datos antiguos pero de bajo volumen -> REVIEW,
        no POSSIBLE_WASTE (no alcanza el umbral de alto ingest)."""
        ds = _ds(
            ingest_gb_per_day=0.3,
            interactive_searches_90d=0,
            parser_confidence=ParserConfidence.UNKNOWN,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.REVIEW

    def test_high_ingest_but_scheduled_is_not_possible_waste(self):
        ds = _ds(
            ingest_gb_per_day=50.0,
            is_scheduled=True,
            parser_confidence=ParserConfidence.HIGH,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.HIGH_VALUE


class TestNormal:
    def test_typical_low_ingest_with_some_usage_is_normal(self):
        ds = _ds(
            ingest_gb_per_day=5.0,
            interactive_searches_30d=5,
            interactive_searches_90d=5,
            parser_confidence=ParserConfidence.HIGH,
        )
        classification, _ = classify(ds, HIGH_INGEST_THRESHOLD, LOW_PARTIAL_RATIO)
        assert classification == Classification.NORMAL


class TestDataValueScore:
    def test_score_is_bounded_0_to_100(self):
        ds = _ds(
            interactive_searches_30d=1000,
            is_scheduled=True,
            has_alert_action=True,
            used_in_dashboards=True,
            unique_users_30d=100,
        )
        assert data_value_score(ds) == 100

    def test_zero_signals_is_zero_score(self):
        ds = _ds()
        assert data_value_score(ds) == 0

    def test_score_is_deterministic_pure_function(self):
        ds = _ds(interactive_searches_30d=5, unique_users_30d=2)
        assert data_value_score(ds) == data_value_score(ds)
        assert data_value_score(ds) == 5 + 5  # 5 searches + 5 (1-2 users)
