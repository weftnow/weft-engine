"""Evaluate F06 against externally reviewed labels; no synthetic labels are generated."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import UUID

MIN_PROFILES = 60
MIN_LABELS = 200
PRECISION_GATE = 0.90
CANDIDATE_RECALL_GATE = 0.95


def canonical_pair(first: str, second: str) -> tuple[str, str]:
    left, right = str(UUID(first)), str(UUID(second))
    if left == right:
        raise ValueError("self pair is not valid benchmark data")
    return tuple(sorted((left, right)))


def pair_set(items: Iterable[dict[str, Any]], profile_ids: set[str]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in items:
        pair = canonical_pair(item["guest_low_id"], item["guest_high_id"])
        if pair[0] not in profile_ids or pair[1] not in profile_ids:
            raise ValueError("benchmark pair references an unknown profile")
        if pair in pairs:
            raise ValueError("duplicate unordered pair in benchmark input")
        pairs.add(pair)
    return pairs


def split_metrics(
    labels: dict[tuple[str, str], bool],
    candidates: set[tuple[str, str]],
    selected: set[tuple[str, str]],
    profile_ids: set[str],
    split: str,
) -> dict[str, float | int | None]:
    split_labels = dict(labels)
    strong_pairs = {pair for pair, strong in split_labels.items() if strong}
    split_candidates = candidates & set(split_labels)
    split_selected = selected & set(split_labels)
    candidate_true_positives = len(strong_pairs & split_candidates)
    selected_true_positives = len({pair for pair in split_selected if split_labels[pair]})
    selected_labeled = len(split_selected)
    selected_guests = {guest_id for pair in split_selected for guest_id in pair}
    precision = selected_true_positives / selected_labeled if selected_labeled else None
    recall = candidate_true_positives / len(strong_pairs) if strong_pairs else None
    return {
        "split": split,
        "labeled_pairs": len(split_labels),
        "strong_pairs": len(strong_pairs),
        "candidate_recall": recall,
        "selected_precision": precision,
        "selected_pairs": selected_labeled,
        "guest_coverage": len(selected_guests) / len(profile_ids) if profile_ids else 0.0,
        "guests_covered": len(selected_guests),
        "eligible_guests": len(profile_ids),
    }


def evaluate(data: dict[str, Any]) -> dict[str, Any]:
    profile_ids = {str(UUID(item)) for item in data["eligible_guest_ids"]}
    labels: dict[tuple[str, str], bool] = {}
    splits: dict[str, str] = {}
    for row in data["labels"]:
        pair = canonical_pair(row["guest_low_id"], row["guest_high_id"])
        if pair[0] not in profile_ids or pair[1] not in profile_ids:
            raise ValueError("label references an unknown profile")
        if pair in labels:
            raise ValueError("duplicate unordered label")
        labels[pair] = bool(row["strong_connection"])
        splits[pair] = row["split"]
    candidates = pair_set(data["candidate_pairs"], profile_ids)
    selected = pair_set(data["selected_pairs"], profile_ids)
    if not selected <= set(labels):
        raise ValueError("every selected pair must have an expert label")
    if not candidates <= set(labels):
        raise ValueError("every benchmark candidate pair must have an expert label")
    held_out = {pair: strong for pair, strong in labels.items() if splits[pair] == "held_out"}
    all_metrics = split_metrics(labels, candidates, selected, profile_ids, "all")
    held_metrics = split_metrics(held_out, candidates, selected, profile_ids, "held_out")
    baseline_metrics: dict[str, Any] = {}
    for name in ("semantic_only", "fixed_rule"):
        baseline = data["baselines"][name]
        baseline_candidates = pair_set(baseline["candidate_pairs"], profile_ids)
        baseline_selected = pair_set(baseline["selected_pairs"], profile_ids)
        if not baseline_selected <= set(labels) or not baseline_candidates <= set(labels):
            raise ValueError(f"every {name} baseline pair must have an expert label")
        baseline_metrics[name] = {
            "all": split_metrics(
                labels, baseline_candidates, baseline_selected, profile_ids, "all"
            ),
            "held_out": split_metrics(
                held_out, baseline_candidates, baseline_selected, profile_ids, "held_out"
            ),
        }
    provenance = data["provider_provenance"]
    violations = data["audited_violations"]
    cost = float(provenance["estimated_cost_usd"])
    approved_budget = float(provenance["approved_budget_usd"])
    gates = {
        "minimum_profiles": len(profile_ids) >= MIN_PROFILES,
        "minimum_labels": len(labels) >= MIN_LABELS,
        "held_out_labels_present": bool(held_out),
        "provider_was_live": int(provenance["live_provider_calls"]) > 0,
        "provider_versions_recorded": all(
            provenance[key]
            for key in ("embedding_model", "evaluation_model", "prompt_version", "policy_version")
        ),
        "spend_within_approved_budget": approved_budget > 0 and cost <= approved_budget,
        "latency_recorded": float(provenance["latency_seconds"]) > 0,
        "baselines_compared": set(data["baselines"]) >= {"semantic_only", "fixed_rule"},
        "expert_review_present": {"Antonio", "Sheary"} <= set(data["reviewed_by"]),
        "held_out_precision": (held_metrics["selected_precision"] or 0) >= PRECISION_GATE,
        "held_out_candidate_recall": (held_metrics["candidate_recall"] or 0)
        >= CANDIDATE_RECALL_GATE,
        "zero_eligibility_violations": not violations["eligibility"],
        "zero_privacy_violations": not violations["privacy"],
        "zero_fabricated_evidence_violations": not violations["fabricated_evidence"],
    }
    return {
        "status": "pass" if all(gates.values()) else "pending_or_failed",
        "gates": gates,
        "metrics": {"all": all_metrics, "held_out": held_metrics, "baselines": baseline_metrics},
        "provider_provenance": provenance,
        "reviewed_by": sorted(set(data["reviewed_by"])),
        "violation_counts": {key: len(values) for key, values in violations.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path, help="externally reviewed benchmark JSON")
    args = parser.parse_args()
    try:
        report = evaluate(json.loads(args.benchmark.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Invalid benchmark input: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
