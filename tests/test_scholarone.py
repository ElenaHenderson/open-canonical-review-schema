# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for ScholarOne mapper."""

import json
from pathlib import Path

from ocrs import map_from, map_to, validate_canonical
from ocrs.mappers.scholarone import from_scholarone, to_scholarone

FIXTURES = Path(__file__).parent / "fixtures" / "scholarone"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES / name).read_text())


def test_scholarone_minimal():
    """Test minimal ScholarOne review conversion."""
    payload = load_fixture("minimal_review.json")
    canon = map_from("scholarone", payload)
    validate_canonical(canon)

    assert canon["provenance"]["source_system"] == "scholarone"
    assert canon["target"]["work_id"] == "DOC-123456"
    assert canon["opinion"]["summary"]
    assert canon["decision"] == {"revision_requirement": "major"}


def test_scholarone_realistic():
    """Test realistic ScholarOne review with all fields."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("scholarone", payload, keep_raw=True)
    validate_canonical(canon)

    # Check basic structure
    assert canon["provenance"]["source_system"] == "scholarone"
    assert canon["provenance"]["raw_payload"] == payload
    assert canon["target"]["work_id"] == "DOC-2024-789012"
    assert canon["target"]["venue"] == "Neurology AI"

    # Check reviewer ID construction
    assert canon["referee"]["referee_id"] == "reviewer_2"

    # Check narrative
    assert "narrative" in canon
    assert canon["narrative"].get("detailed_review")
    assert canon["narrative"].get("confidential_to_editors")

    # Check decision
    assert canon["decision"] == {"revision_requirement": "minor"}

    # Check metrics from criteria responses
    assert len(canon["metrics"]) >= 6
    originality_metric = next((m for m in canon["metrics"] if m["label"] == "Originality"), None)
    assert originality_metric is not None
    assert originality_metric["value"] == 4

    # Check overall metric
    overall_metric = next((m for m in canon["metrics"] if m["key"] == "overall"), None)
    assert overall_metric is not None
    assert overall_metric["value"] == 2


def test_scholarone_recommendation_codes():
    """Test recommendation code mapping."""
    for code, expected in [
        (1, {"recommendation": "accept"}),
        (2, {"revision_requirement": "minor"}),
        (3, {"revision_requirement": "major"}),
        (4, {"recommendation": "reject"}),
        (5, {"revision_requirement": "unspecified"}),
    ]:
        payload = {
            "documentId": f"DOC-{code}",
            "reviewerNumber": 1,
            "overallRecommendation": code,
            "commentsToAuthor": "Test comments.",
        }
        canon = from_scholarone(payload)
        validate_canonical(canon)
        assert canon["decision"] == expected


def test_scholarone_text_recommendation():
    """Test text-based recommendation label parsing."""
    test_cases = [
        ("Accept", {"recommendation": "accept"}),
        ("Minor Revision", {"revision_requirement": "minor"}),
        ("Major Revision", {"revision_requirement": "major"}),
        ("Reject", {"recommendation": "reject"}),
    ]
    for label, expected in test_cases:
        payload = {
            "documentId": f"DOC-{label}",
            "reviewerNumber": 1,
            "overallRecommendationLabel": label,
            "commentsToAuthor": "Test comments.",
        }
        canon = from_scholarone(payload)
        validate_canonical(canon)
        assert canon["decision"] == expected


def test_scholarone_criteria_normalization():
    """Test that criteria responses are properly normalized."""
    payload = {
        "documentId": "DOC-NORM",
        "reviewerNumber": 1,
        "overallRecommendation": 2,
        "commentsToAuthor": "Good paper.",
        "criteriaResponses": [
            {"criterionName": "Quality", "response": 4, "maxResponse": 5},
            {"criterionName": "Novelty", "response": 8, "maxResponse": 10},
        ],
    }
    canon = from_scholarone(payload)
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


def test_scholarone_review_id_construction():
    """Test review ID is constructed from document and reviewer number."""
    payload = {
        "documentId": "DOC-123",
        "submissionId": "SUB-456",
        "reviewerNumber": 3,
        "overallRecommendation": 1,
        "commentsToAuthor": "Good paper.",
    }
    canon = from_scholarone(payload)
    validate_canonical(canon)

    # Review ID should include document ID and reviewer number
    assert canon["review_id"] == "s1_DOC-123_r3"
    assert canon["provenance"]["source_review_id"] == "DOC-123_r3"


def test_scholarone_competing_interests():
    """Test competing interests handling."""
    # No conflicts
    payload1 = {
        "documentId": "DOC-COI1",
        "reviewerNumber": 1,
        "overallRecommendation": 1,
        "commentsToAuthor": "Good paper.",
        "competingInterests": "None declared",
    }
    canon1 = from_scholarone(payload1)
    assert canon1["referee"]["competing_interests_declared"] is False

    # Has conflicts
    payload2 = {
        "documentId": "DOC-COI2",
        "reviewerNumber": 1,
        "overallRecommendation": 1,
        "commentsToAuthor": "Good paper.",
        "competingInterests": "I have received consulting fees from the authors' institution.",
    }
    canon2 = from_scholarone(payload2)
    assert canon2["referee"]["competing_interests_declared"] is True
    assert "consulting fees" in canon2["referee"]["competing_interests_statement"]


def test_scholarone_to_and_back():
    """Test roundtrip conversion (lossy)."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("scholarone", payload)
    validate_canonical(canon)

    back = map_to("scholarone", canon)

    # Verify basic structure preserved
    assert back["documentId"] == "DOC-2024-789012"
    assert "commentsToAuthor" in back
    assert back["overallRecommendation"] == 2
    assert back["overallRecommendationLabel"] == "Minor Revision"
    assert "criteriaResponses" in back


def test_scholarone_to_stub():
    """Test basic to_scholarone stub functionality."""
    canon = {
        "review_id": "s1_DOC-TEST_r2",
        "version": "1.0.0",
        "created_at": "2024-12-25T00:00:00Z",
        "provenance": {
            "source_system": "scholarone",
            "source_review_id": "DOC-TEST_r2",
            "imported_at": "2024-12-25T00:00:00Z",
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": {"referee_type": "human", "identity_mode": "confidential"},
        "target": {
            "work_id": "DOC-TEST",
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
                "label": "Overall",
                "aspect": "overall",
                "value": 1,
                "scale": {"type": "ordinal", "min": 1, "max": 5},
            },
            {
                "key": "novelty",
                "label": "Originality",
                "aspect": "novelty",
                "value": 4,
                "scale": {"type": "ordinal", "min": 1, "max": 5},
            },
        ],
    }
    back = to_scholarone(canon)

    assert back["documentId"] == "DOC-TEST"
    assert back["reviewerNumber"] == 2
    assert back["journalName"] == "Test Journal"
    assert back["commentsToAuthor"] == "The paper is well written."
    assert back["commentsToEditor"] == "No concerns."
    assert back["overallRecommendation"] == 1
    assert back["overallRecommendationLabel"] == "Accept"
    assert len(back["criteriaResponses"]) == 1
    assert back["criteriaResponses"][0]["criterionName"] == "Originality"
