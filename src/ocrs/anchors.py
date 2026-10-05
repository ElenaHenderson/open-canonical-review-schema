# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Find a reviewer's quote in the paper it reviewed.

The paper comes as blocks of plain text (paragraphs, headings, the abstract,
references). A quote matches a block exactly after normalising both, or
fuzzily when at least `FUZZY_THRESHOLD` of the quote appears in the block in
order.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher
from enum import Enum

from pydantic import BaseModel

FUZZY_THRESHOLD = 0.9
# Shorter common runs are mostly coincidence (single letters, spaces), not quoted text.
MIN_RUN = 4

_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(#[^)]*\)")
_MARKUP = re.compile(r"[*_`$\\|#>]")
_SPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.,;:!?)\]])")


class BlockKind(str, Enum):
    BODY = "body"
    ABSTRACT = "abstract"
    REFERENCE = "reference"


class Block(BaseModel):
    id: str | None = None
    kind: BlockKind = BlockKind.BODY
    text: str


class Match(BaseModel):
    block: Block
    exact: bool
    score: float


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _MARKDOWN_LINK.sub("", text)
    text = _MARKUP.sub("", text)
    text = _SPACE.sub(" ", text)
    return _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text).strip().casefold()


def share_found_in_order(quote: str, text: str) -> float:
    matcher = SequenceMatcher(None, text, quote, autojunk=False)
    found = sum(run.size for run in matcher.get_matching_blocks() if run.size >= MIN_RUN)
    return found / len(quote)


def find_quote(quote: str, blocks: Iterable[Block]) -> tuple[Match | None, float]:
    """The block holding `quote`, or None, and the best fuzzy score seen."""
    wanted = normalise(quote)
    if not wanted:
        return None, 0.0
    normalised = [(block, normalise(block.text)) for block in blocks]
    for block, text in normalised:
        if wanted in text:
            return Match(block=block, exact=True, score=1.0), 1.0
    best: Match | None = None
    for block, text in normalised:
        if not text:
            continue
        score = share_found_in_order(wanted, text)
        if best is None or score > best.score:
            best = Match(block=block, exact=False, score=score)
    if best is None:
        return None, 0.0
    return (best if best.score >= FUZZY_THRESHOLD else None), best.score
