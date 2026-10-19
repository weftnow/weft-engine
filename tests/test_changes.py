"""F07 rules that need no database: timing, retry, revocation, state and API contracts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Environment, Settings
from src.main import create_app
from src.matching import changes, models
from src.matching.changes import (
    NEVER_RETRY,
    PendingChanges,
    RetryCandidate,
    derive_state,
    due_batches,
    due_retries,
    retry_decision,
    revocations,
)
from src.matching.models import Recommendation
from src.matching.router import result_item
from src.matching.schemas import FeedEntryOut, FeedResponse, MatchingStatus
from src.matching.worker import MatchingWorker

ROOT = Path(__file__).parents[1]
ORG = UUID("10000000-0000-0000-0000-000000000001")
EVENT = UUID("20000000-0000-0000-0000-000000000001")
OTHER_EVENT = UUID("20000000-0000-0000-0000-000000000002")
GUEST_A = UUID("30000000-0000-0000-0000-000000000001")
GUEST_B = UUID("30000000-0000-0000-0000-000000000002")
GUEST_C = UUID("30000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)


def pending(oldest_age: int, newest_age: int, count: int = 2) -> PendingChanges:
    return PendingChanges(
        organization_id=ORG,
        count=count,
        oldest=NOW - timedelta(seconds=oldest_age),
        newest=NOW - timedelta(seconds=newest_age),
    )


@pytest.mark.parametrize(
    ("oldest_age", "newest_age", "expected"),
    [
        (10, 5, False),  # still inside the quiet period
        (40, 30, True),  # newest change is exactly quiet seconds old
        (200, 29, False),  # still noisy, not yet overdue
        (300, 1, True),  # maximum wait reached while changes keep arriving
        (1000, 0, True),  # catching up after downtime
    ],
)
def test_due_batches_waits_for_quiet_period_or_maximum_wait(
    oldest_age: int, newest_age: int, expected: bool
) -> None:
    due = due_batches({EVENT: pending(oldest_age, newest_age)}, set(), NOW, 30, 300)
    assert (due == [EVENT]) is expected


def test_due_batches_never_starts_a_second_run_for_a_busy_event() -> None:
    both = {EVENT: pending(500, 400), OTHER_EVENT: pending(500, 400)}
    assert due_batches(both, {EVENT}, NOW, 30, 300) == [OTHER_EVENT]
    assert due_batches({EVENT: pending(500, 400, count=0)}, set(), NOW, 30, 300) == []


def test_due_retries_waits_for_backoff_and_an_idle_event() -> None:
    ready = RetryCandidate(UUID(int=1), EVENT, NOW - timedelta(seconds=1))
    waiting = RetryCandidate(UUID(int=2), OTHER_EVENT, NOW + timedelta(seconds=60))
    assert due_retries([ready, waiting], set(), NOW) == [ready]
    assert due_retries([ready, waiting], {EVENT}, NOW) == []


@pytest.mark.parametrize(("attempt", "delay"), [(1, 60), (2, 300), (3, 900), (4, None), (9, None)])
def test_transient_failures_back_off_one_five_fifteen_minutes_then_stop(
    attempt: int, delay: int | None
) -> None:
    assert retry_decision("provider_failure", attempt) == delay
    assert retry_decision(None, attempt) == delay


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_stale_snapshot_reruns_immediately_but_counts_toward_the_cap(attempt: int) -> None:
    assert retry_decision("snapshot_stale", attempt) == 0
    assert retry_decision("snapshot_stale", 4) is None


@pytest.mark.parametrize("code", sorted(NEVER_RETRY))
def test_configuration_and_budget_failures_never_retry(code: str) -> None:
    assert retry_decision(code, 1) is None


def test_retry_cap_follows_configuration() -> None:
    assert retry_decision("provider_failure", 1, retry_limit=0) is None
    assert retry_decision("provider_failure", 4, retry_limit=5) == 900


def test_never_retry_codes_are_codes_the_service_really_raises() -> None:
    source = "".join(
        (ROOT / "src" / "matching" / name).read_text() for name in ("worker.py", "storage.py")
    )
    for code in NEVER_RETRY:
        assert re.search(rf'"{code}"', source), code


@dataclass(frozen=True)
class Pair:
    id: UUID
    guest_low_id: UUID
    guest_high_id: UUID


def guest(guest_id: UUID, **values: object) -> dict[str, Any]:
    return {
        "id": str(guest_id),
        "networking_status": "included",
        "identity_resolution_required": False,
        **values,
    }


def snapshot(
    *guests: dict[str, Any], blocked: tuple[tuple[UUID, UUID], ...] = ()
) -> dict[str, Any]:
    return {
        "guests": list(guests),
        "blocked_pairs": [sorted((str(low), str(high))) for low, high in blocked],
    }


PAIR = Pair(UUID(int=11), GUEST_A, GUEST_B)


def test_edited_profiles_and_unchanged_snapshots_revoke_nothing() -> None:
    current = snapshot(guest(GUEST_A, profile_version=7), guest(GUEST_B), guest(GUEST_C))
    assert revocations([PAIR], current) == []


@pytest.mark.parametrize(
    ("current", "reason"),
    [
        (snapshot(guest(GUEST_A, networking_status="excluded"), guest(GUEST_B)), "guest_excluded"),
        (snapshot(guest(GUEST_A), guest(GUEST_B, networking_status="excluded")), "guest_excluded"),
        (snapshot(guest(GUEST_A), guest(GUEST_B), blocked=((GUEST_B, GUEST_A),)), "pair_blocked"),
        (
            snapshot(guest(GUEST_A), guest(GUEST_B, identity_resolution_required=True)),
            "identity_resolution_required",
        ),
        (snapshot(guest(GUEST_A)), "guest_missing"),
    ],
)
def test_hard_ineligibility_revokes_with_a_reason(current: dict[str, Any], reason: str) -> None:
    assert revocations([PAIR], current) == [(PAIR.id, reason)]


def test_revocation_only_touches_affected_pairs() -> None:
    other = Pair(UUID(int=12), GUEST_B, GUEST_C)
    current = snapshot(guest(GUEST_A, networking_status="excluded"), guest(GUEST_B), guest(GUEST_C))
    assert revocations([PAIR, other], current) == [(PAIR.id, "guest_excluded")]


@pytest.mark.parametrize(
    ("active", "retry", "pending_count", "latest", "expected"),
    [
        (None, False, 0, None, "idle"),
        (None, False, 3, "finished", "waiting"),
        (None, True, 0, "failed", "waiting"),
        ("waiting", False, 0, None, "waiting"),
        ("running", False, 5, "finished", "running"),
        (None, False, 0, "failed", "failed"),
        (None, False, 0, "invalid_result", "invalid_result"),
        (None, False, 0, "finished", "finished"),
    ],
)
def test_state_is_derived_from_runs_pending_changes_and_retries(
    active: str | None, retry: bool, pending_count: int, latest: str | None, expected: str
) -> None:
    assert derive_state(active, pending_count, retry, latest) == expected


def recommendation(revoked: bool = False) -> Recommendation:
    return Recommendation(
        id=UUID(int=11),
        organization_id=ORG,
        event_id=EVENT,
        guest_low_id=GUEST_A,
        guest_high_id=GUEST_B,
        source_run_id=UUID(int=99),
        profile_versions={str(GUEST_A): 1, str(GUEST_B): 2},
        directional_scores={str(GUEST_A): 80, str(GUEST_B): 82},
        pair_score=80,
        benefits={str(GUEST_A): "a", str(GUEST_B): "b"},
        evidence=[
            {"guest_id": str(GUEST_A), "field": "summary", "quote": "public quote"},
            {"guest_id": str(GUEST_B), "field": "goals", "quote": "organizer-only quote"},
        ],
        missing_information={},
        uncertainty="x",
        shareable_reasons={str(GUEST_A): "reason", str(GUEST_B): None},
        revoked_at=NOW if revoked else None,
        revocation_reason="guest_excluded" if revoked else None,
    )


GUESTS = {
    str(GUEST_A): {"id": str(GUEST_A), "organizer_only_fields": []},
    str(GUEST_B): {"id": str(GUEST_B), "organizer_only_fields": ["goals"]},
}


def test_result_item_filters_organizer_only_evidence_and_reports_revocation() -> None:
    active = result_item(recommendation(), GUESTS)
    assert [item["quote"] for item in active.evidence] == ["public quote"]
    assert active.revoked_at is None
    assert active.revocation_reason is None
    revoked = result_item(recommendation(revoked=True), GUESTS)
    assert revoked.revocation_reason == "guest_excluded"
    assert revoked.revoked_at == NOW


def test_feed_serializes_camel_case_with_cursor_and_no_organizer_only_text() -> None:
    entry = FeedEntryOut(
        seq=7,
        kind="revoked",
        run_id=None,
        recommendation=result_item(recommendation(revoked=True), GUESTS),
    )
    body = FeedResponse(entries=[entry], next_cursor=7).model_dump(mode="json")
    assert body["nextCursor"] == 7
    assert body["entries"][0]["recommendation"]["revocationReason"] == "guest_excluded"
    assert body["entries"][0]["runId"] is None
    assert "organizer-only quote" not in str(body)


def test_status_serializes_camel_case() -> None:
    body = MatchingStatus.model_validate(
        {
            "state": "waiting",
            "pending_changes": 2,
            "latest_run": None,
            "last_finished_run_id": None,
            "next_attempt_at": None,
            "automatic_enabled": False,
        }
    ).model_dump(mode="json")
    assert body["pendingChanges"] == 2
    assert body["automaticEnabled"] is False
    assert body["lastFinishedRunId"] is None


@pytest.mark.parametrize("suffix", ["status", "feed"])
async def test_status_and_feed_require_credentials_and_organization_scope(suffix: str) -> None:
    settings = Settings(
        _env_file=None,
        environment=Environment.TEST,
        matching_service_tokens={"unit-secret": [str(ORG)]},
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        path = f"/v1/organizations/{ORG}/events/{EVENT}/matching/{suffix}"
        assert (await client.get(path)).status_code == 401
        wrong_token = await client.get(path, headers={"X-Weft-Service-Token": "nope"})
        assert wrong_token.status_code == 401
        other_org = path.replace(str(ORG), "10000000-0000-0000-0000-000000000099")
        forbidden = await client.get(other_org, headers={"X-Weft-Service-Token": "unit-secret"})
        assert forbidden.status_code == 403
        # Authorized callers get 503, not data, when storage is not configured.
        unavailable = await client.get(path, headers={"X-Weft-Service-Token": "unit-secret"})
        assert unavailable.status_code == 503
        paths = (await client.get("/openapi.json")).json()["paths"]
        assert f"/v1/organizations/{{organizationId}}/events/{{eventId}}/matching/{suffix}" in paths


async def test_feed_rejects_out_of_range_paging() -> None:
    settings = Settings(
        _env_file=None,
        environment=Environment.TEST,
        matching_service_tokens={"unit-secret": [str(ORG)]},
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        path = f"/v1/organizations/{ORG}/events/{EVENT}/matching/feed"
        headers = {"X-Weft-Service-Token": "unit-secret"}
        assert (await client.get(path, params={"limit": 201}, headers=headers)).status_code == 422
        assert (await client.get(path, params={"after": -1}, headers=headers)).status_code == 422


def test_automatic_processing_is_off_by_default_and_documented_in_the_example() -> None:
    assert Settings(_env_file=None).matching_automatic_enabled is False
    example = Settings(_env_file=ROOT / ".env.example")
    assert example.matching_automatic_enabled is False
    assert example.matching_change_quiet_seconds == 30
    assert example.matching_change_max_wait_seconds == 300
    assert example.matching_change_retry_limit == 3
    assert example.matching_change_poll_limit == 500


def test_migration_0002_mirrors_every_new_model_column() -> None:
    migration = (ROOT / "migrations" / "versions" / "0002_f07_change_consumption.py").read_text()
    for table in (models.ChangeBatch, models.ChangeReceipt, models.FeedEntry):
        assert f"weft_engine.{table.__tablename__}" in migration
        for column in table.__table__.columns:
            assert re.search(rf"\b{column.name}\b", migration), (table.__tablename__, column.name)
    for name in ("trigger", "change_batch_id"):
        assert name in models.Run.__table__.columns
        assert re.search(rf"\b{name}\b", migration)
    for name in ("revoked_at", "revocation_reason", "revoked_by_run_id"):
        assert name in models.Recommendation.__table__.columns
        assert re.search(rf"\b{name}\b", migration)
    assert "CREATE ROLE" not in migration.upper()
    assert "GRANT" not in migration.upper()


async def test_automatic_cycle_failure_is_logged_without_details_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(*_args: object) -> int:
        raise RuntimeError("profile text must not be logged")

    monkeypatch.setattr(changes, "ingest", boom)
    worker = MatchingWorker.__new__(MatchingWorker)
    worker.settings = Settings(_env_file=None, matching_automatic_enabled=True)
    worker.sessions = None  # type: ignore[assignment]
    worker.console = None  # type: ignore[assignment]
    with caplog.at_level(logging.WARNING):
        assert await worker.automatic_cycle() is False
    assert "RuntimeError" in caplog.text
    assert "profile text" not in caplog.text
