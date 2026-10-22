# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""The crosswalk generator: what it writes, and that the crosswalk says what the README says."""

import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest
from test_roundtrip import LOSSES

from ocrs.gaps import iter_schema_paths
from ocrs.registry import supported_sources

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_crosswalk.py"
FILES = ["CROSSWALK.md", "coverage.csv", "crosswalk.csv", "crosswalk.long.csv", "gaps.csv"]


def load_script():
    spec = importlib.util.spec_from_file_location("build_crosswalk", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


@pytest.fixture(scope="module")
def files(script):
    return {path.as_posix(): text for path, text in script.outputs().items()}


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


@pytest.fixture(scope="module")
def long_rows(files):
    return rows(files["crosswalk/crosswalk.long.csv"])


def sources(long_rows, system: str, path: str) -> set[str]:
    return {
        r["source_field"] for r in long_rows if r["system"] == system and r["ocrs_path"] == path
    }


def test_it_writes_the_five_files(files):
    assert sorted(files) == [f"crosswalk/{f}" for f in FILES]


def test_every_leaf_field_of_the_schema_has_a_row(files, script):
    schema = json.loads((ROOT / "src/ocrs/schemas/canonical-review.schema.json").read_text())
    paths = sorted({p for p in iter_schema_paths(schema, schema) if not script.is_skipped(p)})
    leaves = {p for i, p in enumerate(paths) if not any(script.under(q, p) for q in paths[i + 1 :])}
    listed = {r["ocrs_path"] for r in rows(files["crosswalk/crosswalk.csv"])}
    assert leaves <= listed
    assert not any(path.startswith("extensions") for path in listed)


def test_every_registered_mapper_has_a_column(files):
    header = next(csv.reader(io.StringIO(files["crosswalk/crosswalk.csv"])))
    assert set(supported_sources()) | {"openreview_page"} <= set(header)


def test_two_runs_write_the_same_bytes(files):
    assert {p.as_posix(): t for p, t in load_script().outputs().items()} == files


def test_lost_on_round_trip_is_what_test_roundtrip_lists(files):
    folder_system = {"journal": "journal_narrative", "openreview_v2": "openreview"}
    expected = {
        (folder_system.get(fixture.split("/")[0], fixture.split("/")[0]), change[2:])
        for fixture, changes in LOSSES.items()
        for change in changes
        if change.startswith("- ")
    }
    lost = {
        (r["system"], r["source_field"])
        for r in rows(files["crosswalk/gaps.csv"])
        if r["kind"] == "lost_on_roundtrip"
    }
    assert lost == expected


# What the README says each mapper does


def test_openreview_saved_page_summary_and_questions(long_rows):
    assert sources(long_rows, "openreview_page", "opinion.summary") == {"Summary"}
    assert sources(long_rows, "openreview_page", "findings.questions[]") == {"Questions"}


def test_reviewer3_overview_and_comments(long_rows):
    assert "overview[].text" in sources(long_rows, "reviewer3", "work_summary.contributions[].text")
    assert "comments[].text" in sources(long_rows, "reviewer3", "findings.comments[].text")
    assert not any(
        r["system"] == "reviewer3" and r["ocrs_path"] == "findings.comments[].severity"
        for r in long_rows
    )


def test_deepreview_potential_issues_become_weaknesses(long_rows):
    # Potential Issues And Suggestions is parsed as `issues`, each point an item of a tier
    assert "issues[].tiers[].items[].text" in sources(
        long_rows, "deepreview", "findings.weaknesses[].text"
    )


def test_jats_fills_the_review_doi(long_rows):
    # JATS keeps no mapping record, so the crosswalk can say only that the field is filled
    jats = [
        r for r in long_rows if r["system"] == "jats" and r["ocrs_path"] == "provenance.review_doi"
    ]
    assert [r["method"] for r in jats] == ["observed"]
