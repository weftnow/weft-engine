from __future__ import annotations

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Environment, Settings
from src.main import create_app
from src.matching.router import shareable_missing_fields
from src.matching.schemas import CreateRun, Evidence, PairEvaluation
from src.matching.selection import Candidate, canonical_pair, select_capacity, validate_evaluation
from src.matching.worker import SYSTEM_INSTRUCTIONS, cosine, profile_text

ORG = UUID("10000000-0000-0000-0000-000000000001")
EVENT = UUID("20000000-0000-0000-0000-000000000001")
GUEST_A = UUID("30000000-0000-0000-0000-000000000001")
GUEST_B = UUID("30000000-0000-0000-0000-000000000002")


def guest(guest_id: UUID, **values: object) -> dict[str, object]:
    return {
        "id": str(guest_id),
        "networking_status": "included",
        "identity_resolution_required": False,
        "summary": "Building open-source payments tools for rural clinics",
        "goals": None,
        "offers": None,
        "desired_connections": None,
        "avoid": None,
        "background": None,
        "linkedin_details": None,
        "organizer_only_fields": [],
        "profile_version": 0,
        **values,
    }


def evaluation(**values: object) -> PairEvaluation:
    data: dict[str, object] = {
        "guest_a_id": GUEST_A,
        "guest_b_id": GUEST_B,
        "benefit_a": "Can learn from the clinic payment deployment experience.",
        "benefit_b": "Can share the open-source payment tools with clinics.",
        "score_a": 80,
        "score_b": 82,
        "evidence": [
            Evidence(guest_id=GUEST_A, field="summary", quote="open-source payments tools"),
            Evidence(guest_id=GUEST_B, field="summary", quote="Clinic payment deployment"),
        ],
        "missing_information_a": [],
        "missing_information_b": [],
        "uncertainty": "The guests have not confirmed interest.",
        "restriction_found": False,
    }
    data.update(values)
    return PairEvaluation.model_validate(data)


def test_canonical_pair_is_order_independent_and_rejects_self_pair() -> None:
    assert canonical_pair(GUEST_A, GUEST_B) == canonical_pair(GUEST_B, GUEST_A)
    with pytest.raises(ValueError, match="self_match"):
        canonical_pair(GUEST_A, GUEST_A)


def test_console_compatible_request_uses_camel_case_and_requires_complete_lifecycle() -> None:
    request = CreateRun.model_validate(
        {
            "mode": "more",
            "targetGuestId": str(GUEST_A),
            "lifecycle": {
                "complete": True,
                "priorDecisions": [],
                "protectedPairs": [],
                "completedPairs": [],
            },
        }
    )
    assert request.target_guest_id == GUEST_A
    assert request.lifecycle.model_dump(mode="json", by_alias=False)["prior_decisions"] == []
    with pytest.raises(ValueError, match="complete"):
        CreateRun.model_validate(
            {
                "mode": "event",
                "lifecycle": {
                    "complete": False,
                    "priorDecisions": [],
                    "protectedPairs": [],
                    "completedPairs": [],
                },
            }
        )


def test_missing_profiles_remain_eligible_and_supported_result_requires_exact_facts() -> None:
    guests = {
        str(GUEST_A): guest(GUEST_A),
        str(GUEST_B): guest(GUEST_B, summary="Clinic payment deployment for rural care."),
    }
    assert validate_evaluation(evaluation(), guests, set(), set())

    wrong_quote = evaluation(
        evidence=[
            Evidence(guest_id=GUEST_A, field="summary", quote="founder seeking millions"),
            Evidence(guest_id=GUEST_B, field="summary", quote="Clinic payment deployment"),
        ]
    )
    assert not validate_evaluation(wrong_quote, guests, set(), set())


@pytest.mark.parametrize(
    ("changes", "blocked", "expected"),
    [
        ({"score_a": 69}, set(), False),
        ({"restriction_found": True}, set(), False),
        ({}, {(str(GUEST_A), str(GUEST_B))}, False),
        ({}, set(), True),
    ],
)
def test_pair_validation_rejects_low_score_or_restrictions(
    changes: dict[str, object], blocked: set[tuple[str, str]], expected: bool
) -> None:
    people = {
        str(GUEST_A): guest(GUEST_A),
        str(GUEST_B): guest(GUEST_B, summary="Clinic payment deployment for rural care."),
    }
    assert validate_evaluation(evaluation(**changes), people, blocked, set()) is expected


def test_linked_guest_group_is_held_without_affecting_sparse_profile_eligibility() -> None:
    people = {
        str(GUEST_A): guest(GUEST_A, identity_resolution_required=True),
        str(GUEST_B): guest(GUEST_B),
    }
    assert not validate_evaluation(evaluation(), people, set(), set())


def test_capacity_selection_respects_both_people_and_more_limit() -> None:
    third = "30000000-0000-0000-0000-000000000003"
    fourth = "30000000-0000-0000-0000-000000000004"
    candidates = [
        Candidate(str(GUEST_A), str(GUEST_B), 80),
        Candidate(str(GUEST_A), third, 75),
        Candidate(str(GUEST_A), fourth, 72),
    ]
    selected, status = select_capacity(
        candidates,
        {str(GUEST_A): 3, str(GUEST_B): 0, third: 1, fourth: 1},
        target_guest_id=str(GUEST_A),
        target_limit=3,
    )
    assert status in {"optimal", "feasible"}
    assert [(pair.guest_low_id, pair.guest_high_id) for pair in selected] == [
        (str(GUEST_A), third),
        (str(GUEST_A), fourth),
    ]


def test_capacity_selection_returns_single_supported_pair_when_only_one_is_passed() -> None:
    third = "30000000-0000-0000-0000-000000000003"
    candidates = [Candidate(str(GUEST_A), third, 80)]
    selected, _ = select_capacity(candidates, {str(GUEST_A): 3, third: 3})
    assert len(selected) == 1


def test_retrieval_does_not_infer_from_empty_text_and_injection_is_untrusted() -> None:
    assert cosine([], [1.0]) == 0.0
    assert profile_text(guest(GUEST_A), "needs") == ""
    assert "untrusted quoted data" in SYSTEM_INSTRUCTIONS


def test_private_fields_are_not_exposed_as_missing_or_as_evidence() -> None:
    person = guest(
        GUEST_A,
        goals="Organizer-only partnership strategy",
        organizer_only_fields=["goals"],
    )
    missing = shareable_missing_fields(person)
    assert "goals" not in missing
    assert {"offers", "desiredConnections", "background", "linkedinDetails"} <= set(missing)


async def test_matching_routes_require_service_credentials_and_org_scope() -> None:
    settings = Settings(
        _env_file=None,
        environment=Environment.TEST,
        matching_service_tokens={"unit-secret": [str(ORG)]},
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        path = f"/v1/organizations/{ORG}/events/{EVENT}/matching-runs"
        denied = await client.post(path, json={}, headers={"Idempotency-Key": "one"})
        assert denied.status_code == 401
        forbidden = await client.post(
            path.replace(str(ORG), "10000000-0000-0000-0000-000000000099"),
            json={},
            headers={"Idempotency-Key": "one", "X-Weft-Service-Token": "unit-secret"},
        )
        assert forbidden.status_code == 403
        assert (
            "/v1/organizations/{organizationId}/events/{eventId}/matching-runs"
            in (await client.get("/openapi.json")).json()["paths"]
        )
