# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Tests for Editorial Manager mapper."""

import json
from pathlib import Path

from ocrs import map_from, map_to, validate_canonical
from ocrs.mappers.editorialmanager import from_editorialmanager, to_editorialmanager

FIXTURES = Path(__file__).parent / "fixtures" / "editorialmanager"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES / name).read_text())


def test_editorialmanager_minimal():
    """Test minimal Editorial Manager review conversion."""
    payload = load_fixture("minimal_review.json")
    canon = map_from("editorialmanager", payload)
    validate_canonical(canon)

    assert canon["provenance"]["source_system"] == "editorialmanager"
    assert canon["target"]["work_id"] == "MS-2024-0042"
    assert canon["opinion"]["summary"]
    assert canon["decision"]["recommendation"] == "major_revision"


def test_editorialmanager_realistic():
    """Test realistic Editorial Manager review with all fields."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("editorialmanager", payload, keep_raw=True)
    validate_canonical(canon)

    # Check basic structure
    assert canon["provenance"]["source_system"] == "editorialmanager"
    assert canon["provenance"]["source_review_id"] == "REV-2024-78543"
    assert canon["provenance"]["raw_payload"] == payload
    assert canon["target"]["work_id"] == "MS-2024-001234"
    assert canon["target"]["venue"] == "Journal of Coastal Research"

    # Check narrative
    assert "narrative" in canon
    assert canon["narrative"].get("detailed_review")
    assert canon["narrative"].get("confidential_to_editors")

    # Check decision
    assert canon["decision"]["recommendation"] == "major_revision"

    # Check round (revisionNumber 0 -> round 1)
    assert canon["review_context"]["round"] == 1

    # Check metrics from ratings
    assert len(canon["metrics"]) == 5
    novelty_metric = next((m for m in canon["metrics"] if m["label"] == "Novelty"), None)
    assert novelty_metric is not None
    assert novelty_metric["value"] == 3


def test_editorialmanager_revision():
    """Test Editorial Manager R2 revision review."""
    payload = load_fixture("realistic_revision.json")
    canon = map_from("editorialmanager", payload)
    validate_canonical(canon)

    # Check revision number mapping
    assert canon["review_context"]["round"] == 3  # revisionNumber 2 -> round 3

    # Check recommendation
    assert canon["decision"]["recommendation"] == "accept"

    # Check improved ratings
    methodology_metric = next((m for m in canon["metrics"] if m["label"] == "Methodology"), None)
    assert methodology_metric is not None
    assert methodology_metric["value"] == 5


def test_editorialmanager_recommendation_code():
    """Test recommendation code mapping."""
    for code, expected in [
        (1, "accept"),
        (2, "minor_revision"),
        (3, "major_revision"),
        (4, "reject"),
        (5, "revise"),
    ]:
        payload = {
            "reviewId": f"test_{code}",
            "manuscriptId": "MS-TEST",
            "recommendationCode": code,
            "commentsToAuthor": "Test comments.",
        }
        canon = from_editorialmanager(payload)
        validate_canonical(canon)
        assert canon["decision"]["recommendation"] == expected


def test_editorialmanager_text_recommendation():
    """Test text-based recommendation parsing."""
    test_cases = [
        ("Accept", "accept"),
        ("Minor Revision", "minor_revision"),
        ("Major Revision", "major_revision"),
        ("Reject", "reject"),
        ("Reject and Encourage Resubmission", "revise"),
    ]
    for text, expected in test_cases:
        payload = {
            "reviewId": f"test_{text}",
            "manuscriptId": "MS-TEST",
            "recommendation": text,
            "commentsToAuthor": "Test comments.",
        }
        canon = from_editorialmanager(payload)
        validate_canonical(canon)
        assert canon["decision"]["recommendation"] == expected


def test_editorialmanager_ratings_normalization():
    """Test that ratings are properly normalized."""
    payload = {
        "reviewId": "test_norm",
        "manuscriptId": "MS-TEST",
        "recommendation": "Accept",
        "commentsToAuthor": "Good paper.",
        "ratings": [
            {"question": "Quality", "score": 4, "maxScore": 5},
            {"question": "Novelty", "score": 8, "maxScore": 10},
        ],
    }
    canon = from_editorialmanager(payload)
    validate_canonical(canon)

    # Check normalization
    quality_metric = next((m for m in canon["metrics"] if m["label"] == "Quality"), None)
    assert quality_metric is not None
    # 4 out of 5 should normalize to 0.75
    assert quality_metric["normalized"]["value_0_1"] == 0.75

    novelty_metric = next((m for m in canon["metrics"] if m["label"] == "Novelty"), None)
    assert novelty_metric is not None
    # 8 out of 10 should normalize to ~0.78
    assert 0.77 < novelty_metric["normalized"]["value_0_1"] < 0.79


def test_editorialmanager_to_and_back():
    """Test roundtrip conversion (lossy)."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("editorialmanager", payload)
    validate_canonical(canon)

    back = map_to("editorialmanager", canon)

    # Verify basic structure preserved
    assert back["manuscriptId"] == "MS-2024-001234"
    assert "commentsToAuthor" in back
    assert "recommendation" in back
    assert back["revisionNumber"] == 0


def test_editorialmanager_to_stub():
    """Test basic to_editorialmanager stub functionality."""
    canon = {
        "review_id": "em_REV123",
        "version": "1.0.0",
        "created_at": "2024-12-25T00:00:00Z",
        "provenance": {
            "source_system": "editorialmanager",
            "source_review_id": "REV123",
            "imported_at": "2024-12-25T00:00:00Z",
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": {"referee_type": "human", "identity_mode": "confidential"},
        "target": {
            "work_id": "MS-2024-TEST",
            "work_type": "article",
            "venue": "Test Journal",
        },
        "opinion": {"summary": "Good paper."},
        "narrative": {
            "detailed_review": "The paper is well written.",
            "confidential_to_editors": "No concerns.",
        },
        "decision": {"recommendation": "accept"},
        "metrics": [
            {
                "key": "overall",
                "label": "Overall Quality",
                "aspect": "overall",
                "value": 4,
                "scale": {"type": "ordinal", "min": 1, "max": 5},
            }
        ],
        "review_context": {"round": 2},
    }
    back = to_editorialmanager(canon)

    assert back["reviewId"] == "REV123"
    assert back["manuscriptId"] == "MS-2024-TEST"
    assert back["journalName"] == "Test Journal"
    assert back["commentsToAuthor"] == "The paper is well written."
    assert back["confidentialCommentsToEditor"] == "No concerns."
    assert back["recommendation"] == "Accept"
    assert back["revisionNumber"] == 1
    assert len(back["ratings"]) == 1
    assert back["ratings"][0]["question"] == "Overall Quality"
    assert back["ratings"][0]["score"] == 4
