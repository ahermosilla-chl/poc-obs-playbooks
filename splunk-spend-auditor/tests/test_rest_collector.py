"""Tests de regresión para bugs reales encontrados en Fase 3A al validar el
collector REST contra una instancia Splunk Enterprise 10.4.3 real (ver
DECISIONS.md D010/D011 y PROJECT_STATUS.md). Usan httpx.MockTransport para
no depender de una instancia Splunk real ni de red."""

from __future__ import annotations

import httpx
import pandas as pd
import pytest

from splunk_spend_auditor.collector.rest_collector import RestConfig, collect


def _oneshot_response(results: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"results": results})


def _saved_searches_response(entries: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"entry": entries})


def _saved_search_entry(name: str, owner: str, search: str = "index=main") -> dict:
    return {
        "name": name,
        "acl": {"owner": owner},
        "content": {
            "search": search,
            "is_scheduled": False,
            "cron_schedule": "",
            "actions": "",
            "next_scheduled_time": "",
        },
    }


def test_oneshot_search_coerces_fully_numeric_columns_to_numeric():
    """Bug real (Fase 3A): la REST API de Splunk devuelve TODOS los valores
    de resultados como string, incluso "gb". Sin coerción, build_datasets
    falla con TypeError al hacer .agg(["mean"]) sobre una columna de texto."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/services/search/jobs":
            body = request.content.decode()
            if "license_usage" in body:
                return _oneshot_response(
                    [
                        {"date": "2026-09-01", "index": "main", "sourcetype": "access", "gb": "0.0004"},
                        {"date": "2026-09-02", "index": "main", "sourcetype": "access", "gb": "0.0006"},
                    ]
                )
            return _oneshot_response([])
        if request.url.path == "/servicesNS/-/-/saved/searches":
            return _saved_searches_response([])
        raise AssertionError(f"unexpected request: {request.url}")

    config = RestConfig(
        host="lab", token="fake-token", transport=httpx.MockTransport(handler)
    )
    collection = collect(config, "queries")

    assert collection.ingest is not None
    assert not collection.ingest.empty
    assert pd.api.types.is_numeric_dtype(collection.ingest["gb"])
    # Las columnas de texto puro deben seguir siendo texto.
    assert not pd.api.types.is_numeric_dtype(collection.ingest["index"])
    assert collection.ingest["gb"].sum() == pytest.approx(0.001, abs=1e-9)


def test_oneshot_search_leaves_mixed_columns_as_text():
    """Una columna que NO es 100% numérica (p.ej. "index") nunca debe
    convertirse -- conversión parcial perdería datos silenciosamente."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/services/search/jobs":
            return _oneshot_response(
                [{"index": "main", "value": "10"}, {"index": "(UNKNOWN)", "value": "20"}]
            )
        return _saved_searches_response([])

    config = RestConfig(
        host="lab", token="fake-token", transport=httpx.MockTransport(handler)
    )
    collection = collect(config, "queries")

    assert not pd.api.types.is_numeric_dtype(collection.ingest["index"])
    assert pd.api.types.is_numeric_dtype(collection.ingest["value"])


def test_saved_searches_excludes_splunk_bundled_content_owned_by_nobody():
    """Bug real (Fase 3A): /servicesNS/-/-/saved/searches devuelve también
    el contenido instalado por Splunk mismo (~170 saved searches de sistema
    en una instancia recién instalada, confirmado empíricamente). Owner
    "nobody" es la convención de Splunk para contenido sin dueño humano
    (instalado por una app). Sin este filtro, esas saved searches (muchas
    con tstats/data models, confianza PARTIAL) inflan
    partial_or_unknown_ratio y disparan la regla UNKNOWN de entorno de D009
    incluso cuando el entorno real del cliente está bien cubierto."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/services/search/jobs":
            return _oneshot_response([])
        if request.url.path == "/servicesNS/-/-/saved/searches":
            return _saved_searches_response(
                [
                    _saved_search_entry("SystemBundledReport", owner="nobody"),
                    _saved_search_entry(
                        "customer-real-alert", owner="admin", search="index=main sourcetype=access"
                    ),
                ]
            )
        raise AssertionError(f"unexpected request: {request.url}")

    config = RestConfig(
        host="lab", token="fake-token", transport=httpx.MockTransport(handler)
    )
    collection = collect(config, "queries")

    assert collection.saved_searches is not None
    names = set(collection.saved_searches["name"])
    assert "customer-real-alert" in names
    assert "SystemBundledReport" not in names
