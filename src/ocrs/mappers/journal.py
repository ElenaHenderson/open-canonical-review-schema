# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Journal narrative format mapper for canonical reviews."""

from __future__ import annotations

import uuid
from typing import Any

from ..util import first_paragraph, now_iso


def _build_target_identifiers(payload: dict[str, Any]) -> dict[str, Any]:
    """Build structured identifiers from journal payload."""
    from ..identifiers import DOI_PATTERN

    identifiers: dict[str, Any] = {}

    # DOI is primary for journal articles
    doi = payload.get("doi")
    if isinstance(doi, str) and doi and DOI_PATTERN.match(doi):
        identifiers["doi"] = {"value": doi, "hyperlink": f"https://doi.org/{doi}"}

    # Manuscript ID as internal_id
    ms_id = payload.get("manuscript_id")
    if isinstance(ms_id, str) and ms_id:
        identifiers["internal_id"] = {
            "field_name": "manuscript_id",
            "value": ms_id,
        }
    elif payload.get("work_id"):
        identifiers["internal_id"] = {
            "field_name": "work_id",
            "value": str(payload["work_id"]),
        }

    return identifiers


def from_journal_narrative(
    payload: dict[str, Any],
    *,
    keep_raw: bool = False,
) -> dict[str, Any]:
    review_id = str(payload.get("review_id") or payload.get("id") or uuid.uuid4())
    created_at = (
        payload.get("created_at") if isinstance(payload.get("created_at"), str) else now_iso()
    )
    full_text = payload.get("full_text") if isinstance(payload.get("full_text"), str) else ""

    work_id = str(
        payload.get("doi") or payload.get("manuscript_id") or payload.get("work_id") or "unknown"
    )
    venue = payload.get("journal") or payload.get("venue")

    out: dict[str, Any] = {
        "review_id": review_id,
        "version": "1.0.0",
        "created_at": created_at,
        "provenance": {
            "source_system": "journal_narrative",
            "source_review_id": str(payload.get("source_review_id") or payload.get("id") or ""),
            "imported_at": now_iso(),
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": {
            "referee_type": "human",
            "identity_mode": "confidential",
            "referee_id": payload.get("reviewer_id"),
            "human_referee": {},
        },
        "target": {
            "identifiers": _build_target_identifiers(payload),
            "work_id": work_id,  # Keep for backward compatibility
            "work_type": "article",
            "venue": venue,
        },
        "metrics": [],
        "opinion": {
            "summary": (
                first_paragraph(full_text, max_len=500)
                if full_text.strip()
                else "No opinion text provided."
            )
        },
        "narrative": {"detailed_review": full_text.strip()} if full_text.strip() else {},
    }

    if out.get("referee", {}).get("referee_id") is None:
        out["referee"].pop("referee_id", None)

    if keep_raw:
        out["provenance"]["raw_payload"] = payload
    return out


def to_journal_narrative(canonical: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["doi"] = canonical.get("target", {}).get("work_id")
    out["journal"] = canonical.get("target", {}).get("venue")
    out["review_id"] = canonical.get("review_id")
    out["created_at"] = canonical.get("created_at")
    # Narrative text
    nar = canonical.get("narrative", {}) or {}
    text = None
    if isinstance(nar.get("detailed_review"), str) and nar["detailed_review"].strip():
        text = nar["detailed_review"].strip()
    else:
        op = canonical.get("opinion", {}) or {}
        if isinstance(op.get("text"), str) and op["text"].strip():
            text = op["text"].strip()
        elif isinstance(op.get("summary"), str):
            text = op["summary"]
    out["full_text"] = text or ""
    return out
