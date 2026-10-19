"""Evidence validation and capacity-aware matching selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from ortools.sat.python import cp_model

from src.matching.schemas import PairEvaluation

SHAREABLE_FIELDS = {
    "summary",
    "goals",
    "offers",
    "desiredConnections",
    "background",
    "linkedinDetails",
}
FIELD_MAP = {
    "desiredConnections": "desired_connections",
    "linkedinDetails": "linkedin_details",
}


def canonical_pair(first: UUID, second: UUID) -> tuple[str, str]:
    if first == second:
        raise ValueError("self_match")
    low, high = sorted((str(first).lower(), str(second).lower()))
    return low, high


def validate_evaluation(
    evaluation: PairEvaluation,
    guests: dict[str, dict[str, object]],
    blocked: set[tuple[str, str]],
    prohibited: set[tuple[str, str]],
) -> bool:
    try:
        low, high = canonical_pair(evaluation.guest_a_id, evaluation.guest_b_id)
    except ValueError:
        return False
    if (
        low not in guests
        or high not in guests
        or (low, high) in blocked
        or (low, high) in prohibited
    ):
        return False
    left, right = guests[low], guests[high]
    if left["networking_status"] != "included" or right["networking_status"] != "included":
        return False
    if bool(left["identity_resolution_required"]) or bool(right["identity_resolution_required"]):
        return False
    if evaluation.restriction_found or min(evaluation.score_a, evaluation.score_b) < 70:
        return False
    if not evaluation.benefit_a.strip() or not evaluation.benefit_b.strip():
        return False
    return evidence_is_grounded(evaluation, guests)


def evidence_is_grounded(evaluation: PairEvaluation, guests: dict[str, dict[str, object]]) -> bool:
    if not evaluation.evidence:
        return False
    low, high = canonical_pair(evaluation.guest_a_id, evaluation.guest_b_id)
    cited_guests: set[str] = set()
    for evidence in evaluation.evidence:
        guest = guests.get(str(evidence.guest_id).lower())
        if guest is None:
            return False
        field = FIELD_MAP.get(evidence.field, evidence.field)
        source = guest.get(field)
        if (
            not isinstance(source, str)
            or not evidence.quote.strip()
            or evidence.quote not in source
        ):
            return False
        cited_guests.add(str(evidence.guest_id).lower())
    return cited_guests == {low, high}


@dataclass(frozen=True)
class Candidate:
    guest_low_id: str
    guest_high_id: str
    pair_score: int


def select_capacity(
    candidates: list[Candidate],
    capacities: dict[str, int],
    target_guest_id: str | None = None,
    target_limit: int | None = None,
) -> tuple[list[Candidate], str]:
    """Maximize total qualifying scores with a secondary coverage term."""
    model = cp_model.CpModel()
    selected = [model.new_bool_var(f"pair_{index}") for index in range(len(candidates))]
    coverage_terms = []
    for guest_id, capacity in capacities.items():
        incident = [
            selected[index]
            for index, pair in enumerate(candidates)
            if guest_id in (pair.guest_low_id, pair.guest_high_id)
        ]
        if incident:
            model.add(sum(incident) <= max(0, capacity))
            covered = model.new_bool_var(f"covered_{guest_id}")
            model.add(covered <= sum(incident))
            for chosen in incident:
                model.add(covered >= chosen)
            coverage_terms.append(covered)
    if target_guest_id is not None and target_limit is not None:
        model.add(
            sum(
                selected[index]
                for index, pair in enumerate(candidates)
                if target_guest_id in (pair.guest_low_id, pair.guest_high_id)
            )
            <= target_limit
        )
    # A point of score outweighs the at-most-300 coverage tie-breaker.
    model.maximize(
        sum(selected[index] * pair.pair_score * 301 for index, pair in enumerate(candidates))
        + sum(coverage_terms)
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], solver.status_name(status).lower()
    output = [pair for index, pair in enumerate(candidates) if solver.value(selected[index])]
    output.sort(key=lambda pair: (-pair.pair_score, pair.guest_low_id, pair.guest_high_id))
    return output, solver.status_name(status).lower()


def token_set(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]{2,}", text.lower())
        if word not in {"with", "that", "from", "this", "have", "your"}
    }


def lexical_similarity(left: str, right: str) -> float:
    a, b = token_set(left), token_set(right)
    return len(a & b) / max(1, len(a | b))
