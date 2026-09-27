"""Tests de regresión para bugs reales encontrados en Fase 3A/3B al validar
y endurecer el collector REST contra una instancia Splunk Enterprise 10.4.3
real (ver DECISIONS.md D010/D011/D012/D013/D014 y PROJECT_STATUS.md). Usan
httpx.MockTransport para no depender de una instancia Splunk real ni de red
-- ver docs de Fase 3B, "Los tests de CI NO deben depender de red/Docker/
Splunk real"."""

from __future__ import annotations

import httpx
import pandas as pd
import pytest

from splunk_spend_auditor.collector.rest_collector import (
    RestCollectionError,
    RestConfig,
    collect,
)
from splunk_spend_auditor.models import SignalAvailability


def _oneshot_response(results: list[dict], messages: list[dict] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"results": results, "messages": messages or []})


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


def _ingest_only_handler(ingest_rows: list[dict]):
    """Handler base: sirve `ingest` con éxito y una respuesta vacía/segura
    para audit_searches, saved_searches y last_seen -- útil como punto de
    partida en tests que solo quieren forzar el fallo de UNA fuente."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/services/search/jobs":
            body = request.content.decode()
            if "license_usage" in body:
                return _oneshot_response(ingest_rows)
            return _oneshot_response([])
        if request.url.path == "/servicesNS/-/-/saved/searches":
            return _saved_searches_response([])
        raise AssertionError(f"unexpected request: {request.url}")

    return handler


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


_SAMPLE_INGEST_ROWS = [
    {"date": "2026-09-01", "index": "main", "sourcetype": "access", "gb": "1.0"},
]


class TestMandatoryIngestFailureBecomesRestCollectionError:
    """Item 4/8 de Fase 3B: un fallo en la fuente OBLIGATORIA (ingest) nunca
    debe dejar escapar una excepción cruda de httpx -- el CLI necesita un
    mensaje humano, no un stack trace de Python por defecto."""

    def test_connection_refused_on_ingest_raises_rest_collection_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError) as exc_info:
            collect(config, "queries")
        assert "conectar" in str(exc_info.value).lower()
        assert isinstance(exc_info.value.__cause__, httpx.ConnectError)

    def test_timeout_on_ingest_raises_rest_collection_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError) as exc_info:
            collect(config, "queries")
        assert "timeout" in str(exc_info.value).lower()

    def test_401_on_ingest_raises_rest_collection_error_mentioning_auth(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"messages": [{"type": "WARN", "text": "call not properly authenticated"}]})

        config = RestConfig(host="lab", token="bad-token", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError) as exc_info:
            collect(config, "queries")
        assert "autenticaci" in str(exc_info.value).lower()

    def test_403_on_ingest_raises_rest_collection_error_mentioning_permissions(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"messages": [{"type": "ERROR", "text": "insufficient permission"}]})

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError) as exc_info:
            collect(config, "queries")
        assert "permisos" in str(exc_info.value).lower()

    def test_500_on_ingest_raises_rest_collection_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"messages": [{"type": "FATAL", "text": "internal error"}]})

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError):
            collect(config, "queries")

    def test_malformed_json_on_ingest_raises_rest_collection_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this is not json")

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError) as exc_info:
            collect(config, "queries")
        assert "malformada" in str(exc_info.value).lower() or "json" in str(exc_info.value).lower()

    def test_fatal_message_with_http_200_on_ingest_raises_rest_collection_error(self):
        """Chequeo defensivo (item 4, 'search job fallido'): aunque en la
        validación real contra el laboratorio un comando SPL roto devolvió
        HTTP 400 (no 200), la API de Splunk no garantiza eso en todas las
        versiones/endpoints -- este test cubre el caso 200+FATAL."""

        def handler(request: httpx.Request) -> httpx.Response:
            return _oneshot_response([], messages=[{"type": "FATAL", "text": "Unknown search command"}])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        with pytest.raises(RestCollectionError):
            collect(config, "queries")


class TestOptionalSourcesDegradeWithoutAbortingTheAudit:
    """Item 5 de Fase 3B: audit_searches/saved_searches/last_seen son
    opcionales -- su fallo nunca debe abortar collect() completo, y debe
    quedar registrado como SignalAvailability.ERROR (se intentó y falló),
    no UNAVAILABLE (nunca se intentó) ni, sobre todo, como si fueran 0
    filas confirmadas."""

    def test_audit_searches_403_degrades_to_error_without_aborting(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                if "_audit" in body:
                    return httpx.Response(403, json={"messages": [{"type": "ERROR", "text": "denied"}]})
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.ingest is not None
        assert collection.audit_searches is None
        assert collection.sources_available["audit_searches"] == SignalAvailability.ERROR

    def test_saved_searches_timeout_degrades_to_error_without_aborting(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])
            if request.url.path == "/servicesNS/-/-/saved/searches":
                raise httpx.ReadTimeout("timed out")
            raise AssertionError(f"unexpected request: {request.url}")

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.ingest is not None
        assert collection.saved_searches is None
        assert collection.sources_available["saved_searches"] == SignalAvailability.ERROR

    def test_all_optional_sources_failing_still_returns_a_usable_collection(self):
        """Escenario conceptual del enunciado: license usage OK, alerts
        permission denied, last_seen timeout -- el audit debe seguir
        adelante con información parcial, nunca abortar por completo."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                raise httpx.ConnectError("network unreachable")
            return httpx.Response(403, json={"messages": [{"type": "ERROR", "text": "denied"}]})

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")  # no debe levantar excepción

        assert collection.ingest is not None
        assert not collection.ingest.empty
        assert collection.sources_available["ingest"] == SignalAvailability.AVAILABLE
        assert collection.sources_available["audit_searches"] == SignalAvailability.ERROR
        assert collection.sources_available["saved_searches"] == SignalAvailability.ERROR
        assert collection.sources_available["last_seen"] == SignalAvailability.ERROR


class TestLastSeenEndToEnd:
    """Item 1 de Fase 3B: metadata_last_seen.spl (corregida en Fase 3A,
    D011) ahora se ejecuta realmente desde collect() -- antes quedaba
    hardcodeada en UNAVAILABLE sin intentarlo nunca."""

    def test_last_seen_success_covering_all_known_indexes_is_available(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(
                        [{"date": "2026-09-01", "index": "main", "sourcetype": "access", "gb": "1.0"}]
                    )
                if "metadata" in body:
                    return _oneshot_response(
                        [{"index": "main", "sourcetype": "access", "last_seen_days_ago": "0.2"}]
                    )
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["last_seen"] == SignalAvailability.AVAILABLE
        assert collection.last_seen is not None
        assert list(collection.last_seen["index"]) == ["main"]

    def test_last_seen_missing_some_known_indexes_is_partial_not_available(self):
        """La query usa `map maxsearches=100` (D011) -- si un entorno tiene
        más índices que ese límite, o si por algún motivo un índice conocido
        por ingest no aparece en el resultado de last_seen, no se puede
        confiar 100% en la cobertura -- se marca PARTIAL, no AVAILABLE."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(
                        [
                            {"date": "2026-09-01", "index": "idx_a", "sourcetype": "st", "gb": "1.0"},
                            {"date": "2026-09-01", "index": "idx_b", "sourcetype": "st", "gb": "1.0"},
                        ]
                    )
                if "metadata" in body:
                    # Solo cubre idx_a -- idx_b falta (p.ej. truncado por map).
                    return _oneshot_response(
                        [{"index": "idx_a", "sourcetype": "st", "last_seen_days_ago": "0.2"}]
                    )
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["last_seen"] == SignalAvailability.PARTIAL
        assert collection.last_seen is not None
        assert "idx_a" in set(collection.last_seen["index"])

    def test_last_seen_filters_out_indexes_not_seen_in_ingest(self):
        """Confirmado empíricamente en Fase 3B contra el laboratorio de Fase
        3A: `eventcount index=*` recorre también índices por defecto de
        Splunk ("main", "history", "summary") que no son parte del "spend"
        real del cliente. Se filtran sin tocar el .spl (D011 -- no se
        reescribe la query), solo el DataFrame resultante en Python."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(
                        [{"date": "2026-09-01", "index": "billing", "sourcetype": "export", "gb": "1.0"}]
                    )
                if "metadata" in body:
                    return _oneshot_response(
                        [
                            {"index": "billing", "sourcetype": "export", "last_seen_days_ago": "0.1"},
                            {"index": "history", "sourcetype": "history", "last_seen_days_ago": "3.0"},
                        ]
                    )
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["last_seen"] == SignalAvailability.AVAILABLE
        assert set(collection.last_seen["index"]) == {"billing"}

    def test_last_seen_query_failure_is_error_not_unavailable_and_does_not_abort(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                if "metadata" in body:
                    raise httpx.ReadTimeout("timed out")
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.last_seen is None
        assert collection.sources_available["last_seen"] == SignalAvailability.ERROR
        # El resto del audit sigue disponible -- no abortó.
        assert collection.ingest is not None
