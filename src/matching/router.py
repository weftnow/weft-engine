"""Authenticated, versioned F06 service endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.matching.auth import authorize_organization
from src.matching.console import ConsoleAdapter
from src.matching.models import Recommendation
from src.matching.schemas import CreateRun, ResultItem, ResultsResponse, RunAccepted
from src.matching.storage import (
    provenance_from_settings,
    run_recommendations,
    scoped_run,
    submit_run,
)

router = APIRouter(
    prefix="/v1/organizations/{organizationId}/events/{eventId}/matching-runs", tags=["matching"]
)
Org = Annotated[UUID, Depends(authorize_organization)]


def shareable_missing_fields(guest: dict[str, object]) -> list[str]:
    """Return only absent profile fields visible to the guest-facing projection."""
    fields = {
        "goals": "goals",
        "offers": "offers",
        "desiredConnections": "desired_connections",
        "background": "background",
        "linkedinDetails": "linkedin_details",
    }
    private_value = guest.get("organizer_only_fields")
    private = {str(value) for value in private_value} if isinstance(private_value, list) else set()
    missing: list[str] = []
    for wire_name, storage_name in fields.items():
        value = guest.get(storage_name)
        if wire_name not in private and not (isinstance(value, str) and value.strip()):
            missing.append(wire_name)
    return missing


def result_item(row: Recommendation, snapshot_guests: dict[str, dict[str, Any]]) -> ResultItem:
    """Guest-safe projection of one recommendation; the only place organizer-only evidence is
    filtered, so results and the feed cannot disagree."""
    return ResultItem(
        recommendation_id=row.id,
        guest_low_id=row.guest_low_id,
        guest_high_id=row.guest_high_id,
        profile_versions=row.profile_versions,
        directional_scores=row.directional_scores,
        pair_score=row.pair_score,
        benefits={guest_id: row.shareable_reasons.get(guest_id) for guest_id in row.benefits},
        evidence=[
            item
            for item in row.evidence
            if item.get("field")
            not in snapshot_guests[str(item.get("guest_id"))]["organizer_only_fields"]
        ],
        missing_information={
            guest_id: shareable_missing_fields(snapshot_guests[guest_id])
            for guest_id in row.benefits
        },
        uncertainty="Guests have not confirmed whether this connection is valuable to them.",
        shareable_reasons=row.shareable_reasons,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,  # type: ignore[arg-type]
    )


def resources(request: Request) -> tuple[async_sessionmaker[AsyncSession], ConsoleAdapter]:
    sessions = getattr(request.app.state, "matching_sessions", None)
    console = getattr(request.app.state, "console_adapter", None)
    if sessions is None or console is None:
        raise HTTPException(status_code=503, detail="matching_storage_unavailable")
    return sessions, console


async def scoped_console(console: ConsoleAdapter, organization_id: UUID, event_id: UUID) -> None:
    if await console.event_organization(event_id) != organization_id:
        raise HTTPException(status_code=404, detail="event_not_found")


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=RunAccepted)
async def create_run(
    body: CreateRun,
    request: Request,
    organization_id: Org,
    eventId: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> RunAccepted:
    sessions, console = resources(request)
    await scoped_console(console, organization_id, eventId)
    try:
        settings = request.app.state.settings
        run = await submit_run(
            sessions,
            console,
            organization_id,
            eventId,
            idempotency_key,
            body,
            provenance_from_settings(settings),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RunAccepted.model_validate({"run_id": run.id, "status": run.status})


@router.get("/{run_id}")
async def get_run(
    run_id: UUID,
    request: Request,
    organization_id: Org,
    eventId: UUID,
) -> dict[str, object]:
    sessions, console = resources(request)
    await scoped_console(console, organization_id, eventId)
    run = await scoped_run(sessions, organization_id, eventId, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return {
        "runId": run.id,
        "status": run.status,
        "progress": run.progress,
        "provenance": run.provenance,
        "usage": run.usage,
        "failure": (
            {"code": run.failure_code, "message": run.failure_message} if run.failure_code else None
        ),
        "createdAt": run.created_at,
    }


@router.get("/{run_id}/results", response_model=ResultsResponse)
async def get_results(
    run_id: UUID,
    request: Request,
    organization_id: Org,
    eventId: UUID,
) -> ResultsResponse:
    sessions, console = resources(request)
    await scoped_console(console, organization_id, eventId)
    run = await scoped_run(sessions, organization_id, eventId, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    rows = await run_recommendations(sessions, organization_id, eventId)
    items = [row for row in rows if row.source_run_id == run_id]
    snapshot_guests = {str(guest["id"]): guest for guest in run.snapshot["console"]["guests"]}
    guest_reasons = run.provenance.get("guest_reasons", {})
    return ResultsResponse(
        run_id=run.id,
        status=run.status,
        snapshot_fingerprint=run.fingerprint,
        source_run_id=run.id,
        guest_reasons=guest_reasons,
        recommendations=[result_item(row, snapshot_guests) for row in items],
    )
