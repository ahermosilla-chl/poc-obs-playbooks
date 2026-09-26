"""Construye el contexto de datos para los reportes y los renderiza con
Jinja2. Ver docs/report-design.md para el diseño de cada sección."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from splunk_spend_auditor import __version__
from splunk_spend_auditor.models import Classification, Dataset, EnvironmentSummary
from splunk_spend_auditor.scoring.classify_all import high_ingest_threshold_for
from splunk_spend_auditor.scoring.rules import REVIEW_WEIGHT
from splunk_spend_auditor.scoring.savings import SavingsEstimate

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
) -> dict:
    del redact_hosts  # reservado: el MVP no muestra host/source en el reporte
    # (ver docs/security.md) -- el flag se acepta para compatibilidad futura.

    high_ingest_threshold = high_ingest_threshold_for(datasets)

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
            "searches_30d": ds.interactive_searches_30d,
            "searches_90d": ds.interactive_searches_90d,
            "is_scheduled": ds.is_scheduled,
            "has_alert": ds.has_alert_action,
            "used_in_dashboards": ds.used_in_dashboards,
            "last_seen_days_ago": ds.last_seen_days_ago,
            "classification": ds.classification.value,
            "explanation": ds.explanation,
            "recommendation": _RECOMMENDATION_TEXT.get(ds.classification, ""),
        }
        for ds in candidates_all[:candidate_top_n]
    ]

    all_datasets_detail = [
        {
            "name": _display_name(ds),
            "gb_per_day": round(ds.ingest_gb_per_day, 2),
            "classification": ds.classification.value,
            "score": ds.data_value_score,
        }
        for ds in all_sorted
    ]

    context = {
        "tool_version": __version__,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tier": tier,
        "lookback_days": summary.lookback_days,
        "total_datasets": summary.total_datasets,
        "current_ingest_gb_day": round(total_gb_actual, 2),
        "ingestion_breakdown": ingestion_breakdown,
        "ingestion_breakdown_truncated": len(all_sorted) > top_n,
        "usage_analysis": usage_analysis if tier != "free" else [],
        "top_candidates": top_candidates,
        "candidates_truncated": len(candidates_all) > candidate_top_n,
        "all_datasets_detail": all_datasets_detail if tier != "free" else [],
        "savings": asdict(savings),
        "review_weight": REVIEW_WEIGHT,
        "high_ingest_threshold_gb": round(high_ingest_threshold, 2),
        "partial_or_unknown_ratio": summary.partial_or_unknown_ratio,
        "sources_available": summary.sources_available,
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
