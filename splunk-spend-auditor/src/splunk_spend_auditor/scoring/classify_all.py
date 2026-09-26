"""Aplica classify() y data_value_score() a una lista completa de Dataset,
calculando primero el umbral de "alto ingest" relativo a este entorno
(docs/scoring.md sección 5, regla 4)."""

from __future__ import annotations

import statistics

from splunk_spend_auditor.models import Dataset
from splunk_spend_auditor.scoring.rules import (
    HIGH_INGEST_PERCENTILE,
    classify,
    data_value_score,
)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    # Interpolación lineal simple (método "inclusive"), sin dependencias
    # externas -- suficiente para el volumen de datos de este producto
    # (cientos a miles de datasets, no millones).
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def classify_all(
    datasets: list[Dataset], environment_partial_unknown_ratio: float = 0.0
) -> list[Dataset]:
    ingest_values = [d.ingest_gb_per_day for d in datasets]
    high_ingest_threshold = _percentile(ingest_values, HIGH_INGEST_PERCENTILE)

    for dataset in datasets:
        classification, explanation = classify(
            dataset, high_ingest_threshold, environment_partial_unknown_ratio
        )
        dataset.classification = classification
        dataset.explanation = explanation
        dataset.data_value_score = data_value_score(dataset)

    return datasets


def high_ingest_threshold_for(datasets: list[Dataset]) -> float:
    """Expuesto para que el reporte pueda mostrar el umbral usado
    (transparencia -- ver docs/report-design.md sección 10, Methodology)."""

    return _percentile(
        [d.ingest_gb_per_day for d in datasets], HIGH_INGEST_PERCENTILE
    )
