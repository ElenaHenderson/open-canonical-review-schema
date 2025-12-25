# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Utility functions for parsing, normalization, and recommendation mapping."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

_num_prefix = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?::|-)?\s*(.*)$")
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
    x = s.casefold()
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
