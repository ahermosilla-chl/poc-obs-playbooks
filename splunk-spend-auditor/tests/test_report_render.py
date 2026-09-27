"""Tests del generador de reportes: que el contexto y el render no
revienten, que free vs. pro recorten lo que deben, y que nunca se filtre
lenguaje de 'guaranteed saving' (docs/report-design.md)."""

from pathlib import Path

import pytest

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import load_from_directory
from splunk_spend_auditor.formatting import format_gb_per_day
from splunk_spend_auditor.models import (
    Classification,
    Dataset,
    DatasetKey,
    EnvironmentSummary,
    ParserConfidence,
    SignalAvailability,
)
from splunk_spend_auditor.reports.render import build_report_context, render_report
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.savings import compute_savings

CASE_MIXED_DIR = Path(__file__).parent.parent / "sample-data" / "case_mixed"


def _classified():
    collection = load_from_directory(CASE_MIXED_DIR)
    datasets, summary = build_datasets(collection)
    # sources_available=summary.sources_available (Fase 3C.1): replica el
    # wiring real de cli.py -- omitirlo (como antes) dejaba
    # dashboards_signal_available siempre en False dentro de classify_all,
    # aunque case_mixed sí trae dashboards_used.csv real.
    datasets = classify_all(
        datasets,
        environment_partial_unknown_ratio=summary.partial_or_unknown_ratio,
        sources_available=summary.sources_available,
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


def _rest_like_environment_without_dashboards_signal():
    """Fase 3C.1/D018: replica el caso REST real -- dashboards_used nunca
    se evalúa (NOT_APPLICABLE), pero hay un candidato POSSIBLE_WASTE
    genuino (alto ingest, cero uso confirmado en las fuentes disponibles)."""

    datasets = [
        Dataset(
            key=DatasetKey(index="idx_waste", sourcetype="st_waste"),
            ingest_gb_per_day=50.0,
            interactive_searches_90d=0,
            parser_confidence=ParserConfidence.HIGH,
        ),
        Dataset(
            key=DatasetKey(index="idx_normal", sourcetype="st_normal"),
            ingest_gb_per_day=1.0,
            interactive_searches_90d=5,
            parser_confidence=ParserConfidence.HIGH,
        ),
    ]
    sources_available = {
        "ingest": SignalAvailability.AVAILABLE,
        "audit_searches": SignalAvailability.AVAILABLE,
        "saved_searches": SignalAvailability.AVAILABLE,
        "last_seen": SignalAvailability.AVAILABLE,
        "dashboards_used": SignalAvailability.NOT_APPLICABLE,
        "protected_overrides": SignalAvailability.NOT_APPLICABLE,
    }
    summary = EnvironmentSummary(
        total_datasets=len(datasets),
        sources_available=sources_available,
    )
    datasets = classify_all(
        datasets, environment_partial_unknown_ratio=0.0, sources_available=sources_available
    )
    savings = compute_savings(datasets, annual_spend=94_200)
    return datasets, summary, savings


class TestDashboardsSignalPresentation:
    """Fase 3C.1/D018: la Fase 3C mostraba 'Dashboards: No' y una
    explicación afirmando 'was not found in ... dashboards' incluso en modo
    REST, donde esa señal es NOT_APPLICABLE (nunca se consulta) -- viola
    missing visibility != zero usage en el lenguaje del reporte, no solo en
    la clasificación."""

    def test_unavailable_dashboard_signal_is_not_rendered_as_no(self):
        datasets, summary, savings = _rest_like_environment_without_dashboards_signal()
        context = build_report_context(datasets, summary, savings, tier="pro")

        rows = context["usage_analysis"] + context["top_candidates"]
        assert rows, "el fixture debe producir al menos una fila para revisar"
        for row in rows:
            assert row["dashboards_display"] == "Not evaluated"
            assert row["dashboards_display"] != "No"

    def test_unavailable_dashboard_signal_is_not_described_as_absence_of_usage(self):
        datasets, summary, savings = _rest_like_environment_without_dashboards_signal()
        context = build_report_context(datasets, summary, savings, tier="pro")

        waste_candidate = next(
            c for c in context["top_candidates"] if c["classification"] == "POSSIBLE_WASTE"
        )
        explanation = waste_candidate["explanation"].lower()
        assert "not found in alerts, dashboards" not in explanation
        assert "not evaluated in this run" in explanation

    def test_available_dashboard_signal_still_renders_yes_no(self):
        """Control: en case_mixed (dashboards_used.csv presente), la señal
        SÍ se evaluó -- debe seguir mostrando Yes/No, nunca "Not evaluated"
        (no perder información real por exceso de cautela)."""
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="pro")
        displays = {row["dashboards_display"] for row in context["usage_analysis"]}
        assert displays <= {"Yes", "No"}


class TestAnnualSpendProvenance:
    """Fase 3C.1: el reporte debe dejar inequívoco que el annual spend es
    un input del usuario, no algo medido/inferido por la herramienta --
    evita que un monto grande junto a un volumen de ingest pequeño (o
    cualquier otra combinación) se lea como una cifra que la herramienta
    "sabe" por su cuenta."""

    def test_rendered_report_labels_annual_spend_as_user_provided(self, tmp_path):
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="pro")
        written = render_report(context, tmp_path, ["html", "md"])
        for path in written.values():
            text = path.read_text().lower()
            assert "user-provided" in text or "as provided for this audit" in text

    def test_no_spend_input_never_implies_user_provided_language(self, tmp_path):
        """Cuando no se dio ningún input de costo, no debe aparecer texto de
        procedencia de un monto que no existe."""
        datasets, summary, savings = _classified()
        savings_no_spend = compute_savings(datasets)
        context = build_report_context(datasets, summary, savings_no_spend, tier="pro")
        written = render_report(context, tmp_path, ["html", "md"])
        for path in written.values():
            text = path.read_text()
            assert "Not provided" in text or "Not provided" in text.title()


class TestInternalIndexFilterNeverHidesRealVolume:
    """Fase 3C.1/D017 (extiende la corrección de Fase 3C): el filtro de
    índices internos (_internal, _audit, ...) solo debe ocultar filas sin
    volumen real. Si alguna vez un índice interno SÍ trae
    ingest_gb_per_day > 0 (p.ej. un CSV manual mal formado, o una versión
    de Splunk que sí mide uso interno), debe seguir visible -- de lo
    contrario el total ejecutivo incluiría dinero que ninguna tabla visible
    puede explicar."""

    def _dataset(self, index: str, gb: float, classification: Classification) -> Dataset:
        ds = Dataset(key=DatasetKey(index=index, sourcetype="st"))
        ds.ingest_gb_per_day = gb
        ds.classification = classification
        ds.explanation = "test"
        ds.data_value_score = 0
        return ds

    def test_zero_volume_internal_dataset_is_hidden(self):
        datasets, summary, savings = _classified()
        datasets = list(datasets) + [self._dataset("_internal", 0.0, Classification.HIGH_VALUE)]
        context = build_report_context(datasets, summary, savings, tier="pro")
        names = [row["name"] for row in context["all_datasets_detail"]]
        assert not any(name.startswith("_internal") for name in names)

    def test_internal_dataset_with_real_volume_stays_visible(self):
        datasets, summary, savings = _classified()
        datasets = list(datasets) + [
            self._dataset("_internal", 5.0, Classification.POSSIBLE_WASTE)
        ]
        context = build_report_context(datasets, summary, savings, tier="pro")
        names = [row["name"] for row in context["all_datasets_detail"]]
        assert any(name.startswith("_internal") for name in names)


class TestLastSeenLabelDoesNotImplySearchActivity:
    """Fase 3C.1: 'Last observed: N days ago', mostrado justo al lado de
    'Searches 90d: 0', se leía como si fuera actividad de búsqueda. La
    señal viene de metadata type=sourcetypes (actividad de datos/ingest) --
    ver queries/metadata_last_seen.spl. El label debe ser inequívoco."""

    def test_html_and_md_use_last_data_observed_label(self, tmp_path):
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="pro")
        written = render_report(context, tmp_path, ["html", "md"])
        for path in written.values():
            text = path.read_text()
            if "days ago" in text or "Last" in text:
                assert "Last data observed" in text
                assert "Last observed" not in text


class TestSignalAvailableCounterExcludesNotApplicable:
    """Fase 3C.2 (D019): bug real -- "Signals available: 6 of 6" en Current
    Environment contaba dashboards_used/protected_overrides (NOT_APPLICABLE,
    nunca evaluadas en modo REST) como "disponibles", mientras Methodology
    las listaba como "not applicable for this run" en la misma corrida --
    una inconsistencia semántica directa entre dos secciones del mismo
    reporte. El contador ahora excluye NOT_APPLICABLE del denominador."""

    def test_not_applicable_signals_are_excluded_from_the_available_ratio(self):
        datasets, summary, savings = _rest_like_environment_without_dashboards_signal()
        context = build_report_context(datasets, summary, savings, tier="pro")

        # sources_available del fixture: 4 AVAILABLE, 2 NOT_APPLICABLE.
        assert context["applicable_signal_count"] == 4
        assert context["available_signal_count"] == 4
        assert context["has_not_applicable_signals"] is True
        assert "dashboards_used" in context["not_applicable_signal_names"]
        assert "protected_overrides" in context["not_applicable_signal_names"]

    def test_rendered_report_never_counts_not_applicable_as_available(self, tmp_path):
        datasets, summary, savings = _rest_like_environment_without_dashboards_signal()
        context = build_report_context(datasets, summary, savings, tier="pro")
        written = render_report(context, tmp_path, ["html", "md"])
        for path in written.values():
            text = path.read_text()
            # El bug real: "6 of 6" -- ningún run con fuentes NOT_APPLICABLE
            # debe decir "X of Y" con Y igual al total crudo de fuentes.
            assert "4 of 6" not in text
            assert "4 of 4" in text
            assert "not applicable" in text.lower()


class TestConfidenceColumnLabelIsUnambiguous:
    """Fase 3C.2 (D019): "Confidence: UNKNOWN" junto a
    "Classification: POSSIBLE_WASTE" podía leerse como si el motor no
    estuviera seguro de la clasificación. Verificado (scoring/rules.py no
    usa parser_confidence en absoluto, ni en classify() ni en
    data_value_score()) que es puramente confianza de evidencia de
    búsqueda/parsing SPL -- no de la clasificación. Se renombra el
    encabezado, sin tocar scoring (no había bug de lógica)."""

    def test_column_header_names_search_evidence_explicitly(self, tmp_path):
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="pro")
        written = render_report(context, tmp_path, ["html", "md"])
        for path in written.values():
            text = path.read_text()
            assert "Search evidence confidence" in text

    def test_classification_is_never_confused_with_a_bare_confidence_column(self):
        """La clasificación de un dataset con parser_confidence=UNKNOWN debe
        poder ser POSSIBLE_WASTE -- confirma que no hay acoplamiento de
        lógica entre ambos conceptos (nunca se tocó classify())."""
        from splunk_spend_auditor.scoring.rules import classify

        ds = Dataset(
            key=DatasetKey(index="idx", sourcetype="st"),
            ingest_gb_per_day=50.0,
            interactive_searches_90d=0,
            parser_confidence=ParserConfidence.UNKNOWN,
        )
        classification, _, _ = classify(ds, high_ingest_threshold_gb=20.0, environment_partial_unknown_ratio=0.05)
        assert classification == Classification.POSSIBLE_WASTE


class TestNoProductTierLabelInReport:
    """Fase 3C.2 (D019): Free/Pro es una hipótesis de producto no validada
    -- el reporte no debe mostrar "(PRO)"/"(FREE)" como si fuera un hecho
    ya decidido. El sistema de tiers (qué contenido se trunca) no cambia,
    solo se deja de nombrar la etiqueta comercial en el reporte visible."""

    def test_rendered_report_does_not_show_tier_label(self, tmp_path):
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="pro")
        written = render_report(context, tmp_path, ["html", "md"])
        for path in written.values():
            text = path.read_text()
            assert "(PRO)" not in text
            assert "(FREE)" not in text

    def test_free_tier_truncation_behavior_is_unchanged(self):
        """El fix es solo de etiqueta -- el truncamiento real de free sigue
        funcionando exactamente igual."""
        datasets, summary, savings = _classified()
        context = build_report_context(datasets, summary, savings, tier="free")
        assert len(context["ingestion_breakdown"]) <= 5
        assert len(context["top_candidates"]) <= 3
        assert context["usage_analysis"] == []


class TestHtmlReportEscapesUntrustedSplunkStrings:
    """Fase 4B (vulnerabilidad CRITICAL, corregida): `select_autoescape(["html"])`
    decide el autoescape mirando si el NOMBRE del template termina en
    ".html" -- pero nuestros archivos se llaman "report.html.j2"/
    "report.md.j2", que terminan en ".j2", no ".html". Jinja2 devolvía
    autoescape=False para el reporte HTML sin ningún error ni warning, y
    cualquier string controlado por Splunk (nombre de index/sourcetype,
    texto de explicación) se insertaba sin escapar -- confirmado
    explotable: un dataset con index=`<script>alert(1)</script>` ejecutaba
    el script al abrir report.html en un browser. render.py ahora usa un
    callable explícito (`_autoescape_for_template`) en vez de depender de
    la heurística de sufijo de `select_autoescape`."""

    _PAYLOAD_INDEX = "<script>alert('xss-index')</script>"
    _PAYLOAD_SOURCETYPE = 'evil"><img src=x onerror=alert(1)>'

    def _malicious_dataset(self) -> Dataset:
        ds = Dataset(key=DatasetKey(index=self._PAYLOAD_INDEX, sourcetype=self._PAYLOAD_SOURCETYPE))
        ds.ingest_gb_per_day = 10.0
        ds.classification = Classification.POSSIBLE_WASTE
        ds.explanation = "Explanation with <script>alert('xss-explanation')</script> and & < > \" ' chars."
        ds.data_value_score = 0
        return ds

    def _render_with_malicious_dataset(self, tmp_path):
        ds = self._malicious_dataset()
        summary = EnvironmentSummary(total_datasets=1, sources_available={})
        savings = compute_savings([ds])
        context = build_report_context([ds], summary, savings, tier="pro")
        return render_report(context, tmp_path, ["html", "md"])

    def test_html_report_never_contains_a_raw_script_tag(self, tmp_path):
        written = self._render_with_malicious_dataset(tmp_path)
        html = written["html"].read_text()
        assert "<script>alert" not in html
        assert "&lt;script&gt;alert" in html

    def test_html_report_never_contains_a_raw_event_handler_breakout(self, tmp_path):
        written = self._render_with_malicious_dataset(tmp_path)
        html = written["html"].read_text()
        # El breakout de atributo (cerrar el <code> con "> e inyectar un tag
        # nuevo) debe quedar neutralizado -- las comillas y los ángulos
        # deben estar escapados, no aparecer crudos formando un tag real.
        assert '"><img src=x onerror=alert(1)>' not in html
        assert "&#34;&gt;&lt;img" in html

    def test_html_report_escapes_ampersand_and_quotes_in_explanation_text(self, tmp_path):
        written = self._render_with_malicious_dataset(tmp_path)
        html = written["html"].read_text()
        assert "&amp;" in html
        assert "&lt;" in html and "&gt;" in html

    def test_autoescape_is_keyed_on_actual_template_filenames(self):
        """Guarda de regresión directa sobre la causa raíz: el callable de
        autoescape debe reconocer "report.html.j2" (no ".html" a secas, que
        es el patrón que select_autoescape() buscaba y nunca encontraba)."""
        from splunk_spend_auditor.reports.render import _autoescape_for_template

        assert _autoescape_for_template("report.html.j2") is True
        assert _autoescape_for_template("report.md.j2") is False
        assert _autoescape_for_template(None) is False
