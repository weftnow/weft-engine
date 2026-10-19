"""Opt-in PostgreSQL integration tests for F07 change consumption.

They run only against an explicitly supplied disposable database:

    WEFT_ENGINE_DATABASE_TEST=1
    WEFT_ENGINE_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host/weft_engine_test

The database name must contain "test". The target must not already contain Console tables; the
fixture creates minimal Console-shaped ``public`` tables, applies migrations 0001-0002 with a
fake provider, and drops everything it created afterwards. Never point this at a shared,
preview or production database.
"""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Environment, Settings
from src.main import create_app
from src.matching import changes
from src.matching.console import ConsoleAdapter
from src.matching.models import ChangeBatch, ChangeReceipt, FeedEntry, Recommendation, Run
from src.matching.schemas import Evidence, EvidenceVerification, PairEvaluation, PairEvaluationBatch
from src.matching.worker import MatchingWorker

ROOT = Path(__file__).parents[1]
URL = os.environ.get("WEFT_ENGINE_TEST_DATABASE_URL", "")
ENABLED = os.environ.get("WEFT_ENGINE_DATABASE_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not ENABLED or not URL,
    reason="set WEFT_ENGINE_DATABASE_TEST=1 and WEFT_ENGINE_TEST_DATABASE_URL (disposable database)",
)

ORG = UUID("10000000-0000-0000-0000-000000000001")
OTHER_ORG = UUID("10000000-0000-0000-0000-000000000002")
EVENT = UUID("20000000-0000-0000-0000-000000000001")
OTHER_EVENT = UUID("20000000-0000-0000-0000-000000000002")
GUEST_A = UUID("30000000-0000-0000-0000-000000000001")
GUEST_B = UUID("30000000-0000-0000-0000-000000000002")
GUEST_C = UUID("30000000-0000-0000-0000-000000000003")
TOKEN = "integration-secret"

CONSOLE_TABLES = (
    "event_matching_changes",
    "event_guest_match_blocks",
    "event_guest_profile_versions",
    "event_guests",
    "events",
)
CONSOLE_DDL = (
    """CREATE TABLE public.events (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, name text NOT NULL DEFAULT 'Event',
      description text NOT NULL DEFAULT '', city text NOT NULL DEFAULT 'City',
      categories text[] NOT NULL DEFAULT '{}', expected_audience text[] NOT NULL DEFAULT '{}')""",
    """CREATE TABLE public.event_guests (
      id uuid PRIMARY KEY, event_id uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
      person_id uuid NOT NULL, revision integer NOT NULL DEFAULT 1,
      profile_version integer NOT NULL DEFAULT 1, networking_version integer NOT NULL DEFAULT 1,
      networking_status text NOT NULL DEFAULT 'included', guest_type text NOT NULL DEFAULT 'Attendee',
      linkedin text)""",
    """CREATE TABLE public.event_guest_profile_versions (
      guest_id uuid NOT NULL, version integer NOT NULL, summary text, goals text, offers text,
      desired_connections text, avoid text, background text, linkedin_details text,
      missing_details text[] NOT NULL DEFAULT '{}', organizer_only_fields text[] NOT NULL DEFAULT '{}',
      PRIMARY KEY (guest_id, version))""",
    """CREATE TABLE public.event_guest_match_blocks (
      event_id uuid NOT NULL, guest_low_id uuid NOT NULL, guest_high_id uuid NOT NULL,
      PRIMARY KEY (event_id, guest_low_id, guest_high_id))""",
    """CREATE TABLE public.event_matching_changes (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      event_id uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
      kind text NOT NULL, guest_ids uuid[] NOT NULL, actor_id uuid, reason text,
      created_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz)""",
)


class FakeProvider:
    """Deterministic stand-in for the OpenAI client; scores every pair 85 with exact quotes."""

    def __init__(self) -> None:
        self.embeddings = SimpleNamespace(create=self._embed)
        self.responses = SimpleNamespace(parse=self._parse)

    async def _embed(self, *, model: str, input: list[str]) -> Any:
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=len(input)),
            data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in input],
        )

    async def _parse(self, *, text_format: Any, input: str, **_: Any) -> Any:
        usage = SimpleNamespace(input_tokens=10, output_tokens=10)
        payload = json.loads(input)
        if text_format is PairEvaluationBatch:
            pairs = []
            for item in payload:
                first, second = UUID(item["guest_a_id"]), UUID(item["guest_b_id"])
                pairs.append(
                    PairEvaluation(
                        guest_a_id=first,
                        guest_b_id=second,
                        benefit_a="Can learn from the other guest's work.",
                        benefit_b="Can share expertise with the other guest.",
                        score_a=85,
                        score_b=85,
                        evidence=[
                            Evidence(
                                guest_id=first, field="summary", quote=item["guest_a"]["summary"]
                            ),
                            Evidence(
                                guest_id=second, field="summary", quote=item["guest_b"]["summary"]
                            ),
                        ],
                        missing_information_a=[],
                        missing_information_b=[],
                        uncertainty="Interest is unconfirmed.",
                        restriction_found=False,
                    )
                )
            return SimpleNamespace(
                id="fake", usage=usage, output_parsed=PairEvaluationBatch(pairs=pairs)
            )
        evidence = payload["evidence"]
        return SimpleNamespace(
            id="fake",
            usage=usage,
            output_parsed=EvidenceVerification(
                supported=True,
                valid_evidence_indexes=list(range(len(evidence))),
                shareable_reasons={item["guest_id"]: "Shared interest." for item in evidence},
            ),
        )


@dataclass
class World:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    console: ConsoleAdapter
    settings: Settings

    def worker(self) -> MatchingWorker:
        return MatchingWorker(self.sessions, self.console, self.settings, client=FakeProvider())  # type: ignore[arg-type]

    async def sql(self, statement: str, **values: Any) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(text(statement), values)

    async def scalar(self, statement: str, **values: Any) -> Any:
        async with self.engine.connect() as connection:
            return await connection.scalar(text(statement), values)

    async def seed_event(self, event_id: UUID, org: UUID, summaries: dict[UUID, str]) -> None:
        await self.sql(
            "INSERT INTO public.events(id, organization_id) VALUES (:e, :o)", e=event_id, o=org
        )
        for guest_id, summary in summaries.items():
            await self.sql(
                "INSERT INTO public.event_guests(id, event_id, person_id) VALUES (:g, :e, :p)",
                g=guest_id,
                e=event_id,
                p=uuid4(),
            )
            await self.sql(
                "INSERT INTO public.event_guest_profile_versions(guest_id, version, summary) "
                "VALUES (:g, 1, :s)",
                g=guest_id,
                s=summary,
            )

    async def add_change(
        self, event_id: UUID, kind: str, guests: list[UUID], age_seconds: int = 0
    ) -> UUID:
        change_id = uuid4()
        await self.sql(
            "INSERT INTO public.event_matching_changes(id, event_id, kind, guest_ids, created_at) "
            "VALUES (:i, :e, :k, :g, now() - (:age * interval '1 second'))",
            i=change_id,
            e=event_id,
            k=kind,
            g=guests,
            age=age_seconds,
        )
        return change_id

    async def exclude(self, guest_id: UUID, excluded: bool = True) -> None:
        await self.sql(
            "UPDATE public.event_guests SET networking_status=:s, "
            "networking_version=networking_version+1 WHERE id=:g",
            s="excluded" if excluded else "included",
            g=guest_id,
        )

    async def cycle(self) -> None:
        await changes.ingest(self.sessions, self.console, 500)
        await changes.settle(self.sessions, self.settings)
        await changes.schedule(self.sessions, self.console, self.settings)

    async def runs(self) -> list[Run]:
        async with self.sessions() as session:
            return list(await session.scalars(select(Run).order_by(Run.created_at, Run.id)))

    async def batches(self) -> list[ChangeBatch]:
        async with self.sessions() as session:
            return list(await session.scalars(select(ChangeBatch).order_by(ChangeBatch.created_at)))

    async def feed(self, event_id: UUID = EVENT) -> list[tuple[str, UUID]]:
        async with self.sessions() as session:
            rows = await session.execute(
                select(FeedEntry.kind, FeedEntry.recommendation_id)
                .where(FeedEntry.event_id == event_id)
                .order_by(FeedEntry.seq)
            )
            return [(kind, recommendation_id) for kind, recommendation_id in rows]


def apply_migrations() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("path_separator", "os")
    command.upgrade(config, "head")


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[World]:
    name = make_url(URL).database or ""
    if "test" not in name:
        pytest.skip("refusing a database whose name does not contain 'test'")
    engine = create_async_engine(URL, hide_parameters=True)
    try:
        if await _scalar(engine, "SELECT to_regclass('public.events')") is not None:
            pytest.skip(
                "target already contains Console tables; supply an empty disposable database"
            )
        await _execute(engine, "DROP SCHEMA IF EXISTS weft_engine CASCADE")
        for statement in CONSOLE_DDL:
            await _execute(engine, statement)
        monkeypatch.setenv("WEFT_MATCHING_DATABASE_URL", URL)
        await asyncio.to_thread(apply_migrations)
        settings = Settings(
            _env_file=None,
            environment=Environment.TEST,
            matching_automatic_enabled=True,
            matching_change_quiet_seconds=0,
            matching_change_max_wait_seconds=0,
            matching_max_spend_usd=100.0,
            matching_input_cost_per_million_usd=1.0,
            matching_output_cost_per_million_usd=1.0,
            matching_embedding_cost_per_million_usd=1.0,
            matching_service_tokens={TOKEN: [str(ORG)]},
        )
        sessions = async_sessionmaker(
            create_async_engine(URL, hide_parameters=True), expire_on_commit=False
        )
        yield World(engine, sessions, ConsoleAdapter(engine), settings)
        await sessions.kw["bind"].dispose()
    finally:
        await _execute(engine, "DROP SCHEMA IF EXISTS weft_engine CASCADE")
        for table in CONSOLE_TABLES:
            await _execute(engine, f"DROP TABLE IF EXISTS public.{table} CASCADE")
        await engine.dispose()


async def _execute(engine: AsyncEngine, statement: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(statement))


async def _scalar(engine: AsyncEngine, statement: str) -> Any:
    async with engine.connect() as connection:
        return await connection.scalar(text(statement))


SUMMARIES = {
    GUEST_A: "Building open-source payments tools for rural clinics",
    GUEST_B: "Running clinic payment deployments across rural regions",
    GUEST_C: "Training community health workers on mobile tools",
}


async def receipt_count(world: World) -> int:
    async with world.sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(ChangeReceipt)) or 0)


async def test_receipts_are_idempotent_and_changes_are_marked_processed(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    first = await world.add_change(EVENT, "profile_updated", [GUEST_A])
    assert await changes.ingest(world.sessions, world.console, 500) == 1
    assert await receipt_count(world) == 1
    assert (
        await world.scalar(
            "SELECT count(*) FROM public.event_matching_changes WHERE processed_at IS NULL"
        )
        == 0
    )
    # Re-reading the same row (as after a crash) must not add a second receipt.
    await world.sql(
        "UPDATE public.event_matching_changes SET processed_at=NULL WHERE id=:i", i=first
    )
    await changes.ingest(world.sessions, world.console, 500)
    assert await receipt_count(world) == 1


async def test_crash_between_receipt_and_processed_at_leaves_no_duplicates(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    for guest_id in (GUEST_A, GUEST_B):
        await world.add_change(EVENT, "profile_updated", [guest_id])

    class Crashing(ConsoleAdapter):
        async def mark_changes_processed(self, change_ids: list[UUID]) -> None:
            raise RuntimeError("worker died before marking rows")

    with pytest.raises(RuntimeError):
        await changes.ingest(world.sessions, Crashing(world.engine), 500)
    assert await receipt_count(world) == 2
    assert await changes.ingest(world.sessions, world.console, 500) == 2
    assert await receipt_count(world) == 2
    await world.cycle()
    assert len(await world.runs()) == 1


async def test_changes_inside_the_quiet_period_coalesce_into_one_run(world: World) -> None:
    quiet = world.settings.model_copy(
        update={"matching_change_quiet_seconds": 30, "matching_change_max_wait_seconds": 300}
    )
    await world.seed_event(EVENT, ORG, SUMMARIES)
    for guest_id in (GUEST_A, GUEST_B, GUEST_C, GUEST_A, GUEST_B):
        await world.add_change(EVENT, "profile_updated", [guest_id], age_seconds=5)
    await changes.ingest(world.sessions, world.console, 500)
    assert await changes.schedule(world.sessions, world.console, quiet) == 0
    await world.sql(
        "UPDATE weft_engine.matching_change_receipts SET change_created_at = now() - interval '60 seconds'"
    )
    assert await changes.schedule(world.sessions, world.console, quiet) == 1
    assert await changes.schedule(world.sessions, world.console, quiet) == 0
    runs = await world.runs()
    assert len(runs) == 1
    assert runs[0].trigger == "change"
    assert runs[0].provenance["lifecycle_source"] == "console_none_recorded"
    assert runs[0].snapshot["lifecycle"]["complete"] is True
    attached = await world.scalar(
        "SELECT count(*) FROM weft_engine.matching_change_receipts WHERE batch_id IS NOT NULL"
    )
    assert attached == 5


async def test_two_workers_never_double_schedule(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await changes.ingest(world.sessions, world.console, 500)
    results = await asyncio.gather(
        *(changes.schedule(world.sessions, world.console, world.settings) for _ in range(4))
    )
    assert sum(results) == 1
    assert len(await world.runs()) == 1
    assert len(await world.batches()) == 1


async def test_transient_failure_retries_with_backoff_then_completes(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    [first] = await world.runs()
    await world.sql(
        "UPDATE weft_engine.matching_runs SET status='failed', failure_code='provider_failure', "
        "finished_at=now() WHERE id=:i",
        i=first.id,
    )
    await changes.settle(world.sessions, world.settings)
    delay = await world.scalar(
        "SELECT extract(epoch FROM next_attempt_at - now()) FROM weft_engine.matching_change_batches"
    )
    assert 50 < delay <= 60
    await changes.schedule(world.sessions, world.console, world.settings)
    assert len(await world.runs()) == 1
    await world.sql(
        "UPDATE weft_engine.matching_change_batches SET next_attempt_at = now() - interval '1 second'"
    )
    await changes.schedule(world.sessions, world.console, world.settings)
    runs = await world.runs()
    assert [run.idempotency_key for run in runs] == [
        f"f07:{first.change_batch_id}:1",
        f"f07:{first.change_batch_id}:2",
    ]
    await world.sql(
        "UPDATE weft_engine.matching_runs SET status='finished', finished_at=now() WHERE id=:i",
        i=runs[1].id,
    )
    await changes.settle(world.sessions, world.settings)
    [batch] = await world.batches()
    assert (batch.state, batch.attempt) == ("completed", 2)


async def test_configuration_failure_is_abandoned_without_retry(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    [run] = await world.runs()
    await world.sql(
        "UPDATE weft_engine.matching_runs SET status='failed', "
        "failure_code='spend_budget_unconfigured', finished_at=now() WHERE id=:i",
        i=run.id,
    )
    await world.cycle()
    [batch] = await world.batches()
    assert (batch.state, batch.abandon_reason) == ("abandoned", "spend_budget_unconfigured")
    assert len(await world.runs()) == 1


async def test_stale_snapshot_reruns_immediately_within_the_cap(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    [first] = await world.runs()
    await world.sql(
        "UPDATE weft_engine.matching_runs SET status='invalid_result', "
        "failure_code='snapshot_stale', finished_at=now() WHERE id=:i",
        i=first.id,
    )
    await world.cycle()
    assert len(await world.runs()) == 2
    [batch] = await world.batches()
    assert batch.attempt == 2


async def test_exclusion_revokes_frees_capacity_and_pair_is_never_reissued(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    assert await world.worker().process_one() is True
    [first] = await world.runs()
    assert first.status == "finished"
    issued = await world.feed()
    assert [kind for kind, _ in issued] == ["issued"] * 3

    await world.cycle()  # settles the first batch
    await world.exclude(GUEST_A)
    await world.add_change(EVENT, "guest_excluded", [GUEST_A])
    await world.cycle()
    second = (await world.runs())[1]
    async with world.sessions() as session:
        revoked = list(
            await session.scalars(
                select(Recommendation).where(Recommendation.revoked_at.is_not(None))
            )
        )
    assert len(revoked) == 2
    assert {row.revocation_reason for row in revoked} == {"guest_excluded"}
    assert {row.revoked_by_run_id for row in revoked} == {second.id}
    assert [kind for kind, _ in await world.feed()].count("revoked") == 2

    assert await world.worker().process_one() is True
    await world.cycle()
    await world.exclude(GUEST_A, excluded=False)
    await world.add_change(EVENT, "guest_restored", [GUEST_A])
    await world.cycle()
    assert await world.worker().process_one() is True
    kinds = [kind for kind, _ in await world.feed()]
    assert kinds.count("issued") == 3, "a revoked pair must not be issued again"
    async with world.sessions() as session:
        total = await session.scalar(select(func.count()).select_from(Recommendation))
    assert total == 3


async def test_exclusion_is_revoked_at_schedule_time_before_any_provider_work(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    assert await world.worker().process_one() is True
    await world.cycle()
    # No worker processes the new run: revocation must already be committed at schedule time.
    await world.exclude(GUEST_B)
    await world.add_change(EVENT, "guest_excluded", [GUEST_B])
    await world.cycle()
    async with world.sessions() as session:
        revoked = await session.scalar(
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.revoked_at.is_not(None))
        )
    assert revoked == 2


async def test_feed_pages_in_order_and_is_scoped_by_event_and_organization(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.seed_event(OTHER_EVENT, OTHER_ORG, {uuid4(): "Other event guest profile text"})
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    assert await world.worker().process_one() is True
    async with world.sessions() as session:
        first, guests = await changes.feed_page(session, ORG, EVENT, 0, 2)
        rest, _ = await changes.feed_page(session, ORG, EVENT, first[-1][0].seq, 2)
        none_for_other_org, _ = await changes.feed_page(session, OTHER_ORG, EVENT, 0, 10)
        none_for_other_event, _ = await changes.feed_page(session, ORG, OTHER_EVENT, 0, 10)
    seqs = [entry.seq for entry, _ in first + rest]
    assert len(first) == 2 and len(rest) == 1
    assert seqs == sorted(seqs) and len(set(seqs)) == 3
    assert none_for_other_org == [] and none_for_other_event == []
    assert set(guests) == {first[0][1].source_run_id}


async def test_status_and_feed_endpoints_report_the_event_lifecycle(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    app = create_app(
        world.settings.model_copy(
            update={"matching_database_url": None, "console_database_url": None}
        )
    )
    app.state.matching_sessions = world.sessions
    app.state.console_adapter = world.console
    headers = {"X-Weft-Service-Token": TOKEN}
    base = f"/v1/organizations/{ORG}/events/{EVENT}/matching"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        idle = (await client.get(f"{base}/status", headers=headers)).json()
        assert (idle["state"], idle["pendingChanges"], idle["latestRun"]) == ("idle", 0, None)
        await world.add_change(EVENT, "profile_updated", [GUEST_A])
        waiting = (await client.get(f"{base}/status", headers=headers)).json()
        assert (waiting["state"], waiting["pendingChanges"]) == ("waiting", 1)
        await world.cycle()
        running_or_waiting = (await client.get(f"{base}/status", headers=headers)).json()
        assert running_or_waiting["latestRun"]["trigger"] == "change"
        assert running_or_waiting["state"] == "waiting"
        assert await world.worker().process_one() is True
        await world.cycle()
        done = (await client.get(f"{base}/status", headers=headers)).json()
        assert (done["state"], done["pendingChanges"]) == ("finished", 0)
        assert done["lastFinishedRunId"] == done["latestRun"]["runId"]
        page = (await client.get(f"{base}/feed", params={"limit": 2}, headers=headers)).json()
        assert len(page["entries"]) == 2
        rest = (
            await client.get(f"{base}/feed", params={"after": page["nextCursor"]}, headers=headers)
        ).json()
        assert len(rest["entries"]) == 1
        end = (
            await client.get(f"{base}/feed", params={"after": rest["nextCursor"]}, headers=headers)
        ).json()
        assert end == {"entries": [], "nextCursor": rest["nextCursor"]}
        wrong_org = base.replace(str(ORG), str(OTHER_ORG))
        assert (await client.get(f"{wrong_org}/feed", headers=headers)).status_code == 403
