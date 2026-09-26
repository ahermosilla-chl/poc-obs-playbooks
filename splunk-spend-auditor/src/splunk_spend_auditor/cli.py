"""CLI de Log Spend Auditor. Ver docs/product-spec.md, "Interfaz (CLI)"."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.csv_collector import load_from_directory
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.savings import compute_savings
from splunk_spend_auditor.reports.render import build_report_context, render_report

app = typer.Typer(
    add_completion=False,
    help="Read-only, local-first audit of Splunk ingest cost vs. real usage.",
)


def _run_pipeline(
    from_csv: str,
    lookback_days: int,
    annual_spend: Optional[float],
    cost_per_gb_day: Optional[float],
):
    collection = load_from_directory(from_csv)
    datasets, summary = build_datasets(collection, lookback_days=lookback_days)
    datasets = classify_all(
        datasets, environment_partial_unknown_ratio=summary.partial_or_unknown_ratio
    )
    savings = compute_savings(
        datasets, annual_spend=annual_spend, cost_per_gb_day=cost_per_gb_day
    )
    return datasets, summary, savings


@app.command()
def quickscan(
    from_csv: str = typer.Option(
        ..., "--from-csv", help="Directory with the exported CSV files."
    ),
    lookback_days: int = typer.Option(90, help="Lookback window in days."),
):
    """Free, no-signup version: terminal summary only (docs/validation-plan.md).
    Top 5 consumers + top 3 optimization candidates, no HTML report."""

    datasets, summary, savings = _run_pipeline(
        from_csv, lookback_days, annual_spend=None, cost_per_gb_day=None
    )

    top5 = sorted(datasets, key=lambda d: d.ingest_gb_per_day, reverse=True)[:5]
    from splunk_spend_auditor.models import Classification

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
    typer.echo("Generate Full Spend Audit -> run `splunk-spend-auditor audit --from-csv ...`")


@app.command()
def audit(
    from_csv: str = typer.Option(
        ..., "--from-csv", help="Directory with the exported CSV files."
    ),
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
):
    """Full audit: classification + potential savings + HTML/Markdown report."""

    datasets, summary, savings = _run_pipeline(
        from_csv, lookback_days, annual_spend, cost_per_gb_day
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
    for fmt, path in written.items():
        typer.echo(f"Report ({fmt}): {path}")


if __name__ == "__main__":
    app()
