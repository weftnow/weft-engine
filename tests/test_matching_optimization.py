from __future__ import annotations

import asyncio

import pytest

from src.config import Settings
from src.matching.experiments import screening_requires_full_evaluation
from src.matching.worker import gather_bounded


@pytest.mark.asyncio
async def test_provider_work_is_overlapped_but_respects_configured_bound() -> None:
    active = 0
    maximum = 0

    async def operation(value: int) -> int:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.005)
        active -= 1
        return value

    assert await gather_bounded(list(range(9)), 4, operation) == list(range(9))
    assert maximum == 4


@pytest.mark.asyncio
async def test_bounded_waves_settle_dispatched_calls_before_raising() -> None:
    settled: list[int] = []

    async def operation(value: int) -> int:
        await asyncio.sleep(0.002)
        settled.append(value)
        if value == 1:
            raise RuntimeError("synthetic provider failure")
        return value

    with pytest.raises(RuntimeError, match="synthetic provider failure"):
        await gather_bounded([0, 1, 2, 3], 2, operation)
    assert sorted(settled) == [0, 1]


def test_experimental_screening_defaults_off_and_uses_versioned_configuration() -> None:
    settings = Settings(_env_file=None)
    assert settings.matching_provider_concurrency == 4
    assert settings.matching_experiments_enabled is False
    assert settings.matching_screening_threshold == 60
    assert settings.matching_candidate_search_mode == "20_40"
    with pytest.raises(ValueError, match="threshold must be 50, 60, or 70"):
        Settings(_env_file=None, matching_screening_threshold=55)


def test_screening_only_skips_confident_low_directional_scores() -> None:
    confident_low = {
        "score_a": 85,
        "score_b": 55,
        "restriction_found": False,
        "uncertain": False,
        "source_fields_a": ["offers"],
        "source_fields_b": ["goals"],
    }
    uncertain_low = {**confident_low, "uncertain": True}
    restricted_low = {**confident_low, "restriction_found": True}
    malformed_low = {**confident_low, "source_fields_a": ["contactDetails"]}

    assert screening_requires_full_evaluation(confident_low, 50)
    assert not screening_requires_full_evaluation(confident_low, 60)
    assert screening_requires_full_evaluation(uncertain_low, 60)
    assert screening_requires_full_evaluation(restricted_low, 60)
    assert screening_requires_full_evaluation(malformed_low, 60)
    assert screening_requires_full_evaluation(
        {**confident_low, "source_fields_a": [], "source_fields_b": []}, 60
    )
