from __future__ import annotations
from typing import Any, Dict, Callable

from .schema import validate_canonical
from .mappers.openreview import from_openreview, to_openreview
from .mappers.cmt import from_cmt, to_cmt
from .mappers.journal import from_journal_narrative, to_journal_narrative

_FROM: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "openreview": from_openreview,
    "cmt": from_cmt,
    "journal_narrative": from_journal_narrative
}

_TO: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "openreview": to_openreview,
    "cmt": to_cmt,
    "journal_narrative": to_journal_narrative
}

def supported_sources():
    return sorted(_FROM.keys())

def supported_targets():
    return sorted(_TO.keys())

def map_from(source: str, payload: Dict[str, Any], *, keep_raw: bool = False) -> Dict[str, Any]:
    if source not in _FROM:
        raise ValueError(f"Unsupported source: {source}. Supported: {supported_sources()}")
    out = _FROM[source](payload, keep_raw=keep_raw)
    validate_canonical(out)
    return out

def map_to(target: str, canonical_review: Dict[str, Any]) -> Dict[str, Any]:
    validate_canonical(canonical_review)
    if target not in _TO:
        raise ValueError(f"Unsupported target: {target}. Supported: {supported_targets()}")
    return _TO[target](canonical_review)
