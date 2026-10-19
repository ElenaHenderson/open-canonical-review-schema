# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""OpenReview format mapper for canonical reviews."""

from __future__ import annotations

import uuid
from typing import Any

from ..catalog import alias_map, load_catalog
from ..identifiers import generate_canonical_work_id
from ..schema import schema_id
from ..util import (
    epoch_ms_to_iso,
    first_paragraph,
    first_present_item,
    guess_scale_from_value,
    is_score_field,
    map_recommendation_from_numeric,
    map_recommendation_from_text,
    match_alias,
    normalize_linear,
    now_iso,
    parse_numeric_prefix,
    source_decision,
    source_work_id,
    split_decision,
)

KNOWN_TEXT_KEYS = {
    "summary",
    "paper_summary",
    "review_summary",
    "review",
    "comments",
    "main_review",
    "detailed_review",
    "confidential_comments",
    "confidential_to_chairs",
    "questions",
    "strengths",
    "weaknesses",
}


RECOMMENDATION_KEYS = (
    "recommendation",
    "rating",
    "decision",
    "overallEvaluation",
    "overall_rating",
    "overall",
)
CONFIDENCE_KEYS = ("confidence", "reviewer_confidence")


def _extract_time(note: dict[str, Any]) -> str:
    # OpenReview uses cdate/tcdate in ms since epoch
    for k in ("tcdate", "cdate", "tmdate", "mdate"):
        v = note.get(k)
        if isinstance(v, int):
            return epoch_ms_to_iso(v)
    return now_iso()


def _get_content(note: dict[str, Any]) -> dict[str, Any]:
    c = note.get("content")
    return c if isinstance(c, dict) else {}


def _get_signer(note: dict[str, Any]) -> str | None:
    sig = note.get("signatures")
    if isinstance(sig, list) and sig:
        if isinstance(sig[0], str):
            return sig[0]
    return None


def _build_target_identifiers(note: dict[str, Any]) -> dict[str, Any]:
    """Build structured identifiers from OpenReview note."""
    from ..identifiers import ARXIV_PATTERN, DOI_PATTERN

    content = _get_content(note)
    identifiers: dict[str, Any] = {}

    # Check for DOI in content
    doi = content.get("doi")
    if isinstance(doi, str) and doi and DOI_PATTERN.match(doi):
        identifiers["doi"] = {"value": doi, "hyperlink": f"https://doi.org/{doi}"}

    # Check for arXiv ID in content
    for arxiv_key in ("arxiv_id", "arxiv", "arXiv"):
        arxiv = content.get(arxiv_key)
        if isinstance(arxiv, str) and arxiv:
            # Clean up potential URL format
            arxiv_clean = arxiv.replace("https://arxiv.org/abs/", "").replace(
                "http://arxiv.org/abs/", ""
            )
            if ARXIV_PATTERN.match(arxiv_clean):
                identifiers["arxiv_id"] = {
                    "value": arxiv_clean,
                    "hyperlink": f"https://arxiv.org/abs/{arxiv_clean}",
                }
                break

    # OpenReview forum/note ID as internal_id
    forum_id = note.get("forum")
    if isinstance(forum_id, str) and forum_id:
        identifiers["internal_id"] = {
            "field_name": "openreview_forum",
            "value": forum_id,
            "hyperlink": f"https://openreview.net/forum?id={forum_id}",
        }
    else:
        # Fallback to note ID
        note_id = note.get("id")
        if isinstance(note_id, str) and note_id:
            identifiers["internal_id"] = {
                "field_name": "openreview_note",
                "value": note_id,
                "hyperlink": f"https://openreview.net/forum?id={note_id}",
            }
        else:
            # Fallback to a paper ID in the review form
            for k in ("paper_id", "submission_id", "work_id"):
                v = content.get(k)
                if isinstance(v, str) and v:
                    identifiers["internal_id"] = {"field_name": k, "value": v}
                    break

    return identifiers


def _build_target(note: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    """Build target object with identifiers."""
    identifiers = _build_target_identifiers(note)
    target: dict[str, Any] = {
        "identifiers": identifiers,
        "work_id": generate_canonical_work_id(identifiers),
        "work_type": "preprint",
    }

    # Add version if present
    version = content.get("version")
    if isinstance(version, str) and version.strip():
        target["version"] = version.strip()

    return target


def _best_text_opinion(content: dict[str, Any]) -> str:
    for k in ("summary", "paper_summary", "review_summary"):
        if isinstance(content.get(k), str) and content[k].strip():
            return content[k].strip()
    for k in ("review", "comments", "main_review", "detailed_review"):
        if isinstance(content.get(k), str) and content[k].strip():
            return first_paragraph(content[k].strip(), max_len=500)
    return ""


def _collect_findings(content: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in ("strengths", "weaknesses", "questions"):
        v = content.get(k)
        if isinstance(v, list):
            items = [{"text": str(x)} for x in v if str(x).strip()]
            if items:
                out[k] = items
        elif isinstance(v, str) and v.strip():
            # if newline-separated
            bullets = [b.strip("-* \t") for b in v.splitlines()]
            bullets = [b for b in bullets if b]
            if bullets:
                out[k] = [{"text": b} for b in bullets]
    return out


def _metric_key_for_label(
    label: str,
    amap: dict[str, str],
    idx: dict[str, Any],
) -> tuple[str, str | None]:
    # Return (key, aspect)
    if not label:
        return "other", "other"
    lcf = label.casefold()
    if lcf in idx:
        m = idx[lcf]
        return m["key"], m.get("aspect")
    key = match_alias(lcf, amap)
    if key:
        return key, None
    return "other", "other"


def from_openreview(note: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    catalog = load_catalog()
    amap = alias_map(catalog)
    # also index by metric key as lowercase to allow exact_key match
    idx = {m["key"].casefold(): m for m in catalog.get("metrics", [])}

    created = _extract_time(note)
    content = _get_content(note)

    signer = _get_signer(note)

    review_id = note.get("id") if isinstance(note.get("id"), str) else str(uuid.uuid4())

    out: dict[str, Any] = {
        "$schema": schema_id(),
        "review_id": review_id,
        "version": "1.0.0",
        "created_at": created,
        "provenance": {
            "source_system": "openreview",
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
            "human_referee": {},
        },
        "target": _build_target(note, content),
        "metric_catalog_ref": catalog.get("catalog_id"),
        "metrics": [],
        "opinion": {"summary": _best_text_opinion(content) or "No summary provided."},
    }

    if isinstance(note.get("id"), str):
        out["provenance"]["source_review_id"] = note["id"]
    if signer:
        out["referee"]["referee_id"] = signer
    if keep_raw:
        out["provenance"]["raw_payload"] = note

    # narrative mapping
    narrative = {}
    for src, dst in [
        ("summary", "summary"),
        ("review", "detailed_review"),
        ("comments", "detailed_review"),
        ("main_review", "detailed_review"),
        ("detailed_review", "detailed_review"),
        ("confidential_comments", "confidential_to_editors"),
        ("confidential_to_chairs", "confidential_to_editors"),
        ("author_questions", "author_questions"),
    ]:
        v = content.get(src)
        if isinstance(v, str) and v.strip():
            # keep the first non-empty for detailed_review fields
            if dst not in narrative:
                narrative[dst] = v.strip()
    if narrative:
        out["narrative"] = narrative

    findings = _collect_findings(content)
    if findings:
        out["findings"] = findings
        # strengthen opinion if missing
        if (not out["opinion"].get("summary")) and findings:
            any_text = next(iter(findings.values()))[0]["text"]
            out["opinion"]["summary"] = first_paragraph(any_text, 200)

    # decision and metrics
    # The first of these the form fills is the recommendation; a null one does not hide the next
    rec_key, rec_raw = first_present_item(content, RECOMMENDATION_KEYS)
    # The first confidence field that gives a number, so `confidence: "High"` beside
    # `reviewer_confidence: 4` still sets the decision's confidence
    numeric = [k for k in CONFIDENCE_KEYS if parse_numeric_prefix(content.get(k))[0] is not None]
    conf_key, conf_raw = (
        (numeric[0], content[numeric[0]])
        if numeric
        else first_present_item(content, CONFIDENCE_KEYS)
    )

    # Parse recommendation
    decision = {}
    if rec_raw is not None:
        num, rest = parse_numeric_prefix(rec_raw)
        if num is not None:
            scale = guess_scale_from_value(num)
            # The reviewer's own words first, as for CMT and HotCRP, then the number
            decision["recommendation"] = (
                map_recommendation_from_text(rest or "")
                or map_recommendation_from_numeric(num, scale)
                or "borderline"
            )
            # also store overall metric
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
            decision["recommendation"] = map_recommendation_from_text(rec_raw) or "borderline"
    if conf_raw is not None:
        num, conf_label = parse_numeric_prefix(conf_raw)
        if num is not None:
            scale = guess_scale_from_value(num)
            # treat confidence as metric; decision.confidence expects 0..1
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
            # The label after the number ("4: I have substantial expertise") is kept
            if conf_label:
                out["metrics"][-1]["justification"] = conf_label
            if isinstance(n01, (int, float)):
                decision["confidence"] = float(max(0.0, min(1.0, n01)))
    if decision:
        out["decision"] = split_decision(decision)

    # Additional structured metric fields from content
    for k, v in content.items():
        # The fields read above; another score field (a numeric `rating` beside a text
        # `recommendation`) is a metric, unless it repeats one already there
        if k in KNOWN_TEXT_KEYS or k in (rec_key, conf_key):
            continue
        if not is_score_field(k):
            continue
        # numeric-like fields
        num, rest = parse_numeric_prefix(v)
        if num is None:
            continue
        key, _aspect = _metric_key_for_label(k.replace("_", " ").strip(), amap, idx)
        # A recommendation or confidence field is that score, whatever its name says
        if k in RECOMMENDATION_KEYS:
            key = "overall"
        elif k in CONFIDENCE_KEYS:
            key = "confidence"
        # One overall score and one confidence: a second field naming either (`overall_rating`
        # beside a numeric `rating`) is the same score, but kept when the first was text
        if key in ("overall", "confidence") and any(m["key"] == key for m in out["metrics"]):
            continue
        aspect = None
        for m in catalog.get("metrics", []):
            if m["key"] == key:
                aspect = m.get("aspect")
                break
        if aspect is None:
            aspect = "other"
        scale = guess_scale_from_value(num)
        norm = normalize_linear(num, scale)
        metric = {
            "key": key,
            "label": k.replace("_", " ").strip(),
            "aspect": aspect,
            "scale": scale,
            "value": num,
        }
        if norm is not None:
            metric["normalized"] = {
                "value_0_1": float(max(0.0, min(1.0, norm))),
                "method": "linear_to_unit_interval",
            }
        if rest:
            metric["justification"] = rest
        out["metrics"].append(metric)

    # Remove null normalized stubs
    for m in out["metrics"]:
        if m.get("normalized") is None:
            m.pop("normalized", None)

    # Ensure opinion exists even if blank
    if not out.get("opinion", {}).get("summary") and not out.get("opinion", {}).get("text"):
        out["opinion"] = {"summary": "No opinion text provided."}
    return out


def to_openreview(canonical: dict[str, Any]) -> dict[str, Any]:
    # Lossy: produce a Note-like dict with a 'content' review form
    content: dict[str, Any] = {}
    # Map narrative/opinion
    op = canonical.get("opinion", {}) or {}
    if isinstance(op.get("summary"), str):
        content["summary"] = op["summary"]
    if isinstance(op.get("text"), str):
        content["review"] = op["text"]
    nar = canonical.get("narrative", {}) or {}
    if "detailed_review" in nar and isinstance(nar["detailed_review"], str):
        content.setdefault("review", nar["detailed_review"])
    if "confidential_to_editors" in nar and isinstance(nar["confidential_to_editors"], str):
        content["confidential_comments"] = nar["confidential_to_editors"]

    # Findings
    findings = canonical.get("findings", {}) or {}
    for k in ("strengths", "weaknesses", "questions"):
        if isinstance(findings.get(k), list) and findings[k]:
            content[k] = [
                f.get("text") for f in findings[k] if isinstance(f, dict) and f.get("text")
            ]

    # Decision recommendation
    dec = source_decision(canonical.get("decision", {}) or {})
    if isinstance(dec.get("recommendation"), str):
        content["recommendation"] = dec["recommendation"].replace("_", " ").title()

    # Metrics back to fields (use key as field name)
    for m in canonical.get("metrics", []) or []:
        if not isinstance(m, dict):
            continue
        key = m.get("key")
        val = m.get("value")
        if key and val is not None:
            # avoid overwriting recommendation
            if key in {"overall", "confidence"}:
                # mirror common OpenReview fields
                if key == "overall":
                    content.setdefault("rating", val)
                else:
                    content.setdefault("confidence", val)
            else:
                content.setdefault(key, val)

    note = {
        "id": canonical.get("review_id"),
        "forum": source_work_id(canonical.get("target", {})),
        "content": content,
        "signatures": (
            [canonical.get("referee", {}).get("referee_id")]
            if canonical.get("referee", {}).get("referee_id")
            else []
        ),
    }
    return note
