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

Each reviewer also has a `to_<name>` that writes an OCRS review back in the reviewer's
own format. It writes back what the mapper reads, from the same OCRS fields, and puts
what the mapper kept in `extensions.<name>` back where it came from, so mapping the
result again gives the same review. A review from anywhere else is written as well as
the format allows; the module of each reviewer says what is lost.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
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

__all__ = [
    "AIReviewMapper",
    "FENCE",
    "Fences",
    "Block",
    "BlockKind",
    "MappingResult",
    "Recorder",
    "add_section",
    "check_text",
    "extension",
    "findings_of",
    "finish",
    "indented",
    "overall_texts",
    "reviewer_model",
]

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


# A fenced code block opens and closes with three or more backticks or tildes
# (a backtick fence's info string has no backticks, so ```example``` is inline code, not a fence)
FENCE = re.compile(r"^ {0,3}(`{3,}(?=[^`]*$)|~{3,})")
# A closing fence has nothing after its marker but whitespace (```python opens, never closes)
CLOSING_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*$")


# A line that starts a block of its own, so never lazily continues a paragraph: a list
# item, a heading, a quote or a thematic break
BLOCK_START = re.compile(
    r"^ {0,3}(?:[-*+]\s|\d{1,9}[.)](?:\s|$)|#{1,6}(?:\s|$)|>|(?:[-*_]\s*){3,}$)"
)
# A list item's marker: `- `, `* `, `+ `, `1. ` or `1) `, after any indentation
LIST_ITEM = re.compile(r"^( *)(?:[-*+]|\d{1,9}[.)])(?: +|$)")


class Fences:
    """Tracks whether a line is inside a fenced code block, line by line.

    With `lists`, a fence belongs to the list item it opens in, as Markdown reads it: it is
    found and closed relative to the item's indentation, and a line indented less than the
    item ends the item and its code. So a fence after a list marker (`- ```py`) is code, its
    closing marker never opens another fence, and a heading at the line's start, which ends
    any item, is never inside an item's code.
    """

    def __init__(self, lists: bool = False) -> None:
        self.open: str | None = None  # the open fence's marker
        self.lists = lists
        self.items: list[int] = []  # content indentation of each open list item, outermost first
        self.depth = 0  # how many items deep the open fence is (0: outside lists)
        self.paragraph = False  # whether the last line continued an item's paragraph

    def closes(self, line: str) -> bool:
        """Whether `line` closes the open fence."""
        closing = CLOSING_FENCE.match(line)
        assert self.open is not None
        return bool(
            closing
            and closing.group(1)[0] == self.open[0]
            and len(closing.group(1)) >= len(self.open)
        )

    def holds(self, line: str) -> bool:
        """Whether `line` still belongs to the open fence (as code or its closing marker),
        before it is read: a line that ends the fence's list item does not."""
        if self.open is None:
            return False
        if not self.lists or not line.strip():
            return True
        base = self.items[self.depth - 1] if self.depth else 0
        return len(line) - len(line.lstrip(" ")) >= base

    def inside(self, line: str) -> bool:
        """Whether `line` is part of a fence (its opening and closing lines included)."""
        if not self.lists:
            if self.open is None:
                fence = FENCE.match(line)
                self.open = fence.group(1) if fence else None
                return fence is not None
            if self.closes(line):
                self.open = None
            return True
        blank = not line.strip()
        indent = len(line) - len(line.lstrip(" "))
        base = self.items[self.depth - 1] if self.open is not None and self.depth else 0
        if self.open is not None and (blank or indent >= base):
            # Still in the fence's item (or outside lists): code until the closing marker
            if self.closes(line[base:]):
                self.open = None
            return True
        if blank:
            self.paragraph = False
            return False
        # A soft-wrapped line straight after an item's paragraph text stays in the item
        # (a lazy continuation), unless it starts a block of its own
        lazy = self.paragraph and not BLOCK_START.match(line) and not FENCE.match(line)
        # Otherwise a line indented less than an item's content ends that item and its code
        while self.items and indent < self.items[-1] and not lazy:
            self.items.pop()
        if self.open is not None and len(self.items) < self.depth:
            self.open = None
        item = LIST_ITEM.match(line)
        # A marker starts a list at up to three spaces, or nests anywhere in an item
        if item and (len(item.group(1)) <= 3 or self.items):
            marker = item.group(0)
            self.items.append(len(marker) if marker.endswith(" ") else len(marker) + 1)
            rest = line[len(marker) :]
        else:
            base = self.items[-1] if self.items else 0
            if indent < base:
                self.paragraph = lazy
                return False
            rest = line[base:]
        fence = FENCE.match(rest)
        if fence:
            self.open, self.depth = fence.group(1), len(self.items)
            self.paragraph = False
            return True
        self.paragraph = bool(self.items) and bool(rest.strip())
        return False


def ocrs_version() -> str:
    try:
        return version("ocrs")
    except PackageNotFoundError:
        return "unknown"


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
            "imported_at": iso(datetime.now(UTC)),
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


# Writing a review back in a reviewer's own format


def extension(canonical: dict[str, Any], framework: str) -> dict[str, Any]:
    """What the reviewer's mapper kept in `extensions.<framework>`, or {} when it kept
    nothing (or the review came from somewhere else)."""
    kept = (canonical.get("extensions") or {}).get(framework)
    return kept if isinstance(kept, dict) else {}


def reviewer_model(canonical: dict[str, Any]) -> str | None:
    """The model the review's AI referee ran as reviewer, if it says one."""
    system = ((canonical.get("referee") or {}).get("ai_referee") or {}).get("system") or {}
    for model in system.get("models") or []:
        if model.get("role") == "reviewer" and model.get("model_id") not in (None, UNSPECIFIED):
            return model["model_id"]
    return None


def overall_texts(canonical: dict[str, Any]) -> tuple[str | None, str | None]:
    """The review's summary and its full text, from `opinion` or else `narrative`. Text
    for the editors only (`narrative.confidential_to_editors`) is never among them."""
    opinion = canonical.get("opinion") or {}
    narrative = canonical.get("narrative") or {}
    summary = opinion.get("summary") or narrative.get("summary")
    text = opinion.get("text") or narrative.get("detailed_review")
    return summary or None, (text if text != summary else None) or None


def findings_of(canonical: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """The review's findings of one kind. One with empty text is kept: a reviewer's empty
    point is still a point, and the IDs of those after it depend on it."""
    found = (canonical.get("findings") or {}).get(kind) or []
    return [p for p in found if isinstance(p, dict) and isinstance(p.get("text"), str)]


def add_section(sections: dict[str, str], heading: str, text: str) -> None:
    """Add `text` under `heading`, after any text already there, so two things with the
    same heading (two checks of one kind, say) are both kept."""
    sections[heading] = f"{sections[heading]}\n\n{text}" if heading in sections else text


def indented(text: str, prefix: str) -> str:
    """`text` with every line after the first indented by `prefix`, blank lines left blank,
    so it stays inside the list item it starts."""
    first, *rest = text.split("\n")
    return "\n".join([first, *(f"{prefix}{line}" if line.strip() else "" for line in rest)])


def check_text(check: dict[str, Any]) -> str:
    """A check in prose, for a format with no place of its own for it: its summary, then
    what else it says (outcome, who ran it, measurements, items, the findings it names)."""
    parts = [check["summary"]] if check.get("summary") else []
    if check.get("outcome"):
        parts.append(f"Outcome: {check['outcome'].replace('_', ' ')}")
    performer = (check.get("performed_by") or {}).get("name")
    if performer and performer not in check.get("summary", ""):
        parts.append(f"Performed by: {performer}")
    lines = []
    for m in check.get("measurements") or []:
        unit = f" {m['unit']}" if m.get("unit") else ""
        lines.append(f"- {m.get('label') or m['key']}: {m['value']}{unit}")
    for item in check.get("items") or []:
        target = item.get("target") or {}
        work = target.get("work") or {}
        name = target.get("ref") or work.get("citation") or work.get("title") or target["type"]
        flagged = " (flagged)" if item.get("flagged") else ""
        notes = f" — {item['notes']}" if item.get("notes") else ""
        lines.append(f"- {name}: {item['status']}{flagged}{notes}")
    if lines:
        parts.append("\n".join(lines))
    if check.get("finding_ids"):
        parts.append(f"Findings: {', '.join(check['finding_ids'])}")
    return "\n\n".join(parts)


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
        mapped_at=datetime.now(UTC),
        steps=recorder.steps,
        skipped=recorder.skipped,
        gaps=gaps,
    )
    return MappingResult(review=review, record=record)
