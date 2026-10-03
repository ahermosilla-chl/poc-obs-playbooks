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

from splunk_spend_auditor import __version__
from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import RawCollection, load_from_directory
from splunk_spend_auditor.collector.rest_collector import RestCollectionError, RestConfig
from splunk_spend_auditor.collector.rest_collector import collect as collect_rest
from splunk_spend_auditor.formatting import format_gb_per_day
from splunk_spend_auditor.models import Classification
from splunk_spend_auditor.reports.render import build_report_context, render_report
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.rules import REVIEW_WEIGHT
from splunk_spend_auditor.scoring.savings import compute_savings

app = typer.Typer(
    add_completion=False,
    help="Read-only, local-first audit of Splunk ingest cost vs. real usage.",
)



def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"splunk-spend-auditor {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
):
    # Windows: stdout/stderr redirigidos usan la codepage local (p.ej. cp1252);
    # nunca fallar por un caracter no representable en la salida.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _resolve_token(cli_verbose: bool) -> str:
    """Never accepts the token as a plain-text CLI argument (docs/security.md)
    -- it's read from SPLUNK_TOKEN or prompted interactively and hidden via
    getpass."""

    token = os.environ.get("SPLUNK_TOKEN")
    if token:
        return token
    if not sys.stdin.isatty():
        typer.secho(
            "SPLUNK_TOKEN is not set and there is no interactive terminal to "
            "prompt for it. Set the SPLUNK_TOKEN environment variable.",
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
    queries_dir: Optional[str],
) -> RawCollection:
    """Decides which collector to use based on the flags -- see
    DECISIONS.md D002. Exactly one of --from-csv / --host must be given; the
    CLI validates this before attempting anything against Splunk."""

    if from_csv and host:
        typer.secho("Use --from-csv or --host, not both.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not from_csv and not host:
        typer.secho(
            "Either --from-csv <directory> (CSV mode) or --host <splunk-host> "
            "(REST mode) is required.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    if from_csv:
        try:
            return load_from_directory(from_csv)
        except FileNotFoundError as exc:
            typer.secho(f"Could not read the data directory: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc

    token = _resolve_token(cli_verbose=False)
    config = RestConfig(host=host, token=token, port=port, verify_ssl=verify_ssl)
    try:
        return collect_rest(config, queries_dir)
    except RestCollectionError as exc:
        typer.secho(f"Could not complete the audit: {exc}", fg=typer.colors.RED, err=True)
        typer.secho("Try again with --verbose to see the technical detail.", err=True)
        raise typer.Exit(code=1) from exc


def _source_label(from_csv: Optional[str], host: Optional[str], port: int) -> str:
    """Fase 3C ("Current Environment"): identificador NO sensible del
    origen de los datos, para mostrar en el reporte -- nunca el token."""

    if host:
        return f"Splunk REST — {host}:{port}"
    return f"CSV import — {from_csv}"


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
    if not degraded:
        return
    typer.secho(
        f"Analysis completed with reduced confidence. Unavailable signals: {', '.join(degraded)}.",
        fg=typer.colors.YELLOW,
    )
    # Fase 3B/D015: si hay una razón más específica que el nombre genérico
    # de la fuente (p.ej. "no se pudo confirmar acceso a _audit"), mostrarla
    # -- item 6: "qué señal falta; por qué importa; que el audit continúa
    # de forma conservadora".
    for source in degraded:
        reason = summary.diagnostics.get(source)
        if reason:
            typer.secho(f"  - {source}: {reason}", fg=typer.colors.YELLOW)


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
    queries_dir: Optional[str] = typer.Option(None, help="Override the bundled SPL queries with a custom directory (REST mode)."),
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
    # Fase 3C.2 (D019): antes se mezclaban POSSIBLE_WASTE y REVIEW en una
    # sola lista "candidates" sumada sin peso -- distinto del full audit,
    # que pesa REVIEW a REVIEW_WEIGHT (scoring/savings.py) y nunca los suma
    # como si fueran lo mismo. Ahora se muestran por separado, y la única
    # cifra "comparable a full audit" (volumen y % de candidatos de
    # optimización) reutiliza `savings.candidate_gb_day`/
    # `savings.potential_reduction_pct` -- el mismo objeto SavingsEstimate
    # que ya calculó `_run_pipeline()` arriba, no un cálculo paralelo.
    waste_candidates = sorted(
        (d for d in datasets if d.classification == Classification.POSSIBLE_WASTE),
        key=lambda d: d.ingest_gb_per_day,
        reverse=True,
    )
    review_candidates = sorted(
        (d for d in datasets if d.classification == Classification.REVIEW),
        key=lambda d: d.ingest_gb_per_day,
        reverse=True,
    )

    typer.echo(f"Total ingest: {format_gb_per_day(sum(d.ingest_gb_per_day for d in datasets))}/day")
    typer.echo("")
    typer.echo("Top 5 consumers by GB/day:")
    for i, d in enumerate(top5, 1):
        typer.echo(f"  {i}. {d.key}  {format_gb_per_day(d.ingest_gb_per_day)}/day")
    typer.echo("")
    if waste_candidates:
        typer.echo(
            f"Possible waste: {len(waste_candidates)} "
            f"{'dataset' if len(waste_candidates) == 1 else 'datasets'}, "
            f"{format_gb_per_day(savings.possible_waste_gb_day)}/day"
        )
        for d in waste_candidates[:3]:
            typer.echo(f"  - {d.key}  POSSIBLE_WASTE  {format_gb_per_day(d.ingest_gb_per_day)}/day")
    if review_candidates:
        typer.echo(
            f"Review (manual validation recommended): {len(review_candidates)} "
            f"{'dataset' if len(review_candidates) == 1 else 'datasets'}, "
            f"{format_gb_per_day(savings.review_gb_day)}/day"
        )
        for d in review_candidates[:3]:
            typer.echo(f"  - {d.key}  REVIEW  {format_gb_per_day(d.ingest_gb_per_day)}/day")
    if not waste_candidates and not review_candidates:
        typer.echo("No optimization candidates found with the current thresholds.")
    if waste_candidates or review_candidates:
        typer.echo("")
        typer.echo(
            f"Optimization candidate volume (possible waste + review, weighted "
            f"x{REVIEW_WEIGHT} -- same calculation as full audit): "
            f"{format_gb_per_day(savings.candidate_gb_day)}/day "
            f"({savings.potential_reduction_pct * 100:.1f}% of total)"
        )
    typer.echo("")
    _echo_degradation_notice(summary)
    if host:
        typer.echo(
            f"Generate Full Spend Audit -> run "
            f"`splunk-spend-auditor audit --host {host} --port {port}`"
        )
    else:
        typer.echo(
            f"Generate Full Spend Audit -> run "
            f"`splunk-spend-auditor audit --from-csv {from_csv}`"
        )


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
    queries_dir: Optional[str] = typer.Option(None, help="Override the bundled SPL queries with a custom directory (REST mode)."),
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
        source_label=_source_label(from_csv, host, port),
    )
    format_list = [f.strip() for f in formats.split(",") if f.strip()]
    written = render_report(context, output_dir, format_list)

    typer.echo("Your Splunk Spend Audit is ready.")
    typer.echo("")
    typer.echo(f"Current ingest: {format_gb_per_day(savings.current_ingest_gb_day)}/day")
    typer.echo(f"Optimization candidates: {format_gb_per_day(savings.candidate_gb_day)}/day")
    typer.echo(f"Potential reduction: {savings.potential_reduction_pct * 100:.1f}%")
    if savings.potential_annual_saving is not None:
        typer.echo(f"Potential annual saving: ${savings.potential_annual_saving:,.0f}")
    typer.echo("")
    _echo_degradation_notice(summary)
    for fmt, path in written.items():
        typer.echo(f"Report ({fmt}): {path}")


@app.command()
def demo(
    output_dir: str = typer.Option("./demo-output", help="Where to write the demo report."),
):
    """Offline demo: a deterministic SYNTHETIC Splunk environment run through
    the real analysis and reporting pipeline. No Splunk, credentials or
    network needed."""

    from splunk_spend_auditor.demo import DEMO_SOURCE_LABEL, build_demo_collection

    typer.echo("Log Spend Auditor — Demo")
    typer.echo("")
    typer.echo("Loading synthetic Splunk environment...")
    collection = build_demo_collection()
    typer.echo("Analyzing ingestion...")
    datasets, summary, savings = _run_pipeline(
        collection, 90, annual_spend=None, cost_per_gb_day=None
    )
    typer.echo("Generating report...")
    context = build_report_context(
        datasets, summary, savings, tier="pro", source_label=DEMO_SOURCE_LABEL
    )
    written = render_report(context, output_dir, ["html", "md"])

    counts = {c: sum(1 for d in datasets if d.classification == c) for c in Classification}
    waste = counts[Classification.POSSIBLE_WASTE]
    review = counts[Classification.REVIEW]
    typer.echo("")
    typer.echo("Analysis complete.")
    typer.echo("")
    typer.echo(f"Indexes analyzed:      {len({d.key.index for d in datasets})}")
    typer.echo(f"Sourcetypes analyzed:  {len(datasets)}")
    typer.echo(f"Daily ingest:          {format_gb_per_day(savings.current_ingest_gb_day)}/day")
    typer.echo(
        f"Findings detected:     {waste + review} "
        f"({waste} possible waste, {review} review)"
    )
    typer.echo(
        f"Optimization candidates: {format_gb_per_day(savings.candidate_gb_day)}/day "
        f"({savings.potential_reduction_pct * 100:.1f}% of observed ingest)"
    )
    typer.echo("")
    typer.echo("This demo uses synthetic data; nothing was read from or sent to Splunk.")
    typer.echo("")
    typer.echo("Report:")
    typer.echo(str(written["html"]))
    typer.echo(str(written["md"]))


if __name__ == "__main__":
    app()
