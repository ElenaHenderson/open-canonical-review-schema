# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the canonical review schema itself."""

from importlib.metadata import version

from ocrs import load_schema, validate_canonical


def test_schema_id_names_the_package_version():
    expected = (
        "https://valency-oss.github.io/open-canonical-review-schema"
        f"/v{version('ocrs')}/canonical-review.schema.json"
    )
    assert load_schema()["$id"] == expected


def test_an_anonymous_human_review_needs_no_human_referee():
    validate_canonical(
        {
            "review_id": "review-1",
            "version": "1.0.0",
            "created_at": "2026-10-06T12:00:00Z",
            "provenance": {"source_system": "example-journal"},
            "referee": {"referee_type": "human", "identity_mode": "double_blind"},
            "target": {"work_id": "paper-1", "work_type": "article"},
            "opinion": {"summary": "A sound paper."},
        }
    )
