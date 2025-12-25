import pytest
from canonreview import map_from, map_to, validate_canonical

def test_openreview_to_canonical_and_back():
    openreview_note = {
        "id": "or_review_1",
        "forum": "or_forum_123",
        "cdate": 1735689600000,  # 2025-01-01T00:00:00Z
        "signatures": ["~Reviewer_One1"],
        "content": {
            "rating": "6: Weak Accept",
            "confidence": "4: confident",
            "summary": "Interesting paper with some gaps.",
            "review": "The main idea is promising. However, the proof is missing key assumptions.\n\nMore detail here.",
            "soundness": 3,
            "clarity": 2,
            "strengths": ["Good motivation", "Solid empirical results"],
            "weaknesses": ["Proof incomplete"]
        }
    }
    canon = map_from("openreview", openreview_note, keep_raw=True)
    validate_canonical(canon)
    assert canon["provenance"]["source_system"] == "openreview"
    assert canon["opinion"]["summary"]
    note2 = map_to("openreview", canon)
    assert "content" in note2 and isinstance(note2["content"], dict)

def test_cmt_to_canonical_and_back():
    cmt = {
        "reviewId": "cmt_r1",
        "paperId": 42,
        "conferenceName": "NeurIPS 2026",
        "trackName": "Main",
        "reviewerId": "rev_77",
        "overallEvaluation": "7: Accept",
        "confidence": 0.8,
        "summary": "Strong contribution.",
        "commentsToAuthors": "Well-written and significant. Missing ablation."
    }
    canon = map_from("cmt", cmt)
    validate_canonical(canon)
    back = map_to("cmt", canon)
    assert back["reviewId"] == "cmt_r1"
    assert "commentsToAuthors" in back

def test_journal_narrative_minimal():
    j = {
        "doi": "10.5555/12345678",
        "journal": "Journal of Tests",
        "full_text": "This manuscript addresses an important problem. The methods are plausible but unclear.\n\nPlease clarify the assumptions."
    }
    canon = map_from("journal_narrative", j)
    validate_canonical(canon)
    assert canon["opinion"]["summary"]
    back = map_to("journal_narrative", canon)
    assert back["full_text"]
