# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the canonical review schema itself."""

from importlib.metadata import version
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

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


def test_the_published_copy_of_this_version_matches_the_package():
    schemas = Path(__file__).parent.parent / "src" / "ocrs" / "schemas"
    published = Path(__file__).parent.parent / "versions" / f"v{version('ocrs')}"
    assert sorted(path.name for path in published.iterdir()) == sorted(
        path.name for path in schemas.glob("*.json")
    )
    for path in published.iterdir():
        assert path.read_bytes() == (schemas / path.name).read_bytes(), path.name


def test_schema_is_valid_json_schema():
    Draft202012Validator.check_schema(load_schema())


def _review_of(identifiers: dict) -> dict:
    return {
        "review_id": "review-1",
        "version": "1.0.0",
        "created_at": "2026-10-15T12:00:00Z",
        "provenance": {"source_system": "example-journal"},
        "referee": {"referee_type": "human", "identity_mode": "double_blind"},
        "target": {"work_id": "paper-1", "work_type": "article", "identifiers": identifiers},
        "opinion": {"summary": "A sound paper."},
    }


def test_target_takes_crossref_identifier_types():
    validate_canonical(
        _review_of(
            {
                "handle": {
                    "value": "1721.1/12345",
                    "hyperlink": "https://hdl.handle.net/1721.1/12345",
                },
                "ark": {"value": "ark:/13030/tf5p30086k"},
                "isbn": {"value": "9780262035613"},
                "issn": {"value": "2050-084X"},
                "ecli": {"value": "ECLI:EU:C:2014:317"},
                "accession": {"value": "MN908947", "database": "GenBank"},
                "purl": "https://purl.org/example/1",
                "uuid": {"value": "123e4567-e89b-12d3-a456-426614174000"},
            }
        )
    )


@pytest.mark.parametrize(
    "identifiers",
    [
        {"handle": {"value": "hdl:1721.1/12345"}},
        {"ark": {"value": "13030/tf5p30086k"}},
        {"isbn": {"value": "978-0-262-03561-3"}},
        {"issn": {"value": "2050084X"}},
        {"ecli": {"value": "EU:C:2014:317"}},
        {"accession": {"database": "GenBank"}},
        {"purl": {"value": "https://purl.org/example/1"}},
        {"uuid": {"value": "123e4567e89b12d3a456426614174000"}},
    ],
)
def test_crossref_identifier_types_reject_malformed_values(identifiers: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_canonical(_review_of(identifiers))


def _review_with(finding: dict, claim: dict) -> dict:
    return {
        "review_id": "review-1",
        "version": "1.0.0",
        "created_at": "2026-10-07T12:00:00Z",
        "provenance": {"source_system": "example-journal"},
        "referee": {"referee_type": "human", "identity_mode": "double_blind"},
        "target": {"work_id": "paper-1", "work_type": "article"},
        "opinion": {"summary": "A sound paper."},
        "findings": {"weaknesses": [finding]},
        "claim_assessments": [claim],
    }


CLAIM = {"claim_id": "c1", "claim_text": "The method doubles accuracy.", "status": "unclear"}
FINDING = {"text": "The baseline is missing."}


def test_findings_and_claims_take_probability_and_credence() -> None:
    validate_canonical(
        _review_with(
            {**FINDING, "probability": 0.8, "credence": 0.6},
            {**CLAIM, "probability": 0.3, "credence": 0.9},
        )
    )
    validate_canonical(_review_with(FINDING, CLAIM))


@pytest.mark.parametrize(
    "estimate", [{"probability": 1.2}, {"probability": -0.1}, {"probability": 0.5, "credence": 2}]
)
def test_probability_and_credence_are_between_0_and_1(estimate: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_canonical(_review_with({**FINDING, **estimate}, CLAIM))
    with pytest.raises(jsonschema.ValidationError):
        validate_canonical(_review_with(FINDING, {**CLAIM, **estimate}))


def test_credence_needs_a_probability() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_canonical(_review_with({**FINDING, "credence": 0.5}, CLAIM))
    with pytest.raises(jsonschema.ValidationError):
        validate_canonical(_review_with(FINDING, {**CLAIM, "credence": 0.5}))
