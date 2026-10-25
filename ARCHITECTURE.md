# Weft Engine architecture

## Implemented foundation

The application uses Python 3.14, FastAPI, Pydantic v2, Pydantic Settings, and Uvicorn. Poetry manages dependencies; Ruff handles linting/imports/formatting, mypy checks strict types, and pytest verifies behavior.

```text
src/
  main.py              application factory and router composition
  config.py            process settings
  logging.py           process logging
  health/
    router.py          GET /health
    schemas.py         public health response
  matching/
    router.py          authenticated versioned matching API
    console.py         read-only Console PostgreSQL adapter
    models.py          engine-owned weft_engine records and caches
    worker.py          leased worker, budget reservation, and provider pipeline
    experiments.py     pure policies for disabled screening experiments
    selection.py       evidence gates and CP-SAT selection
    changes.py         F07 change ingestion, coalescing, retry, revocation, status and feed reads
    status_router.py   F07 per-event status and recommendation feed
tests/                 runtime, contracts, selection, and configuration checks
migrations/            explicit Alembic migrations limited to weft_engine
scripts/               dependency-light documentation checker and fixtures
skills/                readable repository procedures
docs/                  canonical references and planning workflow
```

`create_app` reads settings on invocation, configures logging, constructs FastAPI, and composes health and matching routers. Importing modules does not connect to databases or load credentials. Database pools are created only when URLs are configured and are closed through lifespan. Development exposes OpenAPI and Swagger; production configuration requires documentation to be disabled explicitly. Matching uses separate engine and read-only Console PostgreSQL credentials. Protected routes use configured service tokens with explicit organization grants; the Console remains the browser authorization boundary.

`GET /health` is public process liveness. It does not assert provider, storage, worker, or integration readiness. Logs use the standard library and omit request/profile bodies. Do not infer feature availability from a successful health check.

## Domain-oriented FastAPI conventions

Follow the [FastAPI best-practices guide](https://github.com/zhanymkanov/fastapi-best-practices): keep domains directly under `src/`, with technical responsibilities inside the owning domain. `src/main.py` composes the application; global files exist only for genuinely shared concerns.

When a domain needs them, introduce `router.py` (HTTP adapter), `schemas.py` (Pydantic input/output), `service.py` (business operations), `models.py` (persistence), `dependencies.py` (reusable boundary validation), `config.py` (domain settings), `exceptions.py`, `constants.py`, and `utils.py` (non-business helpers). These are conventions, not mandatory empty files. Avoid top-level technical buckets or generic repository/service hierarchies.

Use explicit module imports across domains. Dependencies may compose authentication, scope, and resource validation; keep HTTP concerns out of business logic. Use response models and constrained input models; reject unexpected request fields when contracts warrant it. Do not mutate data through GET routes or return successful placeholder feature responses.

Async routes and dependencies must use nonblocking I/O. Wrap unavoidable synchronous integrations in threadpool adapters or synchronous routes. CPU-heavy matching and durable recalculations need separate worker processes and persisted jobs; request-local BackgroundTasks cannot provide durable execution. Initialize and close future shared clients/pools through lifespan. Start async HTTP tests from the foundation.

## F06 matching implementation

F06 owns immutable run snapshots, PostgreSQL leased jobs, provider attempts, cached embeddings/evaluations, recommendation records, and slot grants. Alembic migrations create only `weft_engine`; Console tables remain in their existing schema and are queried through explicit SQL projections. `poetry run python -m src.matching.worker` starts a separate worker. Matching outputs remain recommendations, never authoritative introductions. The worker checks Console snapshot freshness before publication, holds linked duplicate identities, verifies evidence quotations against source fields, and filters organizer-only evidence from result responses.

Provider scoring and selected-pair evidence verification run in bounded waves using independent database sessions; the default shared provider concurrency is four (configurable from one to eight). Every dispatched request has an attempt and a durable per-run cost reservation. Reservations are serialized under the run row lock; interrupted or unknown-billing requests retain their reserved amount. Confirmed token usage and cost are recorded separately from estimated spend. Successful embedding, evaluation, and evidence-verification results are cached with their existing model/input/privacy compatibility keys.

The production worker uses `compact-judgment-v1` authoritative judgments for every candidate
in the unchanged 20→40 blended retrieval pool. `compact.py` projects substantive profile facts,
restrictions and privacy metadata, gives source passages exact references, deduplicates profiles
within requests, and batches up to eight pairs (48,000-character soft payload ceiling; a single
oversized pair remains intact). Both directional benefit claims must cite both guests for a
qualifying judgment. Exact quotations are hydrated locally; missing information comes from
saved missing-details facts and uncertainty is rendered from bounded codes. No LLM summary
truncates the source profile. This changes the internal provider contract, not the result API.

Only selected pairs receive longer shareable explanations, through the existing verifier.
Privacy-filtered evidence indexes are rebuilt after filtering, and returned identities/indexes
are validated. Unsupported explanations discard that pair and rerun capacity selection over
already judged candidates; provider/budget failures still fail the run. Verified explanations
can supply selected benefits; private-only benefits retain the concise judgment claim.
No additional screening or full-evaluation pass runs before selection.

Evaluation cache hashes include schema version, event, authoritative pair identities and
matching-relevant content. Model/prompt/policy and organization scope remain database filters;
exact compatible legacy evaluations remain reusable. Metadata-only revision changes do not
invalidate new judgments, but current snapshot/lifecycle/eligibility checks still guard publication.
Verification uses a separate versioned cache. No new migration is needed for these contracts.

Retrieval preserves the prior score formula and tie ordering, precomputes lexical tokens/vector
norms, and stores only the best 40 edges per attendee. This removes per-attendee all-edge scans
and quadratic retained ranking storage; similarity computation still examines every pair.
The 300-eligible-attendee production guard remains. Larger-event CPU/load acceptance is pending.

The historical screening/search helpers and configuration are retained for compatibility but
are not invoked by production processing, even when `WEFT_MATCHING_EXPERIMENTS_ENABLED` is true.
Candidate reduction, new ranking formulas, alternate models and approximate retrieval are deferred
by explicit user direction.

Runtime database roles must have Console `SELECT` access only to required event/profile/restriction tables (plus, for F07, `SELECT` on `public.event_matching_changes` and a column-level `UPDATE (processed_at)`) and `SELECT`/`INSERT`/`UPDATE` access to `weft_engine`. The migration credential alone creates or changes the engine schema. The service does not migrate at startup. Database URLs target the Console PostgreSQL database while preserving existing tables outside `weft_engine`.

Lifecycle context is supplied by the authenticated service caller and cannot be refreshed from Console-owned records that do not exist. Automatic F07 runs supply an explicitly complete but empty lifecycle (`lifecycle_source: console_none_recorded`); F08 must define and supply authoritative lifecycle freshness and recheck before introduction creation.

## Future capability boundaries

F06 matching and F07 automatic updates are implemented in the matching domain. F07 owns durable change consumption, deduplication, coalescing, retry/recovery, revocation, status, and result delivery; do not precreate packages beyond this.

F08 consumes valid selected pairs to create authoritative introduction records and expose match-list data in the product. The engine supplies versioned, traceable results. Creating authoritative matches, guest acceptance, Wefter assignments, meeting outcomes, and UI remain separate product operations. Final service contracts must resolve ownership before implementing cross-service writes.

The engine should own run snapshots, attempts, provider metadata, and result-delivery state. Event/guest identities, participation, profiles, restrictions, accepted/active/completed introductions remain authoritative upstream. Do not share mutable ORM models or take ownership of those records implicitly. See [domain](docs/domain.md) for identifiers and trust boundaries.

## F07 automatic updates

When `WEFT_MATCHING_AUTOMATIC_ENABLED` is true the worker loop runs, before claiming a run: `ingest` (copy unprocessed rows of `public.event_matching_changes` into `matching_change_receipts` with `ON CONFLICT DO NOTHING`, then set `processed_at` on the Console row), `settle` (complete a batch whose run finished; otherwise apply `retry_decision` to plan the next attempt or abandon), and `schedule` (for each event whose newest change is 30 seconds old, or whose oldest has waited 300 seconds, and that has no waiting or running run or unfinished batch). `schedule` runs under the per-event `pg_advisory_xact_lock` in one engine transaction: it creates a `matching_change_batches` row, attaches the receipts read before the fresh Console snapshot, revokes ineligible recommendations, and creates one run with `trigger='change'` and idempotency key `f07:{batchId}:{attempt}`. Backoff retries reuse the batch, attach changes received meanwhile, and count toward the cap.

Revocation (`revocations()` in `changes.py`) applies only to hard ineligibility, at schedule time and again inside the publication transaction, so an exclusion takes effect even when the provider run fails. Revoked rows keep their pair, free capacity, and still count as prior pairs. `issued` and `revoked` entries are appended to `matching_feed_entries` under the event lock, so `seq` order within an event is commit order; `UNIQUE(recommendation_id, kind)` makes writes idempotent. The Console reads state through `GET .../matching/status` and F08 will consume `GET .../matching/feed`; see the [service API](docs/matching-api.md).

Durable architecture decisions belong in this file and the owning reference. Use the [planning policy](docs/PLANS.md) for future implementation work; historical plans never override current product requirements.
