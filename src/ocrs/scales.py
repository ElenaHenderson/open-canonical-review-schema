# Copyright (c) 2026 Valency Systems Inc.
# SPDX-License-Identifier: MIT
"""Scale configurations and transformations for different review systems.

This module provides:
1. Standard scale definitions for common review systems
2. Score transformation functions to convert between scales
3. Text-to-numeric mappings for labeled scores (e.g., "3. Weak Accept" -> 3)

The canonical OCRS scale uses normalized values in [0, 1] where:
- 0 = lowest/worst
- 1 = highest/best

All system-specific scales are transformed to this canonical range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Scale Definitions
# =============================================================================


@dataclass
class ScaleDefinition:
    """Definition of a scoring scale used by a review system.

    Attributes:
        min_value: Minimum possible score
        max_value: Maximum possible score
        step: Step size (1 for integers, smaller for decimals)
        anchors: Mapping of numeric values to text labels
        description: Human-readable description
        higher_is_better: Whether higher scores are better (default True)
    """

    min_value: int | float
    max_value: int | float
    step: int | float = 1
    anchors: dict[int | float, str] = field(default_factory=dict)
    description: str = ""
    higher_is_better: bool = True

    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON schema scale format."""
        result: dict[str, Any] = {
            "type": "ordinal",
            "min": self.min_value,
            "max": self.max_value,
        }
        if self.step != 1:
            result["step"] = self.step
        if self.anchors:
            result["anchors"] = [
                {"value": v, "label": label} for v, label in sorted(self.anchors.items())
            ]
        if self.description:
            result["description"] = self.description
        return result

    def normalize(self, value: int | float) -> float:
        """Normalize a value to [0, 1] range.

        Uses linear interpolation: (value - min) / (max - min)
        If higher_is_better is False, the result is inverted.
        """
        if self.max_value == self.min_value:
            return 0.5
        normalized = (float(value) - self.min_value) / (self.max_value - self.min_value)
        normalized = max(0.0, min(1.0, normalized))
        if not self.higher_is_better:
            normalized = 1.0 - normalized
        return normalized

    def denormalize(self, normalized: float) -> float:
        """Convert normalized [0, 1] value back to this scale."""
        if not self.higher_is_better:
            normalized = 1.0 - normalized
        return self.min_value + normalized * (self.max_value - self.min_value)

    def transform_to(self, value: int | float, target_scale: ScaleDefinition) -> float:
        """Transform a value from this scale to another scale."""
        normalized = self.normalize(value)
        return target_scale.denormalize(normalized)


# =============================================================================
# Standard Scales
# =============================================================================

# OCRS Canonical 1-10 scale (recommended for unified representation)
CANONICAL_SCALE_1_10 = ScaleDefinition(
    min_value=1,
    max_value=10,
    anchors={
        1: "Strong Reject",
        2: "Reject",
        3: "Weak Reject",
        4: "Weak Reject",
        5: "Borderline",
        6: "Weak Accept",
        7: "Accept",
        8: "Accept",
        9: "Strong Accept",
        10: "Strong Accept",
    },
    description="OCRS canonical 1-10 scale",
)

# OCRS Canonical 1-5 scale (alternative)
CANONICAL_SCALE_1_5 = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Reject",
        2: "Weak Reject",
        3: "Borderline",
        4: "Weak Accept",
        5: "Accept",
    },
    description="OCRS canonical 1-5 scale",
)


# =============================================================================
# HotCRP Scales
# =============================================================================

HOTCRP_OVERALL_MERIT_1_5 = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Reject",
        2: "Weak Reject",
        3: "Weak Accept",
        4: "Accept",
        5: "Strong Accept",
    },
    description="HotCRP overall merit (1-5 scale)",
)

HOTCRP_OVERALL_MERIT_1_6 = ScaleDefinition(
    min_value=1,
    max_value=6,
    anchors={
        1: "Strong Reject",
        2: "Reject",
        3: "Weak Reject",
        4: "Weak Accept",
        5: "Accept",
        6: "Strong Accept",
    },
    description="HotCRP overall merit (1-6 scale)",
)

HOTCRP_EXPERTISE_1_5 = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "No familiarity",
        2: "Some familiarity",
        3: "Knowledgeable",
        4: "Expert",
        5: "Leading expert",
    },
    description="HotCRP reviewer expertise",
)

HOTCRP_CONFIDENCE_1_5 = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Low",
        2: "Somewhat confident",
        3: "Confident",
        4: "Very confident",
        5: "Certain",
    },
    description="HotCRP reviewer confidence",
)


# =============================================================================
# OpenReview Scales
# =============================================================================

OPENREVIEW_RATING_1_10 = ScaleDefinition(
    min_value=1,
    max_value=10,
    anchors={
        1: "Strong Reject",
        2: "Reject",
        3: "Reject",
        4: "Weak Reject",
        5: "Borderline Reject",
        6: "Weak Accept",
        7: "Accept",
        8: "Accept",
        9: "Strong Accept",
        10: "Top Submission",
    },
    description="OpenReview paper rating (1-10 scale)",
)

OPENREVIEW_CONFIDENCE_1_5 = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Your assessment is an educated guess",
        2: "Willing to defend your evaluation, but some doubts",
        3: "Fairly confident in your assessment",
        4: "Confident but not absolutely certain",
        5: "Absolutely certain",
    },
    description="OpenReview reviewer confidence",
)


# =============================================================================
# Editorial Manager / ScholarOne Recommendation Scales
# =============================================================================

EDITORIAL_MANAGER_RECOMMENDATION = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Accept",
        2: "Minor Revision",
        3: "Major Revision",
        4: "Reject",
        5: "Reject and Encourage Resubmission",
    },
    higher_is_better=False,  # Lower code = better recommendation
    description="Editorial Manager recommendation codes",
)

SCHOLARONE_RECOMMENDATION = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Accept",
        2: "Minor Revision",
        3: "Major Revision",
        4: "Reject",
        5: "Reject with option to resubmit",
    },
    higher_is_better=False,  # Lower code = better recommendation
    description="ScholarOne recommendation codes",
)

# Generic quality rating scale (common for EM/S1 criteria)
GENERIC_QUALITY_1_5 = ScaleDefinition(
    min_value=1,
    max_value=5,
    anchors={
        1: "Poor",
        2: "Fair",
        3: "Good",
        4: "Very Good",
        5: "Excellent",
    },
    description="Generic 1-5 quality scale",
)

GENERIC_QUALITY_1_10 = ScaleDefinition(
    min_value=1,
    max_value=10,
    anchors={
        1: "Unacceptable",
        2: "Poor",
        3: "Below Average",
        4: "Fair",
        5: "Adequate",
        6: "Good",
        7: "Very Good",
        8: "Excellent",
        9: "Outstanding",
        10: "Exceptional",
    },
    description="Generic 1-10 quality scale",
)


# =============================================================================
# System Scale Registry
# =============================================================================

# Map of system names to their default scales for different metric types
SYSTEM_SCALES: dict[str, dict[str, ScaleDefinition]] = {
    "hotcrp": {
        "overall_merit": HOTCRP_OVERALL_MERIT_1_5,
        "overall": HOTCRP_OVERALL_MERIT_1_5,
        "rating": HOTCRP_OVERALL_MERIT_1_5,
        "expertise": HOTCRP_EXPERTISE_1_5,
        "confidence": HOTCRP_CONFIDENCE_1_5,
        "novelty": GENERIC_QUALITY_1_5,
        "quality": GENERIC_QUALITY_1_5,
        "presentation": GENERIC_QUALITY_1_5,
        "default": GENERIC_QUALITY_1_5,
    },
    "openreview": {
        "rating": OPENREVIEW_RATING_1_10,
        "overall": OPENREVIEW_RATING_1_10,
        "confidence": OPENREVIEW_CONFIDENCE_1_5,
        "soundness": GENERIC_QUALITY_1_5,
        "presentation": GENERIC_QUALITY_1_5,
        "contribution": GENERIC_QUALITY_1_5,
        "default": GENERIC_QUALITY_1_5,
    },
    "editorialmanager": {
        "recommendation": EDITORIAL_MANAGER_RECOMMENDATION,
        "default": GENERIC_QUALITY_1_5,
    },
    "scholarone": {
        "recommendation": SCHOLARONE_RECOMMENDATION,
        "default": GENERIC_QUALITY_1_5,
    },
}


def get_scale_for_system(
    system: str,
    metric_type: str,
    *,
    fallback_min: int = 1,
    fallback_max: int = 5,
) -> ScaleDefinition:
    """Get the appropriate scale definition for a system and metric type.

    Args:
        system: Review system name (e.g., "hotcrp", "openreview")
        metric_type: Type of metric (e.g., "overall", "confidence")
        fallback_min: Minimum value for fallback scale
        fallback_max: Maximum value for fallback scale

    Returns:
        ScaleDefinition for the specified system and metric type
    """
    system_lower = system.lower()
    metric_lower = metric_type.lower().replace(" ", "_").replace("-", "_")

    if system_lower in SYSTEM_SCALES:
        scales = SYSTEM_SCALES[system_lower]
        if metric_lower in scales:
            return scales[metric_lower]
        if "default" in scales:
            return scales["default"]

    # Fallback to generic scale based on range
    if fallback_max <= 5:
        return ScaleDefinition(min_value=fallback_min, max_value=fallback_max)
    return ScaleDefinition(min_value=fallback_min, max_value=fallback_max)


# =============================================================================
# Recommendation Mapping
# =============================================================================

# Mapping from normalized values [0, 1] to recommendation strings
RECOMMENDATION_THRESHOLDS = [
    (0.9, "strong_accept"),
    (0.75, "accept"),
    (0.6, "weak_accept"),
    (0.5, "borderline"),
    (0.35, "weak_reject"),
    (0.2, "reject"),
    (0.0, "strong_reject"),
]


def normalized_to_recommendation(normalized: float) -> str:
    """Convert a normalized [0, 1] score to a recommendation string."""
    for threshold, rec in RECOMMENDATION_THRESHOLDS:
        if normalized >= threshold:
            return rec
    return "strong_reject"


def recommendation_to_normalized(recommendation: str) -> float:
    """Convert a recommendation string to approximate normalized value."""
    rec_values = {
        "strong_accept": 0.95,
        "accept": 0.80,
        "weak_accept": 0.65,
        "borderline": 0.50,
        "weak_reject": 0.35,
        "reject": 0.20,
        "strong_reject": 0.05,
        "major_revision": 0.40,
        "minor_revision": 0.60,
        "revise": 0.45,
    }
    return rec_values.get(recommendation.lower().replace(" ", "_"), 0.5)


# =============================================================================
# Scale Transformation Functions
# =============================================================================


def transform_score(
    value: int | float,
    source_scale: ScaleDefinition | None = None,
    target_scale: ScaleDefinition | None = None,
    *,
    source_min: int | float | None = None,
    source_max: int | float | None = None,
    target_min: int | float = 1,
    target_max: int | float = 10,
) -> float:
    """Transform a score from one scale to another.

    Args:
        value: The score to transform
        source_scale: Source ScaleDefinition (optional)
        target_scale: Target ScaleDefinition (optional)
        source_min: Source minimum (used if source_scale not provided)
        source_max: Source maximum (used if source_scale not provided)
        target_min: Target minimum (used if target_scale not provided)
        target_max: Target maximum (used if target_scale not provided)

    Returns:
        Transformed score in target scale
    """
    # Build source scale if not provided
    if source_scale is None:
        if source_min is None or source_max is None:
            raise ValueError("Must provide source_scale or (source_min, source_max)")
        source_scale = ScaleDefinition(min_value=source_min, max_value=source_max)

    # Build target scale if not provided
    if target_scale is None:
        target_scale = ScaleDefinition(min_value=target_min, max_value=target_max)

    return source_scale.transform_to(value, target_scale)


def transform_to_canonical(
    value: int | float,
    source_min: int | float,
    source_max: int | float,
    *,
    canonical_max: int = 10,
) -> int:
    """Transform a score to the canonical OCRS scale.

    Args:
        value: The score to transform
        source_min: Source scale minimum
        source_max: Source scale maximum
        canonical_max: Target canonical scale maximum (default 10)

    Returns:
        Score on canonical 1-canonical_max scale (rounded to integer)
    """
    source = ScaleDefinition(min_value=source_min, max_value=source_max)
    target = CANONICAL_SCALE_1_10 if canonical_max == 10 else CANONICAL_SCALE_1_5
    transformed = source.transform_to(value, target)
    return max(1, min(canonical_max, round(transformed)))


def infer_scale_from_value(value: int | float) -> ScaleDefinition:
    """Infer the most likely scale from a single value.

    Heuristics:
    - Float in [0, 1] -> ratio scale
    - Integer 1-5 -> ordinal 1-5
    - Integer 1-10 or 1-6 -> ordinal with that range
    - Otherwise -> generic ordinal

    Args:
        value: A score value

    Returns:
        Inferred ScaleDefinition
    """
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return ScaleDefinition(min_value=0.0, max_value=1.0, step=0.01)
        # Float outside 0-1, guess based on magnitude
        if 0.0 <= value <= 5.0:
            return GENERIC_QUALITY_1_5
        if 0.0 <= value <= 10.0:
            return GENERIC_QUALITY_1_10

    if isinstance(value, int):
        if 1 <= value <= 5:
            return GENERIC_QUALITY_1_5
        if 1 <= value <= 6:
            return ScaleDefinition(min_value=1, max_value=6)
        if 1 <= value <= 10:
            return GENERIC_QUALITY_1_10

    # Fallback
    return ScaleDefinition(min_value=1, max_value=10)
