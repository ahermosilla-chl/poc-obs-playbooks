"""Parser de SPL para extraer qué (index, sourcetype) toca una búsqueda.

Ver docs/scoring.md sección 3 y DECISIONS.md D006: este parser NO intenta
cubrir el 100% del lenguaje SPL. Es deliberadamente conservador: prefiere
marcar PARTIAL/UNKNOWN antes que adivinar y arriesgar un falso positivo de
"este dataset no tiene uso".

Confianza:
  HIGH    -> se extrajeron uno o más pares (index=, sourcetype=) explícitos,
             literales, sin depender de resolver macros/eventtypes/subsearches.
  PARTIAL -> se detectó una macro, eventtype, subsearch o tstats/datamodel,
             pero no se resolvió su contenido. Puede que TAMBIÉN haya
             literales HIGH en la misma búsqueda (ej. una macro que además
             tiene un index= explícito fuera de la macro) -- en ese caso se
             devuelven los literales HIGH y se marca has_partial=True para
             que el llamador sepa que la cobertura es incompleta.
  UNKNOWN -> no se encontró ningún patrón reconocido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from splunk_spend_auditor.models import DatasetKey, ParserConfidence

# Patrones que indican que la búsqueda depende de algo que NO resolvemos.
_PARTIAL_PATTERNS = [
    re.compile(r"`[a-zA-Z_][\w]*`"),  # macro: `nombre_macro`
    re.compile(r"\beventtype\s*=", re.IGNORECASE),
    re.compile(r"\btstats\b.*\bdatamodel\s*=", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[\s*search\b", re.IGNORECASE),  # subsearch: [ search ... ]
    re.compile(r"\blookup\b", re.IGNORECASE),
]

# Dos estilos de lista OR que SPL permite y que hay que soportar por separado:
#   Estilo A (keyword una vez):     index=(web OR proxy)
#   Estilo B (keyword repetido):    (index=web OR index=proxy)
# Se procesa primero el Estilo A (regex de grupo con paréntesis) y se "borra"
# del texto para que el Estilo B / valor simple no lo vuelva a capturar.
_INDEX_GROUP = re.compile(r"\bindex\s*=\s*\(([^)]*)\)", re.IGNORECASE)
_INDEX_SINGLE = re.compile(r"\bindex\s*=\s*[\"']?([\w\-\*]+)[\"']?", re.IGNORECASE)
_SOURCETYPE_GROUP = re.compile(r"\bsourcetype\s*=\s*\(([^)]*)\)", re.IGNORECASE)
_SOURCETYPE_SINGLE = re.compile(
    r"\bsourcetype\s*=\s*[\"']?([\w\-:\*]+)[\"']?", re.IGNORECASE
)
_STRIP_QUOTES = re.compile(r"^[\"']|[\"']$")


def _extract_field_values(
    text: str, group_re: re.Pattern[str], single_re: re.Pattern[str]
) -> list[str]:
    """Extrae todos los valores de un campo (index= o sourcetype=), sea que
    aparezcan como lista agrupada 'campo=(a OR b)' o repetidos
    '(campo=a OR campo=b)' o como valor simple 'campo=a'."""

    values: list[str] = []

    def _consume_group(m: re.Match[str]) -> str:
        content = m.group(1)
        for part in re.split(r"\s+OR\s+", content, flags=re.IGNORECASE):
            part = _STRIP_QUOTES.sub("", part.strip())
            if part and part != "*":
                values.append(part)
        # Se reemplaza por espacios (misma longitud) para no perder offsets
        # y para que el regex de valor simple no vuelva a matchear dentro.
        return " " * len(m.group(0))

    remaining_text = group_re.sub(_consume_group, text)

    for m in single_re.finditer(remaining_text):
        value = m.group(1)
        if value and value != "*":
            values.append(value)

    return values


@dataclass
class ParseResult:
    confidence: ParserConfidence
    datasets: list[DatasetKey] = field(default_factory=list)
    has_partial_evidence: bool = False


def parse_search(search_text: str) -> ParseResult:
    """Analiza un único texto SPL y devuelve los datasets que toca con HIGH
    confianza, si los hay, y si además hay evidencia PARTIAL en la misma
    búsqueda (macros, eventtypes, etc. que no se resolvieron)."""

    if not search_text or not search_text.strip():
        return ParseResult(confidence=ParserConfidence.UNKNOWN)

    has_partial = any(p.search(search_text) for p in _PARTIAL_PATTERNS)

    indexes = _extract_field_values(search_text, _INDEX_GROUP, _INDEX_SINGLE)
    sourcetypes = _extract_field_values(
        search_text, _SOURCETYPE_GROUP, _SOURCETYPE_SINGLE
    )
    # dedup preservando orden
    indexes = list(dict.fromkeys(indexes))
    sourcetypes = list(dict.fromkeys(sourcetypes))

    datasets: list[DatasetKey] = []
    if indexes and sourcetypes:
        # Producto cruzado explícito: "index=(a OR b) sourcetype=(x OR y)"
        # toca las 4 combinaciones. Es una simplificación deliberada -- en
        # SPL real esto es casi siempre lo que se quiere decir.
        for idx in indexes:
            for st in sourcetypes:
                datasets.append(DatasetKey(index=idx, sourcetype=st))
    elif indexes and not sourcetypes:
        # Solo index= explícito: no podemos saber a qué sourcetype se
        # refiere con certeza -> no es HIGH para ningún (index, sourcetype)
        # concreto, pero tampoco es evidencia completamente vacía. Se trata
        # como PARTIAL (sabemos el index, no el par completo).
        has_partial = True
    elif sourcetypes and not indexes:
        has_partial = True

    if datasets:
        return ParseResult(
            confidence=ParserConfidence.HIGH,
            datasets=datasets,
            has_partial_evidence=has_partial,
        )
    if has_partial:
        return ParseResult(confidence=ParserConfidence.PARTIAL)
    return ParseResult(confidence=ParserConfidence.UNKNOWN)
