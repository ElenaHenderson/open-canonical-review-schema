# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""OpenAIReview paper.json → OCRS.

OpenAIReview writes one entry per review method under `methods`, keyed
`<method>__<model>`. The mapper reads the merged `progressive` comments, or the
only method there is. The `progressive_original` entry holds the same comments
before merging and is not kept, nor is `paragraphs`, the paper's own text.

Each comment becomes a weakness: `title`, `explanation` as the text,
`comment_type` as a tag and `quote` as an evidence link. OpenAIReview gives no
severity and no location other than its own paragraph number, which is kept
in `extensions.openaireview`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..gaps import generic_path
from ..mapping import MappingResult
from ._ai import AiPayload, Recorder, build_review, finish

FRAMEWORK = "openaireview"
MAPPER_VERSION = "1.0.0"
MERGED_METHOD_PREFIX = "progressive__"
UNMERGED_METHOD_PREFIX = "progressive_original__"
IGNORED = {"paragraphs", f"methods.{UNMERGED_METHOD_PREFIX}*"}


class Comment(BaseModel):
    title: str = ""
    quote: str = ""
    explanation: str = ""
    comment_type: str = ""


class Method(BaseModel):
    overall_feedback: str = ""
    comments: list[Comment] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class PaperResult(BaseModel):
    methods: dict[str, Method] = {}


def method_wildcard(method_keys: list[str]) -> Callable[[str], str]:
    """Turns `methods.progressive__<model>.x` into `methods.progressive__*.x`.

    So gaps from runs on different models sum together. Model names contain
    dots, so the keys must be known rather than parsed out of a path.
    """

    def generic(path: str) -> str:
        path = generic_path(path)
        for key in method_keys:
            prefix = f"methods.{key}"
            if path == prefix or path.startswith((f"{prefix}.", f"{prefix}[")):
                return f"methods.{key.split('__')[0]}__*{path[len(prefix) :]}"
        return path

    return generic


def pick_method(methods: dict[str, Method]) -> str:
    merged = [key for key in methods if key.startswith(MERGED_METHOD_PREFIX)]
    if merged:
        return merged[0]
    others = [key for key in methods if not key.startswith(UNMERGED_METHOD_PREFIX)]
    if len(others) != 1:
        raise ValueError(f"Cannot tell which OpenAIReview method to map: {sorted(methods)}")
    return others[0]


def map_comment(
    comment: Comment, source: str, target: str, recorder: Recorder, payload: AiPayload
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "text": recorder.copy(f"{source}.explanation", f"{target}.text", comment.explanation)
    }
    if comment.title:
        finding["title"] = recorder.copy(f"{source}.title", f"{target}.title", comment.title)
    if comment.comment_type:
        finding["tags"] = [
            recorder.copy(f"{source}.comment_type", f"{target}.tags[0]", comment.comment_type)
        ]
    if comment.quote:
        link_target = f"{target}.evidence_links[0]"
        link = recorder.evidence_link(
            f"{source}.quote", link_target, comment.quote, "", payload.blocks
        )
        finding["evidence_links"] = [link]
    return finding


def map_openaireview(payload: AiPayload) -> MappingResult:
    paper = PaperResult.model_validate(payload.output)
    key = pick_method(paper.methods)
    method, prefix = paper.methods[key], f"methods.{key}"
    recorder = Recorder()
    review = build_review(payload.run, FRAMEWORK, MAPPER_VERSION)
    if method.overall_feedback:
        review["opinion"]["summary"] = recorder.copy(
            f"{prefix}.overall_feedback", "opinion.summary", method.overall_feedback
        )
    if method.prompt_tokens is not None and method.completion_tokens is not None:
        target = "referee.ai_referee.outputs.token_usage"
        review["referee"]["ai_referee"]["outputs"] = {
            "token_usage": {
                "input_tokens": recorder.copy(
                    f"{prefix}.prompt_tokens", f"{target}.input_tokens", method.prompt_tokens
                ),
                "output_tokens": recorder.copy(
                    f"{prefix}.completion_tokens",
                    f"{target}.output_tokens",
                    method.completion_tokens,
                ),
            }
        }
    weaknesses = []
    for index, comment in enumerate(method.comments):
        source = f"{prefix}.comments[{index}]"
        if not comment.explanation:
            recorder.skip(source, "no explanation")
            continue
        target = f"findings.weaknesses[{len(weaknesses)}]"
        weaknesses.append(map_comment(comment, source, target, recorder, payload))
    if weaknesses:
        review["findings"] = {"weaknesses": weaknesses}
    return finish(
        review,
        recorder,
        payload.output,
        framework=FRAMEWORK,
        mapper_version=MAPPER_VERSION,
        ignored=IGNORED,
        generic=method_wildcard(list(paper.methods)),
    )


def from_openaireview(payload: dict[str, Any], *, keep_raw: bool = False) -> dict[str, Any]:
    return map_openaireview(AiPayload.model_validate(payload)).review
