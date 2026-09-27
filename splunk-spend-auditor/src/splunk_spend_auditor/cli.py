"""CLI de Log Spend Auditor. Ver docs/product-spec.md, "Interfaz (CLI)".

Fase 3B (item 8, "CLI Error UX"): los errores operacionales esperables
(Splunk inaccesible, token inválido, permisos insuficientes) se muestran
como un mensaje breve y accionable, nunca como un stack trace de Python por
defecto. El detalle técnico completo sigue disponible con --verbose (logging
estándar, ver `logging.basicConfig` más abajo -- no se construyó un
framework de logging nuevo, solo se usa el de la librería estándar)."""

from __future__ import annotations

import getpass
import logging
import os
import sys
from typing import Optional

import typer

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import RawCollection, load_from_directory
from splunk_spend_auditor.collector.rest_collector import RestCollectionError, RestConfig
from splunk_spend_auditor.collector.rest_collector import collect as collect_rest
from splunk_spend_auditor.models import Classification
from splunk_spend_auditor.reports.render import build_report_context, render_report
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.savings import compute_savings

app = typer.Typer(
    add_completion=False,
    help="Read-only, local-first audit of Splunk ingest cost vs. real usage.",
)

_QUERIES_DIR_DEFAULT = "queries"


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _resolve_token(cli_verbose: bool) -> str:
    """Nunca acepta el token como argumento de línea de comandos en texto
    plano (docs/security.md) -- se lee de SPLUNK_TOKEN o se pide de forma
    interactiva y oculta con getpass."""

    token = os.environ.get("SPLUNK_TOKEN")
    if token:
        return token
    if not sys.stdin.isatty():
        typer.secho(
            "Falta SPLUNK_TOKEN y no hay una terminal interactiva para pedirlo. "
            "Define la variable de entorno SPLUNK_TOKEN.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    return getpass.getpass("Splunk REST token (SPLUNK_TOKEN): ")


def _collect_from_source(
    *,
    from_csv: Optional[str],
    host: Optional[str],
    port: int,
    verify_ssl: bool,
    queries_dir: str,
) -> RawCollection:
    """Decide qué collector usar según los flags -- ver DECISIONS.md D002.
    Exactamente uno de --from-csv / --host debe darse; el CLI lo valida
    antes de intentar nada contra Splunk."""

    if from_csv and host:
        typer.secho("Usa --from-csv o --host, no ambos.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not from_csv and not host:
        typer.secho(
            "Se requiere --from-csv <directorio> (modo CSV) o --host <splunk-host> (modo REST).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    if from_csv:
        try:
            return load_from_directory(from_csv)
        except FileNotFoundError as exc:
            typer.secho(f"No se pudo leer el directorio de datos: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc

    token = _resolve_token(cli_verbose=False)
    config = RestConfig(host=host, token=token, port=port, verify_ssl=verify_ssl)
    try:
        return collect_rest(config, queries_dir)
    except RestCollectionError as exc:
        typer.secho(f"No se pudo completar la auditoría: {exc}", fg=typer.colors.RED, err=True)
        typer.secho("Volvé a intentarlo con --verbose para ver el detalle técnico.", err=True)
        raise typer.Exit(code=1) from exc


def _run_pipeline(
    collection: RawCollection,
    lookback_days: int,
    annual_spend: Optional[float],
    cost_per_gb_day: Optional[float],
):
    datasets, summary = build_datasets(collection, lookback_days=lookback_days)
    datasets = classify_all(
        datasets,
        environment_partial_unknown_ratio=summary.partial_or_unknown_ratio,
        sources_available=summary.sources_available,
    )
    savings = compute_savings(
        datasets, annual_spend=annual_spend, cost_per_gb_day=cost_per_gb_day
    )
    return datasets, summary, savings


def _echo_degradation_notice(summary) -> None:
    from splunk_spend_auditor.models import SignalAvailability

    degraded = [
        source
        for source, status in summary.sources_available.items()
        if status
        in (SignalAvailability.UNAVAILABLE, SignalAvailability.PARTIAL, SignalAvailability.ERROR)
    ]
    if degraded:
        typer.secho(
            f"Analysis completed with reduced confidence. Unavailable signals: {', '.join(degraded)}.",
            fg=typer.colors.YELLOW,
        )


@app.command()
def quickscan(
    from_csv: Optional[str] = typer.Option(
        None, "--from-csv", help="Directory with the exported CSV files."
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Splunk management host (REST mode). Token read from SPLUNK_TOKEN."
    ),
    port: int = typer.Option(8089, help="Splunk management port (REST mode)."),
    verify_ssl: bool = typer.Option(True, help="Verify TLS certificate (REST mode)."),
    queries_dir: str = typer.Option(_QUERIES_DIR_DEFAULT, help="Directory with queries/*.spl (REST mode)."),
    lookback_days: int = typer.Option(90, help="Lookback window in days."),
    verbose: bool = typer.Option(False, "--verbose", help="Show technical error detail."),
):
    """Free, no-signup version: terminal summary only (docs/validation-plan.md).
    Top 5 consumers + top 3 optimization candidates, no HTML report."""

    _configure_logging(verbose)
    collection = _collect_from_source(
        from_csv=from_csv, host=host, port=port, verify_ssl=verify_ssl, queries_dir=queries_dir
    )
    datasets, summary, savings = _run_pipeline(
        collection, lookback_days, annual_spend=None, cost_per_gb_day=None
    )

    top5 = sorted(datasets, key=lambda d: d.ingest_gb_per_day, reverse=True)[:5]
    candidates = [
        d
        for d in sorted(datasets, key=lambda d: d.ingest_gb_per_day, reverse=True)
        if d.classification
        in (Classification.POSSIBLE_WASTE, Classification.REVIEW)
    ][:3]

    typer.echo(f"Total ingest: {sum(d.ingest_gb_per_day for d in datasets):.1f} GB/day")
    typer.echo("")
    typer.echo("Top 5 consumers by GB/day:")
    for i, d in enumerate(top5, 1):
        typer.echo(f"  {i}. {d.key}  {d.ingest_gb_per_day:.1f} GB/day")
    typer.echo("")
    if candidates:
        candidate_gb = sum(d.ingest_gb_per_day for d in candidates)
        pct = 100 * candidate_gb / (sum(d.ingest_gb_per_day for d in datasets) or 1)
        typer.echo(
            f"Review candidates (possible waste): {len(candidates)} datasets, "
            f"{candidate_gb:.1f} GB/day ({pct:.1f}% of total)"
        )
        for d in candidates:
            typer.echo(f"  - {d.key}  {d.classification.value}  {d.ingest_gb_per_day:.1f} GB/day")
    else:
        typer.echo("No optimization candidates found with the current thresholds.")
    typer.echo("")
    _echo_degradation_notice(summary)
    typer.echo("Generate Full Spend Audit -> run `splunk-spend-auditor audit --from-csv ...`")


@app.command()
def audit(
    from_csv: Optional[str] = typer.Option(
        None, "--from-csv", help="Directory with the exported CSV files."
    ),
    host: Optional[str] = typer.Option(
        None, "--host", help="Splunk management host (REST mode). Token read from SPLUNK_TOKEN."
    ),
    port: int = typer.Option(8089, help="Splunk management port (REST mode)."),
    verify_ssl: bool = typer.Option(True, help="Verify TLS certificate (REST mode)."),
    queries_dir: str = typer.Option(_QUERIES_DIR_DEFAULT, help="Directory with queries/*.spl (REST mode)."),
    output_dir: str = typer.Option("./output", help="Where to write the report."),
    annual_spend: Optional[float] = typer.Option(
        None, help="Estimated annual Splunk spend, used to estimate $ savings."
    ),
    cost_per_gb_day: Optional[float] = typer.Option(
        None, help="Cost per GB/day, alternative to --annual-spend."
    ),
    lookback_days: int = typer.Option(90, help="Lookback window in days."),
    tier: str = typer.Option("pro", help="'free' or 'pro' report detail level."),
    formats: str = typer.Option("html,md", help="Comma-separated: html,md"),
    redact_hosts: bool = typer.Option(False, help="Reserved for future host/source reporting."),
    redact_names: bool = typer.Option(
        False, help="Replace index/sourcetype names with generic IDs in the report."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show technical error detail."),
):
    """Full audit: classification + potential savings + HTML/Markdown report."""

    _configure_logging(verbose)
    collection = _collect_from_source(
        from_csv=from_csv, host=host, port=port, verify_ssl=verify_ssl, queries_dir=queries_dir
    )
    datasets, summary, savings = _run_pipeline(
        collection, lookback_days, annual_spend, cost_per_gb_day
    )

    context = build_report_context(
        datasets,
        summary,
        savings,
        tier=tier,
        redact_hosts=redact_hosts,
        redact_names=redact_names,
    )
    format_list = [f.strip() for f in formats.split(",") if f.strip()]
    written = render_report(context, output_dir, format_list)

    typer.echo("Your Splunk Spend Audit is ready.")
    typer.echo("")
    typer.echo(f"Current ingest: {savings.current_ingest_gb_day:.1f} GB/day")
    typer.echo(f"Optimization candidates: {savings.candidate_gb_day:.1f} GB/day")
    typer.echo(f"Potential reduction: {savings.potential_reduction_pct * 100:.1f}%")
    if savings.potential_annual_saving is not None:
        typer.echo(f"Potential annual saving: ${savings.potential_annual_saving:,.0f}")
    typer.echo("")
    _echo_degradation_notice(summary)
    for fmt, path in written.items():
        typer.echo(f"Report ({fmt}): {path}")


if __name__ == "__main__":
    app()
