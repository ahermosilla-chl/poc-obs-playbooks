"""Construye el contexto de datos para los reportes y los renderiza con
Jinja2. Ver docs/report-design.md para el diseño de cada sección."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from splunk_spend_auditor import __version__
from splunk_spend_auditor.formatting import format_gb_per_day
from splunk_spend_auditor.models import Classification, Dataset, EnvironmentSummary, SignalAvailability
from splunk_spend_auditor.scoring.classify_all import high_ingest_threshold_for
from splunk_spend_auditor.scoring.rules import REVIEW_WEIGHT
from splunk_spend_auditor.scoring.savings import SavingsEstimate

# Fase 3B (D013/D014, item 5 "graceful degradation") -- texto legible por
# humanos para cada SignalAvailability, mostrado en la sección Methodology
# del reporte. UNAVAILABLE/PARTIAL/ERROR cuentan como "degraded": ninguno de
# los tres es una confirmación real de la señal, aunque tengan causas
# distintas (no se intentó / cobertura incompleta / falló al intentarlo).
_SIGNAL_STATUS_LABEL = {
    SignalAvailability.AVAILABLE: "available",
    SignalAvailability.UNAVAILABLE: "not available (not attempted for this run)",
    SignalAvailability.PARTIAL: "partially available (coverage may be incomplete)",
    SignalAvailability.ERROR: "not available (query or connection failed)",
    SignalAvailability.NOT_APPLICABLE: "not applicable for this run",
}
_DEGRADED_SIGNAL_STATES = frozenset(
    {SignalAvailability.UNAVAILABLE, SignalAvailability.PARTIAL, SignalAvailability.ERROR}
)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


_RECOMMENDATION_TEXT = {
    Classification.POSSIBLE_WASTE: "Optimization candidate — review ingestion/filtering policy.",
    Classification.REVIEW: "Review candidate — manual validation recommended.",
}

_FIXED_RECOMMENDATIONS = [
    "Validate each optimization candidate with the team that owns the data "
    "before changing anything.",
    "For confirmed low-value high-volume sources, consider filtering at the "
    "forwarder (e.g. INGEST_EVAL / props.conf transforms) rather than "
    "disabling the input entirely.",
    "For data that is rarely queried but must be retained for compliance, "
    "consider a cheaper storage tier instead of reducing ingest.",
    "Re-run this audit periodically (e.g. monthly) — usage patterns change "
    "as teams build new dashboards and alerts.",
]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_report_context(
    datasets: list[Dataset],
    summary: EnvironmentSummary,
    savings: SavingsEstimate,
    tier: str = "pro",
    redact_hosts: bool = False,
    redact_names: bool = False,
    source_label: str | None = None,
) -> dict:
    """source_label (Fase 3C, sección "Current Environment"): identificador
    NO sensible del origen de los datos -- p.ej. "REST — splunk.corp:8089"
    o "CSV import — ./export/". Nunca debe incluir el token (ver
    docs/security.md); quien arma este string (cli.py) es responsable de
    eso, este módulo solo lo muestra tal cual."""

    del redact_hosts  # reservado: el MVP no muestra host/source en el reporte
    # (ver docs/security.md) -- el flag se acepta para compatibilidad futura.

    # Fase 3C ("HTML quality review"): índices internos de Splunk (_internal,
    # _audit, _introspection, _telemetry, ...) nunca aparecen en
    # license_usage.log (no están sujetos a licencia) -- si aparecen como
    # "dataset" es solo porque alguna saved search/búsqueda los menciona
    # explícitamente (D010: contenido de sistema residual que sobrevive el
    # filtro por owner). Mostrarlos en el reporte del cliente es puro ruido
    # confuso ("¿por qué me hablan de _audit?") con 0.0 GB/día garantizado
    # -- nunca afectan clasificación ni ahorro, así que excluirlos aquí es
    # puramente de presentación, no cambia ningún número. Se filtra en la
    # capa de reporte, no en build_datasets/classify_all/compute_savings,
    # para no tocar la lógica de análisis -- ver docs/architecture.md.
    # Fase 3C.1/D018: solo se oculta un índice interno cuando NO tiene
    # volumen (el caso real y único observado -- confirmado empíricamente
    # contra el laboratorio real: license_usage.log nunca incluye índices
    # internos). Si alguna vez un índice `_`-prefijo SÍ trae ingest_gb_per_day
    # > 0 (p.ej. un CSV manual mal formado), se sigue mostrando -- así el
    # total ejecutivo nunca puede incluir dinero que las tablas visibles no
    # puedan explicar (ver DECISIONS.md D017).
    datasets = [
        d for d in datasets if not (d.key.index.startswith("_") and d.ingest_gb_per_day == 0.0)
    ]

    high_ingest_threshold = high_ingest_threshold_for(datasets)

    # Fase 3C.1/D018: "dashboards_used" es una fuente manual/opcional (D002)
    # -- en modo REST siempre es NOT_APPLICABLE (nunca se evalúa) y en modo
    # CSV depende de si el usuario exportó el archivo opcional. Mostrar
    # "No" cuando en realidad nunca se consultó viola "missing visibility !=
    # zero usage" -- ver scoring/rules.py, docstring de
    # dashboards_signal_available.
    dashboards_evaluated = (
        summary.sources_available.get("dashboards_used") == SignalAvailability.AVAILABLE
    )

    def _dashboards_display(ds: Dataset) -> str:
        if ds.used_in_dashboards:
            return "Yes"
        return "No" if dashboards_evaluated else "Not evaluated"

    name_map: dict[str, str] = {}
    if redact_names:
        for i, ds in enumerate(
            sorted(datasets, key=lambda d: (d.key.index, d.key.sourcetype))
        ):
            name_map[str(ds.key)] = f"dataset_{i + 1:03d}"

    def _display_name(ds: Dataset) -> str:
        return name_map.get(str(ds.key), str(ds.key))

    total_gb_actual = sum(d.ingest_gb_per_day for d in datasets)
    total_gb = total_gb_actual or 1.0  # evita división por cero más abajo

    all_sorted = sorted(datasets, key=lambda d: d.ingest_gb_per_day, reverse=True)

    top_n = 5 if tier == "free" else 50
    ingestion_breakdown = [
        {
            "name": _display_name(ds),
            "gb_per_day": round(ds.ingest_gb_per_day, 2),
            "gb_per_day_display": format_gb_per_day(ds.ingest_gb_per_day),
            "pct_of_total": round(100 * ds.ingest_gb_per_day / total_gb, 1),
        }
        for ds in all_sorted[:top_n]
    ]

    usage_analysis = [
        {
            "name": _display_name(ds),
            "searches_30d": ds.interactive_searches_30d,
            "searches_90d": ds.interactive_searches_90d,
            "is_scheduled": ds.is_scheduled,
            "has_alert": ds.has_alert_action,
            "used_in_dashboards": ds.used_in_dashboards,
            "dashboards_display": _dashboards_display(ds),
            "unique_users_30d": ds.unique_users_30d,
            "last_seen_days_ago": ds.last_seen_days_ago,
            "confidence": ds.parser_confidence.value,
        }
        for ds in all_sorted
    ]

    candidates_all = [
        d
        for d in all_sorted
        if d.classification in (Classification.POSSIBLE_WASTE, Classification.REVIEW)
    ]
    candidate_top_n = 3 if tier == "free" else len(candidates_all)
    top_candidates = [
        {
            "name": _display_name(ds),
            "gb_per_day": round(ds.ingest_gb_per_day, 2),
            "gb_per_day_display": format_gb_per_day(ds.ingest_gb_per_day),
            "searches_30d": ds.interactive_searches_30d,
            "searches_90d": ds.interactive_searches_90d,
            "is_scheduled": ds.is_scheduled,
            "has_alert": ds.has_alert_action,
            "used_in_dashboards": ds.used_in_dashboards,
            "dashboards_display": _dashboards_display(ds),
            "last_seen_days_ago": ds.last_seen_days_ago,
            "classification": ds.classification.value,
            "explanation": ds.explanation,
            "recommendation": _RECOMMENDATION_TEXT.get(ds.classification, ""),
        }
        for ds in candidates_all[:candidate_top_n]
    ]

    sources_available_display = [
        {
            "source": source,
            "status": status.value,
            # Fase 3B/D015: `summary.diagnostics` trae una razón específica
            # (p.ej. "no se pudo confirmar acceso a _audit") cuando hay algo
            # más preciso que decir que la etiqueta genérica del estado.
            "label": summary.diagnostics.get(source) or _SIGNAL_STATUS_LABEL.get(status, status.value),
            "degraded": status in _DEGRADED_SIGNAL_STATES,
            "not_applicable": status == SignalAvailability.NOT_APPLICABLE,
        }
        for source, status in summary.sources_available.items()
    ]
    degraded_signal_names = [row["source"] for row in sources_available_display if row["degraded"]]
    # Fase 3C.2 (D019): "Signals available: X of Y" contaba NOT_APPLICABLE
    # como "disponible" (solo excluía UNAVAILABLE/PARTIAL/ERROR) -- una
    # fuente que nunca se evalúa por diseño (dashboards_used/
    # protected_overrides en modo REST) no es lo mismo que una fuente
    # confirmada. El contador ahora es "cuántas de las fuentes APLICABLES a
    # este run están AVAILABLE" -- las NOT_APPLICABLE se excluyen del
    # denominador y se listan aparte, consistente con lo que Methodology ya
    # dice para cada una.
    applicable_signals_display = [row for row in sources_available_display if not row["not_applicable"]]
    available_signal_count = sum(
        1 for row in applicable_signals_display if row["status"] == SignalAvailability.AVAILABLE.value
    )
    not_applicable_signal_names = [
        row["source"] for row in sources_available_display if row["not_applicable"]
    ]

    all_datasets_detail = [
        {
            "name": _display_name(ds),
            "gb_per_day": round(ds.ingest_gb_per_day, 2),
            "gb_per_day_display": format_gb_per_day(ds.ingest_gb_per_day),
            "classification": ds.classification.value,
            "score": ds.data_value_score,
        }
        for ds in all_sorted
    ]

    # Fase 3C ("Protected / High Value", item 4): no esconder lo que el
    # motor decidió NO recomendar -- ver un resumen refuerza confianza en
    # el resto del reporte. Se muestra un top acotado, no la lista completa
    # (que ya está en "Indexes / Sourcetypes" para el tier Pro).
    protected_datasets = [d for d in all_sorted if d.classification == Classification.PROTECTED]
    high_value_datasets = [d for d in all_sorted if d.classification == Classification.HIGH_VALUE]
    _RECOGNIZED_TOP_N = 10
    recognized_datasets = [
        {
            "name": _display_name(ds),
            "gb_per_day_display": format_gb_per_day(ds.ingest_gb_per_day),
            "classification": ds.classification.value,
            "reason": ds.explanation,
        }
        for ds in (protected_datasets + high_value_datasets)[:_RECOGNIZED_TOP_N]
    ]

    # Fase 3C (Executive Summary, item 4): conteo por categoría -- responde
    # "cuántos candidatos / cuántos protegidos / cuántos sin evidencia" sin
    # tener que contar filas de tablas más abajo.
    classification_counts = {
        c.value: sum(1 for d in all_sorted if d.classification == c) for c in Classification
    }

    def _plural(n: int, singular: str, plural: str) -> str:
        return f"{n} {singular if n == 1 else plural}"

    counts_summary_line = " · ".join(
        [
            _plural(len(all_sorted), "dataset analyzed", "datasets analyzed"),
            _plural(classification_counts["POSSIBLE_WASTE"], "optimization candidate", "optimization candidates"),
            _plural(classification_counts["REVIEW"], "review", "reviews"),
            _plural(classification_counts["HIGH_VALUE"], "high value", "high value"),
            _plural(classification_counts["PROTECTED"], "protected", "protected"),
            _plural(classification_counts["UNKNOWN"], "unknown", "unknown"),
            _plural(classification_counts["NORMAL"], "normal", "normal"),
        ]
    )

    savings_dict = asdict(savings)
    savings_display = {
        "current_ingest_gb_day": format_gb_per_day(savings.current_ingest_gb_day),
        "possible_waste_gb_day": format_gb_per_day(savings.possible_waste_gb_day),
        "review_gb_day": format_gb_per_day(savings.review_gb_day),
        "candidate_gb_day": format_gb_per_day(savings.candidate_gb_day),
    }

    context = {
        "tool_version": __version__,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tier": tier,
        "lookback_days": summary.lookback_days,
        # len(datasets), no summary.total_datasets: este último se calculó
        # antes del filtro de índices internos de arriba y quedaría
        # inconsistente con el resto de las tablas del reporte.
        "total_datasets": len(datasets),
        "counts_summary_line": counts_summary_line,
        "current_ingest_gb_day": round(total_gb_actual, 2),
        "current_ingest_display": format_gb_per_day(total_gb_actual),
        "ingestion_breakdown": ingestion_breakdown,
        "ingestion_breakdown_truncated": len(all_sorted) > top_n,
        "usage_analysis": usage_analysis if tier != "free" else [],
        "top_candidates": top_candidates,
        "candidates_truncated": len(candidates_all) > candidate_top_n,
        "all_datasets_detail": all_datasets_detail if tier != "free" else [],
        "recognized_datasets": recognized_datasets,
        "protected_count": len(protected_datasets),
        "high_value_count": len(high_value_datasets),
        "recognized_truncated": len(protected_datasets) + len(high_value_datasets) > _RECOGNIZED_TOP_N,
        "classification_counts": classification_counts,
        "savings": savings_dict,
        "savings_display": savings_display,
        "review_weight": REVIEW_WEIGHT,
        "high_ingest_threshold_gb": round(high_ingest_threshold, 2),
        "high_ingest_threshold_display": format_gb_per_day(high_ingest_threshold),
        "partial_or_unknown_ratio": summary.partial_or_unknown_ratio,
        "sources_available": summary.sources_available,
        "sources_available_display": sources_available_display,
        "reduced_confidence": bool(degraded_signal_names),
        "degraded_signal_names": degraded_signal_names,
        "available_signal_count": available_signal_count,
        "applicable_signal_count": len(applicable_signals_display),
        "has_not_applicable_signals": bool(not_applicable_signal_names),
        "not_applicable_signal_names": not_applicable_signal_names,
        "source_label": source_label,
        # Nota de squashing (docs/splunk-data-sources.md): en el MVP no se
        # analiza host/source, así que esta nota siempre se muestra como
        # recordatorio metodológico, no como señal detectada dinámicamente.
        "show_squashing_note": True,
        "recommendations": _FIXED_RECOMMENDATIONS,
    }
    return context


def render_report(context: dict, output_dir: str | Path, formats: list[str]) -> dict[str, Path]:
    """Renderiza los formatos pedidos ('html', 'md') y devuelve las rutas
    generadas. Ambos formatos se generan desde el mismo `context` -- ver
    docs/architecture.md."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = _env()

    written: dict[str, Path] = {}
    if "html" in formats:
        template = env.get_template("report.html.j2")
        path = output_dir / "report.html"
        path.write_text(template.render(**context))
        written["html"] = path
    if "md" in formats:
        template = env.get_template("report.md.j2")
        path = output_dir / "report.md"
        path.write_text(template.render(**context))
        written["md"] = path
    return written
