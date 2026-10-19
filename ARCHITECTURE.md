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
    models.py          engine-owned weft_engine records
    worker.py          leased worker and live provider pipeline
    selection.py       evidence gates and CP-SAT selection
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

Runtime database roles must have Console `SELECT` access only to required event/profile/restriction tables and `SELECT`/`INSERT`/`UPDATE` access to `weft_engine`. The migration credential alone creates or changes the engine schema. The service does not migrate at startup. Database URLs target the Console PostgreSQL database while preserving existing tables outside `weft_engine`.

Lifecycle context is supplied by the authenticated service caller and cannot be refreshed from Console-owned records that do not exist. F07/F08 must define and supply authoritative lifecycle freshness and recheck before introduction creation.

## Future capability boundaries

F06 matching is implemented in the matching domain. F07 will own durable change consumption, deduplication, coalescing, retry/recovery, status, and result delivery. Reuse domains when these responsibilities remain cohesive; do not precreate packages from this description.

F08 consumes valid selected pairs to create authoritative introduction records and expose match-list data in the product. The engine supplies versioned, traceable results. Creating authoritative matches, guest acceptance, Wefter assignments, meeting outcomes, and UI remain separate product operations. Final service contracts must resolve ownership before implementing cross-service writes.

The engine should own run snapshots, attempts, provider metadata, and result-delivery state. Event/guest identities, participation, profiles, restrictions, accepted/active/completed introductions remain authoritative upstream. Do not share mutable ORM models or take ownership of those records implicitly. See [domain](docs/domain.md) for identifiers and trust boundaries.

F07 change ingestion and result delivery remain future work. Do not add them to the F06 worker queue.

Durable architecture decisions belong in this file and the owning reference. Use the [planning policy](docs/PLANS.md) for future implementation work; historical plans never override current product requirements.
