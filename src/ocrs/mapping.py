# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""What a mapper did, step by step, and where the result falls short of OCRS.

Paths name places in a JSON document: `issues[3].severity` in the reviewer's
output, `findings.weaknesses[2].severity` in the OCRS review. Gap paths use
`[]` for any list position, so they can be summed across reviews.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, JsonValue


class Rule(str, Enum):
    COPIED = "copied"
    LOOKUP = "lookup"
    ANCHORED_EXACT = "anchored_exact"
    ANCHORED_FUZZY = "anchored_fuzzy"


class Step(BaseModel):
    """One value taken from the reviewer's output. A copied value is not repeated
    here: it is in the OCRS review at `target`."""

    source: str
    target: str
    rule: Rule
    original: JsonValue = None
    result: JsonValue = None
    score: float | None = None


class FieldCount(BaseModel):
    path: str
    count: int


class Coercion(BaseModel):
    source: str
    target: str
    original: JsonValue
    result: JsonValue
    reason: str


class UnanchoredQuote(BaseModel):
    source: str
    quote: str
    best_score: float


class SkippedItem(BaseModel):
    source: str
    reason: str


class Gaps(BaseModel):
    unmapped: list[FieldCount] = []
    """Reviewer fields with no OCRS field. Their values are kept in `extensions`."""
    unfilled: list[str] = []
    """OCRS fields this review leaves empty."""
    coerced: list[Coercion] = []
    """Reviewer values that are not allowed in OCRS, with what the mapper did instead."""
    unanchored: list[UnanchoredQuote] | None = None
    """Quotes from the paper that could not be found in it. None when no paper was given."""


class MappingStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class MappingRecord(BaseModel):
    status: MappingStatus
    error: str | None = None
    source_format: str
    mapper_version: str
    ocrs_version: str
    mapped_at: datetime
    steps: list[Step] = []
    skipped: list[SkippedItem] = []
    gaps: Gaps = Gaps()


class MappingResult(BaseModel):
    review: dict[str, Any]
    record: MappingRecord
