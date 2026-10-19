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

Settings read `.env` from the working directory; environment variables override it. Extra dotenv keys are ignored to allow deployment-specific values. Production should inject configuration, set `WEFT_ENVIRONMENT=production` and `WEFT_DOCS_ENABLED=false`, and run behind the deployment's network/TLS boundary. No AI or database credentials are needed yet. Uvicorn controls its own access/error logs independently; the application logging setting configures application loggers. Never log profile or provider payloads.

`GET /health` is public liveness, not readiness. Swagger is at `/docs`; OpenAPI is at `/openapi.json`. ReDoc is disabled. There is no CORS middleware: browser access to future protected operations needs an explicit architecture decision rather than a wildcard default.

## FastAPI conventions

Read [architecture](../ARCHITECTURE.md) before introducing a domain or boundary. Keep validation schemas, routes, services, domain configuration, models, and dependencies local to their domain. Prefer async dependencies for nonblocking validation; blocking libraries need threadpool/synchronous adapters. Keep heavy work out of request processes. Add SQLAlchemy/Alembic or a worker only when implementing an agreed durable capability.

Tests use HTTPX's async ASGI transport and injected settings. The current app has no lifespan resources; when adding them, tests must enter lifespan explicitly to verify startup/cleanup. Do not use mocks to claim live provider matching acceptance.

## Current bootstrap limit

The setup environment could not resolve `pypi.org`, so dependency installation and generated-lock verification remain pending. See [verification](VERIFICATION.md) for actual evidence and [debt](exec-plans/tech-debt-tracker.md) for the concrete recovery command. This limit does not authorize adding fake feature responses or disabling required checks.
