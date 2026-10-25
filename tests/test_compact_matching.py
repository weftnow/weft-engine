from __future__ import annotations

import json
import random
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.config import Settings
from src.matching.compact import (
    Judgment,
    JudgmentBatch,
    JudgmentPacket,
    judgment_chunks,
    judgment_fingerprint,
)
from src.matching.selection import evidence_is_grounded, lexical_similarity
from src.matching.worker import MatchingWorker, cosine, profile_text


def profiles(count: int = 9) -> dict[str, Any]:
    return {
        str(UUID(int=i + 1)): {
            "id": str(UUID(int=i + 1)),
            "person_id": str(UUID(int=1000 + i)),
            "summary": "Builds payments for rural clinics. " * 5,
            "goals": "Find clinic operators for payment deployments.",
            "offers": "Open-source payment integration expertise.",
            "revision": 3,
            "profile_version": 2,
            "networking_version": 1,
            "networking_status": "included",
            "identity_resolution_required": False,
            "organizer_only_fields": [],
            "missing_details": ["Availability unknown"],
        }
        for i in range(count)
    }


def decision(ref: str = "p0", **updates: Any) -> Judgment:
    return Judgment.model_validate(
        {
            "ref": ref,
            "a": 85,
            "b": 80,
            "ca": "Can learn payment integration techniques.",
            "cb": "Can learn clinic deployment requirements.",
            "ea": ["g0.f0", "g1.f0"],
            "eb": ["g0.f0", "g1.f0"],
            "r": False,
            "u": "unconfirmed_interest",
            **updates,
        }
    )


def test_shared_profiles_and_exact_reference_hydration() -> None:
    guests = profiles()
    keys = list(guests)
    pairs = [(keys[0], key) for key in keys[1:]]
    packet = JudgmentPacket(guests, pairs)
    assert len(packet.payload["guests"]) == 9
    assert len(packet.payload["pairs"]) == 8
    assert "person_id" not in packet.text and "profile_version" not in packet.text
    assert keys[0] not in packet.text
    single = JudgmentPacket(guests, pairs[:1])
    result = single.decode(JudgmentBatch(pairs=[decision()]), guests)[pairs[0]]
    assert evidence_is_grounded(result, guests)
    assert result.missing_information_a == ["Availability unknown"]
    assert result.score_b == 80
    legacy = json.dumps(
        [
            {"guest_a_id": a, "guest_b_id": b, "guest_a": guests[a], "guest_b": guests[b]}
            for a, b in pairs
        ]
    )
    assert len(packet.text) < len(legacy) * 0.65


@pytest.mark.parametrize(
    "changes",
    [
        {"ref": "unknown"},
        {"ea": ["g9.f0"]},
        {"ea": ["g0.f0"]},
    ],
)
def test_invalid_or_one_sided_evidence_is_rejected(changes: dict[str, Any]) -> None:
    guests = profiles(2)
    pair = tuple(guests)
    packet = JudgmentPacket(guests, [(pair[0], pair[1])])
    with pytest.raises(ValueError):
        packet.decode(JudgmentBatch(pairs=[decision(**changes)]), guests)


def test_cross_pair_reference_and_duplicate_decisions_are_rejected() -> None:
    guests = profiles(3)
    a, b, c = guests
    packet = JudgmentPacket(guests, [(a, b), (a, c)])
    with pytest.raises(ValueError, match="source reference"):
        packet.decode(
            JudgmentBatch(pairs=[decision(ea=["g0.f0", "g2.f0"]), decision("p1")]), guests
        )
    with pytest.raises(ValueError, match="duplicate"):
        packet.decode(JudgmentBatch(pairs=[decision(), decision()]), guests)


def test_sparse_low_score_is_retained_as_judgment_not_invented_evidence() -> None:
    guests: dict[str, Any] = {str(UUID(int=i)): {} for i in (1, 2)}
    a, b = guests
    packet = JudgmentPacket(guests, [(a, b)])
    result = packet.decode(
        JudgmentBatch(pairs=[decision(a=20, b=20, ea=[], eb=[], u="missing_facts")]), guests
    )
    assert result[(a, b)].evidence == []
    assert result[(a, b)].missing_information_a == []


def test_long_sources_are_not_truncated_and_batching_preserves_all_pairs() -> None:
    guests = profiles(12)
    keys = list(guests)
    text = "Multilingual source: clínica, 支払い. " * 1000
    guests[keys[0]]["summary"] = text
    pairs = [(keys[0], key) for key in keys[1:]]
    chunks = judgment_chunks(guests, pairs)
    assert [pair for chunk in chunks for pair in chunk] == pairs
    assert all(len(chunk) <= 8 for chunk in chunks)
    packet = JudgmentPacket(guests, chunks[0])
    rebuilt = "".join(
        fact.quote
        for fact in packet.evidence.values()
        if str(fact.guest_id) == keys[0] and fact.field == "summary"
    )
    assert rebuilt == text


def test_content_cache_ignores_revisions_but_tracks_facts_privacy_and_event() -> None:
    guests = profiles(2)
    a, b = guests
    event = UUID(int=50)
    before = judgment_fingerprint(event, (a, b), guests)
    guests[a]["revision"] = 100
    guests[a]["profile_version"] = 100
    assert judgment_fingerprint(event, (a, b), guests) == before
    assert judgment_fingerprint(UUID(int=51), (a, b), guests) != before
    guests[a]["organizer_only_fields"] = ["summary"]
    assert judgment_fingerprint(event, (a, b), guests) != before
    guests[a]["organizer_only_fields"] = []
    guests[a]["avoid"] = "Do not meet payment vendors."
    assert judgment_fingerprint(event, (a, b), guests) != before


@pytest.mark.asyncio
async def test_retrieval_matches_original_for_initial_and_expanded_candidates() -> None:
    guests = profiles(53)
    rng = random.Random(42)
    vectors = {
        (key, channel): [rng.random() for _ in range(5)]
        for key in guests
        for channel in ("needs", "offers", "context")
    }
    worker = MatchingWorker(None, None, Settings(_env_file=None), client=object())  # type: ignore[arg-type]
    worker.embedding_vectors = AsyncMock(return_value=vectors)  # type: ignore[method-assign]
    scores = {}
    for a in guests:
        for b in guests:
            if a >= b:
                continue
            need = cosine(vectors[(a, "needs")], vectors[(b, "offers")])
            reverse = cosine(vectors[(b, "needs")], vectors[(a, "offers")])
            shared = cosine(vectors[(a, "context")], vectors[(b, "context")])
            lexical = max(
                lexical_similarity(profile_text(guests[a], x), profile_text(guests[b], y))
                for x, y in (("needs", "offers"), ("offers", "needs"), ("context", "context"))
            )
            scores[(a, b)] = max(need, reverse) * 0.8 + shared * 0.1 + lexical * 0.1
    for expanded in (None, set(list(guests)[:7])):
        expected: set[tuple[str, str]] = set()
        for key in guests:
            ranked = sorted(
                ((score, pair) for pair, score in scores.items() if key in pair),
                key=lambda item: (-item[0], item[1]),
            )
            limit = 40 if expanded and key in expanded else 20
            expected.update(pair for _, pair in ranked[:limit])
        actual = await worker.shortlist(None, list(guests.values()), expanded)  # type: ignore[arg-type]
        assert actual == sorted(expected)
    worker.embedding_vectors.assert_awaited_once()
    assert all(len(ranked) == 40 for ranked in worker._ranking_cache.values())


@pytest.mark.asyncio
async def test_selected_explanation_failure_reallocates_without_rejudging() -> None:
    from src.matching.models import Run
    from src.matching.selection import Candidate, select_capacity
    from src.matching.worker import WorkerFailure

    guests = profiles(4)
    a, b, c, d = guests
    edges = [Candidate(a, b, 95), Candidate(c, d, 94), Candidate(a, c, 85), Candidate(b, d, 84)]
    evaluations = {}
    for edge in edges:
        pair = (edge.guest_low_id, edge.guest_high_id)
        evaluations.update(
            JudgmentPacket(guests, [pair]).decode(JudgmentBatch(pairs=[decision()]), guests)
        )
    capacities = dict.fromkeys(guests, 1)
    selected, _ = select_capacity(edges, capacities)
    worker = MatchingWorker(None, None, Settings(_env_file=None), client=object())  # type: ignore[arg-type]
    worker.heartbeat = AsyncMock()  # type: ignore[method-assign]
    worker._check_snapshot_freshness = AsyncMock()  # type: ignore[method-assign]
    explained = []

    async def verify(run: Any, evaluation: Any, inputs: Any) -> dict[str, str | None]:
        pair = (str(evaluation.guest_a_id), str(evaluation.guest_b_id))
        explained.append(pair)
        if pair == (a, b):
            raise WorkerFailure("evidence_verification_failed", "synthetic rejection")
        return dict.fromkeys(pair, "Can exchange concrete deployment expertise.")

    worker.verify_pair = AsyncMock(side_effect=verify)  # type: ignore[method-assign]
    pairs, reasons = await worker._verify_selection(
        Run(id=UUID(int=20), mode="event"),
        evaluations,
        guests,
        edges,
        capacities,
        selected,
    )
    assert set(pairs) == {(a, c), (b, d)}
    assert (a, b) not in reasons
    assert len(explained) == len(set(explained)) == 4
    assert worker._rejected_explanations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [False, True])
async def test_worker_dispatches_compact_payload_and_accounts_before_validation(
    invalid: bool,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from src.matching.models import Run
    from src.matching.worker import WorkerFailure

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.begin.return_value = session
    session.scalars = AsyncMock(return_value=[])
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    parsed = JudgmentBatch(pairs=[decision(ref="wrong" if invalid else "p0")])
    parse = AsyncMock(
        return_value=SimpleNamespace(
            id="synthetic-response",
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
            output_parsed=parsed,
        )
    )
    worker = MatchingWorker(
        MagicMock(return_value=session),
        MagicMock(),
        Settings(_env_file=None),
        client=MagicMock(responses=MagicMock(parse=parse)),
    )
    worker._reserve_attempt = AsyncMock()  # type: ignore[method-assign]
    worker.record_usage = AsyncMock(return_value=0.001)  # type: ignore[method-assign]
    worker._finish_attempt = AsyncMock()  # type: ignore[method-assign]
    guests = profiles(2)
    a, b = guests
    run = Run(id=UUID(int=11), event_id=UUID(int=12), organization_id=UUID(int=13))
    if invalid:
        with pytest.raises(WorkerFailure, match="invalid judgment references"):
            await worker.evaluate_batch(run, guests, [(a, b)])
        session.execute.assert_not_awaited()
        worker._finish_attempt.assert_awaited_once()
    else:
        result = await worker.evaluate_batch(run, guests, [(a, b)])
        assert result[(a, b)].score_a == 85
        session.execute.assert_awaited_once()
        assert worker._evaluation_live_requests == 1
    worker.record_usage.assert_awaited_once()
    assert worker.record_usage.call_args.args[:3] == (run.id, 123, 45)
    assert parse.call_args.kwargs["text_format"] is JudgmentBatch
    assert set(json.loads(parse.call_args.kwargs["input"])) == {"guests", "pairs"}
