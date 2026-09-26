"""Modelos de dominio. Ver docs/architecture.md, "Por qué esta forma"."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ParserConfidence(str, Enum):
    """Ver docs/scoring.md, sección 3."""

    HIGH = "HIGH"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class Classification(str, Enum):
    """Ver docs/scoring.md, sección 5. El orden aquí no importa para la
    lógica (las reglas se evalúan explícitamente en scoring/classify.py),
    pero se lista en el mismo orden que la documentación para que sea fácil
    de seguir."""

    PROTECTED = "PROTECTED"
    UNKNOWN = "UNKNOWN"
    HIGH_VALUE = "HIGH_VALUE"
    POSSIBLE_WASTE = "POSSIBLE_WASTE"
    REVIEW = "REVIEW"
    NORMAL = "NORMAL"


@dataclass(frozen=True)
class DatasetKey:
    """La unidad de análisis: (index, sourcetype). Ver DECISIONS.md D004 —
    deliberadamente NO incluye host ni source."""

    index: str
    sourcetype: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.index}:{self.sourcetype}"


@dataclass
class Dataset:
    """Todo lo que sabemos de un (index, sourcetype) tras el análisis, antes
    de aplicar las reglas de clasificación. Ver docs/scoring.md, sección 2."""

    key: DatasetKey

    # Volumen
    ingest_gb_per_day: float = 0.0

    # Uso
    interactive_searches_30d: int = 0
    interactive_searches_90d: int = 0
    unique_users_30d: int = 0
    is_scheduled: bool = False
    scheduled_search_count: int = 0
    has_alert_action: bool = False
    used_in_dashboards: bool = False

    # Actividad de ingest
    last_seen_days_ago: float | None = None

    # Confianza: el nivel de confianza MÁS ALTO alcanzado por cualquier
    # evidencia (búsqueda interactiva o saved search) que mencione este
    # dataset. Si ninguna evidencia lo menciona en absoluto, queda en
    # ParserConfidence.UNKNOWN por defecto (nunca vimos nada, ni con certeza
    # ni sin ella).
    parser_confidence: ParserConfidence = ParserConfidence.UNKNOWN

    # Protección
    is_protected: bool = False
    protection_reason: str | None = None

    # Se completa en scoring/
    classification: Classification | None = None
    data_value_score: int | None = None
    explanation: str | None = None


@dataclass
class EnvironmentSummary:
    """Métricas agregadas de todo el entorno, para la sección Methodology
    del reporte (docs/report-design.md, sección 10)."""

    total_datasets: int = 0
    datasets_with_high_confidence_evidence: int = 0
    partial_or_unknown_ratio: float = 0.0
    lookback_days: int = 90
    sources_available: dict[str, bool] = field(default_factory=dict)
