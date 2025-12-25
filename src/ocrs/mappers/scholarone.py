# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""ScholarOne format mapper for canonical reviews."""

from __future__ import annotations

import uuid
from typing import Any

from ..catalog import alias_map, load_catalog
from ..util import (
    first_paragraph,
    map_recommendation_from_numeric,
    map_recommendation_from_text,
    normalize_linear,
    now_iso,
    parse_date_flexible,
)

# ScholarOne recommendation codes (typical configuration)
S1_RECOMMENDATION_MAP = {
    1: "accept",
    2: "minor_revision",
    3: "major_revision",
    4: "reject",
    5: "revise",  # Reject with option to resubmit
}


def _extract_time(payload: dict[str, Any]) -> str:
    """Extract timestamp from ScholarOne payload."""
    for k in (
        "dateReviewReceived",
        "date_review_received",
        "reviewDate",
        "created_at",
    ):
        v = payload.get(k)
        if v is not None:
            return parse_date_flexible(v)
    return now_iso()


def _get_reviewer_id(payload: dict[str, Any]) -> str | None:
    """Extract reviewer identifier."""
    # ScholarOne often uses reviewer number rather than ID
    reviewer_num = payload.get("reviewerNumber") or payload.get("reviewer_number")
    if reviewer_num is not None:
        return f"reviewer_{reviewer_num}"
    for k in ("reviewerId", "reviewer_id", "reviewerOrcid"):
        v = payload.get(k)
        if v is not None:
            return str(v)
    return None


def _get_work_id(payload: dict[str, Any]) -> str:
    """Extract document/work identifier."""
    for k in ("documentId", "document_id", "submissionId", "submission_id", "ms_id"):
        v = payload.get(k)
        if v is not None:
            return str(v)
    return "unknown"


def _get_review_id(payload: dict[str, Any]) -> str:
    """Generate a review identifier from ScholarOne fields."""
    doc_id = payload.get("documentId") or payload.get("document_id") or ""
    sub_id = payload.get("submissionId") or payload.get("submission_id") or ""
    rev_num = payload.get("reviewerNumber") or payload.get("reviewer_number") or ""

    if doc_id and rev_num:
        return f"{doc_id}_r{rev_num}"
    if sub_id and rev_num:
        return f"{sub_id}_r{rev_num}"
    if doc_id:
        return str(doc_id)
    return str(uuid.uuid4())


def _parse_recommendation(payload: dict[str, Any]) -> str | None:
    """Parse recommendation from ScholarOne payload."""
    # Try numeric recommendation first
    rec_num = payload.get("overallRecommendation")
    if isinstance(rec_num, int) and rec_num in S1_RECOMMENDATION_MAP:
        return S1_RECOMMENDATION_MAP[rec_num]

    # Try to map numeric to recommendation using scale
    if isinstance(rec_num, int):
        scale = {"type": "ordinal", "min": 1, "max": 5}
        mapped = map_recommendation_from_numeric(rec_num, scale)
        if mapped:
            return mapped

    # Try text label
    rec_label = payload.get("overallRecommendationLabel")
    if isinstance(rec_label, str):
        return map_recommendation_from_text(rec_label)

    return None


def _best_opinion_text(payload: dict[str, Any]) -> str:
    """Find the best text for the opinion summary."""
    for k in ("commentsToAuthor", "comments_to_author", "summary"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return first_paragraph(v.strip(), max_len=500)
    return "No summary provided."


def _map_criteria_to_metrics(
    criteria: list[dict[str, Any]],
    catalog: dict[str, Any],
    amap: dict[str, str],
) -> list[dict[str, Any]]:
    """Convert ScholarOne criteriaResponses to canonical metrics."""
    metrics = []
    idx = {m["key"].casefold(): m for m in catalog.get("metrics", [])}

    for crit in criteria:
        if not isinstance(crit, dict):
            continue

        name = crit.get("criterionName") or crit.get("name") or ""
        response = crit.get("response") or crit.get("score")
        max_response = crit.get("maxResponse") or crit.get("max_response") or 5

        if response is None:
            continue

        # Map criterion name to metric key
        lcf = name.casefold().strip()
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

        scale = {"type": "ordinal", "min": 1, "max": int(max_response)}
        norm = normalize_linear(response, scale)

        metric: dict[str, Any] = {
            "key": key,
            "label": name,
            "aspect": aspect,
            "scale": scale,
            "value": response,
        }
        if norm is not None:
            metric["normalized"] = {
                "value_0_1": float(max(0.0, min(1.0, norm))),
                "method": "linear_to_unit_interval",
            }

        # Add label from criterion if present
        if crit.get("label"):
            metric["justification"] = crit["label"]

        metrics.append(metric)

    return metrics


def from_scholarone(payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    """Convert a ScholarOne review to canonical format.

    Args:
        payload: ScholarOne review data (from Web Services API or export).
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

    # Build referee object, only adding referee_id if present
    referee: dict[str, Any] = {
        "referee_type": "human",
        "identity_mode": "confidential",
        "human_referee": {},
    }
    if reviewer_id:
        referee["referee_id"] = reviewer_id

    out: dict[str, Any] = {
        "review_id": f"s1_{review_id}",
        "version": "1.0.0",
        "created_at": created,
        "provenance": {
            "source_system": "scholarone",
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
        ("commentsToEditor", "confidential_to_editors"),
        ("comments_to_editor", "confidential_to_editors"),
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

        # Also add overall metric if we have numeric recommendation
        rec_num = payload.get("overallRecommendation")
        if isinstance(rec_num, int):
            scale = {"type": "ordinal", "min": 1, "max": 5}
            norm = normalize_linear(rec_num, scale)
            out["metrics"].append(
                {
                    "key": "overall",
                    "label": "Overall Recommendation",
                    "aspect": "overall",
                    "scale": scale,
                    "value": rec_num,
                    "normalized": (
                        {"value_0_1": norm, "method": "linear_to_unit_interval"}
                        if norm is not None
                        else None
                    ),
                }
            )

    # Criteria responses -> metrics
    criteria = payload.get("criteriaResponses", [])
    if isinstance(criteria, list) and criteria:
        out["metrics"].extend(_map_criteria_to_metrics(criteria, catalog, amap))

    # Clean up null normalized values
    for m in out["metrics"]:
        if m.get("normalized") is None:
            m.pop("normalized", None)

    # Competing interests
    coi = payload.get("competingInterests")
    if isinstance(coi, str) and coi.strip().lower() not in ("none", "none declared"):
        out["referee"]["competing_interests_declared"] = True
        out["referee"]["competing_interests_statement"] = coi
    elif coi:
        out["referee"]["competing_interests_declared"] = False

    return out


def to_scholarone(canonical: dict[str, Any]) -> dict[str, Any]:
    """Convert a canonical review to ScholarOne format (basic stub).

    This is a lossy conversion that produces a minimal ScholarOne-like structure.

    Args:
        canonical: A canonical review dictionary.

    Returns:
        A ScholarOne-like review dictionary.
    """
    # Extract review ID
    rid = canonical.get("review_id", "")
    if rid.startswith("s1_"):
        rid = rid[3:]

    # Try to parse reviewer number from review_id
    reviewer_num = None
    if "_r" in rid:
        parts = rid.rsplit("_r", 1)
        if parts[1].isdigit():
            reviewer_num = int(parts[1])
            rid = parts[0]

    out: dict[str, Any] = {
        "documentId": canonical.get("target", {}).get("work_id"),
    }

    if reviewer_num:
        out["reviewerNumber"] = reviewer_num

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
        out["commentsToEditor"] = nar["confidential_to_editors"]

    # Map recommendation
    dec = canonical.get("decision", {}) or {}
    if isinstance(dec.get("recommendation"), str):
        rec = dec["recommendation"]
        # Reverse map to numeric
        reverse_map = {v: k for k, v in S1_RECOMMENDATION_MAP.items()}
        if rec in reverse_map:
            out["overallRecommendation"] = reverse_map[rec]
        out["overallRecommendationLabel"] = rec.replace("_", " ").title()

    # Map metrics -> criteriaResponses
    criteria = []
    for m in canonical.get("metrics", []) or []:
        if not isinstance(m, dict):
            continue
        # Skip overall metric (handled as recommendation)
        if m.get("key") == "overall":
            continue

        crit: dict[str, Any] = {
            "criterionName": m.get("label") or m.get("key", ""),
            "response": m.get("value"),
        }
        scale = m.get("scale", {})
        if isinstance(scale, dict) and "max" in scale:
            crit["maxResponse"] = scale["max"]
        else:
            crit["maxResponse"] = 5
        criteria.append(crit)

    if criteria:
        out["criteriaResponses"] = criteria

    return out
