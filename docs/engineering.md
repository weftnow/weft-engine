# Engineering

## Runtime and dependencies

Python 3.14 is the supported runtime. Use Poetry 2.2+; CI pins Poetry 2.4.1. This is an application in Poetry non-package mode: it runs from the repository root and does not publish an importable distribution. `src/main.py` is the composition entry point, following the domain-oriented FastAPI convention.

```sh
poetry env use python3.14
poetry lock
poetry sync
cp .env.example .env
make dev
```

`poetry.toml` keeps the environment in `.venv/`. Initial dependency locking requires PyPI access. Once generated, commit `poetry.lock` with `pyproject.toml`; regular installs use `poetry sync` without re-resolving. Never invent a lockfile or mix package managers/requirements files. `poetry check --lock --strict` verifies lock consistency. Use `poetry add` and `poetry add --group dev` for deliberate dependency changes; review resolver output and run verification.

FastAPI/Pydantic/Uvicorn are runtime dependencies. Ruff replaces separate lint, import-sorting, and formatting tools; strict mypy provides established Pydantic support. pytest, pytest-asyncio, HTTPX, and pytest-cov support async boundary tests. Make supplies task aliases without an additional runner dependency.

## Startup and settings

Run `make dev` for reload on `127.0.0.1:8000`, or `make start` for Uvicorn without reload on `0.0.0.0:8000`. Both invoke `src.main:create_app --factory`. Constructing the factory loads configuration; importing the module does not instantiate the service. No migration or external setup runs at startup.

| Variable | Default | Meaning |
| --- | --- | --- |
| `WEFT_ENVIRONMENT` | `development` | `development`, `test`, or `production`; invalid values fail startup |
| `WEFT_DOCS_ENABLED` | `true` | Swagger and OpenAPI routes; must be explicitly false in production |
| `WEFT_LOG_LEVEL` | `INFO` | Standard uppercase process logging level |
| `WEFT_MATCHING_DATABASE_URL` | unset | Async PostgreSQL URL for engine-owned `weft_engine` writes |
| `WEFT_CONSOLE_DATABASE_URL` | unset | Separate read-only PostgreSQL credential for Console-owned `public` matching inputs |
| `WEFT_MATCHING_SERVICE_TOKENS` | `{}` | JSON map from service token to allowed organization UUID strings |
| `WEFT_OPENAI_API_KEY` | unset | OpenAI credential used by the dedicated worker |
| `WEFT_MATCHING_MAX_SPEND_USD` | `0` | Per-run provider spend ceiling; the worker refuses calls when unset |
| `WEFT_MATCHING_INPUT_COST_PER_MILLION_USD` | `0` | Configured evaluation model input rate |
| `WEFT_MATCHING_OUTPUT_COST_PER_MILLION_USD` | `0` | Configured evaluation model output rate |
| `WEFT_MATCHING_EMBEDDING_COST_PER_MILLION_USD` | `0` | Configured embedding model input rate |
| `WEFT_MATCHING_AUTOMATIC_ENABLED` | `false` | F07 automatic processing in the worker; set the same value on the API process so status reports it correctly |
| `WEFT_MATCHING_CHANGE_QUIET_SECONDS` | `30` | Quiet period after the newest change before a run starts |
| `WEFT_MATCHING_CHANGE_MAX_WAIT_SECONDS` | `300` | Longest the oldest pending change waits while changes keep arriving |
| `WEFT_MATCHING_CHANGE_RETRY_LIMIT` | `3` | Retries after a transient failure (backoff 1, 5, 15 minutes) |
| `WEFT_MATCHING_CHANGE_POLL_LIMIT` | `500` | Console change rows read per polling cycle |

Settings read `.env` from the working directory; environment variables override it. Extra dotenv keys are ignored to allow deployment-specific values. Production should inject configuration, set `WEFT_ENVIRONMENT=production` and `WEFT_DOCS_ENABLED=false`, and run behind the deployment's network/TLS boundary. Configure service-token scopes, separate read-only Console and restricted engine runtime roles, worker-only provider credentials, current model prices, and an approved spend ceiling. The worker refuses provider calls when prices or spend limits are missing. Uvicorn controls its own access/error logs independently; the application logging setting configures application loggers. Never log profile or provider payloads.

Apply reviewed migrations explicitly with `WEFT_MATCHING_DATABASE_URL=... poetry run alembic upgrade head`; this URL must use a dedicated migration role. Start the API with `make start` and the separate worker with `make worker`; never run the worker in the API process. Provision Console table grants only for `events`, `event_guests`, `event_guest_profile_versions`, and `event_guest_match_blocks`. For F07 also grant the engine's Console role `SELECT` on `public.event_matching_changes` and a column-level `UPDATE (processed_at)` (`GRANT UPDATE (processed_at) ON public.event_matching_changes TO <role>`); operators apply these grants because no migration creates roles. Give the runtime role access only to `weft_engine`; the migration role alone creates that schema. Deployment values and provider spend approval are not repository defaults.

`GET /health` is public liveness, not readiness. Swagger is at `/docs`; OpenAPI is at `/openapi.json`. ReDoc is disabled. The browser continues through the Console authorization boundary; matching routes are service-token operations.

## FastAPI conventions

Read [architecture](../ARCHITECTURE.md) before introducing a domain or boundary. Keep validation schemas, routes, services, domain configuration, models, and dependencies local to their domain. Prefer async dependencies for nonblocking validation; blocking libraries need threadpool/synchronous adapters. Keep heavy work out of request processes. Add SQLAlchemy/Alembic or a worker only when implementing an agreed durable capability.

Tests use HTTPX's async ASGI transport and injected settings. Database pools are attached only when configured and closed through lifespan; database integration checks must enter lifespan and use explicitly disposable resources. Do not use mocks to claim live provider matching acceptance.

## Current bootstrap limit

Python 3.14 and Poetry are pinned by the repository and the generated lockfile is committed with dependency metadata. See [verification](VERIFICATION.md) for current unit evidence and F06 integration/quality acceptance prerequisites.
