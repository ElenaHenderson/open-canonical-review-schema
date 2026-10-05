# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""What the AI reviewer mappers share: the payload, the step recorder and the review envelope.

An AI mapper copies the reviewer's own output into OCRS. It never rewrites or
invents text. Whatever has no OCRS field goes, unchanged, to
`extensions.<format>`, which mirrors the reviewer's output. The run details
(work, reviewer version, model, times, cost) come from whoever ran the
reviewer, in `run`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pydantic import AwareDatetime, BaseModel, JsonValue

from ..anchors import Block, find_quote
from ..gaps import count_unmapped, generic_path, leftover, unfilled_paths
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
from ..schema import load_schema, validate_canonical

REVIEW_VERSION = "1.0.0"
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


class AiRun(BaseModel):
    review_id: str
    source_system: str
    work_id: str
    work_version: str | None = None
    work_type: str = "preprint"
    reviewer_commit: str
    model_id: str
    started_at: AwareDatetime
    ended_at: AwareDatetime
    cost_usd: float | None = None
    requested_by: str | None = None


class AiPayload(BaseModel):
    output: dict[str, Any]
    run: AiRun
    blocks: list[Block] = []


def ocrs_version() -> str:
    try:
        return version("ocrs")
    except PackageNotFoundError:
        return "unknown"


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Recorder:
    """Collects the steps of one mapping and the paths it read."""

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.read: set[str] = set()
        self.coerced: list[Coercion] = []
        self.unanchored: list[UnanchoredQuote] = []
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
        self, source: str, target: str, quote: str, ref: str, blocks: list[Block]
    ) -> dict[str, Any]:
        """An evidence link for `quote`, and where in the paper the quote was found.

        The place goes in the step's result (part of the paper and block ID), not in
        the link: OCRS has no field for a block ID that would mean anything outside
        the document it came from.
        """
        self.copy(source, f"{target}.quote", quote)
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
        return {"type": "paper_section", "ref": ref, "quote": quote}


def build_review(run: AiRun, framework: str, mapper_version: str) -> dict[str, Any]:
    """The parts of an OCRS review that come from the run, not the reviewer's output."""
    execution: dict[str, Any] = {
        "started_at": iso(run.started_at),
        "ended_at": iso(run.ended_at),
        "wall_time_seconds": (run.ended_at - run.started_at).total_seconds(),
    }
    if run.cost_usd is not None:
        execution["cost"] = {"currency": "USD", "estimated_total": run.cost_usd}
    review: dict[str, Any] = {
        "review_id": run.review_id,
        "version": REVIEW_VERSION,
        "created_at": iso(run.ended_at),
        "provenance": {
            "source_system": run.source_system,
            "source_review_id": run.review_id,
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
                    "critic_framework": {
                        "name": framework,
                        "version": run.reviewer_commit[:12],
                        "commit": run.reviewer_commit,
                    },
                    "models": [{"role": "reviewer", "model_id": run.model_id}],
                },
                "execution": execution,
            },
        },
        "target": {"work_id": run.work_id, "work_type": run.work_type},
        "opinion": {},
    }
    if run.work_version:
        review["target"]["version"] = run.work_version
    if run.requested_by:
        review["review_context"] = {"requested_by": run.requested_by}
    return review


def finish(
    review: dict[str, Any],
    recorder: Recorder,
    output: dict[str, Any],
    *,
    framework: str,
    mapper_version: str,
    ignored: set[str],
    generic: Callable[[str], str] = generic_path,
) -> MappingResult:
    """Put what was not mapped in `extensions`, validate, and record the gaps."""
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
