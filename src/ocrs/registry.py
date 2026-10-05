# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Registry of source/target mappers for canonical review conversion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .mappers import openaireview, pat
from .mappers._ai import AiPayload
from .mappers.cmt import from_cmt, to_cmt
from .mappers.editorialmanager import from_editorialmanager, to_editorialmanager
from .mappers.hotcrp import from_hotcrp, to_hotcrp
from .mappers.journal import from_journal_narrative, to_journal_narrative
from .mappers.openaireview import from_openaireview, map_openaireview
from .mappers.openreview import from_openreview, to_openreview
from .mappers.pat import from_pat, map_pat
from .mappers.scholarone import from_scholarone, to_scholarone
from .mapping import MappingResult
from .schema import validate_canonical

_FROM: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "cmt": from_cmt,
    "editorialmanager": from_editorialmanager,
    "hotcrp": from_hotcrp,
    "journal_narrative": from_journal_narrative,
    "openaireview": from_openaireview,
    "openreview": from_openreview,
    "pat": from_pat,
    "scholarone": from_scholarone,
}

_MAPPER_VERSIONS = {"openaireview": openaireview.MAPPER_VERSION, "pat": pat.MAPPER_VERSION}

# Sources whose mappers also return a mapping record (steps and gaps).
_FROM_WITH_RECORD: dict[str, Callable[[AiPayload], MappingResult]] = {
    "openaireview": map_openaireview,
    "pat": map_pat,
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


def mapper_version(source: str) -> str:
    if source not in _MAPPER_VERSIONS:
        raise ValueError(f"No mapping record for {source}. Supported: {sorted(_MAPPER_VERSIONS)}")
    return _MAPPER_VERSIONS[source]


def map_with_record(source: str, payload: dict[str, Any]) -> MappingResult:
    """Map AI reviewer output to OCRS, with a record of each step and the gaps.

    `payload` is `{"output": <the reviewer's own file>, "run": <AiRun>, "blocks": [<Block>]}`.
    """
    if source not in _FROM_WITH_RECORD:
        raise ValueError(f"No mapping record for {source}. Supported: {sorted(_FROM_WITH_RECORD)}")
    return _FROM_WITH_RECORD[source](AiPayload.model_validate(payload))


def map_to(target: str, canonical_review: dict[str, Any]) -> dict[str, Any]:
    validate_canonical(canonical_review)
    if target not in _TO:
        raise ValueError(f"Unsupported target: {target}. Supported: {supported_targets()}")
    return _TO[target](canonical_review)
