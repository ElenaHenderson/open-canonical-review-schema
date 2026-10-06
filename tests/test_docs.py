# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""The examples in the README and CONTRIBUTING.md work as written.

Each Python block runs on its own. Blocks may use the inputs a reader brings
(`openreview_note`, `openaireview_paper_json`), which come from test fixtures.
Each JSON block is a whole review, or part of one that must validate when
added to a minimal review.
"""

import json
import re
from pathlib import Path

import pytest

from ocrs import validate_canonical
from ocrs.catalog import load_catalog

ROOT = Path(__file__).parent.parent
DOCS = ["README.md", "CONTRIBUTING.md"]
FIXTURES = ROOT / "tests" / "fixtures"
CODE_BLOCK = re.compile(r"^```(\w+)\n(.*?)^```", re.MULTILINE | re.DOTALL)
MINIMAL_REVIEW = {
    "review_id": "review-1",
    "version": "1.0.0",
    "created_at": "2026-10-06T12:00:00Z",
    "provenance": {"source_system": "example-journal"},
    "referee": {"referee_type": "human", "identity_mode": "double_blind"},
    "target": {"work_id": "paper-1", "work_type": "article"},
    "opinion": {"summary": "A sound paper."},
}


def code_blocks(language):
    blocks = []
    for doc in DOCS:
        text = (ROOT / doc).read_text()
        for match in CODE_BLOCK.finditer(text):
            if match.group(1) == language:
                line = text[: match.start()].count("\n") + 1
                blocks.append(pytest.param(match.group(2), id=f"{doc}:{line}"))
    return blocks


def reader_inputs():
    return {
        "openreview_note": json.loads(
            (FIXTURES / "openreview" / "realistic_review.json").read_text()
        ),
        "openaireview_paper_json": json.loads(
            (FIXTURES / "ai" / "openaireview_paper.json").read_text()
        ),
    }


@pytest.mark.parametrize("code", code_blocks("python"))
def test_python_example_runs(code):
    exec(compile(code, "<doc example>", "exec"), reader_inputs())


@pytest.mark.parametrize("text", code_blocks("json"))
def test_json_example_validates(text):
    example = json.loads(text)
    validate_canonical(example if "review_id" in example else {**MINIMAL_REVIEW, **example})


@pytest.mark.parametrize(
    "path", sorted((ROOT / "examples").glob("*.json")), ids=lambda path: path.name
)
def test_example_review_validates(path):
    validate_canonical(json.loads(path.read_text()))


@pytest.mark.parametrize(
    "path", sorted((ROOT / "examples").glob("*.json")), ids=lambda path: path.name
)
def test_example_metrics_use_catalog_keys(path):
    keys = {metric["key"] for metric in load_catalog()["metrics"]}
    for metric in json.loads(path.read_text()).get("metrics", []):
        assert metric["key"] in keys
