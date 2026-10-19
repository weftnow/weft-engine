"""Adapter over Console-owned public PostgreSQL records.

It reads the matching projection and the change log. The only Console write it performs is
setting ``processed_at`` on change rows, which the engine's Console role may update by column.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True)
class ChangeRow:
    """One unprocessed ``public.event_matching_changes`` row; carries no profile content."""

    id: UUID
    event_id: UUID
    kind: str
    guest_ids: list[UUID]
    created_at: datetime


class ConsoleAdapter:
    """Reads the minimal matching projection and the change log; writes only processed_at."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def event_organization(self, event_id: UUID) -> UUID | None:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT organization_id FROM public.events WHERE id=:event_id"),
                {"event_id": event_id},
            )
        return UUID(str(value)) if value else None

    async def pending_changes(self, limit: int) -> list[ChangeRow]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text("""
                SELECT id, event_id, kind::text AS kind, guest_ids, created_at
                FROM public.event_matching_changes WHERE processed_at IS NULL
                ORDER BY created_at, id LIMIT :limit
            """),
                    {"limit": limit},
                )
            ).all()
        return [
            ChangeRow(
                id=UUID(str(row.id)),
                event_id=UUID(str(row.event_id)),
                kind=str(row.kind),
                guest_ids=[UUID(str(value)) for value in row.guest_ids],
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def mark_changes_processed(self, change_ids: list[UUID]) -> None:
        if not change_ids:
            return
        statement = text("""
            UPDATE public.event_matching_changes SET processed_at=now()
            WHERE id = ANY(:ids) AND processed_at IS NULL
        """).bindparams(bindparam("ids", type_=ARRAY(PGUUID(as_uuid=True))))
        async with self._engine.begin() as connection:
            await connection.execute(statement, {"ids": change_ids})

    async def unprocessed_change_count(self, event_id: UUID) -> int:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text("""
                SELECT count(*) FROM public.event_matching_changes
                WHERE event_id=:event_id AND processed_at IS NULL
            """),
                {"event_id": event_id},
            )
        return int(value or 0)

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
