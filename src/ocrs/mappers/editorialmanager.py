# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Editorial Manager format mapper for canonical reviews."""

from __future__ import annotations

import uuid
from typing import Any

from ..catalog import alias_map, load_catalog
from ..util import (
    first_paragraph,
    map_recommendation_from_text,
    normalize_linear,
    now_iso,
    parse_date_flexible,
)

# Editorial Manager recommendation codes
EM_RECOMMENDATION_MAP = {
    1: "accept",
    2: "minor_revision",
    3: "major_revision",
    4: "reject",
    5: "revise",  # Reject and Encourage Resubmission
}


def _extract_time(payload: dict[str, Any]) -> str:
    """Extract timestamp from Editorial Manager payload."""
    for k in ("dateReceived", "date_received", "reviewDate", "created_at"):
        v = payload.get(k)
        if v is not None:
            return parse_date_flexible(v)
    return now_iso()


def _get_reviewer_id(payload: dict[str, Any]) -> str | None:
    """Extract reviewer identifier."""
    for k in ("reviewerId", "reviewer_id", "reviewerEmail"):
        v = payload.get(k)
        if v is not None:
            return str(v)
    return None


def _get_work_id(payload: dict[str, Any]) -> str:
    """Extract manuscript/work identifier."""
    for k in ("manuscriptId", "manuscript_id", "ms_id", "documentId"):
        v = payload.get(k)
        if v is not None:
            return str(v)
    return "unknown"


def _get_review_id(payload: dict[str, Any]) -> str:
    """Extract review identifier."""
    for k in ("reviewId", "review_id", "id"):
        v = payload.get(k)
        if v is not None:
            return str(v)
    return str(uuid.uuid4())


def _parse_recommendation(payload: dict[str, Any]) -> str | None:
    """Parse recommendation from Editorial Manager payload."""
    # Try recommendation code first
    code = payload.get("recommendationCode")
    if isinstance(code, int) and code in EM_RECOMMENDATION_MAP:
        return EM_RECOMMENDATION_MAP[code]

    # Try text recommendation
    rec = payload.get("recommendation")
    if isinstance(rec, str):
        return map_recommendation_from_text(rec)

    return None


def _best_opinion_text(payload: dict[str, Any]) -> str:
    """Find the best text for the opinion summary."""
    for k in ("commentsToAuthor", "comments_to_author", "summary", "comments"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return first_paragraph(v.strip(), max_len=500)
    return "No summary provided."


def _map_ratings_to_metrics(
    ratings: list[dict[str, Any]],
    catalog: dict[str, Any],
    amap: dict[str, str],
) -> list[dict[str, Any]]:
    """Convert Editorial Manager ratings array to canonical metrics."""
    metrics = []
    idx = {m["key"].casefold(): m for m in catalog.get("metrics", [])}

    for rating in ratings:
        if not isinstance(rating, dict):
            continue

        question = rating.get("question") or rating.get("criterionName") or ""
        score = rating.get("score")
        max_score = rating.get("maxScore") or rating.get("max_score") or 5

        if score is None:
            continue

        # Map question to metric key
        lcf = question.casefold().strip()
        key = "other"
        aspect = "other"

        if lcf in idx:
            m = idx[lcf]
            key = m["key"]
            aspect = m.get("aspect", "other")
        elif lcf in amap:
            key = amap[lcf]
        else:
            # Fuzzy match
            for alias, k in amap.items():
                if alias in lcf or lcf in alias:
                    key = k
                    break

        # Look up aspect from catalog if we found a key
        if key != "other":
            for m in catalog.get("metrics", []):
                if m["key"] == key:
                    aspect = m.get("aspect", "other")
                    break

        scale = {"type": "ordinal", "min": 1, "max": int(max_score)}
        norm = normalize_linear(score, scale)

        metric: dict[str, Any] = {
            "key": key,
            "label": question,
            "aspect": aspect,
            "scale": scale,
            "value": score,
        }
        if norm is not None:
            metric["normalized"] = {
                "value_0_1": float(max(0.0, min(1.0, norm))),
                "method": "linear_to_unit_interval",
            }

        # Add label from rating if present
        if rating.get("label"):
            metric["justification"] = rating["label"]

        metrics.append(metric)

    return metrics


def from_editorialmanager(payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    """Convert an Editorial Manager review to canonical format.

    Args:
        payload: Editorial Manager review data (from API or export).
        keep_raw: If True, preserve the original payload in provenance.raw_payload.

    Returns:
        A canonical review dictionary.
    """
    catalog = load_catalog()
    amap = alias_map(catalog)

    created = _extract_time(payload)
    work_id = _get_work_id(payload)
    reviewer_id = _get_reviewer_id(payload)
    review_id = _get_review_id(payload)

    referee: dict[str, Any] = {
        "referee_type": "human",
        "identity_mode": "confidential",
        "human_referee": {},
    }
    if reviewer_id:
        referee["referee_id"] = reviewer_id

    out: dict[str, Any] = {
        "review_id": f"em_{review_id}",
        "version": "1.0.0",
        "created_at": created,
        "provenance": {
            "source_system": "editorialmanager",
            "source_review_id": review_id,
            "imported_at": now_iso(),
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": referee,
        "target": {"work_id": work_id, "work_type": "article"},
        "metric_catalog_ref": catalog.get("catalog_id"),
        "metrics": [],
        "opinion": {"summary": _best_opinion_text(payload)},
    }

    if keep_raw:
        out["provenance"]["raw_payload"] = payload

    # Map venue
    venue = payload.get("journalName") or payload.get("journal_name")
    if venue:
        out["target"]["venue"] = venue

    # Narrative mapping
    narrative: dict[str, Any] = {}

    for src, dst in [
        ("commentsToAuthor", "detailed_review"),
        ("comments_to_author", "detailed_review"),
        ("confidentialCommentsToEditor", "confidential_to_editors"),
        ("confidential_comments_to_editor", "confidential_to_editors"),
        ("summary", "summary"),
    ]:
        v = payload.get(src)
        if isinstance(v, str) and v.strip():
            if dst not in narrative:
                narrative[dst] = v.strip()

    if narrative:
        out["narrative"] = narrative

    # Decision
    rec = _parse_recommendation(payload)
    if rec:
        out["decision"] = {"recommendation": rec}

    # Revision number -> round
    rev = payload.get("revisionNumber")
    if rev is not None:
        # EM uses 0-based revision numbers, we use 1-based rounds
        out["review_context"] = {"round": int(rev) + 1}

    # Ratings -> metrics
    ratings = payload.get("ratings", [])
    if isinstance(ratings, list) and ratings:
        out["metrics"] = _map_ratings_to_metrics(ratings, catalog, amap)

    return out


def to_editorialmanager(canonical: dict[str, Any]) -> dict[str, Any]:
    """Convert a canonical review to Editorial Manager format (basic stub).

    This is a lossy conversion that produces a minimal EM-like structure.

    Args:
        canonical: A canonical review dictionary.

    Returns:
        An Editorial Manager-like review dictionary.
    """
    # Extract review ID
    rid = canonical.get("review_id", "")
    if rid.startswith("em_"):
        rid = rid[3:]

    out: dict[str, Any] = {
        "reviewId": rid,
        "manuscriptId": canonical.get("target", {}).get("work_id"),
    }

    # Map venue
    venue = canonical.get("target", {}).get("venue")
    if venue:
        out["journalName"] = venue

    # Map narrative
    nar = canonical.get("narrative", {}) or {}
    op = canonical.get("opinion", {}) or {}

    if nar.get("detailed_review"):
        out["commentsToAuthor"] = nar["detailed_review"]
    elif op.get("text"):
        out["commentsToAuthor"] = op["text"]
    elif op.get("summary"):
        out["commentsToAuthor"] = op["summary"]

    if nar.get("confidential_to_editors"):
        out["confidentialCommentsToEditor"] = nar["confidential_to_editors"]

    # Map recommendation
    dec = canonical.get("decision", {}) or {}
    if isinstance(dec.get("recommendation"), str):
        out["recommendation"] = dec["recommendation"].replace("_", " ").title()

    # Map round -> revisionNumber
    ctx = canonical.get("review_context", {}) or {}
    if ctx.get("round"):
        out["revisionNumber"] = ctx["round"] - 1

    # Map metrics -> ratings
    ratings = []
    for m in canonical.get("metrics", []) or []:
        if not isinstance(m, dict):
            continue
        rating: dict[str, Any] = {
            "question": m.get("label") or m.get("key", ""),
            "score": m.get("value"),
        }
        scale = m.get("scale", {})
        if isinstance(scale, dict) and "max" in scale:
            rating["maxScore"] = scale["max"]
        else:
            rating["maxScore"] = 5
        ratings.append(rating)

    if ratings:
        out["ratings"] = ratings

    return out
