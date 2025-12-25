# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Registry of source/target mappers for canonical review conversion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .mappers.cmt import from_cmt, to_cmt
from .mappers.journal import from_journal_narrative, to_journal_narrative
from .mappers.openreview import from_openreview, to_openreview
from .schema import validate_canonical

_FROM: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "openreview": from_openreview,
    "cmt": from_cmt,
    "journal_narrative": from_journal_narrative,
}

_TO: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "openreview": to_openreview,
    "cmt": to_cmt,
    "journal_narrative": to_journal_narrative,
}


def supported_sources():
    return sorted(_FROM.keys())


def supported_targets():
    return sorted(_TO.keys())


def map_from(source: str, payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    if source not in _FROM:
        raise ValueError(f"Unsupported source: {source}. Supported: {supported_sources()}")
    out = _FROM[source](payload, keep_raw=keep_raw)
    validate_canonical(out)
    return out


def map_to(target: str, canonical_review: dict[str, Any]) -> dict[str, Any]:
    validate_canonical(canonical_review)
    if target not in _TO:
        raise ValueError(f"Unsupported target: {target}. Supported: {supported_targets()}")
    return _TO[target](canonical_review)
