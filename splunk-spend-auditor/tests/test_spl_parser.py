"""Tests del parser de SPL (src/splunk_spend_auditor/analysis/spl_parser.py).
Ver docs/scoring.md sección 3."""

from splunk_spend_auditor.analysis.spl_parser import parse_search
from splunk_spend_auditor.models import DatasetKey, ParserConfidence


def test_simple_index_and_sourcetype_is_high_confidence():
    result = parse_search("index=main sourcetype=nginx status=500")
    assert result.confidence == ParserConfidence.HIGH
    assert result.datasets == [DatasetKey(index="main", sourcetype="nginx")]


def test_grouped_or_list_style_a_index_equals_parenthesized_list():
    result = parse_search("index=(web OR proxy) sourcetype=access")
    assert result.confidence == ParserConfidence.HIGH
    assert set(result.datasets) == {
        DatasetKey(index="web", sourcetype="access"),
        DatasetKey(index="proxy", sourcetype="access"),
    }


def test_grouped_or_list_style_b_repeated_field_keyword():
    """Regresión: este caso producía un DatasetKey(index='index', ...)
    espurio antes del fix (ver historial de la sesión de Fase 2)."""
    result = parse_search("(index=web OR index=proxy) sourcetype=access")
    assert result.confidence == ParserConfidence.HIGH
    assert set(result.datasets) == {
        DatasetKey(index="web", sourcetype="access"),
        DatasetKey(index="proxy", sourcetype="access"),
    }
    assert DatasetKey(index="index", sourcetype="access") not in result.datasets


def test_macro_only_is_partial_not_high_and_not_unknown():
    result = parse_search("`partner_feed_search` | stats count by status")
    assert result.confidence == ParserConfidence.PARTIAL
    assert result.datasets == []


def test_eventtype_is_partial():
    result = parse_search("eventtype=web_errors | stats count")
    assert result.confidence == ParserConfidence.PARTIAL


def test_tstats_datamodel_is_partial():
    result = parse_search("| tstats count from datamodel=Authentication")
    assert result.confidence == ParserConfidence.PARTIAL


def test_subsearch_is_partial():
    result = parse_search(
        "index=main sourcetype=nginx [ search index=lookup_table | fields host ]"
    )
    # El index=/sourcetype= explícitos del nivel principal SÍ se resuelven
    # (HIGH), pero has_partial_evidence debe quedar en True por la
    # subsearch -- que podría estar tocando otro dataset que no resolvemos.
    assert result.confidence == ParserConfidence.HIGH
    assert result.has_partial_evidence is True


def test_empty_search_text_is_unknown():
    result = parse_search("")
    assert result.confidence == ParserConfidence.UNKNOWN
    assert result.datasets == []


def test_completely_unrecognized_search_is_unknown():
    result = parse_search("| history")
    assert result.confidence == ParserConfidence.UNKNOWN


def test_index_only_without_sourcetype_is_partial_not_high():
    """No podemos determinar el (index, sourcetype) COMPLETO solo con el
    index -- ver docs/scoring.md sección 3."""
    result = parse_search("index=main | stats count")
    assert result.confidence == ParserConfidence.PARTIAL
    assert result.datasets == []


def test_wildcard_only_values_are_not_treated_as_concrete_datasets():
    result = parse_search("index=* sourcetype=*")
    assert result.datasets == []
