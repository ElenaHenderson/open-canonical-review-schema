# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for roundtrip conversion between source formats and canonical schema."""

import json
from pathlib import Path

import pytest

from ocrs import generate_canonical_work_id, map_from, map_to, validate_canonical


def test_openreview_to_canonical_and_back():
    openreview_note = {
        "id": "or_review_1",
        "forum": "or_forum_123",
        "cdate": 1735689600000,  # 2025-01-01T00:00:00Z
        "signatures": ["~Reviewer_One1"],
        "content": {
            "rating": "6: Weak Accept",
            "confidence": "4: confident",
            "summary": "Interesting paper with some gaps.",
            "review": (
                "The main idea is promising. However, the proof is missing key assumptions."
                "\n\nMore detail here."
            ),
            "soundness": 3,
            "clarity": 2,
            "strengths": ["Good motivation", "Solid empirical results"],
            "weaknesses": ["Proof incomplete"],
        },
    }
    canon = map_from("openreview", openreview_note, keep_raw=True)
    validate_canonical(canon)
    assert canon["provenance"]["source_system"] == "openreview"
    assert canon["opinion"]["summary"]
    note2 = map_to("openreview", canon)
    assert "content" in note2 and isinstance(note2["content"], dict)


def test_cmt_to_canonical_and_back():
    cmt = {
        "reviewId": "cmt_r1",
        "paperId": 42,
        "conferenceName": "NeurIPS 2026",
        "trackName": "Main",
        "reviewerId": "rev_77",
        "overallEvaluation": "7: Accept",
        "confidence": 0.8,
        "summary": "Strong contribution.",
        "commentsToAuthors": "Well-written and significant. Missing ablation.",
    }
    canon = map_from("cmt", cmt)
    validate_canonical(canon)
    back = map_to("cmt", canon)
    assert back["reviewId"] == "cmt_r1"
    assert "commentsToAuthors" in back


def test_journal_narrative_minimal():
    j = {
        "doi": "10.5555/12345678",
        "journal": "Journal of Tests",
        "full_text": (
            "This manuscript addresses an important problem. The methods are plausible but unclear."
            "\n\nPlease clarify the assumptions."
        ),
    }
    canon = map_from("journal_narrative", j)
    validate_canonical(canon)
    assert canon["opinion"]["summary"]
    back = map_to("journal_narrative", canon)
    assert back["full_text"]


def test_openreview_note_without_id_or_signature():
    canon = map_from("openreview", {"forum": "or_forum_123", "content": {"summary": "Fine."}})
    assert "referee_id" not in canon["referee"]
    assert "source_review_id" not in canon["provenance"]


FIXTURES = Path(__file__).parent / "fixtures"
# Each source's field for the paper ID, as map_to writes it back
SOURCE_ID_FIELD = {
    "openreview": "forum",
    "cmt": "paperId",
    "hotcrp": "pid",
    "scholarone": "documentId",
    "editorialmanager": "manuscriptId",
}


@pytest.mark.parametrize(
    "fixture",
    sorted(p for source in SOURCE_ID_FIELD for p in (FIXTURES / source).glob("*.json")),
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_work_id_is_canonical_and_maps_back_to_the_source_id(fixture: Path) -> None:
    source = fixture.parent.name
    canon = map_from(source, json.loads(fixture.read_text()))
    target = canon["target"]
    assert target["work_id"] == generate_canonical_work_id(target["identifiers"])
    source_id = target["identifiers"]["internal_id"]["value"]
    assert map_to(source, canon)[SOURCE_ID_FIELD[source]] == source_id


def test_journal_narrative_maps_the_doi_back() -> None:
    canon = map_from(
        "journal_narrative",
        {
            "review_id": "r1",
            "doi": "10.1234/abc",
            "manuscript_id": "MS-1",
            "journal": "Example Journal",
            "full_text": "Fine.",
        },
    )
    assert canon["target"]["work_id"] == "doi:10.1234/abc"
    assert map_to("journal_narrative", canon)["doi"] == "10.1234/abc"
