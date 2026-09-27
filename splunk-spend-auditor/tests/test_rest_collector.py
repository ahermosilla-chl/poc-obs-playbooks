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

from splunk_spend_auditor.analysis.build_datasets import build_datasets
from splunk_spend_auditor.collector.rest_collector import (
    IndexAccessProbe,
    RestCollectionError,
    RestConfig,
    _index_pattern_matches,
    _probe_index_access,
    collect,
)
from splunk_spend_auditor.models import Classification, SignalAvailability
from splunk_spend_auditor.scoring.classify_all import classify_all
from splunk_spend_auditor.scoring.savings import compute_savings


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


def _current_context_response(roles: list[str]) -> httpx.Response:
    return httpx.Response(
        200, json={"entry": [{"content": {"username": "test-user", "roles": roles}}]}
    )


def _role_response(
    allowed: list[str] | None = None,
    disallowed: list[str] | None = None,
    imported_allowed: list[str] | None = None,
    imported_disallowed: list[str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "entry": [
                {
                    "content": {
                        "srchIndexesAllowed": allowed or [],
                        "srchIndexesDisallowed": disallowed or [],
                        "imported_srchIndexesAllowed": imported_allowed or [],
                        "imported_srchIndexesDisallowed": imported_disallowed or [],
                    }
                }
            ]
        },
    )


# D015 (Fase 3B, resuelto): rol de prueba con acceso amplio -- usado como
# default en los handlers base para que tests que no están probando D015
# específicamente sigan viendo el comportamiento pre-existente (audit_searches
# vacío -> AVAILABLE, cero confirmado).
_PERMISSIVE_ROLE = "permissive_test_role"


def _permissive_authz_routes(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/services/authentication/current-context":
        return _current_context_response([_PERMISSIVE_ROLE])
    if request.url.path == f"/services/authorization/roles/{_PERMISSIVE_ROLE}":
        return _role_response(allowed=["*", "_*"])
    return None


def _ingest_only_handler(ingest_rows: list[dict]):
    """Handler base: sirve `ingest` con éxito, una respuesta vacía/segura
    para audit_searches/saved_searches/last_seen, y un rol permisivo para el
    preflight de acceso a `_audit` (D015) -- útil como punto de partida en
    tests que solo quieren forzar el fallo de UNA fuente."""

    def handler(request: httpx.Request) -> httpx.Response:
        authz = _permissive_authz_routes(request)
        if authz is not None:
            return authz
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
        authz = _permissive_authz_routes(request)
        if authz is not None:
            return authz
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
        authz = _permissive_authz_routes(request)
        if authz is not None:
            return authz
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
            authz = _permissive_authz_routes(request)
            if authz is not None:
                return authz
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
                if "eventcount" in body:
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
                if "eventcount" in body:
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
                if "eventcount" in body:
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
                if "eventcount" in body:
                    raise httpx.ReadTimeout("timed out")
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.last_seen is None
        assert collection.sources_available["last_seen"] == SignalAvailability.ERROR
        # El resto del audit sigue disponible -- no abortó.
        assert collection.ingest is not None


class TestIndexPatternMatching:
    """D015 (resuelto): la convención de Splunk de que un `"*"` bare no
    concede acceso a índices internos, confirmada empíricamente contra el
    laboratorio real -- ver docstring de `_index_pattern_matches`."""

    def test_bare_wildcard_does_not_match_internal_index(self):
        assert _index_pattern_matches("*", "_audit") is False

    def test_bare_wildcard_matches_normal_index(self):
        assert _index_pattern_matches("*", "main") is True

    def test_underscore_wildcard_matches_internal_index(self):
        assert _index_pattern_matches("_*", "_audit") is True

    def test_exact_internal_index_name_matches(self):
        assert _index_pattern_matches("_audit", "_audit") is True

    def test_unrelated_prefix_does_not_match(self):
        assert _index_pattern_matches("lsa_*", "_audit") is False


class TestD015AuditIndexAccessProbe:
    """D015 (resuelto): determina de forma determinista si el token actual
    tiene acceso efectivo a `_audit` antes de confiar en un resultado vacío.
    Los 3 estados conceptuales pedidos: access confirmed / access denied /
    access cannot be established."""

    # --- 1. _audit accesible + cero real -------------------------------

    def test_confirmed_access_with_genuinely_empty_audit_is_available(self):
        """Caso A del pedido: acceso confirmado + query vacía SÍ puede
        representar cero real -- no se degrada."""

        def handler(request: httpx.Request) -> httpx.Response:
            authz = _permissive_authz_routes(request)
            if authz is not None:
                return authz
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])  # audit_searches: vacío, pero con acceso confirmado
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.AVAILABLE
        assert collection.audit_searches is not None
        assert collection.audit_searches.empty
        assert "audit_searches" not in collection.diagnostics

    # --- 2. _audit explícitamente no permitido -------------------------

    def test_denied_access_downgrades_to_unavailable_with_clear_reason(self):
        """Caso B: el índice no está permitido -- la señal se marca no
        disponible (UNAVAILABLE), NO como "0 búsquedas"."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/authentication/current-context":
                return _current_context_response(["restricted_role"])
            if request.url.path == "/services/authorization/roles/restricted_role":
                # Igual que el laboratorio real: _internal + lsa_* propios,
                # "*" heredado de "user" (que NO cubre índices internos).
                return _role_response(
                    allowed=["_internal", "lsa_*"], imported_allowed=["*"]
                )
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])  # _audit "vacío" -- en realidad sin acceso
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.UNAVAILABLE
        assert collection.audit_searches is None
        assert "_audit" in collection.diagnostics["audit_searches"]
        assert "not have confirmed access" in collection.diagnostics["audit_searches"]

    def test_disallow_overrides_a_broad_allow(self):
        """Confirmado empíricamente contra el laboratorio real: un rol con
        srchIndexesAllowed=["*","_*"] pero srchIndexesDisallowed=["_audit"]
        NO puede buscar _audit -- disallow siempre gana."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/authentication/current-context":
                return _current_context_response(["broad_but_disallowed"])
            if request.url.path == "/services/authorization/roles/broad_but_disallowed":
                return _role_response(allowed=["*", "_*"], disallowed=["_audit"])
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.UNAVAILABLE

    # --- 3. autorización no determinable --------------------------------

    def test_current_context_unreachable_is_undetermined_and_fails_safe(self):
        """Caso C: no se puede establecer con confianza el acceso efectivo
        (current-context inaccesible) -- fail-safe, nunca se asume cero."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/authentication/current-context":
                return httpx.Response(403, json={"messages": [{"type": "ERROR", "text": "denied"}]})
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.UNAVAILABLE
        assert "could not reliably confirm" in collection.diagnostics["audit_searches"]

    def test_one_unreadable_role_among_several_is_undetermined(self):
        """Un usuario puede tener varios roles propios -- si CUALQUIERA de
        ellos no se puede leer con confianza, todo el resultado es
        UNDETERMINED (fail-safe: nunca CONFIRMED con información parcial),
        incluso si otro de sus roles sí habría permitido _audit."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/authentication/current-context":
                return _current_context_response(["readable_role", "broken_role"])
            if request.url.path == "/services/authorization/roles/readable_role":
                return _role_response(allowed=["_audit"])
            if request.url.path == "/services/authorization/roles/broken_role":
                return httpx.Response(500, json={"messages": [{"type": "FATAL", "text": "boom"}]})
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.UNAVAILABLE

    # --- 4. roles / imported roles afectan el cálculo efectivo ----------

    def test_access_granted_only_via_imported_role_is_confirmed(self):
        """El propio rol no tiene _audit en srchIndexesAllowed, pero SÍ lo
        hereda de un rol importado -- Splunk ya resuelve esto en
        imported_srchIndexesAllowed (confirmado con una cadena de 3 niveles
        contra el laboratorio real) y el probe debe confiar en ese campo."""

        def handler(request: httpx.Request) -> httpx.Response:
            authz_ctx = request.url.path == "/services/authentication/current-context"
            if authz_ctx:
                return _current_context_response(["imports_audit_role"])
            if request.url.path == "/services/authorization/roles/imports_audit_role":
                return _role_response(allowed=[], imported_allowed=["_audit", "lsa_*"])
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.AVAILABLE

    def test_second_role_grants_access_the_first_role_does_not(self):
        """Acceso efectivo = UNIÓN de todos los roles propios del usuario --
        si CUALQUIERA de sus roles permite _audit, hay acceso, aunque el
        primero que se liste no lo permita."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/authentication/current-context":
                return _current_context_response(["no_audit_role", "has_audit_role"])
            if request.url.path == "/services/authorization/roles/no_audit_role":
                return _role_response(allowed=["lsa_*"])
            if request.url.path == "/services/authorization/roles/has_audit_role":
                return _role_response(allowed=["_audit"])
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(_SAMPLE_INGEST_ROWS)
                return _oneshot_response([])
            return _saved_searches_response([])

        config = RestConfig(host="lab", token="t", transport=httpx.MockTransport(handler))
        collection = collect(config, "queries")

        assert collection.sources_available["audit_searches"] == SignalAvailability.AVAILABLE


class TestD015SafetyInvariantEndToEnd:
    """D015 (resuelto): reproduce el pipeline completo (collect ->
    build_datasets -> classify_all -> compute_savings) con un token
    restringido, y demuestra los invariantes de seguridad pedidos: la
    pérdida de acceso a `_audit` nunca aumenta la clasificación de
    desperdicio ni el ahorro potencial estimado."""

    _HIGH_VALUE_DATASET_INDEX = "billing"
    _HIGH_VALUE_DATASET_SOURCETYPE = "export"

    def _handler(self, *, grant_audit_access: bool):
        """Simula un dataset que, con acceso completo a _audit, tiene 12
        búsquedas interactivas reales (HIGH_VALUE) -- exactamente el
        escenario real que originó D015 (lsa_high_value en el laboratorio
        de Fase 3A/3B)."""

        audit_rows = (
            [
                {
                    "date": "2026-09-20",
                    "user": "admin",
                    "search_id": f"'179046{i}.{i}'",
                    "is_scheduled": "false",
                    "search_text": (
                        f"'search index={self._HIGH_VALUE_DATASET_INDEX} "
                        f"sourcetype={self._HIGH_VALUE_DATASET_SOURCETYPE} | stats count'"
                    ),
                }
                for i in range(12)
            ]
            if grant_audit_access
            else []
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/services/authentication/current-context":
                return _current_context_response(["role_under_test"])
            if request.url.path == "/services/authorization/roles/role_under_test":
                if grant_audit_access:
                    return _role_response(allowed=["*", "_*"])
                return _role_response(allowed=[self._HIGH_VALUE_DATASET_INDEX, "_internal"])
            if request.url.path == "/services/search/jobs":
                body = request.content.decode()
                if "license_usage" in body:
                    return _oneshot_response(
                        [
                            {
                                "date": "2026-09-26",
                                "index": self._HIGH_VALUE_DATASET_INDEX,
                                "sourcetype": self._HIGH_VALUE_DATASET_SOURCETYPE,
                                "gb": "50.0",
                            }
                        ]
                    )
                if "eventcount" in body:
                    return _oneshot_response([])
                return _oneshot_response(audit_rows)
            return _saved_searches_response([])

        return handler

    def _classified_datasets(self, *, grant_audit_access: bool):
        config = RestConfig(
            host="lab", token="t", transport=httpx.MockTransport(self._handler(grant_audit_access=grant_audit_access))
        )
        collection = collect(config, "queries")
        datasets, summary = build_datasets(collection)
        classify_all(
            datasets,
            environment_partial_unknown_ratio=summary.partial_or_unknown_ratio,
            sources_available=summary.sources_available,
        )
        return datasets, summary

    def test_full_access_reproduces_high_value_like_the_real_lab(self):
        """Control: con acceso completo a _audit, el dataset SÍ debe llegar
        a HIGH_VALUE (12 búsquedas >= HIGH_VALUE_SEARCH_THRESHOLD) --
        replica lo observado con el token admin en el laboratorio real."""

        datasets, _ = self._classified_datasets(grant_audit_access=True)
        target = next(
            d
            for d in datasets
            if d.key.index == self._HIGH_VALUE_DATASET_INDEX
            and d.key.sourcetype == self._HIGH_VALUE_DATASET_SOURCETYPE
        )
        assert target.classification == Classification.HIGH_VALUE

    def test_7_restricted_access_does_not_reclassify_high_value_as_possible_waste(self):
        """7. Reproducción exacta del bug real que originó D015: con un
        token restringido (sin acceso a _audit), el MISMO dataset que sería
        HIGH_VALUE con visibilidad completa NUNCA debe convertirse en
        POSSIBLE_WASTE -- debe degradar a REVIEW (D014) via UNAVAILABLE."""

        datasets, summary = self._classified_datasets(grant_audit_access=False)
        assert summary.sources_available["audit_searches"] == SignalAvailability.UNAVAILABLE

        target = next(
            d
            for d in datasets
            if d.key.index == self._HIGH_VALUE_DATASET_INDEX
            and d.key.sourcetype == self._HIGH_VALUE_DATASET_SOURCETYPE
        )
        assert target.classification != Classification.POSSIBLE_WASTE
        assert target.classification == Classification.REVIEW

    @staticmethod
    def _waste_candidacy_weight(dataset) -> float:
        """"Severidad" real de una clasificación para efectos de este
        invariante: el peso con el que efectivamente contribuye al cálculo
        de ahorro (scoring/savings.py), NO el nombre de la categoría. Un
        REVIEW con excluded_from_savings_estimate=True pesa 0, igual que
        HIGH_VALUE -- comparar solo por nombre de categoría (HIGH_VALUE=0 <
        REVIEW=2 en cualquier orden fijo) daría un falso positivo aquí,
        porque no todo REVIEW es igual de "agresivo" (ver D015 y
        DECISIONS.md)."""

        if dataset.classification == Classification.POSSIBLE_WASTE:
            return 1.0
        if dataset.classification == Classification.REVIEW and not dataset.excluded_from_savings_estimate:
            return 0.5
        return 0.0

    def test_5_losing_audit_access_never_increases_waste_classification(self):
        """5. La pérdida de _audit nunca puede producir una clasificación
        MÁS agresiva que con visibilidad completa, para el mismo dataset --
        medido por el peso real de "candidato a desperdicio" (0 / 0.5 / 1),
        que es lo que el invariante pedido efectivamente protege (ver
        DECISIONS.md D015)."""

        full, _ = self._classified_datasets(grant_audit_access=True)
        restricted, _ = self._classified_datasets(grant_audit_access=False)

        full_ds = next(d for d in full if d.key.index == self._HIGH_VALUE_DATASET_INDEX)
        restricted_ds = next(d for d in restricted if d.key.index == self._HIGH_VALUE_DATASET_INDEX)
        assert restricted_ds.classification != Classification.POSSIBLE_WASTE
        assert self._waste_candidacy_weight(restricted_ds) <= self._waste_candidacy_weight(full_ds)

    def test_6_losing_audit_access_never_increases_potential_savings(self):
        """6. Idem para el ahorro potencial estimado en dólares."""

        full, _ = self._classified_datasets(grant_audit_access=True)
        restricted, _ = self._classified_datasets(grant_audit_access=False)

        savings_full = compute_savings(full, annual_spend=100_000)
        savings_restricted = compute_savings(restricted, annual_spend=100_000)

        assert savings_restricted.candidate_gb_day <= savings_full.candidate_gb_day
        assert savings_restricted.potential_annual_saving <= savings_full.potential_annual_saving
