"""Reglas de clasificación y protección. Traducción directa de
docs/scoring.md a código -- si se cambia una regla aquí, actualizar también
la documentación (y viceversa)."""

from __future__ import annotations

import re

from splunk_spend_auditor.formatting import format_gb_per_day
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

# Fase 3B (D013/D014) -- fuentes cuya AUSENCIA (SignalAvailability distinto
# de AVAILABLE) impide confiar en "cero uso" para la regla POSSIBLE_WASTE.
# NO incluye "dashboards_used": su ausencia es una limitación estructural
# ya documentada y aceptada desde Fase 2 (docs/splunk-data-sources.md
# sección 7) -- el MVP nunca garantizó tener esa fuente, a diferencia de
# audit_searches/saved_searches, que si fallan representan una pérdida de
# visibilidad NUEVA (no un límite de diseño conocido de antemano) y son
# señales críticas para D007 ("distinguir sin búsquedas manuales de sin
# uso"). Incluir dashboards_used aquí bloquearía POSSIBLE_WASTE en casi
# todos los entornos reales (la mayoría de usuarios no exportan ese CSV
# opcional) y sería un cambio de comportamiento no pedido -- ver
# DECISIONS.md D013.
SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE = frozenset({"audit_searches", "saved_searches"})


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
    unavailable_signals: frozenset[str] = frozenset(),
) -> tuple[Classification, str, bool]:
    """docs/scoring.md sección 5. Devuelve
    (categoría, explicación, excluded_from_savings).

    excluded_from_savings (Fase 3B/D015): True cuando el dataset cae en
    REVIEW sin ninguna base real para asignarle peso en el cálculo de
    ahorro potencial -- porque la misma señal faltante que impidió
    confirmar "cero uso" (D014) también podría haber confirmado
    HIGH_VALUE. Ver models.Dataset.excluded_from_savings_estimate y
    scoring/savings.py.

    high_ingest_threshold_gb: percentil 75 de GB/día de este entorno.

    environment_partial_unknown_ratio: fracción de búsquedas del ENTORNO
    COMPLETO (no de este dataset en particular -- ver docs/scoring.md
    sección 3, "Regla dura") que se resolvieron con confianza PARTIAL o
    UNKNOWN. Si esta fracción es alta, la ausencia de evidencia HIGH para
    cualquier dataset deja de ser confiable (podría estar oculto detrás de
    una macro que no se pudo resolver en NINGÚN lado del entorno), así que
    no se puede confiar en el "silencio" de ningún dataset individual. Si es
    baja, el entorno tiene buena cobertura de parsing y el silencio de un
    dataset específico SÍ es evidencia real de falta de uso.

    unavailable_signals: nombres de fuentes (ver
    SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE) que NO están
    SignalAvailability.AVAILABLE en este run -- Fase 3B (D013/D014). Si
    alguna de las fuentes necesarias para confirmar "cero uso" no está
    disponible, la regla POSSIBLE_WASTE nunca puede aplicarse: el 0 que
    trae el Dataset en esos campos podría ser "confirmado" o simplemente
    "nunca se pudo consultar" y este parámetro es la única forma de
    distinguirlos en este punto (Dataset por sí solo no lo sabe -- ver
    docs/architecture.md, "Manejo de errores")."""

    # Regla 1: PROTECTED
    if dataset.is_protected:
        reason = dataset.protection_reason or "Manual override"
        return Classification.PROTECTED, (
            f"Protected dataset ({reason}). Never auto-classified as waste, "
            "regardless of usage signals."
        ), False
    if matches_default_protected_pattern(dataset):
        return Classification.PROTECTED, (
            "Protected dataset: name matches a default security/compliance "
            "pattern. Never auto-classified as waste, regardless of usage "
            "signals."
        ), False

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
        ), False

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
        ), False

    # A partir de acá el dataset NO pudo confirmarse como HIGH_VALUE. Si
    # además falta una fuente crítica (audit_searches/saved_searches), ese
    # "no pudo confirmarse" es ambiguo: el dataset podría en realidad ser
    # HIGH_VALUE (p.ej. is_scheduled=True que nunca pudimos ver porque
    # saved_searches falló) -- ver DECISIONS.md D015. Cualquier REVIEW al
    # que se llegue desde aquí en adelante, mientras esto sea cierto, no
    # tiene base real para llevar NI SIQUIERA el peso reducido de REVIEW en
    # el cálculo de ahorro (scoring/savings.py) -- se marca
    # excluded_from_savings=True.
    missing_for_zero_usage = unavailable_signals & SOURCES_REQUIRED_FOR_CONFIRMED_ZERO_USAGE
    high_value_unconfirmable = bool(missing_for_zero_usage)

    # Regla 4: POSSIBLE_WASTE
    is_high_ingest = dataset.ingest_gb_per_day >= high_ingest_threshold_gb
    has_zero_usage = (
        dataset.interactive_searches_90d == 0
        and not dataset.is_scheduled
        and not dataset.has_alert_action
        and not dataset.used_in_dashboards
    )
    if is_high_ingest and has_zero_usage and missing_for_zero_usage:
        # Fase 3B, regla de seguridad (D013/D014): con evidencia completa
        # este dataset SERÍA POSSIBLE_WASTE, pero no se puede confirmar
        # "cero uso" porque una o más fuentes necesarias no están
        # disponibles -- la pérdida de visibilidad nunca puede producir una
        # clasificación MÁS agresiva. Se degrada a REVIEW, excluido del
        # cálculo de ahorro (ver arriba y D015) en vez de contar con el
        # peso 0.5 normal de REVIEW -- de lo contrario, un dataset que en
        # realidad era HIGH_VALUE (peso 0 en ahorro) podría terminar
        # aportando MÁS ahorro potencial estimado que con evidencia
        # completa, exactamente el caso real que originó D015.
        missing_label = ", ".join(sorted(missing_for_zero_usage))
        return Classification.REVIEW, (
            f"This dataset ingests {format_gb_per_day(dataset.ingest_gb_per_day)}/day "
            f"and shows no usage in the signals that ARE available, but "
            f"{missing_label} could not be checked in this run "
            f"(insufficient visibility, not confirmed absence of usage). "
            f"Cannot confirm zero usage -- treated as REVIEW, not "
            f"POSSIBLE_WASTE, until those signals are available."
        ), True
    if is_high_ingest and has_zero_usage:
        return Classification.POSSIBLE_WASTE, (
            f"This dataset appears as a candidate because it ingests "
            f"{format_gb_per_day(dataset.ingest_gb_per_day)}/day, has no interactive "
            f"searches in the last 90 days, and was not found in alerts, "
            f"dashboards, or scheduled saved searches."
        ), False

    # Regla 5: REVIEW
    if has_zero_usage or dataset.interactive_searches_90d <= 2:
        return Classification.REVIEW, (
            f"This dataset ingests {format_gb_per_day(dataset.ingest_gb_per_day)}/day "
            f"with limited observed usage "
            f"({dataset.interactive_searches_90d} interactive searches in "
            "90 days). Manual validation recommended before any action."
        ), high_value_unconfirmable

    # Regla 6: NORMAL
    return Classification.NORMAL, (
        "This dataset shows a typical ingest-to-usage ratio for this "
        "environment. No action suggested."
    ), False
