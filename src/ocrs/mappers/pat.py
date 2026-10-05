# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""PAT (Paper Assistant Tool) review.json → OCRS.

Each PAT issue becomes a weakness: `title`, `description` as the text,
`severity`, `category` as a tag, and `evidence` (a verbatim quote) with
`location` as an evidence link. PAT's per-segment reports are drafts of the
same issues and are not kept. Everything else PAT writes (suggested fixes,
confidence, grounding, dropped issues, segments, costs) is unmapped and kept
in `extensions.pat`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..mapping import MappingResult
from ._ai import AiPayload, Recorder, build_review, finish

FRAMEWORK = "pat"
MAPPER_VERSION = "1.0.1"
SEVERITY = {"critical": "critical", "major": "major", "minor": "minor"}
IGNORED = {"reports"}


class PatIssue(BaseModel):
    title: str = ""
    location: str = ""
    category: str = ""
    severity: str = ""
    description: str = ""
    evidence: str = ""


class PatReview(BaseModel):
    summary: str = ""
    issues: list[PatIssue] = []


def map_issue(
    issue: PatIssue, source: str, target: str, recorder: Recorder, payload: AiPayload
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "text": recorder.copy(f"{source}.description", f"{target}.text", issue.description)
    }
    if issue.title:
        finding["title"] = recorder.copy(f"{source}.title", f"{target}.title", issue.title)
    if issue.severity:
        severity = recorder.lookup(
            f"{source}.severity", f"{target}.severity", issue.severity, SEVERITY
        )
        if severity:
            finding["severity"] = severity
    if issue.category:
        finding["tags"] = [recorder.copy(f"{source}.category", f"{target}.tags[0]", issue.category)]
    if issue.evidence:
        link_target = f"{target}.evidence_links[0]"
        ref = (
            recorder.copy(f"{source}.location", f"{link_target}.ref", issue.location)
            if issue.location
            else ""
        )
        link = recorder.evidence_link(
            f"{source}.evidence", link_target, issue.evidence, ref, payload.blocks
        )
        finding["evidence_links"] = [link]
    return finding


def map_pat(payload: AiPayload) -> MappingResult:
    pat = PatReview.model_validate(payload.output)
    recorder = Recorder()
    review = build_review(payload.run, FRAMEWORK, MAPPER_VERSION)
    if pat.summary:
        review["opinion"]["summary"] = recorder.copy("summary", "opinion.summary", pat.summary)
    weaknesses = []
    for index, issue in enumerate(pat.issues):
        source = f"issues[{index}]"
        if not issue.description:
            recorder.skip(source, "no description")
            continue
        target = f"findings.weaknesses[{len(weaknesses)}]"
        weaknesses.append(map_issue(issue, source, target, recorder, payload))
    if weaknesses:
        review["findings"] = {"weaknesses": weaknesses}
    return finish(
        review,
        recorder,
        payload.output,
        framework=FRAMEWORK,
        mapper_version=MAPPER_VERSION,
        ignored=IGNORED,
    )


def from_pat(payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    return map_pat(AiPayload.model_validate(payload)).review
