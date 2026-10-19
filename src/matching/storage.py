"""Engine database session construction and run submission."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import Settings
from src.matching.console import ConsoleAdapter
from src.matching.models import Recommendation, Run, SlotGrant
from src.matching.schemas import CreateRun


def session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        url, pool_pre_ping=True, pool_size=5, max_overflow=5, hide_parameters=True
    )
    return async_sessionmaker(engine, expire_on_commit=False)


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def provenance_from_settings(settings: Settings) -> dict[str, str]:
    return {
        "embedding_model": settings.matching_embedding_model,
        "evaluation_model": settings.matching_evaluation_model,
        "prompt_version": settings.matching_prompt_version,
        "policy_version": settings.matching_policy_version,
    }


def check_event_size(snapshot: dict[str, Any]) -> None:
    eligible = sum(
        1
        for guest in snapshot["guests"]
        if guest["networking_status"] == "included" and not guest["identity_resolution_required"]
    )
    if eligible > 300:
        raise ValueError("event_guest_limit_exceeded")


def run_payload(
    snapshot: dict[str, Any], lifecycle: dict[str, Any], policy_version: str
) -> dict[str, Any]:
    return {"console": snapshot, "lifecycle": lifecycle, "policy_version": policy_version}


async def lock_event(session: AsyncSession, event_id: UUID) -> None:
    """Serialize run creation, capacity allocation and feed writes for one event."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:event,0))"),
        {"event": str(event_id)},
    )


async def create_run(
    session: AsyncSession,
    *,
    organization_id: UUID,
    event_id: UUID,
    idempotency_key: str,
    mode: str,
    target_guest_id: UUID | None,
    payload: dict[str, Any],
    provenance: dict[str, str],
    trigger: str = "api",
    change_batch_id: UUID | None = None,
) -> Run:
    """Insert a waiting run, or return the one saved under this key.

    The caller must hold the event advisory lock inside an open transaction.
    """
    prior = await session.scalar(
        select(Run).where(
            Run.organization_id == organization_id,
            Run.event_id == event_id,
            Run.idempotency_key == idempotency_key,
        )
    )
    if prior is not None:
        return prior
    run = Run(
        id=uuid.uuid4(),
        organization_id=organization_id,
        event_id=event_id,
        idempotency_key=idempotency_key,
        mode=mode,
        target_guest_id=target_guest_id,
        status="waiting",
        snapshot=payload,
        fingerprint=fingerprint(payload),
        progress={"stage": "waiting"},
        provenance=provenance,
        usage={},
        trigger=trigger,
        change_batch_id=change_batch_id,
    )
    session.add(run)
    if mode == "more" and target_guest_id is not None:
        session.add(
            SlotGrant(
                id=uuid.uuid4(),
                organization_id=organization_id,
                event_id=event_id,
                guest_id=target_guest_id,
                request_key=idempotency_key,
                slots=3,
            )
        )
    await session.flush()
    return run


async def submit_run(
    sessions: async_sessionmaker[AsyncSession],
    console: ConsoleAdapter,
    organization_id: UUID,
    event_id: UUID,
    idempotency_key: str,
    request: CreateRun,
    service_provenance: dict[str, str],
) -> Run:
    actual_org = await console.event_organization(event_id)
    if actual_org != organization_id:
        raise LookupError("event_not_found")
    snapshot = await console.snapshot(organization_id, event_id)
    check_event_size(snapshot)
    event_guest_ids = {UUID(guest["id"]) for guest in snapshot["guests"]}
    for pair_group in (
        request.lifecycle.prior_decisions,
        request.lifecycle.protected_pairs,
        request.lifecycle.completed_pairs,
    ):
        for left, right in pair_group:
            if left == right or left not in event_guest_ids or right not in event_guest_ids:
                raise ValueError("invalid_lifecycle_pair")
    if request.target_guest_id:
        target = next(
            (g for g in snapshot["guests"] if g["id"] == str(request.target_guest_id)), None
        )
        if target is None:
            raise LookupError("guest_not_found")
        if target["identity_resolution_required"]:
            raise ValueError("identity_resolution_required")
        if target["networking_status"] != "included":
            raise ValueError("guest_not_eligible")
    payload = run_payload(
        snapshot,
        request.lifecycle.model_dump(mode="json", by_alias=False),
        service_provenance["policy_version"],
    )
    async with sessions() as session, session.begin():
        await lock_event(session, event_id)
        return await create_run(
            session,
            organization_id=organization_id,
            event_id=event_id,
            idempotency_key=idempotency_key,
            mode=request.mode,
            target_guest_id=request.target_guest_id,
            payload=payload,
            provenance=service_provenance,
        )


async def scoped_run(
    sessions: async_sessionmaker[AsyncSession], organization_id: UUID, event_id: UUID, run_id: UUID
) -> Run | None:
    async with sessions() as session:
        return await session.scalar(
            select(Run).where(
                Run.id == run_id,
                Run.organization_id == organization_id,
                Run.event_id == event_id,
            )
        )


async def run_recommendations(
    sessions: async_sessionmaker[AsyncSession], organization_id: UUID, event_id: UUID
) -> list[Recommendation]:
    async with sessions() as session:
        result = await session.scalars(
            select(Recommendation).where(
                Recommendation.organization_id == organization_id,
                Recommendation.event_id == event_id,
            )
        )
        return list(result)
