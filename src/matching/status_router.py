"""Authenticated per-event matching status and recommendation feed (F07)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from src.matching import changes
from src.matching.router import Org, resources, result_item, scoped_console
from src.matching.schemas import FeedEntryOut, FeedResponse, MatchingStatus

router = APIRouter(
    prefix="/v1/organizations/{organizationId}/events/{eventId}/matching", tags=["matching"]
)


@router.get("/status", response_model=MatchingStatus)
async def get_status(request: Request, organization_id: Org, eventId: UUID) -> MatchingStatus:
    sessions, console = resources(request)
    await scoped_console(console, organization_id, eventId)
    async with sessions() as session:
        status = await changes.event_status(
            session,
            console,
            organization_id,
            eventId,
            request.app.state.settings.matching_automatic_enabled,
        )
    return MatchingStatus.model_validate(status)


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    request: Request,
    organization_id: Org,
    eventId: UUID,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> FeedResponse:
    sessions, console = resources(request)
    await scoped_console(console, organization_id, eventId)
    async with sessions() as session:
        page, guests_by_run = await changes.feed_page(
            session, organization_id, eventId, after, limit
        )
    return FeedResponse(
        entries=[
            FeedEntryOut(
                seq=entry.seq,
                kind=entry.kind,  # type: ignore[arg-type]
                run_id=entry.run_id,
                recommendation=result_item(row, guests_by_run[row.source_run_id]),
            )
            for entry, row in page
        ],
        next_cursor=page[-1][0].seq if page else after,
    )
