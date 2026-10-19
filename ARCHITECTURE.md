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
tests/                 runtime and configuration checks
scripts/               dependency-light documentation checker and fixtures
skills/                readable repository procedures
docs/                  canonical references and planning workflow
```

`create_app` reads settings on invocation, configures logging, constructs FastAPI, and includes the health router. Importing modules does not start network clients or load credentials. Tests inject settings and isolate environment variables and dotenv files. Development exposes OpenAPI and Swagger; production configuration requires documentation to be disabled explicitly. There is no database, worker, AI client, authentication integration, CORS policy, or matching API yet.

`GET /health` is public process liveness. It does not assert provider, storage, worker, or integration readiness. Logs use the standard library and omit request/profile bodies. Do not infer feature availability from a successful health check.

## Domain-oriented FastAPI conventions

Follow the [FastAPI best-practices guide](https://github.com/zhanymkanov/fastapi-best-practices): keep domains directly under `src/`, with technical responsibilities inside the owning domain. `src/main.py` composes the application; global files exist only for genuinely shared concerns.

When a domain needs them, introduce `router.py` (HTTP adapter), `schemas.py` (Pydantic input/output), `service.py` (business operations), `models.py` (persistence), `dependencies.py` (reusable boundary validation), `config.py` (domain settings), `exceptions.py`, `constants.py`, and `utils.py` (non-business helpers). These are conventions, not mandatory empty files. Avoid top-level technical buckets or generic repository/service hierarchies.

Use explicit module imports across domains. Dependencies may compose authentication, scope, and resource validation; keep HTTP concerns out of business logic. Use response models and constrained input models; reject unexpected request fields when contracts warrant it. Do not mutate data through GET routes or return successful placeholder feature responses.

Async routes and dependencies must use nonblocking I/O. Wrap unavoidable synchronous integrations in threadpool adapters or synchronous routes. CPU-heavy matching and durable recalculations need separate worker processes and persisted jobs; request-local BackgroundTasks cannot provide durable execution. Initialize and close future shared clients/pools through lifespan. Start async HTTP tests from the foundation.

## Future capability boundaries — not implemented

F06 will belong to a matching domain: immutable run inputs, live provider invocation, structured-result validation, automatic pair selection, and provenance. F07 will own durable change consumption, deduplication, coalescing, retry/recovery, status, and result delivery. Reuse domains when these responsibilities remain cohesive; do not precreate packages from this description.

F08 consumes valid selected pairs to create authoritative introduction records and expose match-list data in the product. The engine supplies versioned, traceable results. Creating authoritative matches, guest acceptance, Wefter assignments, meeting outcomes, and UI remain separate product operations. Final service contracts must resolve ownership before implementing cross-service writes.

The engine should own run snapshots, attempts, provider metadata, and result-delivery state. Event/guest identities, participation, profiles, restrictions, accepted/active/completed introductions remain authoritative upstream. Do not share mutable ORM models or take ownership of those records implicitly. See [domain](docs/domain.md) for identifiers and trust boundaries.

Persistence selection is deferred. The intended default for engine-owned relational storage is PostgreSQL with SQLAlchemy 2 async and Alembic, added when durable features are implemented. Migrations must be reviewed and run explicitly, never at application startup. Worker transport, deployment topology, authentication, and result delivery are unresolved; a Redis broker or provider SDK is not required by this foundation.

Durable architecture decisions belong in this file and the owning reference. Use the [planning policy](docs/PLANS.md) for future implementation work; historical plans never override current product requirements.
