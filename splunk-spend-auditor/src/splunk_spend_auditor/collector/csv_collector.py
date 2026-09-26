"""Collector para el modo CSV (D002). Lee los archivos que produce el
usuario exportando manualmente las queries de queries/*.spl (o el
Quickscan gratuito) desde un directorio local. Nunca requiere credenciales
de Splunk. Ver docs/architecture.md, "Flujo de ejecución (modo CSV)"."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


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

    sources_available: dict[str, bool] = field(default_factory=dict)


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
    for line in path.read_text().splitlines():
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
        collection.sources_available[attr] = df is not None

    collection.protected_overrides = _read_protected_overrides(
        directory / "protected_overrides.txt"
    )
    collection.sources_available["protected_overrides"] = bool(
        collection.protected_overrides
    )

    if collection.ingest is None:
        # El ingest es la única fuente estrictamente obligatoria -- sin ella
        # no hay "spend" que auditar en absoluto.
        raise FileNotFoundError(
            f"No se encontró {_EXPECTED_FILES['ingest']} en {directory}. "
            "Esta fuente es obligatoria (ver docs/splunk-data-sources.md)."
        )

    return collection
