"""Ediciones y capacidades de producto (Fase 5C).

Único lugar donde se decide qué puede hacer cada edición:

    (Fase 5D) validación de licencia  ->  Entitlement  ->  Capabilities

El resto del código pregunta por una CAPACIDAD (`entitlement.allows(...)`),
nunca por la edición. Collectors, análisis y scoring no conocen este módulo.

No existe ningún flag, variable de entorno ni archivo que cambie la edición:
`resolve_entitlement()` devuelve Community hasta que la Fase 5D conecte una
fuente de entitlement real. Los tests inyectan el entitlement en el borde de
la aplicación (reemplazando `resolve_entitlement` en `cli`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Edition(str, Enum):
    COMMUNITY = "Log Spend Auditor Community"
    PRO = "Log Spend Auditor Pro"


class Capability(str, Enum):
    QUICKSCAN = "quickscan"      # resumen agregado + vista previa limitada
    FULL_QUICKSCAN = "full_quickscan"  # inventario/top consumers/candidatos completos en terminal
    FULL_AUDIT = "full_audit"    # auditoría completa de un entorno real
    FULL_REPORT = "full_report"  # reportes HTML/Markdown completos de un entorno real


_CAPABILITIES: dict[Edition, frozenset[Capability]] = {
    Edition.COMMUNITY: frozenset({Capability.QUICKSCAN}),
    Edition.PRO: frozenset(Capability),
}


@dataclass(frozen=True)
class Entitlement:
    edition: Edition

    def allows(self, capability: Capability) -> bool:
        return capability in _CAPABILITIES[self.edition]


COMMUNITY = Entitlement(Edition.COMMUNITY)
PRO = Entitlement(Edition.PRO)


def resolve_entitlement() -> Entitlement:
    """Entitlement efectivo de esta ejecución. Fase 5D reemplazará el cuerpo
    por la validación de licencia; hoy toda ejecución es Community."""

    return COMMUNITY
