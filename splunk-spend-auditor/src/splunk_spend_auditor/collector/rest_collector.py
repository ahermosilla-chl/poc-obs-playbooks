"""Collector para el modo REST (D002) -- conexión directa y de solo lectura
a una instancia Splunk real.

ESTADO: validado en Fase 3A contra una instancia Splunk Enterprise 10.4.3
real (Trial license, laboratorio Docker) -- ver PROJECT_STATUS.md y
DECISIONS.md D010/D011/D012. Endurecido en Fase 3B (D013/D014) contra fallos
reales de red/autenticación/permisos y contra la pérdida silenciosa de
señales -- ver PROJECT_STATUS.md, sección "Fase 3B".

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

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd

from splunk_spend_auditor.collector.csv_collector import RawCollection
from splunk_spend_auditor.models import SignalAvailability

logger = logging.getLogger(__name__)

_SEARCH_JOBS_ENDPOINT = "/services/search/jobs"
# Wildcard de user/app -- ver docs/splunk-data-sources.md sección 3, "gotcha
# de scoping": sin esto se pierden saved searches de otros usuarios/apps.
_SAVED_SEARCHES_ENDPOINT = "/servicesNS/-/-/saved/searches"

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
    """Traduce una excepción técnica (httpx/Splunk) a un mensaje breve y
    accionable para el usuario del CLI (item 8, "CLI Error UX"). El detalle
    técnico completo se conserva en el log (logger.debug) y en
    `exc.__cause__`, no se descarta."""

    if isinstance(exc, httpx.ConnectError):
        return f"No se pudo conectar a Splunk para {context} (host/puerto inaccesible o connection refused)."
    if isinstance(exc, httpx.ConnectTimeout):
        return f"Timeout conectando a Splunk para {context}."
    if isinstance(exc, httpx.ReadTimeout | httpx.PoolTimeout):
        return f"Timeout esperando la respuesta de Splunk para {context}."
    if isinstance(exc, httpx.RequestError):
        return f"Error de red/TLS contactando Splunk para {context}: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return f"Autenticación falló (401) obteniendo {context} -- el token es inválido o expiró."
        if status == 403:
            return f"Permisos insuficientes (403) para obtener {context} -- revisa las capabilities del rol del token."
        if status == 404:
            return f"Endpoint no encontrado (404) obteniendo {context} -- verifica la versión de Splunk/la ruta del endpoint."
        if status == 429:
            return f"Splunk devolvió 429 (too many requests) obteniendo {context} -- reintenta más tarde."
        if 500 <= status < 600:
            return f"Splunk devolvió un error de servidor ({status}) obteniendo {context}."
        return f"Splunk devolvió HTTP {status} obteniendo {context}."
    if isinstance(exc, SplunkQueryError):
        return f"La query de Splunk para {context} falló: {exc}"
    if isinstance(exc, ValueError):
        return f"Respuesta de Splunk malformada (JSON inválido) obteniendo {context}."
    return f"Error inesperado obteniendo {context}: {exc}"


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
    return httpx.Client(
        base_url=f"https://{config.host}:{config.port}",
        headers={"Authorization": f"Bearer {config.token}"},
        verify=config.verify_ssl,
        timeout=config.timeout_seconds,
        transport=config.transport,
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
    text = (queries_path / filename).read_text()
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


def _collect_audit_searches(
    client: httpx.Client, queries_path: Path
) -> tuple[pd.DataFrame | None, SignalAvailability]:
    try:
        df = _run_oneshot_search(client, _load_query(queries_path, "audit_interactive_searches.spl"))
        return df, SignalAvailability.AVAILABLE
    except _RECOVERABLE_REST_ERRORS + (SplunkQueryError, ValueError) as exc:
        logger.debug("audit_searches no disponible: %s", exc, exc_info=True)
        return None, SignalAvailability.ERROR


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


def collect(config: RestConfig, queries_dir: str) -> RawCollection:
    """Punto de entrada del modo REST. Ejecuta las mismas queries
    documentadas en queries/*.spl contra un Splunk real.

    Solo `ingest` es obligatorio (ver csv_collector.load_from_directory,
    mismo principio): si falla, se levanta RestCollectionError con un
    mensaje apto para el usuario. El resto de las fuentes son opcionales --
    su fallo se degrada a un SignalAvailability.ERROR/UNAVAILABLE explícito,
    nunca a "0 filas silenciosas". El collector NUNCA decide clasificación
    (POSSIBLE_WASTE/PROTECTED/REVIEW/UNKNOWN) -- solo recolecta y reporta
    disponibilidad; esa responsabilidad es exclusiva de scoring/rules.py."""

    queries_path = Path(queries_dir)
    collection = RawCollection()

    with _client(config) as client:
        try:
            collection.ingest = _collect_ingest(client, queries_path)
        except _RECOVERABLE_REST_ERRORS + (SplunkQueryError, ValueError) as exc:
            message = _describe_rest_error(exc, "ingest/license usage (fuente obligatoria)")
            logger.debug("ingest (obligatorio) falló: %s", exc, exc_info=True)
            raise RestCollectionError(message) from exc
        collection.sources_available["ingest"] = SignalAvailability.AVAILABLE

        t0 = time.monotonic()
        collection.audit_searches, collection.sources_available["audit_searches"] = (
            _collect_audit_searches(client, queries_path)
        )
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
