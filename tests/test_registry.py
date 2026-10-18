# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the registry: which sources and targets exist, and unknown names."""

import json
from pathlib import Path

import pytest

from ocrs import map_from, map_to, map_with_record, mapper_version, supported_targets

FIXTURES = Path(__file__).parent / "fixtures"
REVIEW = map_from("cmt", json.loads((FIXTURES / "cmt" / "minimal_review.json").read_text()))


def test_unknown_source():
    with pytest.raises(ValueError, match="Unsupported source: nope"):
        map_from("nope", {})


def test_unknown_target():
    with pytest.raises(ValueError, match="Unsupported target: nope"):
        map_to("nope", REVIEW)


def test_mapping_record_only_for_ai_reviewers():
    run = {
        "review_id": "r",
        "source_system": "cmt",
        "work_id": "p",
        "work_type": "preprint",
        "started_at": "2026-10-03T01:00:00Z",
        "ended_at": "2026-10-03T01:08:00Z",
    }
    with pytest.raises(ValueError, match="No mapping record for cmt"):
        map_with_record("cmt", {}, **run)


def test_mapper_version():
    assert mapper_version("reviewer3") == "1.1.0"
    with pytest.raises(ValueError, match="No mapping record for cmt"):
        mapper_version("cmt")


@pytest.mark.parametrize("target", supported_targets())
def test_every_target_writes_any_review(target):
    """A review from another system can be written in every target's format."""
    written = map_to(target, REVIEW)
    assert written and isinstance(written, (dict, str))
