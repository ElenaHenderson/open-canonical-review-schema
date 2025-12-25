# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Utility functions for parsing, normalization, and recommendation mapping."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

_num_prefix = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?::|-)?\s*(.*)$")


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
    # Common phrases
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
    if x.strip() in {"accept", "yes"} or "accept" in x:
        return "accept"
    if x.strip() in {"reject", "no"} or "reject" in x:
        return "reject"
    if "major revision" in x:
        return "major_revision"
    if "minor revision" in x:
        return "minor_revision"
    if "revise" in x or "resubmit" in x:
        return "revise"
    return None
