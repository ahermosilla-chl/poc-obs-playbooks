"""Aplica classify() y data_value_score() a una lista completa de Dataset,
calculando primero el umbral de "alto ingest" relativo a este entorno
(docs/scoring.md sección 5, regla 4)."""

from __future__ import annotations

import statistics

from splunk_spend_auditor.models import Dataset, SignalAvailability
from splunk_spend_auditor.scoring.rules import (
    HIGH_INGEST_PERCENTILE,
    SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE,
    classify,
    data_value_score,
)


def unavailable_signals_from(
    sources_available: dict[str, SignalAvailability] | None,
) -> frozenset[str]:
    """Fase 3B (D013/D014): traduce el mapa crudo de disponibilidad de
    fuentes (`EnvironmentSummary.sources_available`) al conjunto de nombres
    que `classify()` necesita para bloquear POSSIBLE_WASTE cuando falta
    visibilidad -- ver rules.py, SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE.

    Solo AVAILABLE cuenta como "se puede confiar en un cero". PARTIAL,
    ERROR, UNAVAILABLE y NOT_APPLICABLE todos significan "no se puede
    confiar en el cero de esta fuente para este run" -- ninguno de los
    cuatro es una confirmación real de ausencia de uso."""

    if not sources_available:
        return frozenset()
    return frozenset(
        source
        for source in SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE
        if sources_available.get(source) != SignalAvailability.AVAILABLE
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
    datasets: list[Dataset],
    environment_partial_unknown_ratio: float = 0.0,
    sources_available: dict[str, SignalAvailability] | None = None,
) -> list[Dataset]:
    """sources_available: EnvironmentSummary.sources_available de este run
    (Fase 3B, D013/D014) -- se usa para que ningún dataset alcance
    POSSIBLE_WASTE basado en un "cero" que en realidad es "no se pudo
    consultar". Omitir este argumento (comportamiento previo a Fase 3B)
    asume todas las fuentes disponibles -- útil para tests unitarios que
    prueban `classify()` de forma aislada, pero NUNCA debería omitirse en
    el pipeline real (ver cli.py)."""

    ingest_values = [d.ingest_gb_per_day for d in datasets]
    high_ingest_threshold = _percentile(ingest_values, HIGH_INGEST_PERCENTILE)
    unavailable = unavailable_signals_from(sources_available)

    for dataset in datasets:
        classification, explanation = classify(
            dataset, high_ingest_threshold, environment_partial_unknown_ratio, unavailable
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
