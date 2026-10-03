"""Collector para el modo REST (D002) -- conexión directa y de solo lectura
a una instancia Splunk real.

ESTADO: validado en Fase 3A contra una instancia Splunk Enterprise 10.4.3
real (Trial license, laboratorio Docker) -- ver PROJECT_STATUS.md y
DECISIONS.md D010/D011/D012. Endurecido en Fase 3B (D013/D014) contra fallos
reales de red/autenticación/permisos y contra la pérdida silenciosa de
señales. D015 (permisos de índice restringidos que devuelven `200`/`[]` sin
error para `_audit`) resuelto con un preflight determinista de autorización
efectiva (`_probe_index_access`) -- ver DECISIONS.md D015 para el modelo
completo, validado contra el laboratorio real.

Principio rector de Fase 3B (docs/architecture.md, "Manejo de errores"):
la ausencia de una señal NUNCA se convierte en "la señal vale cero". Cada
fuente opcional (audit_searches, saved_searches, last_seen) que falle queda
marcada con un `SignalAvailability` explícito (ERROR/UNAVAILABLE/PARTIAL) en
`RawCollection.sources_available`, y su DataFrame correspondiente queda en
`None` -- nunca en un DataFrame vacío que se confundiría con "consultado,
0 filas". La única fuente obligatoria es `ingest` (igual que en el modo
CSV -- ver csv_collector.py): si falla, `collect()` levanta
`RestCollectionError` con un mensaje apto para el usuario, en vez de dejar
escapar la excepción cruda de httpx (ver CLI, `_describe_rest_error`).

Principios de seguridad aplicados aquí (ver docs/security.md):
- Solo se llama a endpoints de lectura (GET) y a /search/jobs con las
  queries de solo lectura de queries/*.spl -- nunca se escribe/borra nada.
- El token nunca se escribe a disco por este módulo.
"""

from __future__ import annotations

import fnmatch
import logging
import time
from dataclasses import dataclass
from enum import Enum
from importlib import resources
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd

from splunk_spend_auditor.collector.csv_collector import RawCollection
from splunk_spend_auditor.models import SignalAvailability

logger = logging.getLogger(__name__)

_SEARCH_JOBS_ENDPOINT = "/services/search/jobs"
# Wildcard de user/app -- ver docs/splunk-data-sources.md sección 3, "gotcha
# de scoping": sin esto se pierden saved searches de otros usuarios/apps.
_SAVED_SEARCHES_ENDPOINT = "/servicesNS/-/-/saved/searches"
_CURRENT_CONTEXT_ENDPOINT = "/services/authentication/current-context"
_ROLES_ENDPOINT = "/services/authorization/roles"

# Errores de transporte/red (connection refused, DNS, timeout, TLS) -- todos
# son subclases de httpx.RequestError. HTTPStatusError (401/403/404/429/5xx)
# es una jerarquía separada, la levanta response.raise_for_status().
# Confirmado empíricamente en Fase 3B contra el laboratorio de Fase 3A: un
# comando SPL inexistente ("thiscommanddoesnotexist") devuelve HTTP 400 con
# un mensaje FATAL en el cuerpo -- ya cubierto por HTTPStatusError, no
# requiere parseo especial de `messages`.
_RECOVERABLE_REST_ERRORS = (httpx.HTTPStatusError, httpx.RequestError)


class RestCollectionError(Exception):
    """Fallo irrecuperable obteniendo una fuente OBLIGATORIA (ingest) vía
    REST. El CLI la captura y muestra `str(self)` (mensaje apto para
    usuario, sin traceback) salvo en modo --verbose. La causa técnica
    original queda encadenada vía `raise ... from original` (`__cause__`),
    disponible para logging/debug."""


class SplunkQueryError(Exception):
    """La respuesta HTTP fue 2xx pero Splunk reportó un mensaje FATAL/ERROR
    en el cuerpo (`messages`). Chequeo defensivo -- ver nota arriba sobre
    _RECOVERABLE_REST_ERRORS; no se observó este caso en la validación de
    Fase 3B (los fallos de query real ya vienen como HTTP 4xx), pero la API
    de Splunk no garantiza eso para toda versión/endpoint, así que se
    conserva la verificación."""


def _describe_rest_error(exc: Exception, context: str) -> str:
    """Translates a technical exception (httpx/Splunk) into a short,
    actionable message for the CLI user (item 8, "CLI Error UX"). The full
    technical detail is preserved in the log (logger.debug) and in
    `exc.__cause__`, never discarded."""

    if isinstance(exc, httpx.ConnectError):
        return f"Could not connect to Splunk for {context} (host/port unreachable or connection refused)."
    if isinstance(exc, httpx.ConnectTimeout):
        return f"Timed out connecting to Splunk for {context}."
    if isinstance(exc, httpx.ReadTimeout | httpx.PoolTimeout):
        return f"Timed out waiting for Splunk's response for {context}."
    if isinstance(exc, httpx.RequestError):
        return f"Network/TLS error contacting Splunk for {context}: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return f"Authentication failed (401) fetching {context} -- the token is invalid or expired."
        if status == 403:
            return f"Insufficient permissions (403) fetching {context} -- check the token's role capabilities."
        if status == 404:
            return f"Endpoint not found (404) fetching {context} -- check the Splunk version/endpoint path."
        if status == 429:
            return f"Splunk returned 429 (too many requests) fetching {context} -- retry later."
        if 500 <= status < 600:
            return f"Splunk returned a server error ({status}) fetching {context}."
        return f"Splunk returned HTTP {status} fetching {context}."
    if isinstance(exc, SplunkQueryError):
        return f"The Splunk query for {context} failed: {exc}"
    if isinstance(exc, ValueError):
        return f"Malformed response from Splunk (invalid JSON) fetching {context}."
    return f"Unexpected error fetching {context}: {exc}"


class IndexAccessProbe(str, Enum):
    """D015 (Fase 3B, resuelto): resultado de determinar si el token actual
    tiene acceso efectivo de búsqueda a un índice dado, ANTES de confiar en
    un resultado vacío como "cero real". Ver docstring de
    `_probe_index_access` para el porqué y la evidencia empírica.

    - CONFIRMED: se pudo resolver el conjunto efectivo de patrones
      allow/disallow de TODOS los roles del usuario (directos + heredados,
      ya resueltos por Splunk mismo en `imported_srchIndexesAllowed`/
      `imported_srchIndexesDisallowed`) y el índice está permitido.
    - DENIED: idem, pero el índice NO está permitido (ningún patrón allow
      lo cubre, o un patrón disallow lo bloquea explícitamente -- disallow
      siempre gana, confirmado empíricamente).
    - UNDETERMINED: no se pudo resolver el conjunto efectivo con confianza
      (current-context inaccesible, algún rol no se pudo leer, respuesta
      inesperada). Fail-safe: se trata igual que DENIED en cuanto a NO
      confiar en un resultado vacío -- nunca se interpreta como "acceso
      confirmado" por default."""

    CONFIRMED = "CONFIRMED"
    DENIED = "DENIED"
    UNDETERMINED = "UNDETERMINED"


def _index_pattern_matches(pattern: str, index_name: str) -> bool:
    """Replica la convención de Splunk confirmada empíricamente contra el
    laboratorio real (Splunk Enterprise 10.4.3): un patrón `"*"` (bare
    wildcard) por sí solo NO concede acceso a índices internos (que
    empiezan con `_`, p.ej. `_audit`) -- se requiere un patrón que empiece
    con `_` (p.ej. `"_*"`, `"_audit"`) o el nombre exacto. Se comprobó
    creando un rol con `imported_srchIndexesAllowed=["*"]` (heredado del
    rol base "user") y confirmando que NO otorga acceso a `_audit`, y que
    el rol `admin` de Splunk agrega explícitamente `"_*"` ADEMÁS de `"*"`
    en su propio `srchIndexesAllowed` -- si `"*"` ya cubriera índices
    internos, ese segundo patrón sería redundante.

    Para cualquier otro patrón, se usa `fnmatch` estándar (case-sensitive,
    como los nombres de index en Splunk)."""

    if pattern == "*" and index_name.startswith("_"):
        return False
    return fnmatch.fnmatchcase(index_name, pattern)


def _current_user_roles(client: httpx.Client) -> list[str] | None:
    """None si no se pudo determinar con confianza -- nunca se asume una
    lista vacía/default en caso de error (ver IndexAccessProbe.UNDETERMINED)."""

    try:
        response = client.get(_CURRENT_CONTEXT_ENDPOINT, params={"output_mode": "json"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
        logger.debug("current-context no disponible: %s", exc, exc_info=True)
        return None

    entries = payload.get("entry", [])
    if not entries:
        return None
    roles = entries[0].get("content", {}).get("roles")
    if not roles:
        return None
    return list(roles)


def _role_index_patterns(client: httpx.Client, role: str) -> tuple[set[str], set[str]] | None:
    """Devuelve (allowed_patterns, disallowed_patterns) EFECTIVOS para un
    rol -- unión de lo propio (`srchIndexesAllowed`/`srchIndexesDisallowed`)
    y lo heredado de su cadena COMPLETA de `imported_roles` (Splunk mismo
    resuelve la herencia transitiva en `imported_srchIndexesAllowed`/
    `imported_srchIndexesDisallowed`; confirmado empíricamente contra el
    laboratorio con una cadena de 3 niveles de roles importados -- no hace
    falta que este código camine el grafo de roles a mano).

    None si el rol no se pudo leer con confianza.

    Fase 4B: `role` viene de Splunk (`/authentication/current-context`),
    pero a diferencia de un nombre de índice (que Splunk restringe a
    `[a-z0-9_-]` al crearlo -- verificado contra el laboratorio real), un
    nombre de ROL puede contener literalmente cualquier caracter, incluidos
    `/` y `..` -- confirmado creando un rol real con ese nombre exacto
    contra el laboratorio. Interpolado crudo en la URL, esto permitía que
    httpx normalizara `.../roles/../../authentication/users` hacia un
    endpoint completamente distinto (confirmado empíricamente). El fallo
    resultante de D015 seguía cayendo del lado seguro (DENIED, nunca un
    CONFIRMED falso) gracias al chequeo defensivo de campos ya existente,
    pero `quote(..., safe="")` cierra el vector en el origen en vez de
    depender de esa coincidencia -- ningún nombre de rol legítimo (sin
    `/`) cambia de comportamiento."""

    try:
        response = client.get(
            f"{_ROLES_ENDPOINT}/{quote(role, safe='')}", params={"output_mode": "json"}
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
        logger.debug("rol '%s' no disponible: %s", role, exc, exc_info=True)
        return None

    entries = payload.get("entry", [])
    if not entries:
        return None
    content = entries[0].get("content", {})
    allowed = set(content.get("srchIndexesAllowed") or []) | set(
        content.get("imported_srchIndexesAllowed") or []
    )
    disallowed = set(content.get("srchIndexesDisallowed") or []) | set(
        content.get("imported_srchIndexesDisallowed") or []
    )
    return allowed, disallowed


def _probe_index_access(client: httpx.Client, index_name: str) -> IndexAccessProbe:
    """D015 (resuelto): determina de forma DETERMINISTA -- no heurística --
    si el token actual tiene acceso efectivo de búsqueda a `index_name`,
    consultando el modelo de autorización real de Splunk en vez de confiar
    en que una búsqueda vacía significa "no hay datos".

    Un usuario puede tener varios roles propios (no solo `imported_roles`
    dentro de un rol) -- el acceso efectivo es la UNIÓN de lo que cada uno
    de sus roles permite (comportamiento estándar y documentado de Splunk,
    análogo a la herencia entre roles). Si CUALQUIER rol no se puede leer
    con confianza, todo el resultado es UNDETERMINED -- fail-safe: nunca se
    declara CONFIRMED con información parcial (ver item 2 del pedido:
    "no implementes una heurística que pueda declarar falsamente que existe
    acceso").

    Regla de precedencia (confirmada empíricamente contra el laboratorio:
    un rol con `srchIndexesAllowed=["*","_*"]` PERO
    `srchIndexesDisallowed=["_audit"]` NO pudo buscar `_audit`): disallow
    siempre gana sobre allow, sin importar cuán amplio sea el allow."""

    roles = _current_user_roles(client)
    if not roles:
        return IndexAccessProbe.UNDETERMINED

    allowed_all: set[str] = set()
    disallowed_all: set[str] = set()
    for role in roles:
        patterns = _role_index_patterns(client, role)
        if patterns is None:
            return IndexAccessProbe.UNDETERMINED
        allowed, disallowed = patterns
        allowed_all |= allowed
        disallowed_all |= disallowed

    if any(_index_pattern_matches(p, index_name) for p in disallowed_all):
        return IndexAccessProbe.DENIED
    if any(_index_pattern_matches(p, index_name) for p in allowed_all):
        return IndexAccessProbe.CONFIRMED
    return IndexAccessProbe.DENIED


@dataclass
class RestConfig:
    host: str
    token: str
    port: int = 8089
    verify_ssl: bool = True
    lookback_days: int = 90
    timeout_seconds: float = 60.0
    transport: httpx.BaseTransport | None = None  # solo para tests (httpx.MockTransport)


def _client(config: RestConfig) -> httpx.Client:
    # Fase 4B: httpx.Client() por defecto trae trust_env=True, que hace DOS
    # cosas que violan el principio "local-first, solo habla con el Splunk
    # configurado" (docs/security.md, README.md): (1) lee HTTPS_PROXY/
    # HTTP_PROXY/ALL_PROXY del entorno y enruta el tráfico -- incluido el
    # header Authorization con el Bearer token -- a través de ese proxy sin
    # avisar, algo especialmente probable en el entorno corporativo típico
    # del público objetivo de este producto (Splunk Admin/Platform
    # Engineer); (2) lee .netrc. Confirmado empíricamente con el propio
    # _client() de este módulo: para un host no cubierto por NO_PROXY,
    # httpx resuelve un transport respaldado por un HTTPProxy real en vez
    # de una conexión directa. trust_env=False cierra ambas rutas --
    # tradeoff documentado: también deja de honrar SSL_CERT_FILE/
    # SSL_CERT_DIR si algún entorno dependiera de esas variables para un CA
    # bundle interno (poco común -- la mayoría de las CAs corporativas se
    # instalan a nivel de SO, que el contexto SSL por defecto de Python ya
    # lee independientemente de trust_env). Ver DECISIONS.md D021.
    return httpx.Client(
        base_url=f"https://{config.host}:{config.port}",
        headers={"Authorization": f"Bearer {config.token}"},
        verify=config.verify_ssl,
        timeout=config.timeout_seconds,
        transport=config.transport,
        trust_env=False,
    )


def _run_oneshot_search(client: httpx.Client, spl: str) -> pd.DataFrame:
    """Ejecuta una búsqueda en modo 'oneshot' (bloqueante, resultado directo)
    contra /services/search/jobs y devuelve un DataFrame. Modo de solo
    lectura -- nunca se llama a /control con acciones de escritura.

    Levanta httpx.HTTPStatusError / httpx.RequestError / SplunkQueryError /
    ValueError (JSON malformado) en caso de fallo -- el llamador decide,
    según si la fuente es obligatoria u opcional, si eso debe abortar todo
    el collect() o degradar una sola señal."""

    response = client.post(
        _SEARCH_JOBS_ENDPOINT,
        data={
            "search": spl if spl.strip().startswith("|") else f"search {spl}",
            "exec_mode": "oneshot",
            "output_mode": "json",
        },
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(f"respuesta no es JSON válido: {exc}") from exc

    messages = payload.get("messages", [])
    fatal = [m.get("text", "") for m in messages if m.get("type") in ("FATAL", "ERROR")]
    if fatal:
        raise SplunkQueryError("; ".join(fatal))

    results = payload.get("results", [])
    df = pd.DataFrame(results)
    # La REST API de Splunk serializa TODOS los valores de resultados como
    # string (confirmado empíricamente en Fase 3A contra Splunk 10.4.3 real
    # -- a diferencia de pandas.read_csv, que infiere tipos automáticamente
    # en el modo CSV). Sin esto, columnas numéricas como "gb" llegan como
    # texto y build_datasets.py falla con TypeError al hacer .agg(["mean"]).
    # Solo se convierte una columna si el 100% de sus valores son numéricos,
    # para no corromper columnas de texto (p.ej. "index") que por casualidad
    # tengan algunos valores numéricos.
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().all():
            df[col] = converted
    return df


def _load_query(queries_path: Path, filename: str) -> str:
    text = (queries_path / filename).read_text(encoding="utf-8")
    # Las queries en queries/*.spl empiezan con un bloque de comentario
    # ``` ... ``` explicativo -- se descarta antes de ejecutar.
    if text.startswith("```"):
        end = text.index("```", 3)
        text = text[end + 3 :]
    return text.strip()


def _collect_ingest(client: httpx.Client, queries_path: Path) -> pd.DataFrame:
    """Fuente OBLIGATORIA -- ver csv_collector.load_from_directory, misma
    regla: sin ingest no hay "spend" que auditar. Cualquier fallo se
    propaga tal cual; collect() lo envuelve en RestCollectionError."""

    return _run_oneshot_search(client, _load_query(queries_path, "ingest_by_index_sourcetype.spl"))


_AUDIT_INDEX = "_audit"


def _collect_audit_searches(
    client: httpx.Client, queries_path: Path
) -> tuple[pd.DataFrame | None, SignalAvailability, str | None]:
    """D015 (resuelto): un resultado VACÍO de esta query es ambiguo -- puede
    ser "cero búsquedas reales" o "el token no tiene acceso efectivo a
    `_audit` y Splunk aplicó el scope en silencio (HTTP 200, sin error)".
    Confirmado empíricamente contra el laboratorio de Fase 3A/3B: un rol con
    `srchIndexesAllowed` sin `_audit` produce exactamente esa respuesta.

    Por eso solo se confía en un resultado vacío como "cero real" cuando la
    query devuelve AL MENOS una fila (evidencia positiva inequívoca -- si
    Splunk devolviera eventos reales de _audit, el acceso obviamente existe,
    no hace falta ningún chequeo adicional), o cuando el resultado está
    vacío PERO `_probe_index_access` confirma de forma determinista que el
    token sí tiene acceso a `_audit`. En cualquier otro caso (acceso
    denegado o no determinable) se degrada -- nunca se asume cero."""

    try:
        df = _run_oneshot_search(client, _load_query(queries_path, "audit_interactive_searches.spl"))
    except _RECOVERABLE_REST_ERRORS + (SplunkQueryError, ValueError) as exc:
        logger.debug("audit_searches no disponible: %s", exc, exc_info=True)
        return None, SignalAvailability.ERROR, None

    if not df.empty:
        return df, SignalAvailability.AVAILABLE, None

    probe = _probe_index_access(client, _AUDIT_INDEX)
    if probe is IndexAccessProbe.CONFIRMED:
        return df, SignalAvailability.AVAILABLE, None
    if probe is IndexAccessProbe.DENIED:
        reason = (
            "Search usage visibility is incomplete: current credentials do "
            "not have confirmed access to _audit (index access restricted "
            "by role). Usage-dependent classifications were downgraded for "
            "safety instead of treating this as zero interactive searches."
        )
        logger.debug("audit_searches: acceso a _audit denegado para el token actual")
        return None, SignalAvailability.UNAVAILABLE, reason
    reason = (
        "Search usage visibility is incomplete: could not reliably confirm "
        "whether current credentials have access to _audit (fail-safe). "
        "Usage-dependent classifications were downgraded for safety instead "
        "of treating this as zero interactive searches."
    )
    logger.debug("audit_searches: no se pudo determinar el acceso a _audit para el token actual")
    return None, SignalAvailability.UNAVAILABLE, reason


def _collect_saved_searches(
    client: httpx.Client,
) -> tuple[pd.DataFrame | None, SignalAvailability]:
    try:
        saved = client.get(
            _SAVED_SEARCHES_ENDPOINT, params={"output_mode": "json", "count": 0}
        )
        saved.raise_for_status()
        entries = saved.json().get("entry", [])
    except _RECOVERABLE_REST_ERRORS + (ValueError,) as exc:
        logger.debug("saved_searches no disponible: %s", exc, exc_info=True)
        return None, SignalAvailability.ERROR

    # Filtra contenido instalado por Splunk mismo (apps del sistema:
    # splunk_instrumentation, monitoring console, deployment server, etc.),
    # NUNCA saved searches reales del cliente -- ver DECISIONS.md D010.
    entries = [e for e in entries if e.get("acl", {}).get("owner") != "nobody"]
    df = pd.DataFrame(
        [
            {
                "name": e.get("name"),
                "search_text": e.get("content", {}).get("search", ""),
                "is_scheduled": e.get("content", {}).get("is_scheduled", False),
                "cron_schedule": e.get("content", {}).get("cron_schedule", ""),
                "has_alert_action": bool(e.get("content", {}).get("actions", "")),
                "next_scheduled_time": e.get("content", {}).get("next_scheduled_time", ""),
            }
            for e in entries
        ]
    )
    return df, SignalAvailability.AVAILABLE


def _collect_last_seen(
    client: httpx.Client, queries_path: Path, known_indexes: set[str]
) -> tuple[pd.DataFrame | None, SignalAvailability]:
    """Fase 3B (D014): wiring end-to-end de metadata_last_seen.spl (corregida
    en Fase 3A, D011 -- NO se reescribe aquí, solo se ejecuta y se maneja su
    resultado/fallo). `known_indexes` es el conjunto de índices ya visto en
    `ingest` -- se usa para dos cosas, ambas en Python, sin tocar el .spl:

    1. Filtrar filas de índices que no son del cliente (p.ej. "history",
       "summary", "main" -- índices por defecto de Splunk que
       `eventcount index=*` sí recorre, confirmado empíricamente contra el
       laboratorio de Fase 3A/3B; ninguno aparece en license_usage.log en
       una instancia real, así que no son parte del "spend" a auditar).
    2. Detectar cobertura incompleta: si el resultado no cubre todos los
       índices que SÍ vimos en ingest (p.ej. por el límite
       `maxsearches=100` de `| map` en la query), se marca PARTIAL en vez
       de AVAILABLE -- no se descarta el resultado, pero no se lo trata
       como 100% confiable."""

    try:
        df = _run_oneshot_search(client, _load_query(queries_path, "metadata_last_seen.spl"))
    except _RECOVERABLE_REST_ERRORS + (SplunkQueryError, ValueError) as exc:
        logger.debug("last_seen no disponible: %s", exc, exc_info=True)
        return None, SignalAvailability.ERROR

    if df.empty or "index" not in df.columns:
        return df, SignalAvailability.AVAILABLE

    df = df[df["index"].isin(known_indexes)] if known_indexes else df
    covered = set(df["index"].unique()) if not df.empty else set()
    missing = known_indexes - covered
    availability = SignalAvailability.PARTIAL if missing else SignalAvailability.AVAILABLE
    if missing:
        logger.debug("last_seen incompleto -- faltan %d de %d indexes", len(missing), len(known_indexes))
    return df, availability


def collect(config: RestConfig, queries_dir: str | None = None) -> RawCollection:
    """Punto de entrada del modo REST. Ejecuta las mismas queries
    documentadas en queries/*.spl contra un Splunk real.

    Solo `ingest` es obligatorio (ver csv_collector.load_from_directory,
    mismo principio): si falla, se levanta RestCollectionError con un
    mensaje apto para el usuario. El resto de las fuentes son opcionales --
    su fallo se degrada a un SignalAvailability.ERROR/UNAVAILABLE explícito,
    nunca a "0 filas silenciosas". El collector NUNCA decide clasificación
    (POSSIBLE_WASTE/PROTECTED/REVIEW/UNKNOWN) -- solo recolecta y reporta
    disponibilidad; esa responsabilidad es exclusiva de scoring/rules.py."""

    # Fase 5B: por defecto las queries vienen empaquetadas con el paquete
    # (funciona instalado, desde el ejecutable standalone y desde cualquier
    # cwd); queries_dir solo existe para sobreescribirlas explícitamente.
    queries_path = (
        Path(queries_dir)
        if queries_dir
        else Path(str(resources.files("splunk_spend_auditor") / "queries"))
    )
    collection = RawCollection()

    with _client(config) as client:
        try:
            collection.ingest = _collect_ingest(client, queries_path)
        except _RECOVERABLE_REST_ERRORS + (SplunkQueryError, ValueError) as exc:
            message = _describe_rest_error(exc, "ingest/license usage (mandatory source)")
            logger.debug("ingest (obligatorio) falló: %s", exc, exc_info=True)
            raise RestCollectionError(message) from exc
        collection.sources_available["ingest"] = SignalAvailability.AVAILABLE

        t0 = time.monotonic()
        (
            collection.audit_searches,
            collection.sources_available["audit_searches"],
            audit_reason,
        ) = _collect_audit_searches(client, queries_path)
        if audit_reason:
            collection.diagnostics["audit_searches"] = audit_reason
        logger.debug("audit_searches tomó %.2fs", time.monotonic() - t0)

        t0 = time.monotonic()
        collection.saved_searches, collection.sources_available["saved_searches"] = (
            _collect_saved_searches(client)
        )
        logger.debug("saved_searches tomó %.2fs", time.monotonic() - t0)

        known_indexes = (
            set(collection.ingest["index"].unique())
            if collection.ingest is not None and "index" in collection.ingest.columns
            else set()
        )
        t0 = time.monotonic()
        collection.last_seen, collection.sources_available["last_seen"] = _collect_last_seen(
            client, queries_path, known_indexes
        )
        logger.debug("last_seen tomó %.2fs", time.monotonic() - t0)

        # Dashboards: fuente manual por diseño en AMBOS collectors (D002,
        # docs/splunk-data-sources.md sección 7) -- Splunk no expone una API
        # confiable de "qué dataset usa cada panel". No es un fallo del modo
        # REST, es una limitación estructural conocida y aceptada.
        collection.sources_available["dashboards_used"] = SignalAvailability.NOT_APPLICABLE
        collection.sources_available["protected_overrides"] = SignalAvailability.NOT_APPLICABLE

    return collection
