# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the PAT and OpenAIReview mappers, their mapping records and gaps."""

import copy
import json
from pathlib import Path

import pytest

from ocrs import map_from, map_with_record, render_mapping_markdown, validate_canonical
from ocrs.anchors import Block, BlockKind, find_quote
from ocrs.mapping import MappingStatus, Rule

FIXTURES = Path(__file__).parent / "fixtures" / "ai"
PAT = json.loads((FIXTURES / "pat_review.json").read_text())
OPENAIREVIEW = json.loads((FIXTURES / "openaireview_paper.json").read_text())
BLOCKS = json.loads((FIXTURES / "paper_blocks.json").read_text())
RUN = {
    "review_id": "3152f8d9-a9e9-4d97-80be-e6b0d7290d42",
    "source_system": "valency",
    "requested_by": "valency",
    "work_id": "W_hvtukmgk",
    "work_version": "4b1c7e53-ef3c-4309-99ac-f0c599cbf194",
    "reviewer_commit": "4763efa4a819c0ffee0000000000000000000000",
    "model_id": "us.anthropic.claude-opus-5-5",
    "started_at": "2026-10-03T01:00:00Z",
    "ended_at": "2026-10-03T01:08:00Z",
    "cost_usd": 3.04,
}


def _payload(output):
    return {"output": copy.deepcopy(output), "run": RUN, "blocks": BLOCKS}


def _weaknesses(review):
    return review["findings"]["weaknesses"]


class TestPat:
    def test_maps_and_validates(self):
        result = map_with_record("pat", _payload(PAT))
        validate_canonical(result.review)
        assert result.record.status == MappingStatus.OK
        assert len(_weaknesses(result.review)) == len(PAT["issues"])

    def test_copies_issue_fields(self):
        finding = _weaknesses(map_from("pat", _payload(PAT)))[0]
        issue = PAT["issues"][0]
        assert finding["title"] == issue["title"]
        assert finding["text"] == issue["description"]
        assert finding["severity"] == issue["severity"]
        assert finding["tags"] == [issue["category"]]
        link = finding["evidence_links"][0]
        assert (link["ref"], link["quote"]) == (issue["location"], issue["evidence"])

    def test_records_where_each_quote_was_found(self):
        result = map_with_record("pat", _payload(PAT))
        links = [w["evidence_links"][0] for w in _weaknesses(result.review)]
        assert {link["type"] for link in links} == {"paper_section"}
        anchored = (Rule.ANCHORED_EXACT, Rule.ANCHORED_FUZZY)
        anchors = [step.result for step in result.record.steps if step.rule in anchored]
        assert [anchor["part"] for anchor in anchors] == ["body", "abstract", "body", "reference"]
        assert anchors[0]["block_id"] == "ci1nsfat1e"
        assert anchors[1]["block_id"] is None

    def test_run_details(self):
        review = map_from("pat", _payload(PAT))
        framework = review["referee"]["ai_referee"]["system"]["critic_framework"]
        assert framework == {
            "name": "pat",
            "version": "4763efa4a819",
            "commit": RUN["reviewer_commit"],
        }
        assert review["provenance"]["source_system"] == "valency"
        assert review["provenance"]["mapping"] == {
            "mapping_spec_id": "canonical-review.mapping.v1",
            "mapping_spec_version": "1.1.0",
            "mapper_version": "1.0.1",
        }
        assert review["target"]["version"] == RUN["work_version"]
        assert review["review_context"] == {"requested_by": "valency"}

    def test_unmapped_fields_kept_in_extensions(self):
        result = map_with_record("pat", _payload(PAT))
        kept = result.review["extensions"]["pat"]
        assert kept["issues"][0]["suggested_fix"] == PAT["issues"][0]["suggested_fix"]
        assert kept["dropped"] == PAT["dropped"]
        assert "reports" not in kept
        assert not {"title", "description"} & set(kept["issues"][0])
        unmapped = {field.path: field.count for field in result.record.gaps.unmapped}
        assert unmapped["issues[].suggested_fix"] == 4
        assert "issues[].title" not in unmapped

    def test_unknown_severity_is_coerced(self):
        output = copy.deepcopy(PAT)
        output["issues"][0]["severity"] = "high"
        result = map_with_record("pat", _payload(output))
        assert "severity" not in _weaknesses(result.review)[0]
        [coercion] = result.record.gaps.coerced
        assert (coercion.source, coercion.original, coercion.result) == (
            "issues[0].severity",
            "high",
            None,
        )

    def test_issue_without_description_is_skipped(self):
        output = copy.deepcopy(PAT)
        output["issues"][1]["description"] = ""
        result = map_with_record("pat", _payload(output))
        assert result.record.status == MappingStatus.PARTIAL
        assert [item.source for item in result.record.skipped] == ["issues[1]"]
        assert len(_weaknesses(result.review)) == len(PAT["issues"]) - 1


class TestOpenAIReview:
    def test_maps_merged_comments(self):
        result = map_with_record("openaireview", _payload(OPENAIREVIEW))
        validate_canonical(result.review)
        [method] = [m for k, m in OPENAIREVIEW["methods"].items() if k.startswith("progressive__")]
        weaknesses = _weaknesses(result.review)
        assert [w["title"] for w in weaknesses] == [c["title"] for c in method["comments"]]
        assert weaknesses[0]["text"] == method["comments"][0]["explanation"]
        assert weaknesses[0]["tags"] == [method["comments"][0]["comment_type"]]
        assert result.review["opinion"]["summary"] == method["overall_feedback"]

    def test_gaps(self):
        gaps = map_with_record("openaireview", _payload(OPENAIREVIEW)).record.gaps
        assert [quote.source.rsplit(".", 2)[-2] for quote in gaps.unanchored] == ["comments[1]"]
        unmapped = {field.path for field in gaps.unmapped}
        assert "methods.progressive__*.comments[].paragraph_index" in unmapped
        assert not any(path.startswith("paragraphs") for path in unmapped)
        assert not any("progressive_original" in path for path in unmapped)
        assert "findings.weaknesses[].severity" in gaps.unfilled


class TestRecord:
    def test_steps_name_rules(self):
        steps = map_with_record("pat", _payload(PAT)).record.steps
        rules = {(step.source, step.rule) for step in steps}
        assert ("issues[0].title", Rule.COPIED) in rules
        assert ("issues[0].severity", Rule.LOOKUP) in rules
        assert ("issues[2].evidence", Rule.ANCHORED_FUZZY) in rules

    def test_markdown(self):
        markdown = render_mapping_markdown(map_with_record("pat", _payload(PAT)))
        assert markdown.startswith("# pat review mapped to OCRS")
        assert "| Unanchored | 0 of 4 quotes |" in markdown
        assert "`issues[].suggested_fix`" in markdown
        assert "### `issues[0]` → `findings.weaknesses[0]`" in markdown


class TestFindQuote:
    blocks = [
        Block(id="b1", text="We train on **ten** datasets [ref-3](#ref-ref-3)."),
        Block(kind=BlockKind.ABSTRACT, text="A short abstract about citation sets."),
    ]

    def test_exact_after_normalising(self):
        match, _ = find_quote("we train on ten datasets.", self.blocks)
        assert match is not None and match.exact and match.block.id == "b1"

    def test_fuzzy(self):
        match, score = find_quote("A short abstract about the citation sets.", self.blocks)
        assert match is not None and not match.exact and score >= 0.9
        assert match.block.kind == BlockKind.ABSTRACT

    @pytest.mark.parametrize("quote", ["Something the paper never says at all.", ""])
    def test_not_found(self, quote):
        match, score = find_quote(quote, self.blocks)
        assert match is None and score < 0.9


def test_run_times_need_a_timezone():
    run = {**RUN, "started_at": "2026-10-03T01:00:00"}
    with pytest.raises(ValueError):
        map_with_record("pat", {"output": PAT, "run": run, "blocks": BLOCKS})
