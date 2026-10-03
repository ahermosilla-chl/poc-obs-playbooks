"""Collector para el modo CSV (D002). Lee los archivos que produce el
usuario exportando manualmente las queries de queries/*.spl (o el
Quickscan gratuito) desde un directorio local. Nunca requiere credenciales
de Splunk. Ver docs/architecture.md, "Flujo de ejecución (modo CSV)"."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from splunk_spend_auditor.models import SignalAvailability


@dataclass
class RawCollection:
    """Los datos crudos tal como vienen de los CSV, antes de construir los
    Dataset (eso lo hace analysis/build_datasets.py). Cada campo es None si
    el archivo correspondiente no existía en el directorio -- el motor de
    análisis debe manejar explícitamente la ausencia (ver
    docs/architecture.md, "Manejo de errores y datos parciales"), nunca
    asumir silenciosamente que significa "cero actividad"."""

    ingest: pd.DataFrame | None = None
    audit_searches: pd.DataFrame | None = None
    saved_searches: pd.DataFrame | None = None
    dashboards_used: pd.DataFrame | None = None
    last_seen: pd.DataFrame | None = None
    protected_overrides: set[tuple[str, str]] = field(default_factory=set)

    # Ver models.SignalAvailability (D013) -- un archivo presente (incluso
    # vacío) es AVAILABLE; ausente es UNAVAILABLE. El modo CSV nunca produce
    # PARTIAL/ERROR -- esos estados son específicos de fuentes "en vivo"
    # (REST) donde una consulta puede fallar a mitad de camino.
    sources_available: dict[str, SignalAvailability] = field(default_factory=dict)

    # Fase 3B/D015: razón legible por humanos para una fuente degradada,
    # cuando hay algo más específico que decir que el estado genérico (p.ej.
    # "no se pudo confirmar acceso a _audit" en vez de solo "UNAVAILABLE").
    # Opcional -- la mayoría de las fuentes degradadas no la necesitan.
    diagnostics: dict[str, str] = field(default_factory=dict)


_EXPECTED_FILES = {
    "ingest": "ingest_by_index_sourcetype.csv",
    "audit_searches": "audit_searches.csv",
    "saved_searches": "saved_searches.csv",
    "dashboards_used": "dashboards_used.csv",
    "last_seen": "last_seen.csv",
}


def _read_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def _read_protected_overrides(path: Path) -> set[tuple[str, str]]:
    overrides: set[tuple[str, str]] = set()
    if not path.exists():
        return overrides
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        idx, st = line.split(":", 1)
        overrides.add((idx.strip(), st.strip()))
    return overrides


def load_from_directory(directory: str | Path) -> RawCollection:
    """Carga todos los archivos esperados desde un directorio. Archivos
    ausentes quedan como None y se registran en sources_available para que
    el reporte final (sección Methodology) sea honesto sobre qué se pudo
    analizar y qué no."""

    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"No existe el directorio: {directory}")

    collection = RawCollection()
    for attr, filename in _EXPECTED_FILES.items():
        df = _read_optional_csv(directory / filename)
        setattr(collection, attr, df)
        collection.sources_available[attr] = (
            SignalAvailability.AVAILABLE if df is not None else SignalAvailability.UNAVAILABLE
        )

    overrides_path = directory / "protected_overrides.txt"
    collection.protected_overrides = _read_protected_overrides(overrides_path)
    collection.sources_available["protected_overrides"] = (
        SignalAvailability.AVAILABLE
        if overrides_path.exists()
        else SignalAvailability.NOT_APPLICABLE
    )

    if collection.ingest is None:
        # El ingest es la única fuente estrictamente obligatoria -- sin ella
        # no hay "spend" que auditar en absoluto.
        raise FileNotFoundError(
            f"No se encontró {_EXPECTED_FILES['ingest']} en {directory}. "
            "Esta fuente es obligatoria (ver docs/splunk-data-sources.md)."
        )

    return collection
