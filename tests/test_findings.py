# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for finding titles and requested changes."""

import pytest
from jsonschema import ValidationError

from ocrs import validate_canonical


def _review(finding):
    """Create a minimal valid review with one weakness."""
    return _review_with_findings({"weaknesses": [finding]})


def _review_with_findings(findings):
    """Create a minimal valid review with the given findings."""
    return {
        "review_id": "test_finding_001",
        "version": "1.0.0",
        "created_at": "2026-10-05T12:00:00Z",
        "provenance": {"source_system": "test"},
        "referee": {
            "referee_type": "human",
            "identity_mode": "confidential",
            "human_referee": {},
        },
        "target": {
            "work_id": "internal_id:manuscript_id:paper_123",
            "work_type": "preprint",
            "version": "v2",
        },
        "opinion": {"summary": "Test review."},
        "findings": findings,
    }


def test_finding_without_title():
    validate_canonical(_review({"text": "Missing ablation."}))


def test_title():
    validate_canonical(_review({"title": "No ablation", "text": "Missing ablation."}))


def test_empty_title_is_rejected():
    with pytest.raises(ValidationError):
        validate_canonical(_review({"title": "", "text": "Missing ablation."}))


@pytest.mark.parametrize("priority", ["critical", "major", "minor", "trivial"])
def test_change_priority(priority):
    change = {"text": "Fix the proof of Lemma 2.", "priority": priority}
    validate_canonical(_review_with_findings({"changes": [change]}))


@pytest.mark.parametrize("priority", ["low", "medium", "high", "blocking"])
def test_old_priorities_are_rejected(priority):
    change = {"text": "Fix the proof of Lemma 2.", "priority": priority}
    with pytest.raises(ValidationError):
        validate_canonical(_review_with_findings({"changes": [change]}))


@pytest.mark.parametrize("old_name", ["required_changes", "optional_suggestions"])
def test_required_and_optional_changes_are_rejected(old_name):
    with pytest.raises(ValidationError):
        validate_canonical(_review_with_findings({old_name: [{"text": "Add an ablation."}]}))
