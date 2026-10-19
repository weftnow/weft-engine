# Weft Engine

FastAPI foundation for Weft matching and related backend operations. F06 (live AI matching), F07 (automatic updates), and F08 (automatic pair creation) are documented as future scope. No matching logic, jobs, storage, provider integration, or feature execution plans are included.

## Local development

Requires Python 3.14, Poetry 2.2+ (CI uses 2.4.1), and Make.

```sh
poetry env use python3.14
poetry lock
poetry sync
cp .env.example .env
make dev
```

The environment is local to `.venv/`. Initial locking is pending because the setup environment could not resolve PyPI; run `poetry lock` with network access and retain the generated lockfile. Subsequent installs need only `poetry sync`. Visit [Swagger UI](http://127.0.0.1:8000/docs) or call `GET /health` on port 8000. Health returns `{"status":"ok","service":"weft-engine"}` and reports process liveness only. No credentials are required for this foundation. See [engineering](docs/engineering.md) for configuration and startup details.

```sh
make verify       # docs, lint, formatting, strict types, tests
make verify-fast  # docs, lint, formatting, strict types
make format       # explicit formatter; hooks do not rewrite files
make start        # server on 0.0.0.0:8000 without reload
```

Start with [AGENTS.md](AGENTS.md) and the [documentation index](docs/README.md). [Architecture](ARCHITECTURE.md) describes the domain-oriented `src/` layout. [Hooks](docs/HOOKS.md) explains optional checkout activation; the scripts are prepared, not enabled automatically.
