"""Modelos de dominio. Ver docs/architecture.md, "Por qué esta forma"."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ParserConfidence(str, Enum):
    """Ver docs/scoring.md, sección 3."""

    HIGH = "HIGH"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class SignalAvailability(str, Enum):
    """Fase 3B (D013) -- calidad/disponibilidad de una fuente de señal
    (ingest, audit_searches, saved_searches, dashboards_used, last_seen).

    Reemplaza el `dict[str, bool]` de Fase 2/3A, que solo podía distinguir
    "presente" de "ausente" y por lo tanto no podía representar la
    diferencia entre "se consultó y el resultado es 0" (AVAILABLE) y "no fue
    posible obtener la señal" (ERROR/UNAVAILABLE) -- ver DECISIONS.md D013.

    - AVAILABLE: la fuente se consultó con éxito. El resultado (incluso si
      son 0 filas) es una respuesta real y puede usarse como evidencia de
      "confirmado ausente", no solo de "no se sabe".
    - UNAVAILABLE: la fuente nunca se consultó (archivo CSV no existía, o el
      collector no la implementa para este modo). No es un error -- es una
      ausencia estructural, conocida de antemano.
    - PARTIAL: la fuente se consultó pero el resultado puede estar
      incompleto (p.ej. un límite de paginación/`map` alcanzado). Se trata
      igual que UNAVAILABLE para decisiones de clasificación -- no se
      confía en un "cero" parcial -- pero se reporta distinto porque hubo
      señal real, solo que no se puede garantizar que sea completa.
    - ERROR: se intentó consultar la fuente y Splunk/la red devolvió un
      error (401/403/404/429/5xx, timeout, TLS, JSON malformado, etc.).
      Distinto de UNAVAILABLE porque aquí SÍ hubo un intento que falló --
      relevante para diagnóstico y para el mensaje que ve el usuario.
    - NOT_APPLICABLE: la fuente no es un resultado de query en absoluto para
      este contexto (p.ej. `protected_overrides` cuando el usuario no pasó
      ningún archivo de overrides -- es una ausencia de configuración
      opcional, no la pérdida de una señal de uso real)."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


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
    sources_available: dict[str, SignalAvailability] = field(default_factory=dict)
