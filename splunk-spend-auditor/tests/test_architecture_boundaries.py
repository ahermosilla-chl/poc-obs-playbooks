"""Guardrail de arquitectura (Fase 3B, item 3: "Responsabilidad del
collector"). Los collectors (CSV y REST) recolectan datos crudos y
describen su disponibilidad -- NUNCA decide clasificación
(POSSIBLE_WASTE/PROTECTED/REVIEW/UNKNOWN). Esa responsabilidad es exclusiva
de scoring/. Este test lee el código fuente de los collectors y falla si
alguno importa el módulo de scoring o el enum Classification, para que una
futura violación de esta separación se detecte en CI, no en code review."""

from __future__ import annotations

import ast
from pathlib import Path

_COLLECTOR_FILES = [
    Path(__file__).resolve().parent.parent
    / "src"
    / "splunk_spend_auditor"
    / "collector"
    / "csv_collector.py",
    Path(__file__).resolve().parent.parent
    / "src"
    / "splunk_spend_auditor"
    / "collector"
    / "rest_collector.py",
]


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_collectors_never_import_the_scoring_package():
    for path in _COLLECTOR_FILES:
        imports = _imported_module_names(path)
        scoring_imports = {name for name in imports if "scoring" in name}
        assert not scoring_imports, (
            f"{path.name} importa {scoring_imports} -- el collector no debe "
            "conocer las reglas de clasificación (ver docs/architecture.md)."
        )


def test_collectors_only_import_the_signal_availability_enum_from_models():
    """Los collectors pueden usar SignalAvailability (describir disponibilidad
    de datos), pero no Classification (decidir una categoría de negocio)."""

    for path in _COLLECTOR_FILES:
        source = path.read_text(encoding="utf-8")
        assert "Classification" not in source, (
            f"{path.name} menciona 'Classification' -- eso es responsabilidad "
            "de scoring/rules.py, no del collector."
        )
