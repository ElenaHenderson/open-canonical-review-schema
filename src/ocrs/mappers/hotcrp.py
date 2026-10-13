# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""HotCRP format mapper for canonical reviews."""

from __future__ import annotations

import uuid
from typing import Any

from ..catalog import alias_map, load_catalog
from ..util import (
    first_paragraph,
    map_recommendation_from_text,
    now_iso,
    parse_date_flexible,
    parse_labeled_score,
    score_to_recommendation,
    source_decision,
    split_bullet_list,
    split_decision,
)

# Common HotCRP text field names that should not be treated as metrics
KNOWN_TEXT_KEYS = {
    "paper_summary",
    "summary",
    "comments",
    "strengths",
    "weaknesses",
    "questions",
    "questions_for_authors",
    "confidential_comments",
    "comments_to_pc",
    "detailed_comments",
}

# HotCRP expertise level mapping (common scales)
EXPERTISE_LEVEL_MAP = {
    1: "not_familiar",
    2: "somewhat_familiar",
    3: "knowledgeable",
    4: "expert",
    5: "expert",
}


def _extract_time(payload: dict[str, Any]) -> str:
    """Extract timestamp from HotCRP payload."""
    for k in ("submitted_at", "timeSubmitted", "created_at", "cdate"):
        v = payload.get(k)
        if v is not None:
            return parse_date_flexible(v)
    return now_iso()


def _get_reviewer_id(payload: dict[str, Any]) -> str | None:
    """Extract reviewer identifier from HotCRP payload."""
    reviewer = payload.get("reviewer")
    if isinstance(reviewer, dict):
        for k in ("user", "email", "id"):
            v = reviewer.get(k)
            if isinstance(v, str) and v:
                return v
    # Fallback to top-level fields
    for k in ("reviewerEmail", "reviewer_id", "contactId"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _get_work_id(payload: dict[str, Any]) -> str:
    """Extract paper/work identifier."""
    for k in ("pid", "paperId", "paper_id", "submission_id"):
        v = payload.get(k)
        if v is not None:
            return str(v)
    return "unknown"


def _build_target_identifiers(payload: dict[str, Any]) -> dict[str, Any]:
    """Build structured identifiers from HotCRP payload."""
    from ..identifiers import DOI_PATTERN

    identifiers: dict[str, Any] = {}

    # Check for DOI in payload
    doi = payload.get("doi")
    if isinstance(doi, str) and doi and DOI_PATTERN.match(doi):
        identifiers["doi"] = {"value": doi, "hyperlink": f"https://doi.org/{doi}"}

    # HotCRP paper ID as internal_id
    work_id = _get_work_id(payload)
    if work_id != "unknown":
        identifiers["internal_id"] = {
            "field_name": "hotcrp_pid",
            "value": work_id,
        }

    return identifiers


def _build_human_referee(payload: dict[str, Any]) -> dict[str, Any]:
    """Build human_referee object with identity fields."""
    from ..identifiers import normalize_orcid

    human_referee: dict[str, Any] = {}

    # Check for ORCID
    reviewer = payload.get("reviewer", {})
    orcid = None
    if isinstance(reviewer, dict):
        orcid = reviewer.get("orcid")
    if not orcid:
        orcid = payload.get("reviewerOrcid") or payload.get("orcid")

    if orcid and isinstance(orcid, str):
        normalized = normalize_orcid(orcid)
        if normalized:
            human_referee["orcid"] = normalized

    # Name and affiliation
    if isinstance(reviewer, dict):
        if reviewer.get("name"):
            human_referee["name"] = reviewer["name"]
        if reviewer.get("affiliation"):
            human_referee["affiliation"] = reviewer["affiliation"]

    return human_referee


def _best_opinion_text(payload: dict[str, Any]) -> str:
    """Find the best text for the opinion summary."""
    for k in ("paper_summary", "summary", "comments", "detailed_comments"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return first_paragraph(v.strip(), max_len=500)
    return "No summary provided."


def _collect_findings(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract strengths, weaknesses, questions from HotCRP fields."""
    findings: dict[str, Any] = {}
    for k in ("strengths", "weaknesses", "questions", "questions_for_authors"):
        v = payload.get(k)
        canon_key = "questions" if k == "questions_for_authors" else k
        if isinstance(v, list):
            items = [{"text": str(x)} for x in v if str(x).strip()]
            if items:
                findings[canon_key] = items
        elif isinstance(v, str) and v.strip():
            bullets = split_bullet_list(v)
            if bullets:
                findings[canon_key] = [{"text": b} for b in bullets]
    return findings


def _parse_round(payload: dict[str, Any]) -> int | None:
    """Parse review round from HotCRP payload."""
    r = payload.get("round")
    if isinstance(r, int):
        return r
    if isinstance(r, str):
        # Parse strings like "R1", "R2", "main", "Round 2"
        s = r.strip().lower()
        if s in ("main", "r1", "round 1", "1"):
            return 1
        if s.startswith("r") and s[1:].isdigit():
            return int(s[1:])
        if s.startswith("round ") and s[6:].strip().isdigit():
            return int(s[6:].strip())
        if s.isdigit():
            return int(s)
    return None


def _metric_key_for_label(
    label: str,
    amap: dict[str, str],
    idx: dict[str, Any],
) -> tuple[str, str | None]:
    """Map a field label to a metric key and aspect."""
    if not label:
        return "other", "other"
    lcf = label.casefold()
    if lcf in idx:
        m = idx[lcf]
        return m["key"], m.get("aspect")
    if lcf in amap:
        return amap[lcf], None
    # Fuzzy matching
    for alias, key in amap.items():
        if alias in lcf or lcf in alias:
            return key, None
    return "other", "other"


def from_hotcrp(payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    """Convert a HotCRP review to canonical format.

    Args:
        payload: HotCRP review data (from JSON export or API).
        keep_raw: If True, preserve the original payload in provenance.raw_payload.

    Returns:
        A canonical review dictionary.
    """
    catalog = load_catalog()
    amap = alias_map(catalog)
    idx = {m["key"].casefold(): m for m in catalog.get("metrics", [])}

    created = _extract_time(payload)
    work_id = _get_work_id(payload)
    reviewer_id = _get_reviewer_id(payload)

    # Generate review_id
    rid = payload.get("id")
    review_id = str(rid) if rid is not None else str(uuid.uuid4())

    # Build referee object, only adding referee_id if present
    human_referee = _build_human_referee(payload)
    referee: dict[str, Any] = {
        "referee_type": "human",
        "identity_mode": "confidential",
        "human_referee": human_referee if human_referee else {},
    }
    if reviewer_id:
        referee["referee_id"] = reviewer_id

    # Build provenance, only adding source_review_id if present
    provenance: dict[str, Any] = {
        "source_system": "hotcrp",
        "imported_at": now_iso(),
        "mapping": {
            "mapping_spec_id": "canonical-review.mapping.v1",
            "mapping_spec_version": "1.1.0",
            "mapper_version": "0.1.0",
        },
    }
    if rid is not None:
        provenance["source_review_id"] = str(rid)

    out: dict[str, Any] = {
        "review_id": f"hotcrp_{review_id}",
        "version": "1.0.0",
        "created_at": created,
        "provenance": provenance,
        "referee": referee,
        "target": {
            "identifiers": _build_target_identifiers(payload),
            "work_id": work_id,  # Keep for backward compatibility
            "work_type": "article",
        },
        "metric_catalog_ref": catalog.get("catalog_id"),
        "metrics": [],
        "opinion": {"summary": _best_opinion_text(payload)},
    }

    if keep_raw:
        out["provenance"]["raw_payload"] = payload

    # Narrative mapping
    narrative: dict[str, Any] = {}
    for src, dst in [
        ("paper_summary", "summary"),
        ("summary", "summary"),
        ("comments", "detailed_review"),
        ("detailed_comments", "detailed_review"),
        ("confidential_comments", "confidential_to_editors"),
        ("comments_to_pc", "confidential_to_editors"),
        ("questions_for_authors", "author_questions"),
    ]:
        v = payload.get(src)
        if isinstance(v, str) and v.strip():
            if dst not in narrative:
                narrative[dst] = v.strip()
    if narrative:
        out["narrative"] = narrative

    # Findings
    findings = _collect_findings(payload)
    if findings:
        out["findings"] = findings

    # Parse overall merit / recommendation
    rec_raw = None
    for k in ("overall_merit", "overall", "recommendation", "rating", "score"):
        if k in payload:
            rec_raw = payload.get(k)
            break

    decision: dict[str, Any] = {}
    if rec_raw is not None:
        # Use enhanced parsing with proper scale handling
        parsed = parse_labeled_score(
            rec_raw,
            system="hotcrp",
            metric_type="overall_merit",
            expected_min=1,
            expected_max=5,  # Default HotCRP scale
        )

        if parsed["numeric"] is not None:
            # Determine recommendation from text label first, then numeric
            if parsed["label"]:
                decision["recommendation"] = (
                    map_recommendation_from_text(parsed["label"])
                    or score_to_recommendation(parsed["numeric"], scale_min=1, scale_max=5)
                    or "borderline"
                )
            else:
                decision["recommendation"] = (
                    score_to_recommendation(parsed["numeric"], scale_min=1, scale_max=5)
                    or "borderline"
                )

            # Build metric with numeric value and text justification
            metric: dict[str, Any] = {
                "key": "overall",
                "label": "Overall Merit",
                "aspect": "overall",
                "scale": parsed["scale"],
                "value": parsed["numeric"],  # Always numeric
            }
            if parsed["normalized"] is not None:
                metric["normalized"] = {
                    "value_0_1": parsed["normalized"],
                    "method": "linear_to_unit_interval",
                }
            # Store text label as justification
            if parsed["label"]:
                metric["justification"] = parsed["label"]

            out["metrics"].append(metric)
        elif isinstance(rec_raw, str):
            decision["recommendation"] = map_recommendation_from_text(rec_raw) or "borderline"

    # Parse reviewer expertise
    exp_raw = payload.get("reviewer_expertise") or payload.get("expertise")
    if exp_raw is not None:
        parsed = parse_labeled_score(
            exp_raw,
            system="hotcrp",
            metric_type="expertise",
            expected_min=1,
            expected_max=5,
        )
        if parsed["numeric"] is not None:
            metric = {
                "key": "confidence",
                "label": "Reviewer Expertise",
                "aspect": "confidence",
                "scale": parsed["scale"],
                "value": parsed["numeric"],  # Always numeric
            }
            if parsed["normalized"] is not None:
                metric["normalized"] = {
                    "value_0_1": parsed["normalized"],
                    "method": "linear_to_unit_interval",
                }
            # Store text label as justification
            if parsed["label"]:
                metric["justification"] = parsed["label"]
            out["metrics"].append(metric)

            # Also add expertise to review_context
            level = EXPERTISE_LEVEL_MAP.get(int(parsed["numeric"]), "knowledgeable")
            out["review_context"] = {"expertise": {"self_reported_level": level}}

    # Parse confidence if separate from expertise
    conf_raw = payload.get("confidence")
    if conf_raw is not None:
        parsed = parse_labeled_score(
            conf_raw,
            system="hotcrp",
            metric_type="confidence",
            expected_min=1,
            expected_max=5,
        )
        if parsed["numeric"] is not None:
            # Check if we already have a confidence metric
            has_conf = any(m.get("key") == "confidence" for m in out["metrics"])
            if not has_conf:
                metric = {
                    "key": "confidence",
                    "label": "Reviewer Confidence",
                    "aspect": "confidence",
                    "scale": parsed["scale"],
                    "value": parsed["numeric"],  # Always numeric
                }
                if parsed["normalized"] is not None:
                    metric["normalized"] = {
                        "value_0_1": parsed["normalized"],
                        "method": "linear_to_unit_interval",
                    }
                if parsed["label"]:
                    metric["justification"] = parsed["label"]
                out["metrics"].append(metric)
            if parsed["normalized"] is not None:
                decision["confidence"] = float(max(0.0, min(1.0, parsed["normalized"])))

    if decision:
        out["decision"] = split_decision(decision)

    # Additional numeric fields as metrics
    skip_keys = (
        KNOWN_TEXT_KEYS
        | {"id", "pid", "paperId", "ordinal", "rtype", "submitted", "submitted_at"}
        | {"reviewer", "round", "overall_merit", "overall", "recommendation", "rating"}
        | {"reviewer_expertise", "expertise", "confidence", "score"}
    )
    for k, v in payload.items():
        if k in skip_keys:
            continue
        # Use enhanced parsing with proper label extraction
        parsed = parse_labeled_score(
            v,
            system="hotcrp",
            metric_type=k,
            expected_min=1,
            expected_max=5,  # Default HotCRP scale
        )
        if parsed["numeric"] is None:
            continue
        key, _ = _metric_key_for_label(k.replace("_", " ").strip(), amap, idx)
        aspect = None
        for m in catalog.get("metrics", []):
            if m["key"] == key:
                aspect = m.get("aspect")
                break
        if aspect is None:
            aspect = "other"
        metric_entry: dict[str, Any] = {
            "key": key,
            "label": k.replace("_", " ").strip(),
            "aspect": aspect,
            "scale": parsed["scale"],
            "value": parsed["numeric"],  # Always numeric
        }
        if parsed["normalized"] is not None:
            metric_entry["normalized"] = {
                "value_0_1": float(max(0.0, min(1.0, parsed["normalized"]))),
                "method": "linear_to_unit_interval",
            }
        # Store text label as justification
        if parsed["label"]:
            metric_entry["justification"] = parsed["label"]
        out["metrics"].append(metric_entry)

    # Clean up null normalized values
    for m in out["metrics"]:
        if m.get("normalized") is None:
            m.pop("normalized", None)

    # Add round to review_context if present
    rnd = _parse_round(payload)
    if rnd is not None:
        if "review_context" not in out:
            out["review_context"] = {}
        out["review_context"]["round"] = rnd

    return out


def to_hotcrp(canonical: dict[str, Any]) -> dict[str, Any]:
    """Convert a canonical review to HotCRP format (basic stub).

    This is a lossy conversion that produces a minimal HotCRP-like structure.
    Full fidelity roundtrip is not guaranteed.

    Args:
        canonical: A canonical review dictionary.

    Returns:
        A HotCRP-like review dictionary.
    """
    # Extract review ID
    rid = canonical.get("review_id", "")
    if rid.startswith("hotcrp_"):
        rid = rid[7:]

    out: dict[str, Any] = {
        "id": rid,
        "pid": canonical.get("target", {}).get("work_id"),
    }

    # Map opinion/narrative to comments
    op = canonical.get("opinion", {}) or {}
    nar = canonical.get("narrative", {}) or {}

    if nar.get("summary"):
        out["paper_summary"] = nar["summary"]
    if nar.get("detailed_review"):
        out["comments"] = nar["detailed_review"]
    elif op.get("text"):
        out["comments"] = op["text"]
    elif op.get("summary"):
        out["comments"] = op["summary"]

    if nar.get("confidential_to_editors"):
        out["confidential_comments"] = nar["confidential_to_editors"]

    # Map findings
    findings = canonical.get("findings", {}) or {}
    for k in ("strengths", "weaknesses", "questions"):
        if isinstance(findings.get(k), list) and findings[k]:
            out[k] = "\n".join(
                f"- {f.get('text')}" for f in findings[k] if isinstance(f, dict) and f.get("text")
            )

    # Map recommendation
    dec = source_decision(canonical.get("decision", {}) or {})
    if isinstance(dec.get("recommendation"), str):
        # Find overall metric to get numeric value
        for m in canonical.get("metrics", []) or []:
            if m.get("key") == "overall" and m.get("value") is not None:
                label = dec["recommendation"].replace("_", " ").title()
                out["overall_merit"] = f"{m['value']}: {label}"
                break
        else:
            out["overall_merit"] = dec["recommendation"].replace("_", " ").title()

    # Map expertise/confidence
    for m in canonical.get("metrics", []) or []:
        if m.get("key") == "confidence" and m.get("value") is not None:
            out["reviewer_expertise"] = m["value"]
            break

    # Add round if present
    ctx = canonical.get("review_context", {}) or {}
    if ctx.get("round"):
        out["round"] = f"R{ctx['round']}"

    return out
