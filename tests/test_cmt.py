# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for CMT mapper."""

import json
from pathlib import Path

from ocrs import map_from, map_to, validate_canonical
from ocrs.mappers.cmt import from_cmt, to_cmt

FIXTURES = Path(__file__).parent / "fixtures" / "cmt"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES / name).read_text())


def test_cmt_minimal():
    """Test minimal CMT review conversion."""
    payload = load_fixture("minimal_review.json")
    canon = map_from("cmt", payload)
    validate_canonical(canon)

    assert canon["provenance"]["source_system"] == "cmt"
    assert canon["target"]["work_id"] == "42"
    assert canon["opinion"]["summary"]


def test_cmt_realistic():
    """Test realistic CMT review with all fields."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("cmt", payload, keep_raw=True)
    validate_canonical(canon)

    # Check basic structure
    assert canon["provenance"]["source_system"] == "cmt"
    assert canon["provenance"]["source_review_id"] == "ICML2024_Rev_3847"
    assert canon["provenance"]["raw_payload"] == payload
    assert canon["target"]["work_id"] == "2847"
    assert canon["target"]["venue"] == "ICML 2024"
    assert canon["target"]["track"] == "Main Conference"

    # Check narrative
    assert "narrative" in canon
    assert canon["narrative"].get("summary")
    assert canon["narrative"].get("detailed_review")
    assert canon["narrative"].get("confidential_to_editors")

    # Check decision
    assert "decision" in canon
    assert canon["decision"]["recommendation"] == "weak_accept"

    # Check metrics
    assert len(canon["metrics"]) >= 2
    overall_metric = next((m for m in canon["metrics"] if m["key"] == "overall"), None)
    assert overall_metric is not None
    assert overall_metric["value"] == 6


def test_cmt_identifiers_extraction():
    """Test that target identifiers are properly extracted."""
    payload = {
        "reviewId": "test_id",
        "paperId": 42,
        "doi": "10.1234/test.2024",
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    # Check identifiers are populated
    identifiers = canon["target"]["identifiers"]
    assert identifiers["doi"]["value"] == "10.1234/test.2024"
    assert identifiers["doi"]["hyperlink"] == "https://doi.org/10.1234/test.2024"
    assert identifiers["internal_id"]["field_name"] == "paperId"
    assert identifiers["internal_id"]["value"] == "42"

    # work_id should still be populated for backward compatibility
    assert canon["target"]["work_id"] == "42"


def test_cmt_identifiers_without_doi():
    """Test identifier extraction when DOI is not present."""
    payload = {
        "reviewId": "test_id",
        "paperId": 99,
        "overallEvaluation": "4: Accept",
        "commentsToAuthors": "Good paper.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    identifiers = canon["target"]["identifiers"]
    assert "doi" not in identifiers
    assert identifiers["internal_id"]["field_name"] == "paperId"
    assert identifiers["internal_id"]["value"] == "99"


def test_cmt_identifiers_invalid_doi():
    """Test that invalid DOIs are not included in identifiers."""
    payload = {
        "reviewId": "test_id",
        "paperId": 100,
        "doi": "invalid-doi",  # Not a valid DOI format
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    identifiers = canon["target"]["identifiers"]
    assert "doi" not in identifiers
    assert identifiers["internal_id"]["value"] == "100"


def test_cmt_human_referee_orcid():
    """Test ORCID normalization and validation in human referee."""
    payload = {
        "reviewId": "test_id",
        "paperId": 1,
        "reviewerOrcid": "0000-0001-5000-0007",  # Valid ORCID
        "reviewerName": "Dr. Jane Smith",
        "reviewerAffiliation": "MIT",
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    human_referee = canon["referee"]["human_referee"]
    assert human_referee["orcid"] == "0000-0001-5000-0007"
    assert human_referee["name"] == "Dr. Jane Smith"
    assert human_referee["affiliation"] == "MIT"


def test_cmt_human_referee_orcid_url_format():
    """Test ORCID normalization from URL format."""
    payload = {
        "reviewId": "test_id",
        "paperId": 1,
        "orcid": "https://orcid.org/0000-0001-5000-0007",  # URL format
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    human_referee = canon["referee"]["human_referee"]
    assert human_referee["orcid"] == "0000-0001-5000-0007"


def test_cmt_human_referee_invalid_orcid():
    """Test that invalid ORCIDs are not included."""
    payload = {
        "reviewId": "test_id",
        "paperId": 1,
        "reviewerOrcid": "0000-0001-5000-0008",  # Invalid checksum
        "reviewerName": "Dr. Jane Smith",
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    human_referee = canon["referee"]["human_referee"]
    assert "orcid" not in human_referee  # Invalid ORCID should be excluded
    assert human_referee["name"] == "Dr. Jane Smith"


def test_cmt_human_referee_alternative_field_names():
    """Test alternative field names for reviewer identity."""
    payload = {
        "reviewId": "test_id",
        "paperId": 1,
        "reviewer_name": "Prof. John Doe",  # Snake case
        "affiliation": "Stanford University",  # Alternative field name
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    human_referee = canon["referee"]["human_referee"]
    assert human_referee["name"] == "Prof. John Doe"
    assert human_referee["affiliation"] == "Stanford University"


def test_cmt_work_id_from_submission_id():
    """Test work_id extraction from submissionId field."""
    payload = {
        "reviewId": "test_id",
        "submissionId": "SUB-2024-001",  # Use submissionId instead of paperId
        "overallEvaluation": "5: Borderline",
        "commentsToAuthors": "Test review.",
    }
    canon = from_cmt(payload)
    validate_canonical(canon)

    assert canon["target"]["work_id"] == "SUB-2024-001"
    assert canon["target"]["identifiers"]["internal_id"]["value"] == "SUB-2024-001"


def test_cmt_to_and_back():
    """Test roundtrip conversion (lossy)."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("cmt", payload)
    validate_canonical(canon)

    back = map_to("cmt", canon)

    # Verify basic structure preserved
    assert back.get("paperId") == "2847"
    assert back.get("conferenceName") == "ICML 2024"
    assert "commentsToAuthors" in back or "summary" in back


def test_cmt_to_stub():
    """Test basic to_cmt stub functionality."""
    canon = {
        "review_id": "cmt_123",
        "version": "1.0.0",
        "created_at": "2024-12-25T00:00:00Z",
        "provenance": {
            "source_system": "cmt",
            "source_review_id": "123",
            "imported_at": "2024-12-25T00:00:00Z",
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": {"referee_type": "human", "identity_mode": "confidential"},
        "target": {"work_id": "42", "work_type": "other"},
        "opinion": {"summary": "Good paper."},
        "narrative": {
            "summary": "Paper summary here.",
            "detailed_review": "Detailed review text.",
            "confidential_to_editors": "Comments to chairs.",
        },
        "decision": {"recommendation": "accept"},
        "metrics": [{"key": "overall", "aspect": "overall", "value": 4}],
    }
    back = to_cmt(canon)

    assert back["reviewId"] == "cmt_123"
    assert back["paperId"] == "42"
    assert back.get("summary") == "Good paper."  # Uses opinion.summary
    assert back.get("commentsToAuthors") == "Detailed review text."
    assert back.get("commentsToChairs") == "Comments to chairs."
