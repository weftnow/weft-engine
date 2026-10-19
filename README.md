# Weft Engine

FastAPI backend for Weft matching and related operations. F06 implements authenticated run APIs, engine-owned PostgreSQL persistence, a read-only Console adapter, and a separate live AI worker. F06 remains active pending isolated database, live-provider, and expert-reviewed quality acceptance. F07 adds Console change polling, coalesced automatic runs with retry, recommendation revocation, a status endpoint and a pull feed; it is off by default and its acceptance is tracked in the active F07 plan. F08 authoritative pair creation remains future scope.

## Local development

Requires Python 3.14, Poetry 2.2+ (CI uses 2.4.1), and Make.

```sh
poetry env use python3.14
poetry lock
poetry sync
cp .env.example .env
make dev
```

The environment is local to `.venv/`; install locked dependencies with `poetry sync`. Visit [Swagger UI](http://127.0.0.1:8000/docs) or call `GET /health` on port 8000. Health returns `{"status":"ok","service":"weft-engine"}` and reports process liveness only. Matching needs separately provisioned service credentials, PostgreSQL roles, OpenAI credentials, model prices, and an approved spend limit. See [engineering](docs/engineering.md), the [service API](docs/matching-api.md), and [quality evaluation](docs/matching-quality.md) for the operational contract.

```sh
make verify       # docs, lint, formatting, strict types, tests
make verify-fast  # docs, lint, formatting, strict types
make format       # explicit formatter; hooks do not rewrite files
make start        # server on 0.0.0.0:8000 without reload
make worker       # separate durable matching worker
```

Start with [AGENTS.md](AGENTS.md) and the [documentation index](docs/README.md). [Architecture](ARCHITECTURE.md) describes the domain-oriented `src/` layout. [Hooks](docs/HOOKS.md) explains optional checkout activation; the scripts are prepared, not enabled automatically.
