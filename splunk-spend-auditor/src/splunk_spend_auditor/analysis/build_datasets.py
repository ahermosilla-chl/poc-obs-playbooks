"""Motor de análisis: cruza las fuentes crudas (RawCollection) en una lista
de Dataset con toda la evidencia adjunta, ANTES de clasificar (eso lo hace
scoring/). Ver docs/architecture.md, sección "Analysis engine"."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from splunk_spend_auditor.analysis.spl_parser import parse_search
from splunk_spend_auditor.collector.csv_collector import RawCollection
from splunk_spend_auditor.models import Dataset, DatasetKey, EnvironmentSummary, ParserConfidence

_CONFIDENCE_RANK = {
    ParserConfidence.UNKNOWN: 0,
    ParserConfidence.PARTIAL: 1,
    ParserConfidence.HIGH: 2,
}


def _max_confidence(
    a: ParserConfidence, b: ParserConfidence
) -> ParserConfidence:
    return a if _CONFIDENCE_RANK[a] >= _CONFIDENCE_RANK[b] else b


def _infer_as_of_date(collection: RawCollection) -> datetime:
    # Fase 4B: pd.to_datetime() sin errors="coerce" levanta DateParseError
    # (crash sin manejar, hasta el usuario final) ante un solo valor de
    # `date` malformado en una respuesta de Splunk -- confirmado con
    # fuzzing adversarial. Con errors="coerce" un valor inválido se
    # convierte en NaT en vez de abortar todo; `.max()` de pandas ignora
    # NaT salvo que TODA la columna sea NaT, caso que se descarta abajo en
    # vez de comparar NaT contra un datetime real.
    candidates: list[datetime] = []
    if collection.ingest is not None and "date" in collection.ingest.columns:
        ingest_max = pd.to_datetime(collection.ingest["date"], errors="coerce").max()
        if pd.notna(ingest_max):
            candidates.append(ingest_max)
    if (
        collection.audit_searches is not None
        and "date" in collection.audit_searches.columns
        and not collection.audit_searches.empty
    ):
        audit_max = pd.to_datetime(collection.audit_searches["date"], errors="coerce").max()
        if pd.notna(audit_max):
            candidates.append(audit_max)
    if not candidates:
        return datetime.utcnow()
    return max(candidates)


def build_datasets(
    collection: RawCollection, lookback_days: int = 90
) -> tuple[list[Dataset], EnvironmentSummary]:
    as_of = _infer_as_of_date(collection)
    window_30 = as_of - timedelta(days=30)
    window_90 = as_of - timedelta(days=lookback_days)

    datasets: dict[DatasetKey, Dataset] = {}

    def _get(key: DatasetKey) -> Dataset:
        if key not in datasets:
            datasets[key] = Dataset(key=key)
        return datasets[key]

    # --- 1. Ingest (obligatorio) ---
    ingest_df = collection.ingest.copy()
    # errors="coerce" (Fase 4B): ver docstring de _infer_as_of_date -- un
    # solo valor de fecha malformado no puede tirar abajo todo el audit.
    ingest_df["date"] = pd.to_datetime(ingest_df["date"], errors="coerce")
    # Fase 4B: `gb` viene de Splunk (o de un CSV exportado manualmente) sin
    # ninguna garantía de forma -- confirmado que un valor NaN/Infinity
    # (Python's json.loads acepta esos literales no-estándar por defecto,
    # así que una respuesta REST malformada los deja pasar sin error) o
    # negativo envenena silenciosamente el promedio de TODO el dataset
    # (`nan` contamina cualquier suma/media que lo incluya) y de ahí el
    # cálculo de ahorro completo -- el reporte terminaba mostrando
    # literalmente "nan KB/day" en producción. Se descartan filas con `gb`
    # no numérico, no finito o negativo ANTES de agregar -- un volumen de
    # ingest no puede ser negativo ni infinito por definición, así que esto
    # no excluye ningún dato legítimo, solo basura.
    ingest_df["gb"] = pd.to_numeric(ingest_df["gb"], errors="coerce")
    valid_gb = np.isfinite(ingest_df["gb"]) & (ingest_df["gb"] >= 0)
    ingest_df = ingest_df[valid_gb]
    grouped = (
        ingest_df.groupby(["index", "sourcetype"])["gb"]
        .agg(["mean", "count"])
        .reset_index()
    )
    for _, row in grouped.iterrows():
        key = DatasetKey(index=str(row["index"]), sourcetype=str(row["sourcetype"]))
        ds = _get(key)
        # Fase 3C: 8 decimales, no 4 -- con 4 decimales cualquier dataset
        # por debajo de ~50 KB/día redondeaba a 0.0, indistinguible de "no
        # ingiere nada" para el resto del pipeline (clasificación, ahorro,
        # reporte). Confirmado empíricamente contra el laboratorio real
        # (ver queries/ingest_by_index_sourcetype.spl, mismo bug, corregido
        # ahí también -- éste es un segundo punto de redondeo en Python que
        # reintroducía el mismo problema incluso con la query ya corregida).
        ds.ingest_gb_per_day = round(float(row["mean"]), 8)

    # --- 2. Búsquedas interactivas (_audit) ---
    total_search_rows = 0
    partial_or_unknown_rows = 0

    users_30d_by_key: dict[DatasetKey, set] = {}

    if collection.audit_searches is not None and not collection.audit_searches.empty:
        audit_df = collection.audit_searches.copy()
        # errors="coerce" (Fase 4B): una fecha inválida se vuelve NaT, que
        # las comparaciones >= window_30/window_90 de abajo evalúan como
        # False -- la búsqueda simplemente no cuenta para ninguna ventana,
        # en vez de tirar abajo todo el audit con un DateParseError.
        audit_df["date"] = pd.to_datetime(audit_df["date"], errors="coerce")
        # Excluir scheduler tanto por columna is_scheduled como por prefijo
        # de search_id (defensivo: cualquiera de las dos señales basta).
        is_sched_col = audit_df.get("is_scheduled", False)
        is_sched_id = audit_df["search_id"].astype(str).str.startswith("scheduler")
        interactive_df = audit_df[
            ~(is_sched_col.astype(str).str.lower().eq("true") | is_sched_id)
        ]

        for _, row in interactive_df.iterrows():
            total_search_rows += 1
            result = parse_search(str(row.get("search_text", "")))
            if result.confidence != ParserConfidence.HIGH:
                partial_or_unknown_rows += 1
                # PARTIAL/UNKNOWN a nivel de búsqueda individual no se puede
                # atribuir a un dataset concreto -- ver docs/scoring.md
                # sección 3. No se cuenta contra ningún Dataset.
                continue

            in_30d = row["date"] >= window_30
            in_90d = row["date"] >= window_90

            for key in result.datasets:
                ds = _get(key)
                ds.parser_confidence = _max_confidence(
                    ds.parser_confidence, ParserConfidence.HIGH
                )
                if in_90d:
                    ds.interactive_searches_90d += 1
                if in_30d:
                    ds.interactive_searches_30d += 1
                    users_30d_by_key.setdefault(key, set()).add(row.get("user"))

        for key, users in users_30d_by_key.items():
            datasets[key].unique_users_30d = len(users)

    # --- 3. Saved searches / alertas programadas ---
    if collection.saved_searches is not None and not collection.saved_searches.empty:
        for _, row in collection.saved_searches.iterrows():
            total_search_rows += 1
            result = parse_search(str(row.get("search_text", "")))
            if result.confidence != ParserConfidence.HIGH:
                partial_or_unknown_rows += 1
                continue

            is_scheduled = str(row.get("is_scheduled", "false")).lower() == "true"
            has_alert = str(row.get("has_alert_action", "false")).lower() == "true"

            for key in result.datasets:
                ds = _get(key)
                ds.parser_confidence = _max_confidence(
                    ds.parser_confidence, ParserConfidence.HIGH
                )
                if is_scheduled:
                    ds.is_scheduled = True
                    ds.scheduled_search_count += 1
                if has_alert:
                    ds.has_alert_action = True

    # --- 4. Dashboards (manual, opcional) ---
    if (
        collection.dashboards_used is not None
        and not collection.dashboards_used.empty
    ):
        for _, row in collection.dashboards_used.iterrows():
            key = DatasetKey(index=str(row["index"]), sourcetype=str(row["sourcetype"]))
            ds = _get(key)
            ds.used_in_dashboards = True

    # --- 5. Última actividad de ingest ---
    if collection.last_seen is not None and not collection.last_seen.empty:
        for _, row in collection.last_seen.iterrows():
            key = DatasetKey(index=str(row["index"]), sourcetype=str(row["sourcetype"]))
            ds = _get(key)
            ds.last_seen_days_ago = float(row["last_seen_days_ago"])

    # --- 6. Overrides manuales de protección ---
    for idx, st in collection.protected_overrides:
        key = DatasetKey(index=idx, sourcetype=st)
        ds = _get(key)
        ds.is_protected = True
        ds.protection_reason = "Manual override (protected_overrides.txt)"

    partial_unknown_ratio = (
        round(partial_or_unknown_rows / total_search_rows, 4)
        if total_search_rows
        else 0.0
    )

    summary = EnvironmentSummary(
        total_datasets=len(datasets),
        datasets_with_high_confidence_evidence=sum(
            1 for d in datasets.values() if d.parser_confidence == ParserConfidence.HIGH
        ),
        partial_or_unknown_ratio=partial_unknown_ratio,
        lookback_days=lookback_days,
        sources_available=dict(collection.sources_available),
        diagnostics=dict(collection.diagnostics),
    )

    return list(datasets.values()), summary
