"""Read-only adapter over Console-owned public PostgreSQL records."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class ConsoleAdapter:
    """Reads the minimal matching projection; never writes Console tables."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def event_organization(self, event_id: UUID) -> UUID | None:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT organization_id FROM public.events WHERE id=:event_id"),
                {"event_id": event_id},
            )
        return UUID(str(value)) if value else None

    async def snapshot(self, organization_id: UUID, event_id: UUID) -> dict[str, Any]:
        async with self._engine.connect() as connection:
            event = (
                (
                    await connection.execute(
                        text("""
                SELECT id, organization_id, name, description, city, categories, expected_audience
                FROM public.events WHERE id=:event_id AND organization_id=:organization_id
            """),
                        {"event_id": event_id, "organization_id": organization_id},
                    )
                )
                .mappings()
                .first()
            )
            if event is None:
                raise LookupError("event_not_found")
            guests = (
                (
                    await connection.execute(
                        text("""
                SELECT g.id, g.person_id, g.revision, g.profile_version, g.networking_version,
                       g.networking_status, g.guest_type,
                       (g.linkedin IS NOT NULL AND btrim(g.linkedin) <> '') AS linkedin_url_only,
                       p.summary, p.goals, p.offers, p.desired_connections, p.avoid, p.background,
                       p.linkedin_details, p.missing_details, p.organizer_only_fields
                FROM public.event_guests AS g
                LEFT JOIN public.event_guest_profile_versions AS p
                  ON p.guest_id=g.id AND p.version=g.profile_version
                WHERE g.event_id=:event_id ORDER BY g.id
            """),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .all()
            )
            blocks = (
                await connection.execute(
                    text("""
                SELECT guest_low_id, guest_high_id
                FROM public.event_guest_match_blocks WHERE event_id=:event_id
            """),
                    {"event_id": event_id},
                )
            ).all()
        guest_items = [dict(row) for row in guests]
        person_counts: dict[UUID, int] = {}
        for guest in guest_items:
            person_id = UUID(str(guest["person_id"]))
            person_counts[person_id] = person_counts.get(person_id, 0) + 1
        for guest in guest_items:
            person_id = UUID(str(guest["person_id"]))
            guest["person_id"] = str(person_id)
            guest["id"] = str(guest["id"])
            guest["identity_resolution_required"] = person_counts[person_id] > 1
            guest["organizer_only_fields"] = list(guest["organizer_only_fields"] or [])
            for key in ("linkedin_url_only",):
                guest[key] = bool(guest[key])
        return {
            "event": {
                key: (str(value) if isinstance(value, UUID) else value)
                for key, value in event.items()
            },
            "guests": guest_items,
            "blocked_pairs": [sorted((str(low), str(high))) for low, high in blocks],
        }
