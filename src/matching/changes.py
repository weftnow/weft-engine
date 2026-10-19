"""F07 automatic matching updates: change ingestion, coalescing, retry, revocation and status.

The functions at the top are pure so the timing and revocation rules can be tested without a
database. ``ingest``, ``schedule`` and ``settle`` own the durable state machine; each is
idempotent and safe to run from several workers at once.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings
from src.matching.console import ConsoleAdapter
from src.matching.models import ChangeBatch, ChangeReceipt, FeedEntry, Recommendation, Run
from src.matching.storage import (
    check_event_size,
    create_run,
    lock_event,
    provenance_from_settings,
    run_payload,
)

# Failures that a retry cannot fix: configuration, budget and size limits.
NEVER_RETRY = frozenset(
    {
        "spend_budget_unconfigured",
        "provider_pricing_unconfigured",
        "spend_budget_exhausted",
        "worker_configuration_changed",
        "event_guest_limit_exceeded",
    }
)
RETRY_DELAYS_SECONDS = (60, 300, 900)
LIFECYCLE_SOURCE = "console_none_recorded"
AUTOMATIC_LIFECYCLE: dict[str, Any] = {
    "complete": True,
    "prior_decisions": [],
    "protected_pairs": [],
    "completed_pairs": [],
}
ACTIVE_RUN_STATUSES = ("waiting", "running")
TERMINAL_RUN_STATUSES = ("failed", "finished", "invalid_result")


@dataclass(frozen=True)
class PendingChanges:
    """Changes received for one event that no run has been scheduled for yet."""

    organization_id: UUID
    count: int
    oldest: datetime
    newest: datetime


@dataclass(frozen=True)
class RetryCandidate:
    batch_id: UUID
    event_id: UUID
    next_attempt_at: datetime


class PairLike(Protocol):
    @property
    def id(self) -> UUID: ...
    @property
    def guest_low_id(self) -> UUID: ...
    @property
    def guest_high_id(self) -> UUID: ...


def due_batches(
    pending_by_event: Mapping[UUID, PendingChanges],
    active_runs: Collection[UUID],
    now: datetime,
    quiet_seconds: int,
    max_wait_seconds: int,
) -> list[UUID]:
    """Events whose pending changes should start a run now.

    ``active_runs`` holds events that already have a waiting or running run, or an unfinished
    change batch; none of them may start another, so there is at most one in flight per event.
    A run starts once the newest change is ``quiet_seconds`` old, or the oldest change has
    waited ``max_wait_seconds``, whichever comes first.
    """
    busy = set(active_runs)
    due: list[UUID] = []
    for event_id, pending in pending_by_event.items():
        if event_id in busy or pending.count <= 0:
            continue
        quiet = (now - pending.newest).total_seconds() >= quiet_seconds
        overdue = (now - pending.oldest).total_seconds() >= max_wait_seconds
        if quiet or overdue:
            due.append(event_id)
    return sorted(due, key=str)


def due_retries(
    candidates: Iterable[RetryCandidate], active_runs: Collection[UUID], now: datetime
) -> list[RetryCandidate]:
    """Batches waiting for a retry whose backoff has elapsed and whose event is idle."""
    busy = set(active_runs)
    return sorted(
        (item for item in candidates if item.event_id not in busy and item.next_attempt_at <= now),
        key=lambda item: (item.next_attempt_at, str(item.batch_id)),
    )


def retry_decision(failure_code: str | None, attempt: int, retry_limit: int = 3) -> int | None:
    """Seconds to wait before the next attempt, or None when the batch must be abandoned.

    ``attempt`` is the 1-based attempt that just failed. A stale snapshot re-runs immediately;
    other transient failures back off 1, 5 and 15 minutes. Every re-run counts toward the cap.
    """
    if failure_code in NEVER_RETRY or attempt > retry_limit:
        return None
    if failure_code == "snapshot_stale":
        return 0
    return RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS)) - 1]


def revocations(
    active_recommendations: Iterable[PairLike], console_snapshot: Mapping[str, Any]
) -> list[tuple[UUID, str]]:
    """Active recommendations that are no longer allowed, with the reason for each.

    Only hard ineligibility revokes: a missing guest, an exclusion, a do-not-match block or an
    identity hold. Profile edits never revoke.
    """
    guests = {str(guest["id"]): guest for guest in console_snapshot["guests"]}
    blocked = {tuple(sorted(pair)) for pair in console_snapshot["blocked_pairs"]}
    revoked: list[tuple[UUID, str]] = []
    for item in active_recommendations:
        low, high = str(item.guest_low_id), str(item.guest_high_id)
        first, second = guests.get(low), guests.get(high)
        reason: str | None = None
        if first is None or second is None:
            reason = "guest_missing"
        elif {first["networking_status"], second["networking_status"]} != {"included"}:
            reason = "guest_excluded"
        elif (low, high) in blocked:
            reason = "pair_blocked"
        elif first["identity_resolution_required"] or second["identity_resolution_required"]:
            reason = "identity_resolution_required"
        if reason is not None:
            revoked.append((item.id, reason))
    return revoked


def derive_state(
    active_run_status: str | None,
    pending_changes: int,
    retry_scheduled: bool,
    latest_run_status: str | None,
) -> str:
    """Event-level matching state shown to the Console."""
    if active_run_status == "running":
        return "running"
    if active_run_status == "waiting" or retry_scheduled or pending_changes > 0:
        return "waiting"
    return latest_run_status or "idle"


# --- ingestion -------------------------------------------------------------------------------


async def ingest(
    sessions: async_sessionmaker[AsyncSession], console: ConsoleAdapter, poll_limit: int
) -> int:
    """Copy unprocessed Console change rows into receipts, then mark them processed.

    Receipts are written first with ON CONFLICT DO NOTHING, so a crash before the Console update
    only means the rows are read again; they never create a second receipt.
    """
    rows = await console.pending_changes(poll_limit)
    if not rows:
        return 0
    organizations = {
        event_id: await console.event_organization(event_id)
        for event_id in {row.event_id for row in rows}
    }
    values = [
        {
            "change_id": row.id,
            "organization_id": organizations[row.event_id],
            "event_id": row.event_id,
            "kind": row.kind,
            "guest_ids": row.guest_ids,
            "change_created_at": row.created_at,
        }
        for row in rows
        if organizations[row.event_id] is not None
    ]
    if values:
        async with sessions() as session, session.begin():
            await session.execute(
                pg_insert(ChangeReceipt)
                .values(values)
                .on_conflict_do_nothing(index_elements=["change_id"])
            )
    await console.mark_changes_processed([row.id for row in rows])
    return len(rows)


# --- revocation and feed writes ----------------------------------------------------------------


async def active_recommendations(
    session: AsyncSession, organization_id: UUID, event_id: UUID
) -> list[Recommendation]:
    result = await session.scalars(
        select(Recommendation)
        .where(
            Recommendation.organization_id == organization_id,
            Recommendation.event_id == event_id,
            Recommendation.revoked_at.is_(None),
        )
        .order_by(Recommendation.created_at, Recommendation.id)
    )
    return list(result)


async def apply_revocations(
    session: AsyncSession,
    rows: Sequence[Recommendation],
    console_snapshot: Mapping[str, Any],
    run_id: UUID | None,
) -> int:
    """Revoke ineligible active rows and append their feed entries. Idempotent.

    The caller holds the event advisory lock, which keeps feed ``seq`` in commit order.
    """
    reasons = dict(revocations(rows, console_snapshot))
    now = await _database_now(session)
    revoked = 0
    for row in rows:
        reason = reasons.get(row.id)
        if reason is None or row.revoked_at is not None:
            continue
        row.revoked_at = now
        row.revocation_reason = reason
        row.revoked_by_run_id = run_id
        await session.execute(
            pg_insert(FeedEntry)
            .values(
                organization_id=row.organization_id,
                event_id=row.event_id,
                kind="revoked",
                recommendation_id=row.id,
                run_id=run_id,
            )
            .on_conflict_do_nothing(constraint="matching_feed_entries_once")
        )
        revoked += 1
    if revoked:
        await session.flush()
    return revoked


async def append_issued(session: AsyncSession, rows: Iterable[Recommendation]) -> None:
    """Append ``issued`` feed entries for newly stored recommendations (event lock held)."""
    for row in sorted(rows, key=lambda item: (str(item.guest_low_id), str(item.guest_high_id))):
        await session.execute(
            pg_insert(FeedEntry)
            .values(
                organization_id=row.organization_id,
                event_id=row.event_id,
                kind="issued",
                recommendation_id=row.id,
                run_id=row.source_run_id,
            )
            .on_conflict_do_nothing(constraint="matching_feed_entries_once")
        )


# --- scheduling --------------------------------------------------------------------------------


async def _database_now(session: AsyncSession) -> datetime:
    value = await session.scalar(select(func.now()))
    if not isinstance(value, datetime):
        raise RuntimeError("database clock unavailable")
    return value


async def _active_run_events(session: AsyncSession) -> set[UUID]:
    rows = await session.scalars(
        select(Run.event_id).where(Run.status.in_(ACTIVE_RUN_STATUSES)).distinct()
    )
    return set(rows)


async def _scheduled_batch_events(session: AsyncSession) -> set[UUID]:
    rows = await session.scalars(
        select(ChangeBatch.event_id).where(ChangeBatch.state == "scheduled").distinct()
    )
    return set(rows)


async def _pending_by_event(session: AsyncSession) -> dict[UUID, PendingChanges]:
    rows = await session.execute(
        select(
            ChangeReceipt.event_id,
            ChangeReceipt.organization_id,
            func.count(),
            func.min(ChangeReceipt.change_created_at),
            func.max(ChangeReceipt.change_created_at),
        )
        .where(ChangeReceipt.batch_id.is_(None))
        .group_by(ChangeReceipt.event_id, ChangeReceipt.organization_id)
    )
    return {
        event_id: PendingChanges(organization_id, count, oldest, newest)
        for event_id, organization_id, count, oldest, newest in rows
    }


async def _unbatched_receipt_ids(session: AsyncSession, event_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        select(ChangeReceipt.change_id)
        .where(ChangeReceipt.event_id == event_id, ChangeReceipt.batch_id.is_(None))
        .order_by(ChangeReceipt.change_created_at, ChangeReceipt.change_id)
    )
    return list(rows)


def _abandon(batch: ChangeBatch, reason: str) -> None:
    batch.state = "abandoned"
    batch.abandon_reason = reason[:80]
    batch.next_attempt_at = None


async def _start_attempt(
    session: AsyncSession,
    console: ConsoleAdapter,
    settings: Settings,
    batch: ChangeBatch,
    receipt_ids: list[UUID],
) -> bool:
    """Take a fresh snapshot, revoke what became ineligible, and create this attempt's run.

    The caller holds the event lock inside a transaction and chose ``receipt_ids`` before this
    call, so every attached change was committed before the snapshot below. Returns False when
    the batch had to be abandoned instead of producing a run.
    """
    if receipt_ids:
        await session.execute(
            update(ChangeReceipt)
            .where(ChangeReceipt.change_id.in_(receipt_ids))
            .values(batch_id=batch.id)
        )
    try:
        snapshot = await console.snapshot(batch.organization_id, batch.event_id)
    except LookupError:
        _abandon(batch, "event_not_found")
        return False
    try:
        check_event_size(snapshot)
    except ValueError as error:
        # No run can answer this batch, but an exclusion must still take effect.
        _abandon(batch, str(error))
        await apply_revocations(
            session,
            await active_recommendations(session, batch.organization_id, batch.event_id),
            snapshot,
            None,
        )
        return False
    provenance = {**provenance_from_settings(settings), "lifecycle_source": LIFECYCLE_SOURCE}
    run = await create_run(
        session,
        organization_id=batch.organization_id,
        event_id=batch.event_id,
        idempotency_key=f"f07:{batch.id}:{batch.attempt}",
        mode="event",
        target_guest_id=None,
        payload=run_payload(snapshot, AUTOMATIC_LIFECYCLE, settings.matching_policy_version),
        provenance=provenance,
        trigger="change",
        change_batch_id=batch.id,
    )
    batch.last_run_id = run.id
    batch.next_attempt_at = None
    await apply_revocations(
        session,
        await active_recommendations(session, batch.organization_id, batch.event_id),
        snapshot,
        run.id,
    )
    return True


async def _event_has_active_run(session: AsyncSession, event_id: UUID) -> bool:
    found = await session.scalar(
        select(Run.id).where(Run.event_id == event_id, Run.status.in_(ACTIVE_RUN_STATUSES)).limit(1)
    )
    return found is not None


async def _schedule_event(
    sessions: async_sessionmaker[AsyncSession],
    console: ConsoleAdapter,
    settings: Settings,
    organization_id: UUID,
    event_id: UUID,
) -> bool:
    async with sessions() as session, session.begin():
        await lock_event(session, event_id)
        # Re-check under the lock: another worker may have scheduled this event already.
        if await _event_has_active_run(session, event_id) or event_id in (
            await _scheduled_batch_events(session)
        ):
            return False
        receipt_ids = await _unbatched_receipt_ids(session, event_id)
        if not receipt_ids:
            return False
        batch = ChangeBatch(
            id=uuid.uuid4(),
            organization_id=organization_id,
            event_id=event_id,
            attempt=1,
            state="scheduled",
        )
        session.add(batch)
        await session.flush()
        return await _start_attempt(session, console, settings, batch, receipt_ids)


async def _retry_event(
    sessions: async_sessionmaker[AsyncSession],
    console: ConsoleAdapter,
    settings: Settings,
    batch_id: UUID,
) -> bool:
    async with sessions() as session, session.begin():
        event_id = await session.scalar(
            select(ChangeBatch.event_id).where(ChangeBatch.id == batch_id)
        )
        if event_id is None:
            return False
        await lock_event(session, event_id)
        batch = await session.get(ChangeBatch, batch_id, with_for_update=True)
        now = await _database_now(session)
        if (
            batch is None
            or batch.state != "scheduled"
            or batch.next_attempt_at is None
            or batch.next_attempt_at > now
            or await _event_has_active_run(session, batch.event_id)
        ):
            return False
        batch.attempt += 1
        # Changes received during the backoff are covered by this attempt's fresh snapshot.
        receipt_ids = await _unbatched_receipt_ids(session, batch.event_id)
        return await _start_attempt(session, console, settings, batch, receipt_ids)


async def schedule(
    sessions: async_sessionmaker[AsyncSession],
    console: ConsoleAdapter,
    settings: Settings,
) -> int:
    """Create runs for events whose changes are due, and for batches whose backoff elapsed."""
    async with sessions() as session:
        now = await _database_now(session)
        pending = await _pending_by_event(session)
        active_run_events = await _active_run_events(session)
        busy = active_run_events | await _scheduled_batch_events(session)
        candidates = [
            RetryCandidate(batch_id, event_id, next_attempt_at)
            for batch_id, event_id, next_attempt_at in await session.execute(
                select(ChangeBatch.id, ChangeBatch.event_id, ChangeBatch.next_attempt_at).where(
                    ChangeBatch.state == "scheduled", ChangeBatch.next_attempt_at.is_not(None)
                )
            )
            if next_attempt_at is not None
        ]
    created = 0
    for event_id in due_batches(
        pending,
        busy,
        now,
        settings.matching_change_quiet_seconds,
        settings.matching_change_max_wait_seconds,
    ):
        if await _schedule_event(
            sessions, console, settings, pending[event_id].organization_id, event_id
        ):
            created += 1
    for candidate in due_retries(candidates, active_run_events, now):
        if await _retry_event(sessions, console, settings, candidate.batch_id):
            created += 1
    return created


async def settle(sessions: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Close batches whose run ended: complete them, or plan the next attempt, or abandon."""
    settled = 0
    async with sessions() as session, session.begin():
        now = await _database_now(session)
        rows = await session.execute(
            select(ChangeBatch, Run)
            .join(Run, Run.id == ChangeBatch.last_run_id)
            .where(
                ChangeBatch.state == "scheduled",
                ChangeBatch.next_attempt_at.is_(None),
                Run.status.in_(TERMINAL_RUN_STATUSES),
            )
            .with_for_update(of=ChangeBatch, skip_locked=True)
        )
        for batch, run in rows.all():
            settled += 1
            if run.status == "finished":
                batch.state = "completed"
                continue
            delay = retry_decision(
                run.failure_code, batch.attempt, settings.matching_change_retry_limit
            )
            if delay is None:
                _abandon(batch, run.failure_code or "matching_failed")
            else:
                batch.next_attempt_at = now + timedelta(seconds=delay)
    return settled


# --- status and feed reads ---------------------------------------------------------------------


async def event_status(
    session: AsyncSession,
    console: ConsoleAdapter,
    organization_id: UUID,
    event_id: UUID,
    automatic_enabled: bool,
) -> dict[str, Any]:
    """Per-event matching status; counts changes the worker has not yet read as pending too."""
    runs = (
        await session.scalars(
            select(Run)
            .where(Run.organization_id == organization_id, Run.event_id == event_id)
            .order_by(Run.created_at.desc(), Run.id)
        )
    ).all()
    latest = runs[0] if runs else None
    active = next((run for run in runs if run.status in ACTIVE_RUN_STATUSES), None)
    last_finished = next((run for run in runs if run.status == "finished"), None)
    ingested_pending = (
        await session.scalar(
            select(func.count())
            .select_from(ChangeReceipt)
            .outerjoin(ChangeBatch, ChangeBatch.id == ChangeReceipt.batch_id)
            .where(
                ChangeReceipt.organization_id == organization_id,
                ChangeReceipt.event_id == event_id,
                or_(ChangeReceipt.batch_id.is_(None), ChangeBatch.state == "scheduled"),
            )
        )
        or 0
    )
    next_attempt_at = await session.scalar(
        select(func.min(ChangeBatch.next_attempt_at)).where(
            ChangeBatch.organization_id == organization_id,
            ChangeBatch.event_id == event_id,
            ChangeBatch.state == "scheduled",
        )
    )
    pending = int(ingested_pending) + await console.unprocessed_change_count(event_id)
    return {
        "state": derive_state(
            active.status if active else None,
            pending,
            next_attempt_at is not None,
            latest.status if latest else None,
        ),
        "pending_changes": pending,
        "latest_run": (
            {
                "run_id": latest.id,
                "status": latest.status,
                "trigger": latest.trigger,
                "failure": (
                    {"code": latest.failure_code, "message": latest.failure_message}
                    if latest.failure_code
                    else None
                ),
                "created_at": latest.created_at,
                "finished_at": latest.finished_at,
            }
            if latest
            else None
        ),
        "last_finished_run_id": last_finished.id if last_finished else None,
        "next_attempt_at": next_attempt_at,
        "automatic_enabled": automatic_enabled,
    }


async def feed_page(
    session: AsyncSession, organization_id: UUID, event_id: UUID, after: int, limit: int
) -> tuple[list[tuple[FeedEntry, Recommendation]], dict[UUID, dict[str, dict[str, Any]]]]:
    """One page of feed entries after ``after``, with each source run's guest projections."""
    rows = (
        await session.execute(
            select(FeedEntry, Recommendation)
            .join(Recommendation, Recommendation.id == FeedEntry.recommendation_id)
            .where(
                FeedEntry.organization_id == organization_id,
                FeedEntry.event_id == event_id,
                FeedEntry.seq > after,
            )
            .order_by(FeedEntry.seq)
            .limit(limit)
        )
    ).all()
    entries = [(entry, recommendation) for entry, recommendation in rows]
    run_ids = {recommendation.source_run_id for _, recommendation in entries}
    guests_by_run: dict[UUID, dict[str, dict[str, Any]]] = defaultdict(dict)
    if run_ids:
        snapshots = await session.execute(
            select(Run.id, Run.snapshot["console"]["guests"]).where(Run.id.in_(run_ids))
        )
        for run_id, guests in snapshots:
            guests_by_run[run_id] = {str(guest["id"]): guest for guest in guests}
    return entries, dict(guests_by_run)
