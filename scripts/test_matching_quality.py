from __future__ import annotations

from itertools import combinations
from typing import Any
from uuid import UUID

import pytest
from evaluate_matching_quality import evaluate


def benchmark() -> dict[str, Any]:
    guests = [str(UUID(int=index + 1)) for index in range(60)]
    pairs = list(combinations(guests, 2))[:200]
    pair_records = [{"guest_low_id": low, "guest_high_id": high} for low, high in pairs]
    return {
        "eligible_guest_ids": guests,
        "labels": [
            {
                "guest_low_id": low,
                "guest_high_id": high,
                "strong_connection": True,
                "split": "held_out" if index % 2 else "development",
            }
            for index, (low, high) in enumerate(pairs)
        ],
        "candidate_pairs": pair_records,
        "selected_pairs": pair_records,
        "baselines": {
            "semantic_only": {"candidate_pairs": pair_records, "selected_pairs": pair_records},
            "fixed_rule": {"candidate_pairs": pair_records, "selected_pairs": pair_records},
        },
        "reviewed_by": ["Antonio", "Sheary"],
        "provider_provenance": {
            "embedding_model": "text-embedding-3-large",
            "evaluation_model": "gpt-6.1-sol",
            "prompt_version": "test-prompt-v1",
            "policy_version": "test-policy-v1",
            "live_provider_calls": 1,
            "estimated_cost_usd": 1.0,
            "approved_budget_usd": 10.0,
            "latency_seconds": 10.0,
        },
        "audited_violations": {
            "eligibility": [],
            "privacy": [],
            "fabricated_evidence": [],
        },
    }


def test_benchmark_reports_held_out_precision_recall_coverage_and_provenance() -> None:
    result = evaluate(benchmark())
    assert result["status"] == "pass"
    held_out = result["metrics"]["held_out"]
    assert held_out["selected_precision"] == 1.0
    assert held_out["candidate_recall"] == 1.0
    assert held_out["guest_coverage"] > 0


def test_benchmark_fails_when_selected_pairs_are_unsupported() -> None:
    data = benchmark()
    data["selected_pairs"] = []
    result = evaluate(data)
    assert result["status"] == "pending_or_failed"
    assert result["gates"]["held_out_precision"] is False


def test_benchmark_rejects_reversed_duplicate_unordered_labels() -> None:
    data = benchmark()
    labels = data["labels"]
    labels.append(
        {
            "guest_low_id": labels[0]["guest_high_id"],
            "guest_high_id": labels[0]["guest_low_id"],
            "strong_connection": True,
            "split": "held_out",
        }
    )
    with pytest.raises(ValueError, match="duplicate unordered label"):
        evaluate(data)
