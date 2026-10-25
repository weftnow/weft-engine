"""Pure policies for disabled-by-default matching experiments."""

from __future__ import annotations

from typing import Any

SCREENING_VERSION = "f06-compact-screen-v1"
SCREENING_FIELDS = frozenset(
    {"summary", "goals", "offers", "desiredConnections", "background", "linkedinDetails"}
)


def screening_requires_full_evaluation(result: dict[str, Any], threshold: int) -> bool:
    """Only confident low screens may skip full evaluation; malformed screens escalate."""
    try:
        if result["uncertain"] or result["restriction_found"]:
            return True
        source_fields_a = set(result["source_fields_a"])
        source_fields_b = set(result["source_fields_b"])
        if not source_fields_a or not source_fields_b:
            return True
        if not source_fields_a <= SCREENING_FIELDS:
            return True
        if not source_fields_b <= SCREENING_FIELDS:
            return True
        score_a, score_b = int(result["score_a"]), int(result["score_b"])
        if not (0 <= score_a <= 100 and 0 <= score_b <= 100):
            return True
        return min(score_a, score_b) >= threshold
    except KeyError, TypeError, ValueError:
        return True
