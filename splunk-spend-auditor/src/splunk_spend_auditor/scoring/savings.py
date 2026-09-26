"""Cálculo de ahorro potencial. Traducción directa de docs/scoring.md
sección 8. Nunca "guaranteed saving" -- siempre "potential saving"."""

from __future__ import annotations

from dataclasses import dataclass

from splunk_spend_auditor.models import Classification, Dataset
from splunk_spend_auditor.scoring.rules import REVIEW_WEIGHT


@dataclass
class SavingsEstimate:
    current_ingest_gb_day: float
    candidate_gb_day: float
    potential_reduction_pct: float
    possible_waste_gb_day: float
    review_gb_day: float
    annual_spend_input: float | None = None
    cost_per_gb_day_input: float | None = None
    potential_annual_saving: float | None = None


def compute_savings(
    datasets: list[Dataset],
    annual_spend: float | None = None,
    cost_per_gb_day: float | None = None,
) -> SavingsEstimate:
    """docs/scoring.md sección 8. Exactamente una de annual_spend o
    cost_per_gb_day debería darse; si se dan ambas, se prioriza
    annual_spend (más directo: el usuario ya sabe lo que paga en total).
    Si no se da ninguna, potential_annual_saving queda en None y el reporte
    solo muestra el porcentaje de reducción, no una cifra en dólares."""

    current_ingest_gb_day = sum(d.ingest_gb_per_day for d in datasets)

    possible_waste_gb_day = sum(
        d.ingest_gb_per_day
        for d in datasets
        if d.classification == Classification.POSSIBLE_WASTE
    )
    review_gb_day = sum(
        d.ingest_gb_per_day
        for d in datasets
        if d.classification == Classification.REVIEW
    )

    candidate_gb_day = possible_waste_gb_day + REVIEW_WEIGHT * review_gb_day

    potential_reduction_pct = (
        candidate_gb_day / current_ingest_gb_day if current_ingest_gb_day > 0 else 0.0
    )

    potential_annual_saving: float | None = None
    if annual_spend is not None:
        potential_annual_saving = annual_spend * potential_reduction_pct
    elif cost_per_gb_day is not None:
        potential_annual_saving = candidate_gb_day * cost_per_gb_day * 365

    return SavingsEstimate(
        current_ingest_gb_day=round(current_ingest_gb_day, 2),
        candidate_gb_day=round(candidate_gb_day, 2),
        potential_reduction_pct=round(potential_reduction_pct, 4),
        possible_waste_gb_day=round(possible_waste_gb_day, 2),
        review_gb_day=round(review_gb_day, 2),
        annual_spend_input=annual_spend,
        cost_per_gb_day_input=cost_per_gb_day,
        potential_annual_saving=(
            round(potential_annual_saving, 2)
            if potential_annual_saving is not None
            else None
        ),
    )
