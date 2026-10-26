# F06 quality evaluation

Run `poetry run python scripts/evaluate_matching_quality.py benchmark.json` on a reviewed export. The evaluator reads labels and provider provenance; it does not generate profiles, labels, model outputs, or acceptance data. Unit tests use synthetic fixtures only and are not product-quality evidence.

The JSON input contains:

- `eligible_guest_ids`: synthetic benchmark profile UUIDs;
- `labels`: canonical or reversed guest ID pairs, `strong_connection`, and `split` (`development` or `held_out`);
- `candidate_pairs` and `selected_pairs`: pairs from the evaluated run, each linked to an expert label;
- `baselines`: candidate and selected pairs for both `semantic_only` and `fixed_rule` approaches;
- `reviewed_by`: the human reviewers;
- `provider_provenance`: `embedding_model`, `evaluation_model`, `prompt_version`, `policy_version`, `live_provider_calls`, `estimated_cost_usd`, `approved_budget_usd`, and `latency_seconds`;
- `audited_violations`: arrays named `eligibility`, `privacy`, and `fabricated_evidence`.

The evaluator requires at least 60 profiles and 200 unique labeled pairs, two reviewers, held-out labels, recorded live provider calls and versions, recorded latency, spend within the supplied approved budget, both baselines, and zero audited violations. It gates held-out selected-pair precision at 90% and candidate recall at 95%. It reports precision, candidate recall, selected pairs, and guest coverage for all and held-out labels and compares both baselines. An empty selected set has no precision and fails the gate, so an empty result cannot pass by itself.

Use separately generated synthetic benchmark profiles and independently reviewed labels. Include both strong and weak connections, sparse and URL-only profiles, complementary needs/offers, private fields, explicit restrictions, and held-out cases. Do not place real guest profiles or provider payloads in benchmark artifacts. Record the 300-guest live run's actual latency, cost, model/prompt/policy versions, cache/live-call provenance, coverage, and baseline results alongside the report. Until experts supply the labeled dataset and a credentialed run with approved spend is performed, F06 matching quality remains unaccepted.
