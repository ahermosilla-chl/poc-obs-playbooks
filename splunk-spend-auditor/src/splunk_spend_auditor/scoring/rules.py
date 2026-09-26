"""Reglas de clasificación y protección. Traducción directa de
docs/scoring.md a código -- si se cambia una regla aquí, actualizar también
la documentación (y viceversa)."""

from __future__ import annotations

import re

from splunk_spend_auditor.models import Classification, Dataset, ParserConfidence

# docs/scoring.md sección 6 -- patrones protegidos por defecto. Case
# insensitive, se evalúan contra "index:sourcetype" completo para cubrir
# el caso en que el nombre sensible está en el index, en el sourcetype, o
# en ambos.
DEFAULT_PROTECTED_PATTERNS = [
    r"audit",
    r"compliance",
    r"security",
    r"firewall",
    r"\bids\b",
    r"\bips\b",
    r"auth",
    r"forensic",
    r"siem",
    r"\bedr\b",
    r"\bdlp\b",
]

_PROTECTED_RE = re.compile("|".join(DEFAULT_PROTECTED_PATTERNS), re.IGNORECASE)

# docs/scoring.md sección 4 -- constante nombrada, ver DECISIONS.md/scoring.md
# para el razonamiento del peso 0.5 en REVIEW.
REVIEW_WEIGHT = 0.5

# docs/scoring.md sección 5, regla 4 -- percentil de ingest que define "alto
# volumen" para POSSIBLE_WASTE.
HIGH_INGEST_PERCENTILE = 0.75

# docs/scoring.md sección 5, regla 3 -- umbral de búsquedas interactivas que
# por sí solo basta para HIGH_VALUE.
HIGH_VALUE_SEARCH_THRESHOLD = 10

# docs/scoring.md sección 3, "Regla dura" -- por encima de este umbral de
# partial_or_unknown_ratio del ENTORNO, ya no se confía en el silencio de
# ningún dataset individual como evidencia de falta de uso.
UNKNOWN_ENVIRONMENT_RATIO_THRESHOLD = 0.5


def matches_default_protected_pattern(dataset: Dataset) -> bool:
    combined = f"{dataset.key.index}:{dataset.key.sourcetype}"
    return bool(_PROTECTED_RE.search(combined))


def data_value_score(dataset: Dataset) -> int:
    """docs/scoring.md sección 4. Suma simple y auditable -- nunca ML."""

    score = 0
    score += min(dataset.interactive_searches_30d, 30)
    score += 25 if dataset.is_scheduled else 0
    score += 20 if dataset.has_alert_action else 0
    score += 15 if dataset.used_in_dashboards else 0
    if dataset.unique_users_30d >= 3:
        score += 10
    elif dataset.unique_users_30d >= 1:
        score += 5
    return min(score, 100)


def classify(
    dataset: Dataset,
    high_ingest_threshold_gb: float,
    environment_partial_unknown_ratio: float,
) -> tuple[Classification, str]:
    """docs/scoring.md sección 5. Devuelve (categoría, explicación).

    high_ingest_threshold_gb: percentil 75 de GB/día de este entorno.

    environment_partial_unknown_ratio: fracción de búsquedas del ENTORNO
    COMPLETO (no de este dataset en particular -- ver docs/scoring.md
    sección 3, "Regla dura") que se resolvieron con confianza PARTIAL o
    UNKNOWN. Si esta fracción es alta, la ausencia de evidencia HIGH para
    cualquier dataset deja de ser confiable (podría estar oculto detrás de
    una macro que no se pudo resolver en NINGÚN lado del entorno), así que
    no se puede confiar en el "silencio" de ningún dataset individual. Si es
    baja, el entorno tiene buena cobertura de parsing y el silencio de un
    dataset específico SÍ es evidencia real de falta de uso."""

    # Regla 1: PROTECTED
    if dataset.is_protected:
        reason = dataset.protection_reason or "Manual override"
        return Classification.PROTECTED, (
            f"Protected dataset ({reason}). Never auto-classified as waste, "
            "regardless of usage signals."
        )
    if matches_default_protected_pattern(dataset):
        return Classification.PROTECTED, (
            "Protected dataset: name matches a default security/compliance "
            "pattern. Never auto-classified as waste, regardless of usage "
            "signals."
        )

    # Regla 2: UNKNOWN -- solo se aplica cuando el ENTORNO en su conjunto
    # tiene mala cobertura de parsing (ver docs/scoring.md sección 3, "Regla
    # dura"). Si el dataset mismo tiene evidencia HIGH, esta regla no aplica
    # de todas formas (ya sabemos con certeza que se usa). Un dataset SIN
    # evidencia HIGH propia, en un entorno con buena cobertura global, no
    # cae aquí -- su "silencio" se trata como señal real en las reglas 3-6.
    if (
        dataset.parser_confidence != ParserConfidence.HIGH
        and environment_partial_unknown_ratio > UNKNOWN_ENVIRONMENT_RATIO_THRESHOLD
    ):
        return Classification.UNKNOWN, (
            "Insufficient high-confidence evidence to determine usage for "
            "this dataset. This environment has a high proportion of "
            f"partial/unknown search evidence overall "
            f"({environment_partial_unknown_ratio * 100:.0f}%, e.g. searches "
            "using macros or eventtypes that could not be resolved), so the "
            "absence of a direct match cannot be trusted as real evidence "
            "of no usage. Not classified as waste."
        )

    # Regla 3: HIGH_VALUE
    if (
        dataset.is_scheduled
        or dataset.has_alert_action
        or dataset.interactive_searches_30d >= HIGH_VALUE_SEARCH_THRESHOLD
        or dataset.used_in_dashboards
    ):
        signals = []
        if dataset.is_scheduled:
            signals.append("is used by a scheduled search")
        if dataset.has_alert_action:
            signals.append("triggers an alert")
        if dataset.interactive_searches_30d >= HIGH_VALUE_SEARCH_THRESHOLD:
            signals.append(
                f"has {dataset.interactive_searches_30d} interactive searches in 30 days"
            )
        if dataset.used_in_dashboards:
            signals.append("is used in a dashboard")
        return Classification.HIGH_VALUE, (
            "This dataset is actively used: " + "; ".join(signals) + "."
        )

    # Regla 4: POSSIBLE_WASTE
    is_high_ingest = dataset.ingest_gb_per_day >= high_ingest_threshold_gb
    has_zero_usage = (
        dataset.interactive_searches_90d == 0
        and not dataset.is_scheduled
        and not dataset.has_alert_action
        and not dataset.used_in_dashboards
    )
    if is_high_ingest and has_zero_usage:
        return Classification.POSSIBLE_WASTE, (
            f"This dataset appears as a candidate because it ingests "
            f"{dataset.ingest_gb_per_day:.1f} GB/day, has no interactive "
            f"searches in the last 90 days, and was not found in alerts, "
            f"dashboards, or scheduled saved searches."
        )

    # Regla 5: REVIEW
    if has_zero_usage or dataset.interactive_searches_90d <= 2:
        return Classification.REVIEW, (
            f"This dataset ingests {dataset.ingest_gb_per_day:.1f} GB/day "
            f"with limited observed usage "
            f"({dataset.interactive_searches_90d} interactive searches in "
            "90 days). Manual validation recommended before any action."
        )

    # Regla 6: NORMAL
    return Classification.NORMAL, (
        "This dataset shows a typical ingest-to-usage ratio for this "
        "environment. No action suggested."
    )
