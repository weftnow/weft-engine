"""Opt-in PostgreSQL integration tests against Neon ``weft_console_test``.

They run only against an explicitly supplied disposable database:

    WEFT_ENGINE_DATABASE_TEST=1
    WEFT_ENGINE_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host/weft_console_test

The fixture preserves Console tables and existing rows, uses generated synthetic IDs, upgrades
only ``weft_engine``, and removes only the synthetic rows it creates. It must never run against
local, production, preview, or another database.
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
from src.matching.compact import Judgment, JudgmentBatch, judgment_fingerprint
from src.matching.console import ConsoleAdapter
from src.matching.models import (
    Attempt,
    BudgetReservation,
    ChangeBatch,
    ChangeReceipt,
    EvaluationCache,
    FeedEntry,
    Recommendation,
    Run,
    ScreeningCache,
)
from src.matching.schemas import Evidence, EvidenceVerification, PairEvaluation
from src.matching.storage import fingerprint
from src.matching.worker import MatchingWorker, WorkerFailure

ROOT = Path(__file__).parents[1]
URL = os.environ.get("WEFT_ENGINE_TEST_DATABASE_URL", "")
ENABLED = os.environ.get("WEFT_ENGINE_DATABASE_TEST") == "1"

ORG = uuid4()
OTHER_ORG = uuid4()
EVENT = uuid4()
OTHER_EVENT = uuid4()
GUEST_A = uuid4()
GUEST_B = uuid4()
GUEST_C = uuid4()
TOKEN = "integration-secret"


class FakeProvider:
    """Deterministic stand-in for the OpenAI client; scores every pair 85 with exact quotes."""

    def __init__(self) -> None:
        self.parse_calls = 0
        self.embeddings = SimpleNamespace(create=self._embed)
        self.responses = SimpleNamespace(parse=self._parse)

    async def _embed(self, *, model: str, input: list[str]) -> Any:
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=len(input)),
            data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in input],
        )

    async def _parse(self, *, text_format: Any, input: str, **_: Any) -> Any:
        self.parse_calls += 1
        usage = SimpleNamespace(input_tokens=10, output_tokens=10)
        payload = json.loads(input)
        if text_format is JudgmentBatch:
            pairs = []
            for item in payload["pairs"]:
                refs = [
                    f"{key}.{next(iter(payload['guests'][key]['facts']))}"
                    for key in (item["a"], item["b"])
                ]
                pairs.append(
                    Judgment(
                        ref=item["ref"],
                        a=85,
                        b=85,
                        ca="Can learn from the other guest's work.",
                        cb="Can share expertise with the other guest.",
                        ea=refs,
                        eb=refs,
                        r=False,
                        u="unconfirmed_interest",
                    )
                )
            return SimpleNamespace(id="fake", usage=usage, output_parsed=JudgmentBatch(pairs=pairs))
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
    actor_id: UUID

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
            "INSERT INTO public.organizations(id,name) VALUES (:o,:name)",
            o=org,
            name=f"Synthetic matching test {org}",
        )
        await self.sql(
            "INSERT INTO public.events(id,organization_id,creator_id,name,description,city,"
            "categories,expected_audience,start_date,end_date,timezone,starts_at,ends_at) "
            "VALUES (:e,:o,:actor,'Synthetic test event','Integration fixture','Las Vegas, USA',"
            "ARRAY['Technology']::text[],ARRAY[]::text[],'2026-01-01','2026-01-01','UTC',"
            "'2026-01-01T00:00:00Z','2026-01-01T23:59:59Z')",
            e=event_id,
            o=org,
            actor=self.actor_id,
        )
        for position, (guest_id, summary) in enumerate(summaries.items(), start=1):
            person_id = uuid4()
            await self.sql(
                "INSERT INTO public.event_people(id,event_id) VALUES (:p,:e)",
                p=person_id,
                e=event_id,
            )
            await self.sql(
                "INSERT INTO public.event_guests(id,event_id,person_id,position,first_name,last_name,"
                "email,normalized_email,phone,company,job_position,profile_type,linkedin,guest_type,"
                "source,profile_version) VALUES (:g,:e,:p,:position,:first,:last,:email,lower(:email),"
                "'','Synthetic company','Attendee','Attendee','','Attendee','manual',1)",
                g=guest_id,
                e=event_id,
                p=person_id,
                position=position,
                first=f"Synthetic{position}",
                last="Guest",
                email=f"{guest_id}@invalid.test",
            )
            await self.sql(
                "INSERT INTO public.event_guest_profile_versions("
                "event_id,guest_id,version,summary,created_by) VALUES (:e,:g,1,:s,:actor)",
                e=event_id,
                g=guest_id,
                s=summary,
                actor=self.actor_id,
            )

    async def add_change(
        self, event_id: UUID, kind: str, guests: list[UUID], age_seconds: int = 0
    ) -> UUID:
        change_id = uuid4()
        await self.sql(
            "INSERT INTO public.event_matching_changes("
            "id,event_id,kind,guest_ids,actor_id,created_at) "
            "VALUES (:i,:e,:k,:g,:actor,now() - (:age * interval '1 second'))",
            i=change_id,
            e=event_id,
            k=kind,
            g=guests,
            actor=self.actor_id,
            age=age_seconds,
        )
        return change_id

    async def exclude(self, guest_id: UUID, excluded: bool = True) -> None:
        if excluded:
            await self.sql(
                "UPDATE public.event_guests SET networking_status='excluded', "
                "networking_excluded_at=now(), networking_excluded_by=:actor, "
                "networking_exclusion_reason='other', "
                "networking_version=networking_version+1 WHERE id=:g",
                actor=self.actor_id,
                g=guest_id,
            )
        else:
            await self.sql(
                "UPDATE public.event_guests SET networking_status='included', "
                "networking_excluded_at=NULL, networking_excluded_by=NULL, "
                "networking_exclusion_reason=NULL, "
                "networking_version=networking_version+1 WHERE id=:g",
                g=guest_id,
            )

    async def cycle(self) -> None:
        event_ids = {EVENT, OTHER_EVENT}
        await changes.ingest(self.sessions, self.console, 500, event_ids=event_ids)
        await changes.settle(self.sessions, self.settings, event_ids=event_ids)
        await changes.schedule(self.sessions, self.console, self.settings, event_ids=event_ids)

    async def runs(self) -> list[Run]:
        async with self.sessions() as session:
            return list(
                await session.scalars(
                    select(Run).where(Run.event_id == EVENT).order_by(Run.created_at, Run.id)
                )
            )

    async def batches(self) -> list[ChangeBatch]:
        async with self.sessions() as session:
            return list(
                await session.scalars(
                    select(ChangeBatch)
                    .where(ChangeBatch.event_id == EVENT)
                    .order_by(ChangeBatch.created_at)
                )
            )

    async def feed(self, event_id: UUID | None = None) -> list[tuple[str, UUID]]:
        if event_id is None:
            event_id = EVENT
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


def _validated_database_url(raw_url: str) -> str:
    parsed_url = make_url(raw_url)
    if parsed_url.database != "weft_console_test" or not (parsed_url.host or "").endswith(
        ".neon.tech"
    ):
        raise ValueError("database tests are restricted to Neon database weft_console_test")
    query = {
        key: value
        for key, value in parsed_url.query.items()
        if key not in {"channel_binding", "sslmode"}
    }
    if parsed_url.query.get("sslmode") == "require":
        query["ssl"] = "require"
    if parsed_url.drivername in {"postgres", "postgresql"}:
        parsed_url = parsed_url.set(drivername="postgresql+asyncpg")
    return parsed_url.set(query=query).render_as_string(hide_password=False)


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[World]:
    if not ENABLED or not URL:
        pytest.skip(
            "set WEFT_ENGINE_DATABASE_TEST=1 and WEFT_ENGINE_TEST_DATABASE_URL "
            "for Neon weft-console-test"
        )
    for name in ("ORG", "OTHER_ORG", "EVENT", "OTHER_EVENT", "GUEST_A", "GUEST_B", "GUEST_C"):
        monkeypatch.setitem(globals(), name, uuid4())
    monkeypatch.setitem(
        globals(),
        "SUMMARIES",
        {
            GUEST_A: "Building open-source payments tools for rural clinics",
            GUEST_B: "Running clinic payment deployments across rural regions",
            GUEST_C: "Training community health workers on mobile tools",
        },
    )
    try:
        database_url = _validated_database_url(URL)
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    engine = create_async_engine(
        database_url, hide_parameters=True, pool_pre_ping=True, pool_recycle=60
    )
    sessions_engine = create_async_engine(
        database_url, hide_parameters=True, pool_pre_ping=True, pool_recycle=60
    )
    world_instance: World | None = None
    try:
        required_tables = (
            "events",
            "event_people",
            "event_guests",
            "event_guest_profile_versions",
            "event_guest_match_blocks",
            "event_matching_changes",
        )
        for table in required_tables:
            if await _scalar(engine, f"SELECT to_regclass('public.{table}')") is None:
                pytest.fail(f"Neon weft_console_test is missing public.{table}")
        actor_id = await _scalar(engine, "SELECT id FROM public.users ORDER BY id LIMIT 1")
        if actor_id is None:
            pytest.fail("Neon weft_console_test needs one existing user for Console foreign keys")
        monkeypatch.setenv("WEFT_MATCHING_DATABASE_URL", database_url)
        await asyncio.to_thread(apply_migrations)
        for table in (
            "matching_budget_reservations",
            "matching_verifications",
            "matching_screenings",
        ):
            if await _scalar(engine, f"SELECT to_regclass('weft_engine.{table}')") is None:
                pytest.fail(f"Neon weft-console-test migration is missing weft_engine.{table}")
        await cleanup_stale_synthetic_rows(engine)
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
        sessions = async_sessionmaker(sessions_engine, expire_on_commit=False)
        world_instance = World(
            engine, sessions, ConsoleAdapter(engine), settings, UUID(str(actor_id))
        )
    except Exception:
        await sessions_engine.dispose()
        await engine.dispose()
        pytest.fail(
            "Could not initialize Neon weft-console-test; database error details are suppressed "
            "to protect connection credentials.",
            pytrace=False,
        )

    assert world_instance is not None
    try:
        yield world_instance
    finally:
        try:
            await cleanup_world(world_instance)
        except Exception:
            pytest.fail(
                "Could not clean synthetic rows from Neon weft-console-test; "
                "database error details are suppressed to protect connection credentials.",
                pytrace=False,
            )
        finally:
            await sessions_engine.dispose()
            await engine.dispose()


async def cleanup_world(world: World) -> None:
    """Remove only synthetic event-scoped rows; retain Console and engine schemas."""
    event_ids = [EVENT, OTHER_EVENT]
    await cleanup_synthetic_rows(world.engine, event_ids, [ORG, OTHER_ORG])


async def cleanup_stale_synthetic_rows(engine: AsyncEngine) -> None:
    """Recover test-owned synthetic rows left by an interrupted previous test process."""
    async with engine.connect() as connection:
        org_ids = list(
            await connection.scalars(
                text(
                    "SELECT id FROM public.organizations WHERE name LIKE 'Synthetic matching test %'"
                )
            )
        )
        if not org_ids:
            return
        event_ids = list(
            await connection.scalars(
                text(
                    "SELECT id FROM public.events WHERE organization_id = ANY(:orgs) "
                    "AND name='Synthetic test event' AND description='Integration fixture'"
                ),
                {"orgs": org_ids},
            )
        )
    await cleanup_synthetic_rows(engine, event_ids, org_ids)


async def cleanup_synthetic_rows(
    engine: AsyncEngine, event_ids: list[UUID], org_ids: list[UUID]
) -> None:
    """Delete only synthetic test events and their engine-owned records."""
    async with engine.begin() as connection:
        for table in (
            "matching_feed_entries",
            "recommendations",
            "matching_verifications",
            "matching_screenings",
            "matching_embeddings",
            "matching_evaluations",
            "matching_change_receipts",
            "matching_slot_grants",
        ):
            await connection.execute(
                text(f"DELETE FROM weft_engine.{table} WHERE event_id = ANY(:events)"),
                {"events": event_ids},
            )
        await connection.execute(
            text(
                "DELETE FROM weft_engine.matching_budget_reservations "
                "WHERE run_id IN (SELECT id FROM weft_engine.matching_runs "
                "WHERE event_id = ANY(:events))"
            ),
            {"events": event_ids},
        )
        await connection.execute(
            text(
                "DELETE FROM weft_engine.matching_attempts "
                "WHERE run_id IN (SELECT id FROM weft_engine.matching_runs "
                "WHERE event_id = ANY(:events))"
            ),
            {"events": event_ids},
        )
        await connection.execute(
            text(
                "UPDATE weft_engine.matching_runs SET change_batch_id=NULL "
                "WHERE event_id = ANY(:events)"
            ),
            {"events": event_ids},
        )
        await connection.execute(
            text(
                "UPDATE weft_engine.matching_change_batches SET last_run_id=NULL "
                "WHERE event_id = ANY(:events)"
            ),
            {"events": event_ids},
        )
        await connection.execute(
            text("DELETE FROM weft_engine.matching_change_batches WHERE event_id = ANY(:events)"),
            {"events": event_ids},
        )
        await connection.execute(
            text("DELETE FROM weft_engine.matching_runs WHERE event_id = ANY(:events)"),
            {"events": event_ids},
        )
        for table in (
            "event_matching_changes",
            "event_guest_match_blocks",
            "event_guest_profile_versions",
            "event_guests",
            "event_people",
        ):
            await connection.execute(
                text(f"DELETE FROM public.{table} WHERE event_id = ANY(:events)"),
                {"events": event_ids},
            )
        await connection.execute(
            text("DELETE FROM public.events WHERE id = ANY(:events)"),
            {"events": event_ids},
        )
        await connection.execute(
            text("DELETE FROM public.organizations WHERE id = ANY(:orgs)"),
            {"orgs": org_ids},
        )


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
        return int(
            await session.scalar(
                select(func.count())
                .select_from(ChangeReceipt)
                .where(ChangeReceipt.event_id == EVENT)
            )
            or 0
        )


def test_database_target_requires_the_named_neon_test_database() -> None:
    url = _validated_database_url(
        "postgresql://test:secret@ep-example-pooler.us-east-2.aws.neon.tech/"
        "weft_console_test?sslmode=require&channel_binding=require"
    )
    assert url.startswith(
        "postgresql+asyncpg://test:secret@ep-example-pooler.us-east-2.aws.neon.tech/"
    )
    assert "channel_binding" not in url
    assert "ssl=require" in url

    with pytest.raises(ValueError, match="restricted to Neon database"):
        _validated_database_url("postgresql://user:secret@localhost/weft_console_test")
    with pytest.raises(ValueError, match="restricted to Neon database"):
        _validated_database_url(
            "postgresql://user:secret@ep-example.us-east-2.aws.neon.tech/production"
        )


async def _budget_test_run(world: World, max_spend_usd: float) -> tuple[Run, MatchingWorker]:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await world.cycle()
    [run] = await world.runs()
    settings = world.settings.model_copy(update={"matching_max_spend_usd": max_spend_usd})
    worker = MatchingWorker(world.sessions, world.console, settings, client=FakeProvider())  # type: ignore[arg-type]
    worker._run_id = run.id
    return run, worker


async def _add_attempts(world: World, run_id: UUID, count: int) -> list[UUID]:
    ids = [uuid4() for _ in range(count)]
    async with world.sessions() as session, session.begin():
        for attempt_id in ids:
            session.add(
                Attempt(
                    id=attempt_id,
                    run_id=run_id,
                    kind="pair_evaluation_batch",
                    status="running",
                    model="test-model",
                    prompt_version="test-v1",
                    input_fingerprint=str(attempt_id),
                )
            )
    return ids


async def test_budget_reservations_serialize_concurrent_admission(world: World) -> None:
    run, worker = await _budget_test_run(world, max_spend_usd=0.000015)
    first, second = await _add_attempts(world, run.id, 2)

    async def reserve(attempt_id: UUID) -> bool:
        try:
            await worker.budget_check(10, input_rate=1.0, attempt_id=attempt_id)
            return True
        except WorkerFailure as error:
            assert error.code == "spend_budget_exhausted"
            return False

    results = await asyncio.gather(reserve(first), reserve(second))
    assert sorted(results) == [False, True]
    async with world.sessions() as session:
        reservations = list(
            await session.scalars(
                select(BudgetReservation).where(BudgetReservation.run_id == run.id)
            )
        )
    assert len(reservations) == 1
    assert reservations[0].state == "reserved"


async def test_unknown_billing_reservation_remains_in_budget_after_recovery(world: World) -> None:
    run, worker = await _budget_test_run(world, max_spend_usd=0.000015)
    first, second = await _add_attempts(world, run.id, 2)
    await worker.budget_check(10, input_rate=1.0, attempt_id=first)
    await worker.record_usage(run.id, 0, 0, attempt_id=first, confirmed=False)

    recovered_worker = MatchingWorker(
        world.sessions,
        world.console,
        worker.settings,
        client=FakeProvider(),  # type: ignore[arg-type]
    )
    recovered_worker._run_id = run.id
    with pytest.raises(WorkerFailure, match="budget would be exceeded") as error:
        await recovered_worker.budget_check(10, input_rate=1.0, attempt_id=second)
    assert error.value.code == "spend_budget_exhausted"
    async with world.sessions() as session:
        reservation = await session.get(BudgetReservation, first)
    assert reservation is not None and reservation.state == "unknown"


async def test_confirmed_usage_settles_reservation_at_actual_cost(world: World) -> None:
    run, worker = await _budget_test_run(world, max_spend_usd=100.0)
    [attempt_id] = await _add_attempts(world, run.id, 1)
    await worker.budget_check(1, input_rate=1.0, attempt_id=attempt_id)

    cost = await worker.record_usage(run.id, 20, 10, input_rate=1.0, attempt_id=attempt_id)
    async with world.sessions() as session:
        reservation = await session.get(BudgetReservation, attempt_id)
        updated_run = await session.get(Run, run.id)
    assert reservation is not None
    assert reservation.state == "settled"
    assert float(reservation.reserved_cost_usd) == pytest.approx(cost)
    assert float(reservation.actual_cost_usd or 0) == pytest.approx(cost)
    assert updated_run is not None
    assert updated_run.usage["provider_confirmed_input_tokens"] == 20
    assert updated_run.usage["provider_confirmed_output_tokens"] == 10


async def test_screening_cache_entry_never_substitutes_for_full_evaluation(world: World) -> None:
    run, _ = await _budget_test_run(world, max_spend_usd=100.0)
    guest_a_id, guest_b_id = str(GUEST_A), str(GUEST_B)
    guests = {
        guest_a_id: {"id": guest_a_id, "summary": "Builds rural payment systems"},
        guest_b_id: {"id": guest_b_id, "summary": "Deploys clinic payment systems"},
    }
    pair = (min(guest_a_id, guest_b_id), max(guest_a_id, guest_b_id))
    payload = {
        "guest_a_id": pair[0],
        "guest_b_id": pair[1],
        "guest_a": guests[pair[0]],
        "guest_b": guests[pair[1]],
    }
    screen_attempt_id = uuid4()
    async with world.sessions() as session, session.begin():
        session.add(
            Attempt(
                id=screen_attempt_id,
                run_id=run.id,
                kind="candidate_screening",
                status="finished",
                model=world.settings.matching_evaluation_model,
                prompt_version="screen-test-v1",
                input_fingerprint=fingerprint(payload),
            )
        )
        session.add(
            ScreeningCache(
                id=uuid4(),
                organization_id=run.organization_id,
                event_id=run.event_id,
                input_fingerprint=fingerprint(payload),
                model=world.settings.matching_evaluation_model,
                screening_version="screen-test-v1",
                live_attempt_id=screen_attempt_id,
                result={"score_a": 95, "score_b": 95, "uncertain": False},
            )
        )

    provider = FakeProvider()
    worker = MatchingWorker(world.sessions, world.console, world.settings, client=provider)  # type: ignore[arg-type]
    worker._run_id = run.id
    result = await worker.evaluate_batch(run, guests, [pair])
    assert provider.parse_calls == 1
    assert pair in result
    async with world.sessions() as session:
        full_evaluation = await session.scalar(
            select(EvaluationCache).where(
                EvaluationCache.organization_id == run.organization_id,
                EvaluationCache.pair_fingerprint
                == judgment_fingerprint(run.event_id, pair, guests),
            )
        )
    assert full_evaluation is not None


async def test_verification_cache_reuse_is_scoped_by_privacy_context(world: World) -> None:
    run, _ = await _budget_test_run(world, max_spend_usd=100.0)
    provider = FakeProvider()
    worker = MatchingWorker(world.sessions, world.console, world.settings, client=provider)  # type: ignore[arg-type]
    worker._run_id = run.id
    pair = PairEvaluation(
        guest_a_id=GUEST_A,
        guest_b_id=GUEST_B,
        benefit_a="Can share rural payment deployment experience.",
        benefit_b="Can learn from open-source payment tools.",
        score_a=85,
        score_b=85,
        evidence=[
            Evidence(
                guest_id=GUEST_A,
                field="summary",
                quote=SUMMARIES[GUEST_A],
            ),
            Evidence(
                guest_id=GUEST_B,
                field="summary",
                quote=SUMMARIES[GUEST_B],
            ),
        ],
        missing_information_a=[],
        missing_information_b=[],
        uncertainty="Interest is unconfirmed.",
        restriction_found=False,
    )
    guests = {
        str(GUEST_A): {"summary": SUMMARIES[GUEST_A], "organizer_only_fields": []},
        str(GUEST_B): {"summary": SUMMARIES[GUEST_B], "organizer_only_fields": []},
    }

    await worker.verify_pair(run, pair, guests)
    await worker.verify_pair(run, pair, guests)
    assert provider.parse_calls == 1
    assert worker._verification_cache_hits == 1

    # Even an organizer-only field unrelated to these quotes creates a separate cache context.
    guests[str(GUEST_A)]["organizer_only_fields"] = ["privateNotes"]
    await worker.verify_pair(run, pair, guests)
    assert provider.parse_calls == 2


async def test_receipts_are_idempotent_and_changes_are_marked_processed(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    first = await world.add_change(EVENT, "profile_updated", [GUEST_A])
    assert await changes.ingest(world.sessions, world.console, 500, event_ids={EVENT}) == 1
    assert await receipt_count(world) == 1
    assert (
        await world.scalar(
            "SELECT count(*) FROM public.event_matching_changes "
            "WHERE event_id=:e AND processed_at IS NULL",
            e=EVENT,
        )
        == 0
    )
    # Re-reading the same row (as after a crash) must not add a second receipt.
    await world.sql(
        "UPDATE public.event_matching_changes SET processed_at=NULL WHERE id=:i", i=first
    )
    await changes.ingest(world.sessions, world.console, 500, event_ids={EVENT})
    assert await receipt_count(world) == 1


async def test_crash_between_receipt_and_processed_at_leaves_no_duplicates(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    for guest_id in (GUEST_A, GUEST_B):
        await world.add_change(EVENT, "profile_updated", [guest_id])

    class Crashing(ConsoleAdapter):
        async def mark_changes_processed(self, change_ids: list[UUID]) -> None:
            raise RuntimeError("worker died before marking rows")

    with pytest.raises(RuntimeError):
        await changes.ingest(world.sessions, Crashing(world.engine), 500, event_ids={EVENT})
    assert await receipt_count(world) == 2
    assert await changes.ingest(world.sessions, world.console, 500, event_ids={EVENT}) == 2
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
    await changes.ingest(world.sessions, world.console, 500, event_ids={EVENT})
    assert await changes.schedule(world.sessions, world.console, quiet, event_ids={EVENT}) == 0
    await world.sql(
        "UPDATE weft_engine.matching_change_receipts "
        "SET change_created_at = now() - interval '60 seconds' WHERE event_id=:e",
        e=EVENT,
    )
    assert await changes.schedule(world.sessions, world.console, quiet, event_ids={EVENT}) == 1
    assert await changes.schedule(world.sessions, world.console, quiet, event_ids={EVENT}) == 0
    runs = await world.runs()
    assert len(runs) == 1
    assert runs[0].trigger == "change"
    assert runs[0].provenance["lifecycle_source"] == "console_none_recorded"
    assert runs[0].snapshot["lifecycle"]["complete"] is True
    attached = await world.scalar(
        "SELECT count(*) FROM weft_engine.matching_change_receipts "
        "WHERE event_id=:e AND batch_id IS NOT NULL",
        e=EVENT,
    )
    assert attached == 5


async def test_two_workers_never_double_schedule(world: World) -> None:
    await world.seed_event(EVENT, ORG, SUMMARIES)
    await world.add_change(EVENT, "profile_updated", [GUEST_A])
    await changes.ingest(world.sessions, world.console, 500, event_ids={EVENT})
    results = await asyncio.gather(
        *(
            changes.schedule(world.sessions, world.console, world.settings, event_ids={EVENT})
            for _ in range(4)
        )
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
    await changes.settle(world.sessions, world.settings, event_ids={EVENT})
    delay = await world.scalar(
        "SELECT extract(epoch FROM next_attempt_at - now()) "
        "FROM weft_engine.matching_change_batches WHERE event_id=:e",
        e=EVENT,
    )
    assert 50 < delay <= 60
    await changes.schedule(world.sessions, world.console, world.settings, event_ids={EVENT})
    assert len(await world.runs()) == 1
    await world.sql(
        "UPDATE weft_engine.matching_change_batches "
        "SET next_attempt_at = now() - interval '1 second' WHERE event_id=:e",
        e=EVENT,
    )
    await changes.schedule(world.sessions, world.console, world.settings, event_ids={EVENT})
    runs = await world.runs()
    assert [run.idempotency_key for run in runs] == [
        f"f07:{first.change_batch_id}:1",
        f"f07:{first.change_batch_id}:2",
    ]
    await world.sql(
        "UPDATE weft_engine.matching_runs SET status='finished', finished_at=now() WHERE id=:i",
        i=runs[1].id,
    )
    await changes.settle(world.sessions, world.settings, event_ids={EVENT})
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
                select(Recommendation).where(
                    Recommendation.organization_id == ORG,
                    Recommendation.event_id == EVENT,
                    Recommendation.revoked_at.is_not(None),
                )
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
        total = await session.scalar(
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.organization_id == ORG, Recommendation.event_id == EVENT)
        )
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
            .where(
                Recommendation.organization_id == ORG,
                Recommendation.event_id == EVENT,
                Recommendation.revoked_at.is_not(None),
            )
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
