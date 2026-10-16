# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Utility functions for parsing, normalization, and recommendation mapping."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from .scales import (
    ScaleDefinition,
    get_scale_for_system,
    infer_scale_from_value,
    normalized_to_recommendation,
)

# Pattern to match numeric prefix with optional separator (: . -)
# For "4. Accept", "3: Weak Accept", "6 - Borderline"
# Note: The (?:\.\s+) ensures we don't match decimal numbers like "3.5"
_num_prefix = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:(?:\.\s+)|[:\-]\s*)?\s*(.*)$")
_bullet_pattern = re.compile(r"^\s*(?:[-*•]|\d+[.)\]])\s*", re.MULTILINE)


def now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch_ms_to_iso(ms: int) -> str:
    return (
        _dt.datetime.fromtimestamp(ms / 1000.0, tz=_dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def first_paragraph(text: str, max_len: int = 500) -> str:
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts:
        return text.strip()[:max_len]
    return parts[0][:max_len]


def parse_numeric_prefix(value: Any) -> tuple[int | float | None, str | None]:
    """Parse strings like '6: Weak Accept' -> (6, 'Weak Accept')."""
    if isinstance(value, (int, float)):
        return value, None
    if not isinstance(value, str):
        return None, None
    m = _num_prefix.match(value)
    if not m:
        return None, value.strip() or None
    num_s, rest = m.group(1), m.group(2)
    num: int | float
    if "." in num_s:
        num = float(num_s)
    else:
        num = int(num_s)
    rest = rest.strip() or None
    return num, rest


def guess_scale_from_value(num: int | float) -> dict[str, Any]:
    # Best-effort: common rubrics are 1..5 or 1..10
    if isinstance(num, float):
        # If in 0..1, treat as ratio
        if 0.0 <= num <= 1.0:
            return {"type": "ratio", "min": 0, "max": 1, "step": 0.01}
        # Otherwise treat as interval with unknown bounds
        return {"type": "interval"}
    if 0 <= num <= 1:
        return {"type": "ratio", "min": 0, "max": 1, "step": 0.05}
    if 1 <= num <= 5:
        return {"type": "ordinal", "min": 1, "max": 5}
    if 1 <= num <= 10:
        return {"type": "ordinal", "min": 1, "max": 10}
    return {"type": "interval"}


def normalize_linear(num: int | float, scale: dict[str, Any]) -> float | None:
    t = scale.get("type")
    if t == "ratio" and scale.get("min") == 0 and scale.get("max") == 1:
        return float(num)
    if t == "ordinal" and "min" in scale and "max" in scale:
        lo, hi = float(scale["min"]), float(scale["max"])
        if hi == lo:
            return None
        return (float(num) - lo) / (hi - lo)
    return None


def map_recommendation_from_numeric(num: int | float, scale: dict[str, Any]) -> str | None:
    # Conservative buckets; adjustable per venue template later
    t = scale.get("type")
    if t != "ordinal" or "min" not in scale or "max" not in scale:
        return None
    lo, hi = int(scale["min"]), int(scale["max"])
    if lo == 1 and hi == 10 and isinstance(num, (int, float)):
        n = float(num)
        if n >= 9:
            return "strong_accept"
        if n >= 7:
            return "accept"
        if n >= 6:
            return "weak_accept"
        if n >= 5:
            return "borderline"
        if n >= 3:
            return "weak_reject"
        if n >= 2:
            return "reject"
        return "strong_reject"
    if lo == 1 and hi == 5 and isinstance(num, (int, float)):
        n = float(num)
        if n >= 5:
            return "accept"
        if n >= 4:
            return "weak_accept"
        if n >= 3:
            return "borderline"
        if n >= 2:
            return "weak_reject"
        return "reject"
    return None


def map_recommendation_from_text(s: str) -> str | None:
    if not s:
        return None
    x = s.casefold().replace("_", " ")
    # Common phrases - order matters for overlapping matches
    if "strong accept" in x:
        return "strong_accept"
    if "weak accept" in x:
        return "weak_accept"
    if "border" in x:
        return "borderline"
    if "weak reject" in x:
        return "weak_reject"
    if "strong reject" in x:
        return "strong_reject"
    # Check "resubmit/resubmission" before "reject" as "reject and encourage resubmission" -> revise
    if "resubmit" in x or "resubmission" in x:
        return "revise"
    if x.strip() in {"accept", "yes"} or "accept" in x:
        return "accept"
    if x.strip() in {"reject", "no"} or "reject" in x:
        return "reject"
    if "major revision" in x:
        return "major_revision"
    if "minor revision" in x:
        return "minor_revision"
    if "revise" in x:
        return "revise"
    return None


def split_bullet_list(text: str) -> list[str]:
    """Split text on bullet markers (-, *, •, numbered) or double newlines.

    Returns a list of stripped, non-empty items.
    """
    if not text or not text.strip():
        return []
    # First, check if text has bullet markers
    if _bullet_pattern.search(text):
        # Split on newlines and strip bullet markers
        items = []
        for line in text.splitlines():
            cleaned = _bullet_pattern.sub("", line).strip()
            if cleaned:
                items.append(cleaned)
        return items
    # Otherwise split on double newlines or single newlines
    parts = re.split(r"\n\s*\n|\n", text)
    return [p.strip() for p in parts if p.strip()]


def migrate_work_id_to_identifiers(
    work_id: str, source_system: str | None = None
) -> dict[str, Any]:
    """Convert legacy work_id string to identifiers structure.

    Auto-detects identifier type from format:
    - Canonical work ID ("doi:10.xxxx/...", "internal_id:paperId:42") -> that identifier
    - DOI format (10.xxxx/...) -> doi
    - URL format -> permalink
    - Otherwise -> internal_id with source_system as field_name

    Args:
        work_id: Legacy work_id string
        source_system: Source system name for internal_id field_name

    Returns:
        Dictionary matching workIdentifiers schema
    """
    from .identifiers import DOI_PATTERN, build_resolver_url, parse_canonical_work_id

    work_id = work_id.strip()

    parsed = parse_canonical_work_id(work_id)
    if parsed:
        id_type, field_name, value = parsed
        if id_type == "internal_id":
            return {"internal_id": {"field_name": field_name, "value": value}}
        if id_type in ("permalink", "purl"):
            return {id_type: value}
        identifier = {"value": value}
        hyperlink = build_resolver_url(id_type, value)
        if hyperlink:
            identifier["hyperlink"] = hyperlink
        return {id_type: identifier}

    # Check if it's a DOI
    if DOI_PATTERN.match(work_id):
        return {"doi": {"value": work_id, "hyperlink": f"https://doi.org/{work_id}"}}

    # Check if it's a URL
    if work_id.startswith("http://") or work_id.startswith("https://"):
        return {"permalink": work_id}

    # Fallback to internal_id
    field_name = source_system or "legacy_work_id"
    return {"internal_id": {"field_name": field_name, "value": work_id}}


def source_work_id(target: dict[str, Any]) -> str | None:
    """The source system's own ID for the reviewed work, for mapping back to it.

    Uses identifiers.internal_id, then the value in a canonical work_id. A work_id
    that is not canonical (from a record made before work_id had a format) is
    returned as is.
    """
    from .identifiers import parse_canonical_work_id

    internal = (target.get("identifiers") or {}).get("internal_id")
    if isinstance(internal, dict) and internal.get("value"):
        return str(internal["value"])
    work_id = target.get("work_id")
    if not isinstance(work_id, str) or work_id == "unknown":
        return None
    parsed = parse_canonical_work_id(work_id)
    return parsed[2] if parsed else work_id


def parse_date_flexible(value: str | int | float) -> str:
    """Parse various date formats to ISO 8601 datetime string.

    Handles:
    - ISO 8601 strings (passthrough if already valid)
    - Unix timestamps in seconds (int/float)
    - Unix timestamps in milliseconds (int > 1e11)
    - Date-only strings like "2024-12-20" (assumes midnight UTC)
    """
    if isinstance(value, (int, float)):
        # Heuristic: if > 1e11, it's likely milliseconds
        if value > 1e11:
            return epoch_ms_to_iso(int(value))
        return (
            _dt.datetime.fromtimestamp(value, tz=_dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if not isinstance(value, str):
        return now_iso()
    s = value.strip()
    if not s:
        return now_iso()
    # If it looks like ISO 8601 with time component, return as-is (normalize Z)
    if "T" in s:
        # Ensure it ends with Z or timezone
        if not s.endswith("Z") and "+" not in s and "-" not in s[10:]:
            s = s + "Z"
        return s.replace("+00:00", "Z")
    # Date-only: assume midnight UTC
    try:
        dt = _dt.datetime.strptime(s, "%Y-%m-%d")
        return dt.replace(tzinfo=_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass
    # Try other common formats
    for fmt in ("%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            dt = _dt.datetime.strptime(s, fmt)
            return dt.replace(tzinfo=_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    # Fallback: return current time
    return now_iso()


# =============================================================================
# Enhanced Score Parsing and Transformation
# =============================================================================


def parse_labeled_score(
    value: Any,
    *,
    system: str | None = None,
    metric_type: str | None = None,
    expected_min: int | float | None = None,
    expected_max: int | float | None = None,
) -> dict[str, Any]:
    """Parse a labeled score like "3. Weak Accept" into components.

    This function handles various formats:
    - Pure numeric: 4, 3.5
    - Numeric with text: "4. Accept", "3: Weak Accept", "6 - Borderline"
    - Text only: "Accept", "Weak Reject" (returns None for numeric)

    Args:
        value: The score value to parse (int, float, or string)
        system: Optional source system for scale lookup
        metric_type: Optional metric type for scale lookup
        expected_min: Override minimum for scale inference
        expected_max: Override maximum for scale inference

    Returns:
        Dictionary with:
        - numeric: The numeric value (or None if text-only)
        - label: The text label (or None if numeric-only)
        - scale: Inferred or looked-up scale definition as dict
        - normalized: Normalized value in [0, 1] range
        - justification: Text explanation (same as label, for convenience)
    """
    numeric, label = parse_numeric_prefix(value)

    result: dict[str, Any] = {
        "numeric": numeric,
        "label": label,
        "scale": None,
        "normalized": None,
        "justification": label,
    }

    if numeric is None:
        return result

    # Determine the scale to use
    if expected_min is not None and expected_max is not None:
        scale = ScaleDefinition(min_value=expected_min, max_value=expected_max)
    elif system and metric_type:
        scale = get_scale_for_system(system, metric_type)
    else:
        scale = infer_scale_from_value(numeric)

    result["scale"] = scale.to_schema()
    result["normalized"] = scale.normalize(numeric)

    return result


def build_metric_from_score(
    key: str,
    label: str,
    value: Any,
    *,
    aspect: str | None = None,
    system: str | None = None,
    expected_min: int | float = 1,
    expected_max: int | float = 5,
) -> dict[str, Any] | None:
    """Build a canonical metric assessment from a score value.

    Ensures that:
    - metric.value is always numeric
    - Text labels go into metric.justification
    - Proper normalization is applied

    Args:
        key: Metric key (e.g., "overall", "novelty")
        label: Human-readable label for the metric
        value: The score value (may be labeled like "4. Accept")
        aspect: Optional aspect category
        system: Source system for scale lookup
        expected_min: Expected minimum value on source scale
        expected_max: Expected maximum value on source scale

    Returns:
        Canonical metric assessment dict, or None if value cannot be parsed
    """
    parsed = parse_labeled_score(
        value,
        system=system,
        metric_type=key,
        expected_min=expected_min,
        expected_max=expected_max,
    )

    if parsed["numeric"] is None:
        return None

    metric: dict[str, Any] = {
        "key": key,
        "label": label,
        "scale": parsed["scale"] or {"type": "ordinal", "min": expected_min, "max": expected_max},
        "value": parsed["numeric"],  # Always numeric
    }

    if aspect:
        metric["aspect"] = aspect

    if parsed["normalized"] is not None:
        metric["normalized"] = {
            "value_0_1": float(max(0.0, min(1.0, parsed["normalized"]))),
            "method": "linear_to_unit_interval",
        }

    if parsed["label"]:
        metric["justification"] = parsed["label"]

    return metric


def score_to_recommendation(
    value: Any,
    *,
    scale_min: int | float = 1,
    scale_max: int | float = 5,
) -> str | None:
    """Convert a numeric or labeled score to a recommendation string.

    Uses the configured thresholds to map normalized scores to recommendations.

    Args:
        value: Score value (numeric or labeled string)
        scale_min: Minimum value on the source scale
        scale_max: Maximum value on the source scale

    Returns:
        Recommendation string or None if value cannot be parsed
    """
    parsed = parse_labeled_score(value, expected_min=scale_min, expected_max=scale_max)

    # First try text-based mapping
    if parsed["label"]:
        text_rec = map_recommendation_from_text(parsed["label"])
        if text_rec:
            return text_rec

    # Then try numeric-based mapping
    if parsed["normalized"] is not None:
        return normalized_to_recommendation(parsed["normalized"])

    return None


def split_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Separate source revision labels without inferring an acceptance judgment."""
    result = {key: value for key, value in decision.items() if value is not None}
    revision = {
        "minor_revision": "minor",
        "major_revision": "major",
        "revise": "unspecified",
    }.get(result.get("recommendation"))
    if revision:
        result.pop("recommendation")
        result["revision_requirement"] = revision
    return result


def source_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Join decisions for single-field exports, prioritizing requested revision.

    This is lossy when an independent acceptance judgment is also present.
    An explicit no-revision requirement leaves the acceptance judgment unchanged.
    """
    result = dict(decision)
    recommendation = {
        "minor": "minor_revision",
        "major": "major_revision",
        "unspecified": "revise",
    }.get(result.get("revision_requirement"))
    if recommendation:
        result["recommendation"] = recommendation
    return result
