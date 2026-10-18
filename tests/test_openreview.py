# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenReview mapper."""

import datetime as dt
import json
from pathlib import Path

import pytest

from ocrs import map_from, map_to, validate_canonical
from ocrs.catalog import alias_map, load_catalog
from ocrs.mappers.openreview import _metric_key_for_label, to_openreview

FIXTURES = Path(__file__).parent / "fixtures" / "openreview"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    return json.loads((FIXTURES / name).read_text())


def note(content: dict, **fields) -> dict:
    """Build an OpenReview note with an ID and forum around a review form."""
    return {"id": "or_note_1", "forum": "or_forum_1", "content": content, **fields}


def metric(canon: dict, key: str) -> dict:
    """Return the canonical metric with the given key."""
    return next(m for m in canon["metrics"] if m["key"] == key)


# from_openreview: fixtures


def test_openreview_minimal():
    """Test minimal OpenReview review conversion."""
    canon = map_from("openreview", load_fixture("minimal_review.json"))

    assert canon["review_id"] == "or_min_1"
    assert canon["created_at"] == "2025-01-01T00:00:00Z"
    assert canon["provenance"]["source_review_id"] == "or_min_1"
    assert "raw_payload" not in canon["provenance"]
    assert canon["target"]["work_id"] == "internal_id:openreview_forum:abc123"
    assert canon["target"]["work_type"] == "preprint"
    assert canon["opinion"]["summary"] == "Interesting paper with some gaps."
    assert canon["decision"] == {"recommendation": "weak_accept"}
    assert metric(canon, "overall")["value"] == 6


def test_openreview_realistic():
    """Test realistic OpenReview review with ratings, findings and sub-scores."""
    payload = load_fixture("realistic_review.json")
    canon = map_from("openreview", payload, keep_raw=True)

    assert canon["provenance"]["raw_payload"] == payload
    assert canon["referee"]["referee_id"] == "~Reviewer_ABC1"
    assert canon["target"]["identifiers"]["internal_id"]["hyperlink"] == (
        "https://openreview.net/forum?id=xY9kL2mN3pQ"
    )
    assert canon["decision"]["recommendation"] == "accept"
    assert canon["decision"]["confidence"] == 0.75
    assert canon["narrative"]["detailed_review"].startswith("## Summary")
    assert len(canon["findings"]["strengths"]) == 4
    assert canon["findings"]["questions"][0]["text"] == (
        "Sensitivity to sparsity predictor architecture?"
    )
    # Sub-scores map to catalog metrics; text-only fields are not metrics
    by_label = {m["label"]: m for m in canon["metrics"]}
    assert by_label["soundness"]["key"] == "correctness"
    assert by_label["soundness"]["justification"] == "Good"
    assert by_label["presentation"]["key"] == "clarity"
    assert by_label["contribution"]["key"] == "novelty"
    assert by_label["reproducibility"]["aspect"] == "reproducibility"
    assert "ethics flag" not in by_label
    assert "title" not in by_label


# from_openreview: timestamps, IDs and referee


def test_openreview_created_at_prefers_tcdate():
    """Test that tcdate wins over the other OpenReview timestamps."""
    canon = map_from("openreview", note({}, cdate=0, tcdate=1735689600000))
    assert canon["created_at"] == "2025-01-01T00:00:00Z"


def test_openreview_created_at_from_mdate():
    """Test that mdate is used when it is the only integer timestamp."""
    canon = map_from("openreview", note({}, cdate="2024-01-01", mdate=1735689600000))
    assert canon["created_at"] == "2025-01-01T00:00:00Z"


def test_openreview_created_at_defaults_to_now():
    """Test that a note without timestamps gets the import time."""
    before = dt.datetime.now(tz=dt.UTC)
    canon = map_from("openreview", note({}))
    created = dt.datetime.fromisoformat(canon["created_at"].replace("Z", "+00:00"))
    assert created >= before.replace(microsecond=0)


def test_openreview_review_id_generated_without_note_id():
    """Test that a note without a string ID gets a generated review ID."""
    canon = map_from("openreview", {"id": 17, "forum": "f1", "content": {}})
    assert isinstance(canon["review_id"], str) and len(canon["review_id"]) == 36
    assert "source_review_id" not in canon["provenance"]


def test_openreview_non_string_signature_is_ignored():
    """Test that a signature that is not a string does not become the referee ID."""
    canon = map_from("openreview", note({}, signatures=[{"id": "~Reviewer1"}]))
    assert "referee_id" not in canon["referee"]
    canon = map_from("openreview", note({}, signatures=[]))
    assert "referee_id" not in canon["referee"]


# from_openreview: target identifiers


def test_openreview_doi_identifier():
    """Test that a valid DOI in the review form becomes the primary identifier."""
    canon = map_from("openreview", note({"doi": "10.1234/abc.2024"}))
    identifiers = canon["target"]["identifiers"]
    assert identifiers["doi"] == {
        "value": "10.1234/abc.2024",
        "hyperlink": "https://doi.org/10.1234/abc.2024",
    }
    assert identifiers["internal_id"]["value"] == "or_forum_1"
    assert canon["target"]["work_id"] == "doi:10.1234/abc.2024"


def test_openreview_invalid_doi_is_dropped():
    """Test that a DOI that does not match the DOI pattern is ignored."""
    canon = map_from("openreview", note({"doi": "not-a-doi"}))
    assert "doi" not in canon["target"]["identifiers"]
    assert canon["target"]["work_id"] == "internal_id:openreview_forum:or_forum_1"


def test_openreview_arxiv_identifier_from_url():
    """Test that an arXiv abs URL is reduced to its ID."""
    canon = map_from("openreview", {"content": {"arxiv": "https://arxiv.org/abs/2401.12345v2"}})
    identifiers = canon["target"]["identifiers"]
    assert identifiers["arxiv_id"] == {
        "value": "2401.12345v2",
        "hyperlink": "https://arxiv.org/abs/2401.12345v2",
    }
    assert canon["target"]["work_id"] == "arxiv_id:2401.12345v2"


def test_openreview_arxiv_identifier_skips_invalid_keys():
    """Test that an invalid arXiv value falls through to the next arXiv key."""
    canon = map_from(
        "openreview",
        note({"arxiv_id": "not an id", "arXiv": "http://arxiv.org/abs/hep-th/9901001"}),
    )
    assert canon["target"]["identifiers"]["arxiv_id"]["value"] == "hep-th/9901001"


def test_openreview_internal_id_falls_back_to_note_id():
    """Test that the note ID is the internal ID when the note has no forum."""
    canon = map_from("openreview", {"id": "note_9", "content": {}})
    assert canon["target"]["identifiers"]["internal_id"] == {
        "field_name": "openreview_note",
        "value": "note_9",
        "hyperlink": "https://openreview.net/forum?id=note_9",
    }
    assert canon["target"]["work_id"] == "internal_id:openreview_note:note_9"


def test_openreview_internal_id_falls_back_to_form_paper_id():
    """Test that a paper ID in the review form is used when the note has no IDs."""
    canon = map_from("openreview", {"content": {"paper_id": "", "submission_id": "S-7"}})
    assert canon["target"]["identifiers"]["internal_id"] == {
        "field_name": "submission_id",
        "value": "S-7",
    }
    assert canon["target"]["work_id"] == "internal_id:submission_id:S-7"


def test_openreview_no_identifiers():
    """Test that a note with no identifiers at all has an unknown work ID."""
    canon = map_from("openreview", {"content": {"summary": "Fine."}})
    assert canon["target"]["identifiers"] == {}
    assert canon["target"]["work_id"] == "unknown"


def test_openreview_target_version():
    """Test that a version string in the review form is trimmed onto the target."""
    canon = map_from("openreview", note({"version": "  v2 "}))
    assert canon["target"]["version"] == "v2"
    canon = map_from("openreview", note({"version": "   "}))
    assert "version" not in canon["target"]


# from_openreview: opinion, narrative and findings


def test_openreview_opinion_skips_blank_summary():
    """Test that a blank summary falls through to the next summary field."""
    canon = map_from("openreview", note({"summary": "  ", "paper_summary": " A solid paper. "}))
    assert canon["opinion"]["summary"] == "A solid paper."
    assert "narrative" not in canon


def test_openreview_opinion_from_first_review_paragraph():
    """Test that the opinion falls back to the first paragraph of the review."""
    review = "First paragraph of the review.\n\nSecond paragraph."
    canon = map_from("openreview", note({"main_review": review}))
    assert canon["opinion"]["summary"] == "First paragraph of the review."
    assert canon["narrative"] == {"detailed_review": review}


def test_openreview_opinion_without_text():
    """Test the opinion placeholder when the review form has no text."""
    canon = map_from("openreview", note({"rating": 5}))
    assert canon["opinion"]["summary"] == "No summary provided."
    assert "narrative" not in canon
    assert "findings" not in canon


def test_openreview_narrative_keeps_first_detailed_review():
    """Test that the first non-empty detailed review source wins."""
    canon = map_from(
        "openreview",
        note(
            {
                "review": "  ",
                "comments": "From comments.",
                "detailed_review": "From detailed_review.",
                "confidential_to_chairs": " For the chairs. ",
                "author_questions": "Why this baseline?",
            }
        ),
    )
    assert canon["narrative"] == {
        "detailed_review": "From comments.",
        "confidential_to_editors": "For the chairs.",
        "author_questions": "Why this baseline?",
    }


def test_openreview_findings_from_bulleted_text():
    """Test that newline-separated findings become one item per bullet."""
    canon = map_from(
        "openreview",
        note({"strengths": "- Clear writing\n* Strong baselines\n\n", "weaknesses": "  "}),
    )
    assert canon["findings"] == {
        "strengths": [{"text": "Clear writing"}, {"text": "Strong baselines"}]
    }


def test_openreview_findings_skip_blank_list_items():
    """Test that blank list items are dropped, and an all-blank list is omitted."""
    canon = map_from(
        "openreview",
        note({"weaknesses": ["", "  "], "questions": ["Why?", " ", 3]}),
    )
    assert canon["findings"] == {"questions": [{"text": "Why?"}, {"text": "3"}]}


# from_openreview: decision and metrics


def test_openreview_decision_from_text():
    """Test that a text-only decision maps to a recommendation without a metric."""
    canon = map_from("openreview", note({"decision": "Reject"}))
    assert canon["decision"] == {"recommendation": "reject"}
    assert canon["metrics"] == []


def test_openreview_unrecognized_text_recommendation_is_borderline():
    """Test that unmapped recommendation text defaults to borderline."""
    canon = map_from("openreview", note({"recommendation": "Not sure"}))
    assert canon["decision"] == {"recommendation": "borderline"}


def test_openreview_revision_recommendation_is_a_revision_requirement():
    """Test that a revision recommendation becomes a revision requirement."""
    canon = map_from("openreview", note({"overallEvaluation": "Minor revision"}))
    assert canon["decision"] == {"revision_requirement": "minor"}


def test_openreview_numeric_recommendation_falls_back_to_text():
    """Test that text after an out-of-rubric number decides the recommendation."""
    canon = map_from("openreview", note({"overall_rating": "15: strong accept"}))
    assert canon["decision"]["recommendation"] == "strong_accept"
    overall = next(m for m in canon["metrics"] if m["label"] == "Overall Assessment")
    assert overall["value"] == 15
    assert overall["scale"] == {"type": "interval"}
    assert "normalized" not in overall


def test_openreview_numeric_recommendation_without_mapping_is_borderline():
    """Test that an unmappable bare number defaults to borderline."""
    canon = map_from("openreview", note({"overall": 0.8}))
    assert canon["decision"]["recommendation"] == "borderline"
    overall = next(m for m in canon["metrics"] if m["label"] == "Overall Assessment")
    assert overall["normalized"] == {"value_0_1": 0.8, "method": "linear_to_unit_interval"}


def test_openreview_non_text_recommendation_is_ignored():
    """Test that a recommendation that is neither a number nor text adds no decision."""
    canon = map_from("openreview", note({"recommendation": ["Accept"]}))
    assert "decision" not in canon
    assert canon["metrics"] == []


def test_openreview_reviewer_confidence():
    """Test that reviewer_confidence becomes a metric and the decision confidence."""
    canon = map_from("openreview", note({"rating": 8, "reviewer_confidence": "3: fair"}))
    assert canon["decision"] == {"recommendation": "accept", "confidence": 0.5}
    assert metric(canon, "confidence")["scale"] == {"type": "ordinal", "min": 1, "max": 5}
    assert metric(canon, "overall")["normalized"]["value_0_1"] == 7 / 9


def test_openreview_non_numeric_confidence_is_ignored():
    """Test that text-only confidence adds neither a metric nor a decision."""
    canon = map_from("openreview", note({"confidence": "very high"}))
    assert canon["metrics"] == []
    assert "decision" not in canon


def test_openreview_unbounded_confidence_has_no_decision_confidence():
    """Test that confidence on an unknown scale is kept only as a raw metric."""
    canon = map_from("openreview", note({"rating": "4", "confidence": 50}))
    assert canon["decision"] == {"recommendation": "weak_accept"}
    conf = metric(canon, "confidence")
    assert conf["value"] == 50
    assert "normalized" not in conf


def test_openreview_extra_metrics():
    """Test that other numeric form fields map to catalog or 'other' metrics."""
    canon = map_from(
        "openreview",
        note(
            {
                "novelty": 4,
                "technical_soundness": "2: fair",
                "word_count": 1200,
                "ethics_flag": "No",
            }
        ),
    )
    by_label = {m["label"]: m for m in canon["metrics"]}
    # exact catalog key
    assert by_label["novelty"]["key"] == "novelty"
    assert by_label["novelty"]["normalized"]["value_0_1"] == 0.75
    # alias contained in the label
    assert by_label["technical soundness"]["key"] == "correctness"
    assert by_label["technical soundness"]["justification"] == "fair"
    # no catalog match, and no bounds to normalize against
    assert by_label["word count"]["key"] == "other"
    assert by_label["word count"]["aspect"] == "other"
    assert "normalized" not in by_label["word count"]
    assert "ethics flag" not in by_label


def test_metric_key_for_empty_label():
    """Test that an empty label maps to the 'other' metric."""
    assert _metric_key_for_label("", {"clarity": "clarity"}, {}) == ("other", "other")


def test_metric_key_for_exact_key_returns_catalog_aspect():
    """Test that an exact catalog key returns the catalog aspect."""
    idx = {"novelty": {"key": "novelty", "aspect": "novelty"}}
    assert _metric_key_for_label("Novelty", {}, idx) == ("novelty", "novelty")


# to_openreview


def canonical(**fields) -> dict:
    """Build a minimal valid canonical review, overriding top-level fields."""
    canon = {
        "review_id": "rev_1",
        "version": "1.0.0",
        "created_at": "2025-01-01T00:00:00Z",
        "provenance": {
            "source_system": "openreview",
            "imported_at": "2025-01-01T00:00:00Z",
            "mapping": {
                "mapping_spec_id": "canonical-review.mapping.v1",
                "mapping_spec_version": "1.1.0",
                "mapper_version": "0.1.0",
            },
        },
        "referee": {"referee_type": "human", "identity_mode": "confidential"},
        "target": {"work_id": "internal_id:openreview_forum:F1", "work_type": "preprint"},
        "opinion": {"summary": "Good paper."},
    }
    canon.update(fields)
    validate_canonical(canon)
    return canon


def canonical_metric(key: str, value: int) -> dict:
    """Build a canonical metric on a 1-10 scale."""
    scale = {"type": "ordinal", "min": 1, "max": 10}
    return {"key": key, "label": key, "aspect": key, "scale": scale, "value": value}


def test_to_openreview_full():
    """Test mapping a canonical review with every mapped field to a note."""
    canon = canonical(
        referee={
            "referee_type": "human",
            "identity_mode": "confidential",
            "referee_id": "~Reviewer_One1",
        },
        opinion={"summary": "Good paper.", "text": "Opinion text."},
        narrative={
            "detailed_review": "Detailed review.",
            "confidential_to_editors": "For the chairs.",
        },
        findings={
            "strengths": [{"text": "Clear"}, {"text": ""}],
            "weaknesses": [],
        },
        decision={"recommendation": "weak_accept"},
        metrics=[
            canonical_metric("overall", 6),
            canonical_metric("confidence", 4),
            canonical_metric("novelty", 3),
            canonical_metric("novelty", 1),
        ],
    )
    # a metric without a value is not written back
    canon["metrics"].append({"key": "clarity", "label": "clarity", "value": None})
    out = to_openreview(canon)

    assert out["id"] == "rev_1"
    assert out["forum"] == "F1"
    assert out["signatures"] == ["~Reviewer_One1"]
    assert out["content"] == {
        "summary": "Good paper.",
        # opinion.text wins over narrative.detailed_review
        "review": "Opinion text.",
        "confidential_comments": "For the chairs.",
        "strengths": ["Clear"],
        "recommendation": "Weak Accept",
        "rating": 6,
        "confidence": 4,
        # the first metric with a key wins
        "novelty": 3,
    }


def test_to_openreview_detailed_review_without_opinion_text():
    """Test that narrative.detailed_review is the review when there is no opinion text."""
    canon = canonical(narrative={"detailed_review": "Detailed review."})
    out = to_openreview(canon)
    assert out["content"]["review"] == "Detailed review."
    assert "recommendation" not in out["content"]
    assert out["signatures"] == []


def test_to_openreview_opinion_text_without_summary():
    """Test that opinion text alone is written as the review."""
    canon = canonical()
    canon["opinion"] = {"text": "Opinion text."}
    assert to_openreview(canon)["content"] == {"review": "Opinion text."}


def test_to_openreview_revision_requirement():
    """Test that a revision requirement is written as the recommendation."""
    canon = canonical(decision={"revision_requirement": "major"})
    assert to_openreview(canon)["content"]["recommendation"] == "Major Revision"


def test_to_openreview_skips_malformed_metrics_and_findings():
    """Test that non-dict metrics and findings, and metrics without a key, are skipped."""
    canon = canonical()
    canon["metrics"] = ["not a metric", {"value": 3}, {"key": "rigor", "value": 2}]
    canon["findings"] = {"questions": ["not a finding", {"text": "Why?"}]}
    content = to_openreview(canon)["content"]
    assert content == {"summary": "Good paper.", "questions": ["Why?"], "rigor": 2}


def test_to_openreview_unknown_work_id():
    """Test that an unknown work ID maps to no forum."""
    canon = canonical(target={"work_id": "unknown", "work_type": "preprint"})
    assert to_openreview(canon)["forum"] is None


def test_openreview_realistic_round_trip():
    """Test that the realistic fixture keeps its decision and findings through a round trip."""
    canon = map_from("openreview", load_fixture("realistic_review.json"))
    note2 = map_to("openreview", canon)
    assert note2["forum"] == "xY9kL2mN3pQ"
    assert note2["content"]["recommendation"] == "Accept"
    assert note2["content"]["rating"] == 7

    canon2 = map_from("openreview", note2)
    assert canon2["decision"] == canon["decision"]
    assert canon2["findings"] == canon["findings"]
    assert canon2["target"]["work_id"] == canon["target"]["work_id"]
    assert canon2["referee"]["referee_id"] == "~Reviewer_ABC1"


def test_openreview_identifiers_are_not_scores():
    content = {
        "doi": "10.1234/abc",
        "arxiv_id": "2401.12345",
        "version": "2",
        "paper_id": "123",
        "soundness": "3: good",
    }
    canon = map_from("openreview", note(content))
    assert [m["label"] for m in canon["metrics"]] == ["soundness"]


def test_openreview_a_null_recommendation_does_not_hide_the_rating():
    canon = map_from("openreview", note({"recommendation": None, "rating": "6: Weak Accept"}))
    assert canon["decision"]["recommendation"] == "weak_accept"
    assert [m["value"] for m in canon["metrics"] if m["key"] == "overall"] == [6]


def test_openreview_overall_rating_is_one_metric():
    canon = map_from("openreview", note({"overall_rating": "6: ok"}))
    assert [m["key"] for m in canon["metrics"]] == ["overall"]


def test_openreview_a_bare_bullet_is_no_finding():
    canon = map_from("openreview", note({"summary": "S.", "strengths": "-\n- ok\n*"}))
    assert canon["findings"]["strengths"] == [{"text": "ok"}]


def test_openreview_the_label_wins_over_the_number():
    """As in CMT and HotCRP, the reviewer's words come before the number."""
    canon = map_from("openreview", note({"recommendation": "3: Strong Accept"}))
    assert canon["decision"]["recommendation"] == "strong_accept"


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("ab", "other"),
        ("quality", "other"),
        ("presentation", "clarity"),
        ("Soundness score", "correctness"),
    ],
)
def test_metric_key_matches_whole_words_of_one_metric(label, key):
    catalog = load_catalog()
    idx = {m["key"].casefold(): m for m in catalog["metrics"]}
    assert _metric_key_for_label(label, alias_map(catalog), idx)[0] == key


def test_openreview_numeric_overall_rating_beside_a_text_recommendation_is_kept():
    canon = map_from("openreview", note({"recommendation": "Accept", "overall_rating": 8}))
    assert canon["decision"]["recommendation"] == "accept"
    assert [(m["key"], m["value"]) for m in canon["metrics"]] == [("overall", 8)]


def test_openreview_a_second_overall_score_is_not_a_second_metric():
    canon = map_from("openreview", note({"rating": 6, "overall": 7}))
    assert [(m["key"], m["value"]) for m in canon["metrics"]] == [("overall", 6)]


def test_openreview_numeric_rating_beside_a_text_recommendation_is_kept():
    canon = map_from("openreview", note({"recommendation": "Accept", "rating": 8}))
    assert canon["decision"]["recommendation"] == "accept"
    assert [(m["key"], m["value"]) for m in canon["metrics"]] == [("overall", 8)]
    again = map_from("openreview", map_to("openreview", canon))
    assert [(m["key"], m["value"]) for m in again["metrics"]] == [("overall", 8)]


def test_openreview_other_recommendation_fields_are_the_overall_score():
    canon = map_from("openreview", note({"recommendation": "Accept", "overallEvaluation": 8}))
    assert [(m["key"], m["value"]) for m in canon["metrics"]] == [("overall", 8)]
    canon = map_from("openreview", note({"rating": 6, "overallEvaluation": 8}))
    assert [(m["key"], m["value"]) for m in canon["metrics"]] == [("overall", 6)]


@pytest.mark.parametrize(
    ("rating", "recommendation"),
    [
        ("2: Not acceptable", "reject"),
        ("2: Marginally acceptable", "weak_reject"),
        ("8: Clear accept", "accept"),
        ("9: Recommend acceptance", "accept"),
    ],
)
def test_openreview_recommendation_words_are_whole_words(rating, recommendation):
    canon = map_from("openreview", note({"rating": rating}))
    assert canon["decision"]["recommendation"] == recommendation


def test_openreview_a_negated_strong_accept_leaves_the_score_to_decide():
    canon = map_from("openreview", note({"rating": "6: Not a strong accept"}))
    assert canon["decision"]["recommendation"] == "weak_accept"


def test_openreview_a_stated_label_beside_a_negated_qualifier_is_kept():
    canon = map_from("openreview", note({"rating": "3: Weak accept (not a strong accept)"}))
    assert canon["decision"]["recommendation"] == "weak_accept"


def test_openreview_a_double_negative_leaves_the_score_to_decide():
    canon = map_from("openreview", note({"rating": "6: Not unacceptable"}))
    assert canon["decision"]["recommendation"] == "weak_accept"
