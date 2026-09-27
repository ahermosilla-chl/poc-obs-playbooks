"""Formato compartido de valores de volumen (GB/día). Vive fuera de
reports/ para que scoring/rules.py (los textos de explicación) y cli.py
puedan usarlo sin que scoring dependa de reports (ver docs/architecture.md,
separación de capas)."""

from __future__ import annotations


def format_gb_per_day(value: float) -> str:
    """Fase 3C ("Verificar los números" / "HTML quality review"): un
    dataset de bajo volumen real (p.ej. 0.0004 GB/día) redondeaba a
    "0.0 GB/day" en todo el reporte, la terminal y el texto de explicación
    de cada candidato -- se lee como "nada", no como "muy poco", justo para
    el tipo de dataset de bajo volumen que el propio producto también
    audita (docs/scoring.md: REVIEW no requiere alto ingest). Auto-escala a
    la unidad más legible; nunca depende de la escala del entorno
    analizado (aplica igual a un laboratorio pequeño que a un cliente real
    con forwarders de bajo volumen)."""

    if value <= 0:
        return "0 GB"
    if value >= 1:
        return f"{value:,.1f} GB"
    if value >= 1 / 1024:
        return f"{value * 1024:,.1f} MB"
    return f"{value * 1024 * 1024:,.0f} KB"
