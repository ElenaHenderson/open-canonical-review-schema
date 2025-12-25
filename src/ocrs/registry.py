# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Registry of source/target mappers for canonical review conversion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .mappers.cmt import from_cmt, to_cmt
from .mappers.editorialmanager import from_editorialmanager, to_editorialmanager
from .mappers.hotcrp import from_hotcrp, to_hotcrp
from .mappers.journal import from_journal_narrative, to_journal_narrative
from .mappers.openreview import from_openreview, to_openreview
from .mappers.scholarone import from_scholarone, to_scholarone
from .schema import validate_canonical

_FROM: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "cmt": from_cmt,
    "editorialmanager": from_editorialmanager,
    "hotcrp": from_hotcrp,
    "journal_narrative": from_journal_narrative,
    "openreview": from_openreview,
    "scholarone": from_scholarone,
}

_TO: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "cmt": to_cmt,
    "editorialmanager": to_editorialmanager,
    "hotcrp": to_hotcrp,
    "journal_narrative": to_journal_narrative,
    "openreview": to_openreview,
    "scholarone": to_scholarone,
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
