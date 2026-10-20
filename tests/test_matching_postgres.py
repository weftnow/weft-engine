"""Opt-in PostgreSQL integration checks; all synthetic records roll back.

Set WEFT_INTEGRATION_DATABASE_URL_FILE to a dedicated test URL file and
WEFT_INTEGRATION_DATABASE_NAME to the explicitly authorized database name.
The provider transport is synthetic: these checks do not establish live AI quality.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Environment, Settings
from src.main import create_app
from src.matching.console import ConsoleAdapter
from src.matching.models import Run
from src.matching.worker import MatchingWorker, WorkerFailure

pytestmark = pytest.mark.skipif(
    not os.environ.get("WEFT_INTEGRATION_DATABASE_URL_FILE"),
    reason="requires an explicitly authorized PostgreSQL test target",
)


class BoundEngine:
    """Run the real Console adapter SQL inside the fixture's rollback transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        yield self.connection


class SyntheticProvider:
    """Exercise the real SDK's response parsing without network access or spend."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.invalid_evidence = False
        self.provider_error = False
        self.client = AsyncOpenAI(
            api_key="synthetic-integration-only",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.respond)),
        )

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            self.calls.append("embedding")
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": body["model"],
                    "data": [
                        {"object": "embedding", "index": i, "embedding": [1.0, 0.5, 0.25]}
                        for i, _ in enumerate(body["input"])
                    ],
                    "usage": {"prompt_tokens": 10, "total_tokens": 10},
                },
            )
        if self.provider_error:
            return httpx.Response(503, json={"error": {"message": "synthetic unavailable"}})
        data = json.loads(body["input"])
        if isinstance(data, list):
            self.calls.append("evaluation")
            output: dict[str, Any] = {"pairs": []}
            for pair in data:
                a, b = pair["guest_a"], pair["guest_b"]
                supported = bool(a["summary"] and b["summary"])
                output["pairs"].append(
                    {
                        "guest_a_id": a["id"],
                        "guest_b_id": b["id"],
                        "benefit_a": "Can learn practical clinic deployment methods.",
                        "benefit_b": "Can learn practical open-source payment methods.",
                        "score_a": 80 if supported else 40,
                        "score_b": 82 if supported else 40,
                        "evidence": [
                            {
                                "guest_id": g["id"],
                                "field": "summary",
                                "quote": "fabricated quote"
                                if self.invalid_evidence
                                else g["summary"],
                            }
                            for g in (a, b)
                            if g["summary"]
                        ],
                        "missing_information_a": [],
                        "missing_information_b": [],
                        "uncertainty": "Synthetic integration response; no AI quality evidence.",
                        "restriction_found": False,
                    }
                )
        else:
            self.calls.append("verification")
            output = {
                "supported": True,
                "valid_evidence_indexes": list(range(len(data["evidence"]))),
                "shareable_reasons": {
                    evidence["guest_id"]: evidence["quote"] for evidence in data["evidence"]
                },
            }
        return httpx.Response(
            200,
            json={
                "id": f"resp_synthetic_{uuid4().hex}",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": body["model"],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "output": [
                    {
                        "type": "message",
                        "id": "msg_synthetic",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(output), "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 20,
                    "total_tokens": 40,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )


@dataclass
class DatabaseCase:
    connection: AsyncConnection
    sessions: async_sessionmaker[AsyncSession]
    console: ConsoleAdapter
    settings: Settings
    provider: SyntheticProvider
    org: UUID
    event: UUID
    guests: list[UUID]
    actor: UUID

    @property
    def path(self) -> str:
        return f"/v1/organizations/{self.org}/events/{self.event}/matching-runs"

    @asynccontextmanager
    async def api(self) -> AsyncIterator[httpx.AsyncClient]:
        app = create_app(self.settings)
        app.state.matching_sessions = self.sessions
        app.state.console_adapter = self.console
        async with app.router.lifespan_context(app):
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://integration",
                    headers={
                        "X-Weft-Service-Token": next(iter(self.settings.matching_service_tokens))
                    },
                ) as client:
                    yield client
            finally:
                # The fixture owns the connection and its outer rollback transaction.
                app.state.matching_sessions = None

    async def submit(self, client: httpx.AsyncClient, key: str, **body: Any) -> UUID:
        response = await client.post(
            self.path,
            headers={"Idempotency-Key": key},
            json={
                "mode": "event",
                "lifecycle": {
                    "complete": True,
                    "priorDecisions": [],
                    "protectedPairs": [],
                    "completedPairs": [],
                },
                **body,
            },
        )
        assert response.status_code == 202, response.text
        return UUID(response.json()["runId"])

    async def process(self, run_id: UUID, **settings: Any) -> MatchingWorker:
        worker = MatchingWorker(
            self.sessions,
            self.console,
            self.settings.model_copy(update=settings),
            client=self.provider.client,
        )
        # Target only our uncommitted run; never drain the shared database queue.
        await self.connection.execute(
            text("""
                UPDATE weft_engine.matching_runs SET status='running',lease_owner=:owner,
                lease_expires_at=now()+interval '90 seconds' WHERE id=:run
            """),
            {"owner": worker.worker_id, "run": run_id},
        )
        try:
            await worker.process(run_id)
        except WorkerFailure as error:
            await worker.fail(run_id, error.code, str(error))
        return worker


@pytest.fixture
async def database_case() -> AsyncIterator[DatabaseCase]:
    url_file = Path(os.environ["WEFT_INTEGRATION_DATABASE_URL_FILE"])
    url = make_url((await asyncio.to_thread(url_file.read_text)).strip())
    expected = os.environ.get("WEFT_INTEGRATION_DATABASE_NAME")
    if not expected or url.database != expected:
        pytest.fail("test URL does not match the explicitly authorized database name")
    query = dict(url.query)
    query.pop("channel_binding", None)
    ssl_mode = query.pop("sslmode", "require")
    query["ssl"] = ssl_mode
    url = url.set(drivername="postgresql+asyncpg", query=query)
    engine = create_async_engine(url, hide_parameters=True, connect_args={"timeout": 15})
    provider = SyntheticProvider()
    org, event, actor = uuid4(), uuid4(), uuid4()
    guests = [uuid4() for _ in range(6)]
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(
                    text("INSERT INTO public.organizations(id,name) VALUES (:id,:name)"),
                    {"id": org, "name": f"F06 integration {org}"},
                )
                await connection.execute(
                    text("INSERT INTO public.users(id,display_name) VALUES (:id,'F06 test actor')"),
                    {"id": actor},
                )
                await connection.execute(
                    text("""
                        INSERT INTO public.events(id,organization_id,creator_id,name,description,
                        city,categories,start_date,end_date,timezone,starts_at,ends_at)
                        VALUES (:id,:org,:actor,'F06 integration test','Synthetic fixtures only',
                        'Singapore',ARRAY['Technology'],current_date,current_date,'UTC',
                        now(),now()+interval '1 hour')
                    """),
                    {"id": event, "org": org, "actor": actor},
                )
                linked_person = uuid4()
                for index, guest_id in enumerate(guests):
                    person = linked_person if index >= 4 else uuid4()
                    await connection.execute(
                        text("""
                            INSERT INTO public.event_people(id,event_id) VALUES (:id,:event)
                            ON CONFLICT DO NOTHING
                        """),
                        {"id": person, "event": event},
                    )
                    await connection.execute(
                        text("""
                            INSERT INTO public.event_guests(id,event_id,person_id,position,
                            first_name,last_name,email,phone,company,job_position,profile_type,
                            linkedin,guest_type,source,profile_version)
                            VALUES (:id,:event,:person,:position,'Synthetic','Guest','','','','',
                            '','','Attendee','manual',:version)
                        """),
                        {
                            "id": guest_id,
                            "event": event,
                            "person": person,
                            "position": index,
                            "version": 1 if index in (0, 1) else 0,
                        },
                    )
                    if index in (0, 1):
                        await connection.execute(
                            text("""
                                INSERT INTO public.event_guest_profile_versions(event_id,guest_id,
                                version,summary,goals,organizer_only_fields,created_by)
                                VALUES (:event,:guest,1,:summary,'private integration goal',
                                ARRAY['goals'],:actor)
                            """),
                            {
                                "event": event,
                                "guest": guest_id,
                                "summary": (
                                    "Builds open-source clinic payments."
                                    if index == 0
                                    else "Deploys rural clinic payment systems."
                                ),
                                "actor": actor,
                            },
                        )
                await connection.execute(
                    text("""
                        UPDATE public.event_guests SET networking_status='excluded',
                        networking_excluded_at=now(),networking_excluded_by=:actor,
                        networking_exclusion_reason='organizer_decision' WHERE id=:id
                    """),
                    {"actor": actor, "id": guests[3]},
                )
                sessions = async_sessionmaker(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                console = ConsoleAdapter(cast(AsyncEngine, BoundEngine(connection)))
                settings = Settings(
                    _env_file=None,
                    environment=Environment.TEST,
                    matching_service_tokens={secrets.token_urlsafe(24): [str(org)]},
                    matching_embedding_model="synthetic-integration-embedding",
                    matching_evaluation_model="synthetic-integration-evaluation",
                    matching_max_spend_usd=1,
                    matching_input_cost_per_million_usd=1,
                    matching_output_cost_per_million_usd=1,
                    matching_embedding_cost_per_million_usd=1,
                )
                yield DatabaseCase(
                    connection, sessions, console, settings, provider, org, event, guests, actor
                )
            finally:
                await transaction.rollback()
        async with engine.connect() as check:
            assert not await check.scalar(
                text("SELECT EXISTS(SELECT 1 FROM public.events WHERE id=:id)"), {"id": event}
            )
            assert not await check.scalar(
                text("SELECT EXISTS(SELECT 1 FROM weft_engine.matching_runs WHERE event_id=:id)"),
                {"id": event},
            )
    finally:
        await provider.client.close()
        await engine.dispose()


async def test_postgres_api_worker_results_and_idempotency(database_case: DatabaseCase) -> None:
    case = database_case
    snapshot = await case.console.snapshot(case.org, case.event)
    by_id = {g["id"]: g for g in snapshot["guests"]}
    assert by_id[str(case.guests[2])]["profile_version"] == 0
    assert by_id[str(case.guests[2])]["summary"] is None
    assert by_id[str(case.guests[4])]["identity_resolution_required"]
    async with case.api() as client:
        run_id = await case.submit(client, "first")
        assert await case.submit(client, "first") == run_id
        await case.process(run_id)
        status = (await client.get(f"{case.path}/{run_id}")).json()
        assert status["status"] == "finished", status
        response = await client.get(f"{case.path}/{run_id}/results")
        assert response.status_code == 200
        results = response.json()
        assert len(results["recommendations"]) == 1
        pair = results["recommendations"][0]
        assert {pair["guestLowId"], pair["guestHighId"]} == {
            str(case.guests[0]),
            str(case.guests[1]),
        }
        assert pair["pairScore"] == 80
        assert "private integration goal" not in response.text
        assert results["guestReasons"][str(case.guests[3])] == "excluded"
        assert results["guestReasons"][str(case.guests[4])] == "identity_resolution_required"
        assert results["guestReasons"][str(case.guests[2])] == "insufficient_support"
        second = await case.submit(client, "recalculate")
        await case.process(second)
        assert (await client.get(f"{case.path}/{second}/results")).json()["recommendations"] == []
        assert (await client.get(f"{case.path}/{run_id}/results")).json() == results
        more = await case.submit(client, "more", mode="more", targetGuestId=str(case.guests[0]))
        assert (
            await case.submit(client, "more", mode="more", targetGuestId=str(case.guests[0]))
            == more
        )
        grants = await case.connection.scalar(
            text("SELECT count(*) FROM weft_engine.matching_slot_grants WHERE event_id=:event"),
            {"event": case.event},
        )
        assert grants == 1
    assert set(case.provider.calls) == {"embedding", "evaluation", "verification"}


async def test_postgres_scope_validation_and_blocks(database_case: DatabaseCase) -> None:
    case = database_case
    async with case.api() as client:
        assert (
            await client.get(f"{case.path}/{uuid4()}", headers={"X-Weft-Service-Token": "invalid"})
        ).status_code == 401
        wrong_org = case.path.replace(str(case.org), str(uuid4()))
        assert (await client.get(f"{wrong_org}/{uuid4()}")).status_code == 403
        wrong_event = case.path.replace(str(case.event), str(uuid4()))
        assert (await client.get(f"{wrong_event}/{uuid4()}")).status_code == 404
        assert (await client.get(f"{case.path}/{uuid4()}")).status_code == 404
        low, high = sorted(case.guests[:2], key=str)
        await case.connection.execute(
            text("""
                INSERT INTO public.event_guest_match_blocks(event_id,guest_low_id,
                guest_high_id,created_by) VALUES (:event,:low,:high,:actor)
            """),
            {"event": case.event, "low": low, "high": high, "actor": case.actor},
        )
        run_id = await case.submit(client, "blocked")
        await case.process(run_id)
        response = await client.get(f"{case.path}/{run_id}/results")
        assert response.json()["status"] == "finished", response.text
        assert response.json()["recommendations"] == []


@pytest.mark.parametrize("scenario", ["stale", "budget", "invalid_evidence", "provider_failure"])
async def test_postgres_failures_are_visible(database_case: DatabaseCase, scenario: str) -> None:
    case = database_case
    async with case.api() as client:
        run_id = await case.submit(client, scenario)
        overrides: dict[str, Any] = {}
        if scenario == "stale":
            await case.connection.execute(
                text("UPDATE public.event_guests SET revision=revision+1 WHERE id=:id"),
                {"id": case.guests[0]},
            )
        elif scenario == "budget":
            overrides["matching_max_spend_usd"] = 0
        elif scenario == "invalid_evidence":
            case.provider.invalid_evidence = True
        else:
            case.provider.provider_error = True
        await case.process(run_id, **overrides)
        response = await client.get(f"{case.path}/{run_id}")
        result = response.json()
        expected = {
            "stale": ("invalid_result", "snapshot_stale"),
            "budget": ("failed", "spend_budget_unconfigured"),
            "invalid_evidence": ("invalid_result", "provider_invalid_result"),
            "provider_failure": ("failed", "provider_failure"),
        }[scenario]
        assert (result["status"], result["failure"]["code"]) == expected
        assert (await client.get(f"{case.path}/{run_id}/results")).json()["recommendations"] == []


async def test_postgres_lease_owner_fences_processing(database_case: DatabaseCase) -> None:
    case = database_case
    async with case.api() as client:
        run_id = await case.submit(client, "lease")
        worker = MatchingWorker(case.sessions, case.console, case.settings, case.provider.client)
        # A replacement worker owns this run. The old worker cannot advance it.
        await case.connection.execute(
            text("""
                UPDATE weft_engine.matching_runs SET status='running',lease_owner='replacement',
                lease_expires_at=now()+interval '90 seconds' WHERE id=:id
            """),
            {"id": run_id},
        )
        with pytest.raises(WorkerFailure, match="lease expired"):
            await worker.process(run_id)
        await worker.fail(run_id, "old_worker_failure", "must not overwrite replacement")
        async with case.sessions() as session:
            run = await session.get(Run, run_id)
            assert run is not None and run.status == "running"
            assert run.failure_code is None
