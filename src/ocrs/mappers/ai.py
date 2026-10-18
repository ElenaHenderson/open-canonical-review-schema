# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Writing an AI reviewer mapper: the step recorder, the review envelope and `finish`.

An AI review mapper copies the reviewer's own output into OCRS. It never rewrites or
invents text. Whatever has no OCRS field goes, unchanged, to
`extensions.<name>`, which mirrors the reviewer's output. The run details
(work, reviewer commit, model, times, cost) come from whoever ran the
reviewer, as `map_with_record`'s keyword arguments, and are already in the
envelope the mapper receives.

A mapper is an `AIReviewMapper`: it takes the reviewer's output, the envelope and the
paper's blocks (or None), fills the envelope through a `Recorder`, and returns
`finish(...)`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pydantic import JsonValue

from ..anchors import Block, BlockKind, find_quote
from ..gaps import count_unmapped, generic_path, leftover, unfilled_paths
from ..identifiers import generate_canonical_work_id
from ..mapping import (
    Coercion,
    Gaps,
    MappingRecord,
    MappingResult,
    MappingStatus,
    Rule,
    SkippedItem,
    Step,
    UnanchoredQuote,
)
from ..schema import load_schema, schema_id, validate_canonical
from ..util import migrate_work_id_to_identifiers

__all__ = ["AIReviewMapper", "Block", "BlockKind", "MappingResult", "Recorder", "finish"]

AIReviewMapper = Callable[[Any, dict[str, Any], list[Block] | None], MappingResult]
"""(reviewer's output, envelope, paper blocks or None) → the filled review and its record.

The output is the reviewer's JSON as a dict, or its text when the reviewer writes Markdown."""

REVIEW_VERSION = "1.0.0"
UNSPECIFIED = "unspecified"
# The mapping spec every mapper here follows: schemas/mapping-spec.v1.1.0.json.
MAPPING_SPEC_ID = "canonical-review.mapping.v1"
MAPPING_SPEC_VERSION = "1.1.0"
# OCRS fields that cannot apply to a review written by one AI reviewer.
NOT_FOR_AI_REVIEWS = {
    "referees",
    "referee.human_referee",
    "referee.hybrid_workflow",
    "referee.ai_referee.reference",
    "provenance.raw_payload",
    "calibration",
    "signatures",
    "written_report",
}


def ocrs_version() -> str:
    try:
        return version("ocrs")
    except PackageNotFoundError:
        return "unknown"


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Recorder:
    """Collects the steps of one mapping and the paths it read."""

    def __init__(self, checks_quotes: bool) -> None:
        self.steps: list[Step] = []
        self.read: set[str] = set()
        self.coerced: list[Coercion] = []
        self.unanchored: list[UnanchoredQuote] | None = [] if checks_quotes else None
        self.skipped: list[SkippedItem] = []

    def copy(self, source: str, target: str, value: JsonValue) -> JsonValue:
        self.read.add(source)
        self.steps.append(Step(source=source, target=target, rule=Rule.COPIED))
        return value

    def lookup(self, source: str, target: str, value: str, table: dict[str, str]) -> str | None:
        self.read.add(source)
        result = table.get(value)
        if result is None:
            reason = f"not one of {sorted(table)}; left out"
            self.coerced.append(
                Coercion(source=source, target=target, original=value, result=None, reason=reason)
            )
            return None
        self.steps.append(
            Step(source=source, target=target, rule=Rule.LOOKUP, original=value, result=result)
        )
        return result

    def skip(self, source: str, reason: str) -> None:
        self.skipped.append(SkippedItem(source=source, reason=reason))

    def evidence_link(
        self, source: str, target: str, quote: str, ref: str, blocks: list[Block] | None
    ) -> dict[str, Any]:
        """An evidence link for `quote`, and where in the paper the quote was found.

        The place goes in the step's result (part of the paper and block ID), not in
        the link: OCRS has no field for a block ID that would mean anything outside
        the document it came from.
        """
        self.copy(source, f"{target}.quote", quote)
        self.anchor(source, target, quote, blocks)
        return {"type": "paper_section", "ref": ref, "quote": quote}

    def parse(self, source: str, target: str, original: str, result: JsonValue) -> JsonValue:
        """`result` was read out of `original`, part of a value at `source`, by a pattern."""
        self.read.add(source)
        self.steps.append(
            Step(source=source, target=target, rule=Rule.PARSED, original=original, result=result)
        )
        return result

    def anchor(self, source: str, target: str, quote: str, blocks: list[Block] | None) -> None:
        """Record where in the paper `quote` was found, or that it was not."""
        if blocks is None or self.unanchored is None:
            return
        match, best_score = find_quote(quote, blocks)
        if match is None:
            self.unanchored.append(
                UnanchoredQuote(source=source, quote=quote, best_score=best_score)
            )
        else:
            self.steps.append(
                Step(
                    source=source,
                    target=target,
                    rule=Rule.ANCHORED_EXACT if match.exact else Rule.ANCHORED_FUZZY,
                    result={"part": match.block.kind.value, "block_id": match.block.id},
                    score=round(match.score, 3),
                )
            )


def build_review(
    *,
    framework: str,
    mapper_version: str,
    review_id: str,
    source_system: str,
    work_id: str,
    work_type: str,
    started_at: datetime,
    ended_at: datetime,
    reviewer_commit: str | None = None,
    reviewer_version: str | None = None,
    model_id: str | None = None,
    work_version: str | None = None,
    requested_by: str | None = None,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """The parts of an OCRS review that come from the run, not the reviewer's output.

    `work_id` is any identifier of the paper: a canonical work ID, a DOI, a URL, or the
    platform's own ID, which becomes an internal_id named after `source_system`. A hosted
    reviewer may publish no commit, version or model; those are then `unspecified`,
    which OCRS requires to be stated.
    """
    identifiers = migrate_work_id_to_identifiers(work_id, source_system)
    framework_info: dict[str, Any] = {
        "name": framework,
        "version": reviewer_version or (reviewer_commit[:12] if reviewer_commit else UNSPECIFIED),
    }
    if reviewer_commit:
        framework_info["commit"] = reviewer_commit
    execution: dict[str, Any] = {
        "started_at": iso(started_at),
        "ended_at": iso(ended_at),
        "wall_time_seconds": (ended_at - started_at).total_seconds(),
    }
    if cost_usd is not None:
        execution["cost"] = {"currency": "USD", "estimated_total": cost_usd}
    review: dict[str, Any] = {
        "$schema": schema_id(),
        "review_id": review_id,
        "version": REVIEW_VERSION,
        "created_at": iso(ended_at),
        "provenance": {
            "source_system": source_system,
            "source_review_id": review_id,
            "imported_at": iso(datetime.now(timezone.utc)),
            "mapping": {
                "mapping_spec_id": MAPPING_SPEC_ID,
                "mapping_spec_version": MAPPING_SPEC_VERSION,
                "mapper_version": mapper_version,
            },
        },
        "referee": {
            "referee_type": "ai",
            "identity_mode": "open",
            "ai_referee": {
                "system": {
                    "critic_framework": framework_info,
                    "models": [{"role": "reviewer", "model_id": model_id or UNSPECIFIED}],
                },
                "execution": execution,
            },
        },
        "target": {
            "work_id": generate_canonical_work_id(identifiers),
            "work_type": work_type,
            "identifiers": identifiers,
        },
        "opinion": {},
    }
    if work_version:
        review["target"]["version"] = work_version
    if requested_by:
        review["review_context"] = {"requested_by": requested_by}
    return review


def finish(
    review: dict[str, Any],
    recorder: Recorder,
    output: dict[str, Any],
    *,
    ignored: set[str],
    generic: Callable[[str], str] = generic_path,
) -> MappingResult:
    """Put what was not mapped in `extensions`, validate, and record the gaps.

    `ignored` lists output paths that are deliberately not kept (`*` matches
    any key). `generic` turns an output path into the form gaps are summed by.
    """
    framework = review["referee"]["ai_referee"]["system"]["critic_framework"]["name"]
    mapper_version = review["provenance"]["mapping"]["mapper_version"]
    left = leftover(output, recorder.read, ignored, generic)
    if left:
        review["extensions"] = {framework: left}
    validate_canonical(review)
    gaps = Gaps(
        unmapped=count_unmapped(left, generic),
        unfilled=unfilled_paths(review, load_schema(), NOT_FOR_AI_REVIEWS),
        coerced=recorder.coerced,
        unanchored=recorder.unanchored,
    )
    record = MappingRecord(
        status=MappingStatus.PARTIAL if recorder.skipped else MappingStatus.OK,
        source_format=framework,
        mapper_version=mapper_version,
        ocrs_version=ocrs_version(),
        mapped_at=datetime.now(timezone.utc),
        steps=recorder.steps,
        skipped=recorder.skipped,
        gaps=gaps,
    )
    return MappingResult(review=review, record=record)
