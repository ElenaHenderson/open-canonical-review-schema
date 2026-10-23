# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""The crosswalk generator: what it writes, and that the crosswalk says what the README says."""

import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest
from test_real_reviews import LOSSES as REAL_LOSSES
from test_real_reviews import SOURCES
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


def test_lost_on_round_trip_is_what_the_round_trip_tests_list(files):
    folder_system = {"journal": "journal_narrative", "openreview_v2": "openreview"}
    real_system = {source["file"]: source["system"] for source in SOURCES}
    systems = {
        **{f: folder_system.get(f.split("/")[0], f.split("/")[0]) for f in LOSSES},
        **{f: real_system[f] for f in REAL_LOSSES},
    }
    expected = {
        (systems[fixture], change[2:])
        for fixture, changes in [*LOSSES.items(), *REAL_LOSSES.items()]
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


def test_a_step_that_fills_a_whole_item_leaves_its_leaves_observed(files, long_rows):
    # A saved page's steps fill whole metrics and narrative parts; the leaves they fill are
    # not blank, which would say no fixture fills them
    assert "Rating" in sources(long_rows, "openreview_page", "metrics[]")
    wide = {r["ocrs_path"]: r for r in rows(files["crosswalk/crosswalk.csv"])}
    for path in ("metrics[].value", "narrative[].content", "findings.strengths[].text"):
        assert wide[path]["openreview_page"] == "observed", path


def test_only_a_record_says_a_field_is_unmapped(files):
    gaps = rows(files["crosswalk/gaps.csv"])
    # JATS keeps the article's title to write it back, and maps it to target.title
    assert {"system": "jats", "kind": "kept_in_extensions", "source_field": "article.title"} in [
        {k: r[k] for k in ("system", "kind", "source_field")} for r in gaps
    ]
    assert not any(r["kind"] == "unmapped" and r["system"] in {"jats", "openreview"} for r in gaps)
    coverage = {r["system"]: r for r in rows(files["crosswalk/coverage.csv"])}
    assert coverage["jats"]["unmapped_source_fields"] == ""
    assert coverage["openaireview"]["unmapped_source_fields"] != ""


def test_the_source_archive_ships_the_crosswalk():
    # scripts/generate_docs.py publishes it, and the archive carries that script
    assert "graft crosswalk" in (ROOT / "MANIFEST.in").read_text().splitlines()
