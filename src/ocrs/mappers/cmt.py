# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""CMT format mapper for canonical reviews."""

from __future__ import annotations

import uuid
from typing import Any

from ..catalog import alias_map, load_catalog
from ..util import (
    first_paragraph,
    guess_scale_from_value,
    map_recommendation_from_numeric,
    map_recommendation_from_text,
    normalize_linear,
    now_iso,
    parse_numeric_prefix,
)

NARR_KEYS = {"summary", "commentsToAuthors", "reviewText", "commentsToChairs"}


def from_cmt(payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    catalog = load_catalog()
    amap = alias_map(catalog)

    review_id = str(payload.get("reviewId") or payload.get("id") or uuid.uuid4())
    created_at = (
        payload.get("createdAt") if isinstance(payload.get("createdAt"), str) else now_iso()
    )

    work_id = str(payload.get("paperId") or payload.get("submissionId") or "unknown")
    venue = payload.get("conferenceName")
    track = payload.get("trackName")

    out: dict[str, Any] = {
        "review_id": review_id,
        "version": "1.0.0",
        "created_at": created_at,
        "provenance": {
            "source_system": "cmt",
            "source_review_id": str(payload.get("reviewId") or payload.get("id") or ""),
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
            "referee_id": (
                str(payload.get("reviewerId")) if payload.get("reviewerId") is not None else None
            ),
            "human_referee": {},
        },
        "target": {
            "work_id": work_id,
            "work_type": "other",
            "venue": venue,
            "track": track,
        },
        "metric_catalog_ref": catalog.get("catalog_id"),
        "metrics": [],
        "opinion": {"summary": "No summary provided."},
    }
    if keep_raw:
        out["provenance"]["raw_payload"] = payload

    # Narrative
    nar = {}
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        nar["summary"] = summary.strip()
        out["opinion"]["summary"] = summary.strip()
    review_text = payload.get("commentsToAuthors") or payload.get("reviewText")
    if isinstance(review_text, str) and review_text.strip():
        nar["detailed_review"] = review_text.strip()
        if out["opinion"]["summary"] == "No summary provided.":
            out["opinion"]["summary"] = first_paragraph(review_text.strip())
    chairs = payload.get("commentsToChairs")
    if isinstance(chairs, str) and chairs.strip():
        nar["confidential_to_editors"] = chairs.strip()
    if nar:
        out["narrative"] = nar

    # Decision
    dec = {}
    rec_raw = payload.get("overallEvaluation") or payload.get("recommendation")
    if rec_raw is not None:
        num, rest = parse_numeric_prefix(rec_raw)
        if num is not None:
            scale = guess_scale_from_value(num)
            dec["recommendation"] = (
                map_recommendation_from_numeric(num, scale)
                or map_recommendation_from_text(rest or "")
                or "borderline"
            )
            n01 = normalize_linear(num, scale)
            out["metrics"].append(
                {
                    "key": "overall",
                    "label": "Overall Assessment",
                    "aspect": "overall",
                    "scale": scale,
                    "value": num,
                    "normalized": (
                        {"value_0_1": n01, "method": "linear_to_unit_interval"}
                        if n01 is not None
                        else None
                    ),
                }
            )
        elif isinstance(rec_raw, str):
            dec["recommendation"] = map_recommendation_from_text(rec_raw) or "borderline"
    conf_raw = payload.get("confidence")
    if conf_raw is not None:
        num, _ = parse_numeric_prefix(conf_raw)
        if num is not None:
            scale = guess_scale_from_value(num)
            n01 = normalize_linear(num, scale)
            out["metrics"].append(
                {
                    "key": "confidence",
                    "label": "Reviewer Confidence",
                    "aspect": "confidence",
                    "scale": scale,
                    "value": num,
                    "normalized": (
                        {"value_0_1": n01, "method": "linear_to_unit_interval"}
                        if n01 is not None
                        else None
                    ),
                }
            )
            if n01 is not None:
                dec["confidence"] = float(max(0.0, min(1.0, n01)))
    if dec:
        out["decision"] = {k: v for k, v in dec.items() if v is not None}

    # Metrics from remaining numeric fields
    for k, v in payload.items():
        if k in NARR_KEYS or k in {
            "reviewId",
            "id",
            "createdAt",
            "paperId",
            "submissionId",
            "conferenceName",
            "trackName",
            "reviewerId",
            "overallEvaluation",
            "recommendation",
            "confidence",
        }:
            continue
        num, rest = parse_numeric_prefix(v)
        if num is None:
            continue
        label = k.replace("_", " ").strip()
        lcf = label.casefold()
        key = amap.get(lcf, "other")
        aspect = next(
            (m.get("aspect") for m in catalog.get("metrics", []) if m["key"] == key),
            "other",
        )
        scale = guess_scale_from_value(num)
        n01 = normalize_linear(num, scale)
        mm = {"key": key, "label": label, "aspect": aspect, "scale": scale, "value": num}
        if n01 is not None:
            mm["normalized"] = {
                "value_0_1": float(max(0.0, min(1.0, n01))),
                "method": "linear_to_unit_interval",
            }
        if rest:
            mm["justification"] = rest
        out["metrics"].append(mm)

    if out.get("referee", {}).get("referee_id") is None:
        out["referee"].pop("referee_id", None)

    # cleanup
    for m in out["metrics"]:
        if m.get("normalized") is None:
            m.pop("normalized", None)
    if not out.get("opinion", {}).get("summary") and not out.get("opinion", {}).get("text"):
        out["opinion"] = {"summary": "No opinion text provided."}
    return out


def to_cmt(canonical: dict[str, Any]) -> dict[str, Any]:
    # Lossy dict approximating a CMT export row
    out: dict[str, Any] = {}
    out["reviewId"] = canonical.get("review_id")
    out["paperId"] = canonical.get("target", {}).get("work_id")
    out["conferenceName"] = canonical.get("target", {}).get("venue")
    out["trackName"] = canonical.get("target", {}).get("track")
    out["reviewerId"] = canonical.get("referee", {}).get("referee_id")

    # narrative/opinion
    op = canonical.get("opinion", {}) or {}
    if isinstance(op.get("summary"), str):
        out["summary"] = op["summary"]
    nar = canonical.get("narrative", {}) or {}
    if isinstance(nar.get("detailed_review"), str):
        out["commentsToAuthors"] = nar["detailed_review"]
    elif isinstance(op.get("text"), str):
        out["commentsToAuthors"] = op["text"]
    if isinstance(nar.get("confidential_to_editors"), str):
        out["commentsToChairs"] = nar["confidential_to_editors"]

    # decision + metrics
    dec = canonical.get("decision", {}) or {}
    if isinstance(dec.get("recommendation"), str):
        out["recommendation"] = dec["recommendation"]
    # store overall/confidence metrics explicitly if available
    for m in canonical.get("metrics", []) or []:
        if not isinstance(m, dict):
            continue
        if m.get("key") == "overall":
            out.setdefault("overallEvaluation", m.get("value"))
        if m.get("key") == "confidence":
            out.setdefault("confidence", m.get("value"))
    return out
