# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for finding titles."""

import pytest
from jsonschema import ValidationError

from ocrs import validate_canonical


def _review(finding):
    """Create a minimal valid review with one weakness."""
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
        "findings": {"weaknesses": [finding]},
    }


def test_finding_without_title():
    validate_canonical(_review({"text": "Missing ablation."}))


def test_title():
    validate_canonical(_review({"title": "No ablation", "text": "Missing ablation."}))


def test_empty_title_is_rejected():
    with pytest.raises(ValidationError):
        validate_canonical(_review({"title": "", "text": "Missing ablation."}))
