# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for HotCRP mapper."""

import json
from pathlib import Path

from ocrs import map_from, map_to, validate_canonical
from ocrs.mappers.hotcrp import from_hotcrp, to_hotcrp

FIXTURES = Path(__file__).parent / "fixtures" / "hotcrp"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES / name).read_text())


def test_hotcrp_minimal():
    """Test minimal HotCRP review conversion."""
    payload = load_fixture("minimal_review.json")
    canon = map_from("hotcrp", payload)
    validate_canonical(canon)

    assert canon["provenance"]["source_system"] == "hotcrp"
    assert canon["target"]["work_id"] == "internal_id:hotcrp_pid:42"
    assert canon["opinion"]["summary"]


def test_hotcrp_realistic():
    """Test realistic HotCRP review with all fields."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("hotcrp", payload, keep_raw=True)
    validate_canonical(canon)

    # Check basic structure
    assert canon["provenance"]["source_system"] == "hotcrp"
    assert canon["provenance"]["source_review_id"] == "4527"
    assert canon["provenance"]["raw_payload"] == payload
    assert canon["target"]["work_id"] == "internal_id:hotcrp_pid:183"

    # Check narrative
    assert "narrative" in canon
    assert canon["narrative"].get("summary")
    assert canon["narrative"].get("confidential_to_editors")

    # Check findings
    assert "findings" in canon
    assert len(canon["findings"].get("strengths", [])) > 0
    assert len(canon["findings"].get("weaknesses", [])) > 0

    # Check decision
    assert "decision" in canon
    assert canon["decision"]["recommendation"] in (
        "accept",
        "weak_accept",
        "strong_accept",
    )

    # Check metrics
    assert len(canon["metrics"]) >= 2
    overall_metric = next((m for m in canon["metrics"] if m["key"] == "overall"), None)
    assert overall_metric is not None
    assert overall_metric["value"] == 4

    # Check review context (round)
    assert canon.get("review_context", {}).get("round") == 1


def test_hotcrp_strengths_weaknesses_parsing():
    """Test bullet list parsing for strengths/weaknesses."""
    payload = {
        "id": 1,
        "pid": 1,
        "overall_merit": "3. Weak Accept",
        "strengths": "- Point one\n- Point two\n- Point three",
        "weaknesses": "* First issue\n* Second issue",
        "comments": "Some comments here.",
    }
    canon = from_hotcrp(payload)
    validate_canonical(canon)

    assert len(canon["findings"]["strengths"]) == 3
    assert canon["findings"]["strengths"][0]["text"] == "Point one"
    assert len(canon["findings"]["weaknesses"]) == 2
    assert canon["findings"]["weaknesses"][0]["text"] == "First issue"


def test_hotcrp_expertise_mapping():
    """Test reviewer expertise level mapping."""
    payload = {
        "id": 2,
        "pid": 2,
        "overall_merit": "3. Weak Accept",
        "reviewer_expertise": "4. Expert",
        "comments": "Good paper.",
    }
    canon = from_hotcrp(payload)
    validate_canonical(canon)

    # Check expertise in review_context
    assert canon["review_context"]["expertise"]["self_reported_level"] == "expert"

    # Check expertise as metric
    conf_metric = next((m for m in canon["metrics"] if m["key"] == "confidence"), None)
    assert conf_metric is not None
    assert conf_metric["value"] == 4


def test_hotcrp_round_parsing():
    """Test review round parsing from various formats."""
    for round_val, expected in [
        ("R1", 1),
        ("R2", 2),
        ("main", 1),
        ("Round 2", 2),
        (3, 3),
    ]:
        payload = {
            "id": 3,
            "pid": 3,
            "round": round_val,
            "overall_merit": "3. Weak Accept",
            "comments": "Review comments.",
        }
        canon = from_hotcrp(payload)
        assert canon.get("review_context", {}).get("round") == expected


def test_hotcrp_to_and_back():
    """Test roundtrip conversion (lossy)."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("hotcrp", payload)
    validate_canonical(canon)

    back = map_to("hotcrp", canon)

    # Verify basic structure preserved
    assert back.get("pid") == "183"
    assert "overall_merit" in back or "comments" in back
    assert "strengths" in back or "weaknesses" in back


def test_hotcrp_additional_metrics():
    """Test that additional numeric fields become metrics."""
    payload = {
        "id": 4,
        "pid": 4,
        "overall_merit": "4. Accept",
        "novelty": "3. Some new ideas",
        "technical_quality": "4. Strong",
        "presentation": "3. Adequate",
        "comments": "The paper is well written.",
    }
    canon = from_hotcrp(payload)
    validate_canonical(canon)

    # Should have overall + 3 additional metrics
    assert len(canon["metrics"]) >= 4
    keys = {m["key"] for m in canon["metrics"]}
    assert "overall" in keys
    assert "novelty" in keys


def test_hotcrp_to_stub():
    """Test basic to_hotcrp stub functionality."""
    canon = {
        "review_id": "hotcrp_123",
        "version": "1.0.0",
        "created_at": "2024-12-25T00:00:00Z",
        "provenance": {
            "source_system": "hotcrp",
            "source_review_id": "123",
            "imported_at": "2024-12-25T00:00:00Z",
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": {"referee_type": "human", "identity_mode": "confidential"},
        "target": {"work_id": "internal_id:hotcrp_pid:42", "work_type": "article"},
        "opinion": {"summary": "Good paper."},
        "narrative": {
            "summary": "Paper summary here.",
            "detailed_review": "Detailed review text.",
        },
        "findings": {
            "strengths": [{"text": "Strong point 1"}, {"text": "Strong point 2"}],
            "weaknesses": [{"text": "Weak point 1"}],
        },
        "decision": {"recommendation": "accept"},
        "metrics": [{"key": "overall", "aspect": "overall", "value": 4}],
        "review_context": {"round": 2},
    }
    back = to_hotcrp(canon)

    assert back["id"] == "123"
    assert back["pid"] == "42"
    assert back.get("paper_summary") == "Paper summary here."
    assert "strengths" in back
    assert "- Strong point 1" in back["strengths"]
    assert back["round"] == "R2"
