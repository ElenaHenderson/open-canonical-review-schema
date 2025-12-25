# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Tests for scale transformations and score parsing."""

import pytest

from ocrs.scales import (
    EDITORIAL_MANAGER_RECOMMENDATION,
    HOTCRP_OVERALL_MERIT_1_5,
    OPENREVIEW_RATING_1_10,
    SCHOLARONE_RECOMMENDATION,
    ScaleDefinition,
    get_scale_for_system,
    infer_scale_from_value,
    normalized_to_recommendation,
    recommendation_to_normalized,
    transform_score,
    transform_to_canonical,
)
from ocrs.util import (
    build_metric_from_score,
    parse_labeled_score,
    score_to_recommendation,
)


class TestScaleDefinition:
    """Tests for ScaleDefinition class."""

    def test_normalize_basic(self):
        """Test basic normalization."""
        scale = ScaleDefinition(min_value=1, max_value=5)

        assert scale.normalize(1) == 0.0
        assert scale.normalize(5) == 1.0
        assert scale.normalize(3) == 0.5
        assert scale.normalize(4) == 0.75

    def test_normalize_1_10_scale(self):
        """Test normalization on 1-10 scale."""
        scale = ScaleDefinition(min_value=1, max_value=10)

        assert scale.normalize(1) == 0.0
        assert scale.normalize(10) == 1.0
        assert scale.normalize(5.5) == 0.5
        assert abs(scale.normalize(7) - 0.6666666666) < 0.01

    def test_normalize_higher_is_worse(self):
        """Test scales where lower is better."""
        # Recommendation codes: 1=accept, 5=reject
        scale = ScaleDefinition(min_value=1, max_value=5, higher_is_better=False)

        assert scale.normalize(1) == 1.0  # Best
        assert scale.normalize(5) == 0.0  # Worst
        assert scale.normalize(3) == 0.5

    def test_denormalize(self):
        """Test denormalization."""
        scale = ScaleDefinition(min_value=1, max_value=5)

        assert scale.denormalize(0.0) == 1.0
        assert scale.denormalize(1.0) == 5.0
        assert scale.denormalize(0.5) == 3.0

    def test_transform_between_scales(self):
        """Test transforming between different scales."""
        scale_1_5 = ScaleDefinition(min_value=1, max_value=5)
        scale_1_10 = ScaleDefinition(min_value=1, max_value=10)

        # 3 on 1-5 scale (middle) should become 5.5 on 1-10 scale
        transformed = scale_1_5.transform_to(3, scale_1_10)
        assert abs(transformed - 5.5) < 0.01

        # 10 on 1-10 should become 5 on 1-5
        back = scale_1_10.transform_to(10, scale_1_5)
        assert abs(back - 5.0) < 0.01

    def test_to_schema(self):
        """Test schema conversion."""
        scale = ScaleDefinition(
            min_value=1,
            max_value=5,
            anchors={1: "Poor", 5: "Excellent"},
            description="Quality scale",
        )
        schema = scale.to_schema()

        assert schema["type"] == "ordinal"
        assert schema["min"] == 1
        assert schema["max"] == 5
        assert len(schema["anchors"]) == 2
        assert schema["description"] == "Quality scale"


class TestSystemScales:
    """Tests for predefined system scales."""

    def test_hotcrp_overall_merit(self):
        """Test HotCRP overall merit scale."""
        scale = HOTCRP_OVERALL_MERIT_1_5

        assert scale.normalize(1) == 0.0  # Reject
        assert scale.normalize(5) == 1.0  # Strong Accept
        assert 4 in scale.anchors

    def test_openreview_rating(self):
        """Test OpenReview rating scale."""
        scale = OPENREVIEW_RATING_1_10

        assert scale.normalize(1) == 0.0
        assert scale.normalize(10) == 1.0
        assert scale.normalize(6) == pytest.approx(0.555, rel=0.01)

    def test_em_recommendation_inverted(self):
        """Test Editorial Manager recommendation (lower=better)."""
        scale = EDITORIAL_MANAGER_RECOMMENDATION

        # 1=Accept should be best
        assert scale.normalize(1) == 1.0
        # 4=Reject should be low
        assert scale.normalize(4) == pytest.approx(0.25, rel=0.01)

    def test_scholarone_recommendation_inverted(self):
        """Test ScholarOne recommendation (lower=better)."""
        scale = SCHOLARONE_RECOMMENDATION

        assert scale.normalize(1) == 1.0  # Accept
        assert scale.normalize(5) == 0.0  # Reject


class TestScaleLookup:
    """Tests for scale lookup functions."""

    def test_get_scale_for_hotcrp(self):
        """Test getting scale for HotCRP."""
        scale = get_scale_for_system("hotcrp", "overall_merit")
        assert scale.min_value == 1
        assert scale.max_value == 5

        scale = get_scale_for_system("hotcrp", "confidence")
        assert scale.min_value == 1
        assert scale.max_value == 5

    def test_get_scale_for_openreview(self):
        """Test getting scale for OpenReview."""
        scale = get_scale_for_system("openreview", "rating")
        assert scale.min_value == 1
        assert scale.max_value == 10

    def test_get_scale_fallback(self):
        """Test fallback scale for unknown system/metric."""
        scale = get_scale_for_system("unknown", "unknown", fallback_min=1, fallback_max=7)
        assert scale.min_value == 1
        assert scale.max_value == 7

    def test_infer_scale_from_value(self):
        """Test scale inference from values."""
        # Float in [0,1] -> ratio
        scale = infer_scale_from_value(0.75)
        assert scale.min_value == 0.0
        assert scale.max_value == 1.0

        # Integer 1-5 -> ordinal 1-5
        scale = infer_scale_from_value(3)
        assert scale.min_value == 1
        assert scale.max_value == 5

        # Integer 8 -> ordinal 1-10
        scale = infer_scale_from_value(8)
        assert scale.min_value == 1
        assert scale.max_value == 10


class TestRecommendationMapping:
    """Tests for recommendation string mapping."""

    def test_normalized_to_recommendation(self):
        """Test converting normalized score to recommendation."""
        assert normalized_to_recommendation(0.95) == "strong_accept"
        assert normalized_to_recommendation(0.80) == "accept"
        assert normalized_to_recommendation(0.65) == "weak_accept"
        assert normalized_to_recommendation(0.50) == "borderline"
        assert normalized_to_recommendation(0.35) == "weak_reject"
        assert normalized_to_recommendation(0.20) == "reject"
        assert normalized_to_recommendation(0.05) == "strong_reject"

    def test_recommendation_to_normalized(self):
        """Test converting recommendation to normalized value."""
        assert recommendation_to_normalized("strong_accept") == 0.95
        assert recommendation_to_normalized("accept") == 0.80
        assert recommendation_to_normalized("weak_accept") == 0.65
        assert recommendation_to_normalized("borderline") == 0.50
        assert recommendation_to_normalized("major_revision") == 0.40


class TestScoreTransformation:
    """Tests for score transformation functions."""

    def test_transform_score_with_scales(self):
        """Test score transformation with ScaleDefinition objects."""
        source = ScaleDefinition(min_value=1, max_value=5)
        target = ScaleDefinition(min_value=1, max_value=10)

        result = transform_score(4, source, target)
        # 4 on 1-5 is 0.75 normalized, which is 7.75 on 1-10
        assert abs(result - 7.75) < 0.01

    def test_transform_score_with_bounds(self):
        """Test score transformation with min/max bounds."""
        result = transform_score(
            4,
            source_min=1,
            source_max=5,
            target_min=1,
            target_max=10,
        )
        assert abs(result - 7.75) < 0.01

    def test_transform_to_canonical(self):
        """Test transformation to canonical scale."""
        # 4 on 1-5 scale should become 7 or 8 on canonical 1-10
        result = transform_to_canonical(4, source_min=1, source_max=5, canonical_max=10)
        assert result in (7, 8)

        # 10 on 1-10 should become 10 on canonical
        result = transform_to_canonical(10, source_min=1, source_max=10, canonical_max=10)
        assert result == 10


class TestLabeledScoreParsing:
    """Tests for parsing labeled scores like '3. Weak Accept'."""

    def test_parse_numeric_only(self):
        """Test parsing pure numeric values."""
        result = parse_labeled_score(4)
        assert result["numeric"] == 4
        assert result["label"] is None
        assert result["normalized"] is not None

    def test_parse_labeled_string(self):
        """Test parsing labeled strings."""
        result = parse_labeled_score("4. Accept")
        assert result["numeric"] == 4
        assert result["label"] == "Accept"
        assert result["normalized"] is not None

    def test_parse_colon_separator(self):
        """Test parsing with colon separator."""
        result = parse_labeled_score("3: Weak Accept")
        assert result["numeric"] == 3
        assert result["label"] == "Weak Accept"

    def test_parse_with_expected_scale(self):
        """Test parsing with explicit scale bounds."""
        result = parse_labeled_score(
            "8. Strong Accept",
            expected_min=1,
            expected_max=10,
        )
        assert result["numeric"] == 8
        assert result["normalized"] == pytest.approx(0.777, rel=0.01)

    def test_parse_with_system_scale(self):
        """Test parsing with system-specific scale."""
        result = parse_labeled_score(
            "4. Accept",
            system="hotcrp",
            metric_type="overall_merit",
        )
        assert result["numeric"] == 4
        assert result["normalized"] == 0.75  # (4-1)/(5-1)

    def test_parse_text_only(self):
        """Test parsing text-only values."""
        result = parse_labeled_score("Accept")
        assert result["numeric"] is None
        assert result["label"] == "Accept"
        assert result["normalized"] is None


class TestBuildMetricFromScore:
    """Tests for building canonical metrics from scores."""

    def test_build_from_numeric(self):
        """Test building metric from pure numeric value."""
        metric = build_metric_from_score(
            key="overall",
            label="Overall Merit",
            value=4,
            aspect="overall",
            expected_min=1,
            expected_max=5,
        )

        assert metric is not None
        assert metric["key"] == "overall"
        assert metric["value"] == 4  # Numeric
        assert metric["normalized"]["value_0_1"] == 0.75
        assert "justification" not in metric

    def test_build_from_labeled(self):
        """Test building metric from labeled score."""
        metric = build_metric_from_score(
            key="overall",
            label="Overall Merit",
            value="4. Accept",
            aspect="overall",
            expected_min=1,
            expected_max=5,
        )

        assert metric is not None
        assert metric["key"] == "overall"
        assert metric["value"] == 4  # Numeric, not string
        assert metric["justification"] == "Accept"
        assert metric["normalized"]["value_0_1"] == 0.75

    def test_build_returns_none_for_text_only(self):
        """Test that text-only values return None."""
        metric = build_metric_from_score(
            key="overall",
            label="Overall Merit",
            value="Accept",  # No numeric value
            aspect="overall",
        )

        assert metric is None


class TestScoreToRecommendation:
    """Tests for converting scores to recommendations."""

    def test_numeric_score_to_recommendation(self):
        """Test converting numeric score to recommendation."""
        rec = score_to_recommendation(4, scale_min=1, scale_max=5)
        assert rec in ("accept", "weak_accept")  # 0.75 normalized

        rec = score_to_recommendation(3, scale_min=1, scale_max=5)
        assert rec == "borderline"  # 0.5 normalized

    def test_labeled_score_to_recommendation(self):
        """Test converting labeled score to recommendation."""
        # Text label takes precedence
        rec = score_to_recommendation("3. Weak Accept", scale_min=1, scale_max=5)
        assert rec == "weak_accept"

        rec = score_to_recommendation("2. Reject", scale_min=1, scale_max=5)
        assert rec == "reject"

    def test_text_only_recommendation(self):
        """Test text-only recommendation parsing."""
        rec = score_to_recommendation("Accept", scale_min=1, scale_max=5)
        assert rec == "accept"

        rec = score_to_recommendation("Major Revision", scale_min=1, scale_max=5)
        assert rec == "major_revision"


class TestScaleTransformationExamples:
    """End-to-end examples of scale transformations."""

    def test_hotcrp_to_openreview_scale(self):
        """Test converting HotCRP 1-5 scores to OpenReview 1-10."""
        hotcrp_scale = HOTCRP_OVERALL_MERIT_1_5
        openreview_scale = OPENREVIEW_RATING_1_10

        # HotCRP 4 (Accept) should map to around 7-8 on OpenReview
        result = hotcrp_scale.transform_to(4, openreview_scale)
        assert 7.0 <= result <= 8.0

        # HotCRP 5 (Strong Accept) should map to 10
        result = hotcrp_scale.transform_to(5, openreview_scale)
        assert result == 10.0

        # HotCRP 1 (Reject) should map to 1
        result = hotcrp_scale.transform_to(1, openreview_scale)
        assert result == 1.0

    def test_different_scale_normalization(self):
        """Test that same conceptual score normalizes consistently."""
        # "Accept" on different scales should all normalize to similar values

        hotcrp_accept = HOTCRP_OVERALL_MERIT_1_5.normalize(4)  # 4. Accept
        openreview_accept = OPENREVIEW_RATING_1_10.normalize(7)  # 7: Accept

        # Both should be around 0.65-0.75
        assert 0.6 <= hotcrp_accept <= 0.8
        assert 0.6 <= openreview_accept <= 0.75

    def test_em_recommendation_normalization(self):
        """Test Editorial Manager recommendation code normalization."""
        em_scale = EDITORIAL_MANAGER_RECOMMENDATION

        # Code 1 = Accept = best = 1.0
        assert em_scale.normalize(1) == 1.0

        # Code 3 = Major Revision = middle
        assert 0.4 <= em_scale.normalize(3) <= 0.6

        # Code 4 = Reject = low
        assert em_scale.normalize(4) < 0.5
