# Optimize Weft Engine while preserving reciprocal match quality

Status: Active — candidate-preserving cost revision implemented; current database/live acceptance pending
Owner: implementing agent
Created: 2026-10-24

## Authorized cost-reduction revision — 2026-10-25

This section supersedes the earlier Stage 2 screening proposal. User authorized implementation
without halving candidate judgments. Preserve the production 20→40 candidate search, scoring
rubric, reciprocal three-slot allocation, restrictions, and provider/model. Do not enable
screening, smaller candidate pools, approximate retrieval, or a new model/provider.

### Required implementation

- [x] Replace verbose per-candidate output with compact authoritative judgments: directional
  scores, concise benefit claims, source references, restrictions, uncertainty codes.
- [x] Project matching facts without operational metadata; retain all substantive source text,
  restrictions, privacy and unknowns. Resolve references into exact quotations in code.
- [x] Deduplicate profiles inside bounded batches; use eight judgments per request and a
  payload-size ceiling. Preserve all candidate edges and deterministic identity mapping.
- [x] Generate longer shareable explanations only for selected pairs, using the existing
  evidence verifier rather than adding another generation pass. Preserve final API fields.
- [x] Reuse content-equivalent judgments while keeping identity/event/tenant/policy/privacy
  boundaries and publication freshness. Retain compatible legacy cache reuse.
- [x] Eliminate repeated retrieval tokenization/norms and per-attendee all-edge scans without
  changing retrieval scores/order. Keep the 300-person production guard pending scale evidence.
- [x] Correct expanded-evaluation timing, validate rejection/reselection, and run verification.

### Acceptance and evidence

Required live targets: at least 60% lower total cold-run AI cost and 2× lower end-to-end time
than the existing parallel implementation, with identical datasets, models, prices and
candidate coverage. Include embeddings, expansion, retries, verification and rejected
explanations; report warm runs separately. These targets are not measured results.
Preserve ≥90% held-out precision, ≥95% candidate recall, zero audited privacy/eligibility/
fabrication violations, and no regression in coverage or selection value. Use independent
expert labels; unit tests do not establish semantic quality or live savings.

Illustrative screenshot baseline: 698×(3,800 input + 1,100 output) = 2,652,400 input and
767,800 output tokens. At constant illustrative $2/M input and $10/M output this is $12.98.
2,790 compact decisions averaging 350/70 tokens plus 225 selected explanations averaging
650/180 tokens would cost $4.60 (64.5% less), excluding separate verification/embedding/retries.
This is a sizing scenario, not an invoice or a guaranteed outcome. Candidate-halving savings
are explicitly excluded from this implementation.

Affected boundaries: engine-internal requests/caches and worker; preserve Console ownership,
organization/event isolation, API serialization, private evidence filtering and lifecycle rules.
No deployment, production activation, migration application or unbudgeted provider benchmark.
Use the existing live-provider acceptance prerequisites in Verification.

### Research basis

- [Retrieve and rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)
- [Output reduction](https://developers.openai.com/api/docs/guides/latency-optimization)
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Boardy](https://www.boardy.ai/) describes a large persistent network, but does not disclose
  architecture or per-introduction costs; no implementation claim is inferred from its scale.

### Progress — 2026-10-25

Implemented the compact provider contract as the production path. Candidate reduction and
historical screening/search experiments are bypassed, including when old experiment settings
are enabled. Every initial and expanded candidate still receives a judgment or compatible
cached judgment. Shared-profile batches contain at most eight edges; source references hydrate
exact quotations. Revision-only changes reuse content-equivalent evaluations, with event/tenant/
model/policy/privacy boundaries intact. Existing exact legacy caches remain readable.

The existing selected-pair verifier supplies longer shareable benefits, avoiding the additional
selected-detail generation pass assumed in the sizing scenario. Private-only benefits retain
short evidence-backed claims. Missing-information lists now use saved missing-details facts and
uncertainty text comes from bounded codes; no unsupported missing facts are generated. Rejected
selected explanations trigger reallocation among already judged candidates. Provider or budget
failures still propagate. Verification cache version changed for the new contract.

Retrieval retains the same scoring/tie ordering and 20→40 sets, precomputes lexical tokens and
vector norms, and retains only 40 edges per attendee. No approximate search, new provider/model,
dependency, database migration, production cap change or deployment was introduced.

Verification:
- `poetry check --lock --strict`: passed.
- `make verify`: passed; 96 tests passed, 16 database tests skipped. Documentation, Ruff,
  formatting and strict mypy all passed. New tests cover source/identity validation, lossless
  long fields, content cache invalidation, exact retrieval parity, selected-edge rejection and
  reallocation, compact request dispatch, and usage accounting before malformed-result rejection.
- `git diff --check`: passed.
- Offline eight-pair shared-attendee fixture: two legacy requests become one compact request;
  input serialization including instructions/schema dropped from 15,962 to approximately 6,100
  characters (~62%). This measures characters on synthetic data, not tokens or billed savings.
- No explicit `WEFT_ENGINE_TEST_DATABASE_URL` is configured. Current integration checks were
  skipped; the earlier revision's Neon results do not validate this revision.
- No paid provider calls, deployment, database writes or migration application performed.

Remaining acceptance: designated Neon test URL, explicitly budgeted live 150/300-guest cold/warm
benchmark with actual token accounting, independent labels and quality gates, and larger-event
load measurements. The ≥60% total-cost and 2× speed targets remain unproven, so this plan stays
active. The 300-guest guard remains in place; similarity computation is still all-pairs even
though retained ranking storage and per-attendee scans were improved.

## Summary and acceptance

Optimize `weft-engine` in two stages: first remove execution bottlenecks without changing matching decisions, then benchmark ways to reduce expensive AI evaluation.

Every selected match remains **one shared, reciprocal pair** that consumes one slot from each attendee. Preserve complementary benefit, restrictions, evidence requirements, tenant isolation, and the initial three-match capacity. Return fewer matches when support or capacity is insufficient; three is a maximum, not a guaranteed result.

Success means:

- At least **3× faster combined scoring and verification** with concurrency 4 versus the serial baseline.
- Fewer paid evaluations on repeated or interrupted runs.
- No selection changes from execution-only optimizations when supplied identical model outputs.
- Experimental changes reach production only when they reduce measured cost without degrading the established quality baseline.

The approach follows [staged recommendation architectures](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/) and [reciprocal recommendation research](https://luiz.pizzato.cc/assets/pdf/papers/UMAP2010-ITWP-Pizzato-ReciprocalRecommender.pdf). Published results inform experiments; they do not establish Weft's performance.

## Context and constraints

- Work in the `weft-engine` repository. The sibling Console remains a read-only integration reference; this plan does not authorize Console implementation changes.
- Extend the implemented pipeline documented in [F06 live AI matching](2026-10-19-f06-live-ai-matching.md) and [F07 automatic matching updates](2026-10-19-f07-automatic-matching-updates.md). Their existing acceptance gates remain open independently; this plan does not certify them.
- Read repository instructions, [Product](../../product.md), [Architecture](../../../ARCHITECTURE.md), [Engineering](../../engineering.md), and [Verification](../../VERIFICATION.md) before implementation. Inspect current code and working-tree changes rather than treating older plan descriptions as current code.
- The inspected implementation lives primarily in `src/matching/worker.py`, `src/matching/selection.py`, and the matching models/storage/schema modules. It uses OpenAI, serial four-pair evaluation batches, a provider semaphore with default concurrency 2, 20→40 candidate retrieval, and a separate serial evidence-verification pass. The DeepSeek configuration in the original screenshots does not describe this checkout.
- Preserve the unrelated untracked `.serena/` directory and any other unrelated work.
- Preserve organization/event scope, service authorization, local role boundaries, pinned profiles, privacy labels, explicit identity holds, historical pairs, revocation behavior, and durable slot grants. Matching is not guest acceptance or a physical meeting.
- Use Python 3.14, Poetry, and the existing lockfile. Keep matching business logic in its owning domain and routers thin. Add dependencies only when justified by implementation requirements.
- Keep credentials, attendee profiles, organizer-only content, and provider payloads out of logs and benchmark artifacts. Database tests must use the user-designated Neon project `Weft B2B`, branch `dev`, database `weft_console_test` (`weft-console-test`). Do not start or use a local database. Preserve Console schemas and unrelated rows; clean only generated synthetic rows.

## Stage 1 — Optimize the existing pipeline

### Concurrent, recoverable provider execution

- Replace serial evaluation and verification loops with bounded task pools sharing the existing provider semaphore. Set default concurrency to **4**; retain support for 1–8.
- Preserve four-pair evaluation batches, candidate ordering, scoring prompts, validation, and deterministic merging.
- Use independent database sessions for concurrent operations and persist successful evaluations immediately.
- Make provider retries explicit and bounded, with a persisted attempt for each dispatched request.
- Supervise heartbeat renewal alongside processing. Stop dispatching after lease loss, shutdown, terminal failure, or stale input; settle outstanding tasks before returning.
- Preserve the final freshness, eligibility, capacity, and lease checks before atomic publication.

### Budget safety and accurate accounting

- Add durable per-attempt cost reservations through an additive engine-only Alembic migration.
- Admit requests under a run-row lock only when recorded spend, outstanding reservations, and the new request estimate fit the configured ceiling.
- Estimate the complete request, including instructions, schema, input, and maximum output.
- Record returned usage before result validation, including malformed or rejected output. Preserve actual usage even when it exceeds the reservation.
- Retain conservative reservations for interrupted requests with unknown billing. Recovery must not silently release them and authorize repeated spending.
- Snapshot configured model prices in run provenance and distinguish estimated spend from provider-confirmed token usage.

### Avoid repeated work

- Replace per-item embedding and evaluation cache queries with bounded bulk reads. Preserve existing cache keys and previously saved evaluations.
- Compute profile text, lexical tokens, vector norms, similarities, and candidate rankings once per snapshot. Reuse them during expanded retrieval.
- Determine remaining capacities before evaluation. Skip pairs with an attendee who has no remaining capacity while preserving retrieval rankings.
- Cache successful evidence verification using tenant/event, exact verification inputs, privacy context, model, and verifier version. Retain original live-attempt provenance.
- Check snapshot freshness between dispatch waves, at most once every 30 seconds, to stop expensive work that cannot be published.

### Observability

- Record retrieval, evaluation, selection, verification, and total durations.
- Record candidate counts, cache hits, live requests, retries, token usage, reservations, and failures throughout the run, including failed runs.
- Measure provider prompt-cache reads, writes, and charges. Keep stable request prefixes where compatible with the existing prompt; measure net savings rather than assuming cache hits. Follow [official caching guidance](https://developers.openai.com/api/docs/guides/prompt-caching).

## Stage 2 — Benchmark selective AI evaluation

Build an isolated, disabled-by-default experimental path. Continue using the current provider and evaluation model.

### Compact screening

- Compare full evaluation of every candidate against a compact screening response containing directional scores, restriction findings, uncertainty, and source-field references.
- Test directional screening cutoffs of **50, 60, and 70** on development labels. Escalate uncertain results to full evaluation rather than rejecting them.
- Surviving pairs receive the existing complete evaluation and selected-pair evidence verification.
- Count screening, repeated input, full evaluations, verification, retries, and failures when comparing total cost. An additional screening stage must earn its overhead.
- Use separate experimental prompt/schema versions and caches. A screening result cannot satisfy a full-evaluation cache lookup or become a published recommendation.

Reducing generated text is a promising latency optimization, supported by [OpenAI's latency guidance](https://developers.openai.com/api/docs/guides/latency-optimization).

### Candidate search experiments

- Compare the production **20→40** search with **8→20→40** and **12→20→40** waves.
- Re-run the global capacity optimizer after each wave; expand for attendees with unfilled capacity or unresolved screening decisions.
- Compare existing retrieval against separately ranked needs→offers, reverse needs→offers, and shared-context candidates.
- Evaluate candidate recall and final selection quality across the entire event. Filling slots alone does not establish that stopping early preserves quality.
- Include complementary profiles, sparse information, and strong one-way relevance in the benchmark. Missing information remains unknown and never excludes an attendee.

Choose thresholds on development data, freeze the configuration, then evaluate held-out data. Promote the lowest-cost passing configuration only if it also avoids a latency regression; otherwise retain Stage 1 behavior.

Specialized cross-encoders remain subsequent benchmark candidates. [Retrieve-and-rerank systems](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) justify investigating them, but relevance scores cannot replace Weft's validated mutual-benefit evaluation. Concrete candidates researched are [BAAI's multilingual BGE reranker](https://huggingface.co/BAAI/bge-reranker-v2-m3), [Cohere Rerank](https://docs.cohere.com/docs/rerank), and [Voyage rerankers](https://docs.voyageai.com/docs/reranker); none is selected for a production integration by this plan.

## Verification

- **Execution:** prove concurrency bounds, overlapping calls, deterministic merging, and serial/concurrent selection parity with frozen model outputs.
- **Recovery:** cover partial completion, retries, shutdown, lease reclamation, stale snapshots, and reuse of completed evaluation/verification work.
- **Budgets:** race simultaneous reservations near the ceiling; test invalid output, missing usage, uncertain billing, and actual usage above estimates.
- **Matching:** cover reciprocal slot consumption, exclusions, blocked pairs, identity holds, private evidence, tenant isolation, duplicate publication, and `more` mode.
- **Performance:** benchmark identical synthetic 150- and 300-attendee workloads with cold caches, warm caches, and interrupted-run recovery. Compare median durations over three repetitions; report stage and total times separately.
- **Quality:** require ≥90% held-out selected precision, ≥95% candidate recall, zero audited eligibility/privacy/fabrication violations, and no regression against baseline precision, recall, guest coverage, or total selection value.
- Run `poetry check --lock --strict`, `make verify`, migration checks, and isolated PostgreSQL integration tests. Live speed and quality claims require measured provider runs and independently reviewed labels, following [matching-quality requirements](../../matching-quality.md).

### Planning baseline evidence

During the 2026-10-24 planning session, before implementation:

- `poetry check --lock --strict` passed.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_matching.py tests/test_config.py tests/test_changes.py scripts/test_matching_quality.py -q -p no:cacheprovider` passed: **67 passed**.
- These focused checks are baseline evidence only. No optimized implementation, full verification, migration acceptance, live-provider benchmark, or expert-reviewed quality acceptance has been completed by saving this plan.

## Interfaces, rollout, and defaults

- Keep public recommendation, status, and feed contracts compatible. Add aggregate diagnostics through existing run progress, provenance, and usage fields.
- Keep CP-SAT selection, the current provider/models, and production matching rules. Introduce no vector database, queue service, or production reranking provider.
- Update canonical architecture, configuration, accounting, and verification documentation alongside implementation. Update this plan after material progress and before handoff.
- Generate and review the migration; verify fresh installation and upgrade against disposable storage. Never migrate at application startup.
- Roll out Stage 1 first. Concurrency can return to 1 for diagnosis. Keep Stage 2 disabled until its acceptance gates pass, with the existing pipeline retained as fallback.
- Shared-database migration, deployment, and live-provider spending remain outside this implementation scope. Report unavailable acceptance prerequisites explicitly. Keep the plan active while required acceptance is incomplete; do not claim the live 3× target from mocked-provider timings.

## Steps and progress

- [x] Inspect the pipeline, research related systems, confirm quality/provider preferences, and save the accepted plan.
- [x] Reconcile the current implementation. Planning-session focused baseline remains 67 passed; no timing baseline was available.
- [x] Implement Stage 1 concurrency, durable budget reservations, cache reuse, snapshot checks, and diagnostics.
- [x] Verify available unit/static checks and render the additive migration offline.
- [x] Implement disabled Stage 2 screening, cutoff, candidate-wave, and retrieval-mode experiments.
- [x] Run Neon `weft-console-test` migration, worker recovery, reservation-race, cache, publication, capacity, and event-scope acceptance.
- [x] Add and run opt-in PostgreSQL tests for concurrent budget admission, uncertain-billing retention after recovery, confirmed usage above estimate, migration tables, full-evaluation cache separation from screening, and verification-cache privacy compatibility.
- [ ] Run cold/warm/interrupted 150- and 300-attendee benchmarks and reviewed held-out quality evaluation; preserve the production defaults until these pass.
- [x] Update canonical docs and this plan; keep external and data-dependent acceptance gates pending.

## Implementation evidence (2026-10-24)

- Default provider concurrency is 4 (configurable 1–8). Evaluation batches and evidence verification run in bounded ordered waves; failures wait for already-dispatched calls to settle. OpenAI SDK retries are disabled and one explicit retry is allowed for retryable connection, timeout, rate-limit, conflict, and server errors. Each dispatch gets its own attempt and budget reservation.
- Run-row locking serializes reservation admission against confirmed spend and other outstanding/unknown reservations. Usage is saved before evaluation or verifier output validation. Missing usage and interrupted requests retain an unknown reservation. Run provenance snapshots model price rates. The reservation and separate screening/verification cache tables are introduced in migration `0003_matching_budget`.
- Embedding and evaluation cache reads are bulk queries. Retrieval vectors/rankings are reused for expansion, no-capacity pairs are skipped before full evaluation, and successful evidence verification has an event/privacy/model/version scoped cache.
- Diagnostics record stage durations, cache hits, candidates, requests, retries, token/spend usage, and safe failure codes. Provider prompt-cache read tokens are recorded when returned by the SDK; net cache charges are not calculated because the deployment-specific cached-input price is not configured separately.
- `WEFT_MATCHING_EXPERIMENTS_ENABLED=false` remains the default. The experimental path has a separate compact-screening schema, prompt version, and cache; uncertain, malformed, restricted, or unsupported-source screens escalate to full evaluation. Screening survivors are always fully evaluated and selected pairs are still evidence-verified. Search waves (20→40, 8→20→40, 12→20→40) and retrieval ranking variants can be selected only when the experiment flag is enabled.
- `poetry check --lock --strict` passed. Final `make verify` passed documentation checks, Ruff, formatting, strict mypy, and pytest: **84 passed, 16 skipped**. The 16 skips are the opt-in Neon PostgreSQL tests; all were run separately against Neon as detailed below. The optimization policy tests use mocked providers and do not establish live latency or quality.
- Offline `alembic upgrade head --sql` rendered `0001_f06` through `0003_matching_budget` without connecting to a database. The additive `0003_matching_budget` migration was then applied to the user-designated Neon `weft-console-test` database by the integration fixture. The complete database suite passed **16 tests in 657.82s**; after adding the privacy-context cache case, that case passed separately in **38.26s**. `git diff --check` passed.
- `AGENTS.md` and [Verification](../../VERIFICATION.md) require Neon `weft-console-test` and prohibit local database tests. The fixture uses fresh UUIDs, validates `.neon.tech` plus the exact database name, normalizes URL options for `asyncpg`, upgrades only `weft_engine`, scopes change polling/scheduling to generated events, and cleans only synthetic rows. The target-guard test rejects non-Neon and wrong-database URLs. No local database was used.
- No live-provider requests, deployment, commit, or push occurred. The user confirmed that a test-only provider credential, approved spend ceiling, and expert-reviewed benchmark dataset are unavailable. Therefore the live 3× scoring/verification target and held-out quality thresholds remain pending; no speedup or quality acceptance is claimed. Stage 2 remains disabled by default.

## Decisions and discoveries

- **2026-10-24:** The user selected `weft-engine`, preservation of match quality, the current provider/model setup, and a measured 3× scoring/verification speedup target.
- **2026-10-24:** Reciprocal matching was explicitly clarified: Julia↔Simon is one shared pair consuming one slot for both people. Candidate-shortlist membership is only an internal retrieval decision and may differ by attendee; it is not a selected match or guest action.
- **2026-10-24:** For 150 attendees, `150 × 149 ÷ 2 = 11,175` describes possible unordered pairs. With three initial slots each, at most `150 × 3 ÷ 2 = 225` pairs can be selected before additional grants, subject to evidence and restrictions. The screenshot's 2,790 candidates is event-specific, not a fixed requirement.
- **2026-10-24:** Research also covered [Grip's supply/demand and interaction signals](https://support.grip.events/artificial-intelligence-and-machine-learning-delivered-by-grip), [Swapcard's interest/knowledge and graph/vector approach](https://help.swapcard.com/en/articles/9449143-maximize-your-event-impact-using-the-power-of-ai), [adaptive computation](https://arxiv.org/abs/2505.18512), [model cascades](https://arxiv.org/abs/2305.05176), and [capacity-aware b-matching](https://arxiv.org/abs/2211.07796). These support experiments, not provider replacement, new behavioral-data collection, or claims of accepted Weft quality.
- **2026-10-24:** Stage 2 remains disabled by default. Thresholds and retrieval variants are implemented as experiment controls, but cannot be promoted from mocked/unit evidence; held-out labels and event-wide benchmark runs are still required.

## Handoff or outcome

Next action: when available, provide a test-only provider credential, approved spend ceiling, and the required independently reviewed development/held-out benchmark labels. Then run the planned cold/warm/interrupted 150- and 300-attendee evaluations for latency, spend, candidate recall, and held-out precision, retaining Stage 2 disabled unless every gate passes. Complete interface verification after those acceptance artifacts are reviewable. No other implementation or database-integration work remains.
