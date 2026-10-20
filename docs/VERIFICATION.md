# Verification

Run commands from the repository root with Python 3.14, Poetry 2.2+, Make, and installed dependencies. Initial resolution needs PyPI; subsequent environments use `poetry.lock`. Unit checks require no provider or database. F06 acceptance also needs an explicitly isolated disposable PostgreSQL database with representative Console tables and `weft_engine`, plus separately supplied live-provider credentials and an approved spend budget.

| Command | Evidence |
| --- | --- |
| `poetry check --lock --strict` | Project metadata and generated-lock consistency |
| `make check-docs` | Required paths, entry-point length, conventional local Markdown links |
| `make lint` | Ruff lint, import-order, upgrade, and async checks |
| `make format-check` | Ruff formatting without mutations |
| `make typecheck` | Strict mypy on application/tests with the Pydantic plugin |
| `make test` | pytest runtime/configuration, documentation-checker, and hook-dispatch tests; application branch coverage |
| `make verify-fast` | Documentation, lint, formatting, and types |
| `make verify` | All fast checks plus tests |
| `WEFT_ENGINE_DATABASE_TEST=1 WEFT_ENGINE_TEST_DATABASE_URL=... pytest tests/test_changes_database.py` | Opt-in F07 PostgreSQL integration; needs an explicitly disposable, empty database whose name contains `test` |

`make format` is an explicit source mutation. Checks and hooks do not fix, stage, or rewrite source. No dummy build command exists: this service runs directly through Uvicorn and uses Poetry only for application dependency management.

## Change matrix

- Documentation/instructions: run `make check-docs`; checker/hook changes also require their failure fixtures and full verification.
- Application, dependency, configuration, or CI changes: run lock validation and `make verify`; exercise affected HTTP/startup behavior.
- Future protected operations: cover authenticated/unauthenticated, permitted/denied organization/event scope, malformed input, stale versions, and duplicate delivery.
- Future persistent jobs/results: use explicitly isolated disposable storage and verify retries, concurrency, stale/invalid output, shutdown/recovery, and delivery idempotency.
- Future live AI integration: record actual provider/model and versioned synthetic inputs with redacted evidence; mock responses do not prove F06 success.
- F06 PostgreSQL integration: connect only when explicitly supplied an isolated disposable test database identity and separate credentials. Never reuse production, preview, or shared development database URLs.
- F06 live-provider checks: require credentials explicitly supplied for the check, configured model prices, and an approved spend ceiling. Do not read production credentials from ambient shell state or claim live acceptance from mocks.

## Runtime smoke

Start `make dev`, request `GET http://127.0.0.1:8000/health`, and expect 200 with `status: ok` and `service: weft-engine`. Check `/docs` and `/openapi.json`. Stop the process after inspection. For production configuration, set `WEFT_ENVIRONMENT=production WEFT_DOCS_ENABLED=false`; docs/OpenAPI must return 404 while health remains available. A production environment with docs enabled must fail settings validation. No secrets or profiles should appear in output.

Async ASGI tests exercise routing/serialization, authentication boundaries, and production docs behavior without a socket. They do not prove Uvicorn process startup, deployment routing, TLS, PostgreSQL integration, or live matching. Enter lifespan for any configured database-pool tests.

## Dependency-free harness checks

When application dependencies are unavailable, run these directly; they do not establish application acceptance:

```sh
python3 scripts/check_harness.py
python3 -m unittest discover -s scripts -p 'test_*.py'
```

The checker derives the root from its location. Fixtures exercise valid/broken/encoded/reference links, missing paths, long instructions, invalid configuration, symlink traversal, and CLI exit status. It checks existence, not Markdown anchors, remote URLs, undefined reference labels, HTML/MDX, or all Markdown grammar. Hook fixtures use stubbed Git/Make processes and temporary directories; they prove dispatch and failure propagation, not actual verification success. See [hooks](HOOKS.md).

Tests isolate dotenv/environment settings and use synthetic values. Future integration tests must require an explicit opt-in, disposable resource identity, bounded cleanup, and separate credentials; never use production by default. Keep live integrations out of normal unit tests.

## Opt-in PostgreSQL matching checks

`tests/test_matching_postgres.py` exercises the real Console adapter SQL, authenticated API, run persistence, worker processing, SDK response parsing, recommendation storage, idempotency, restrictions, freshness, failures, and lease-owner fencing. The provider transport returns synthetic responses and makes no paid calls. These checks do not establish live AI quality.

Supply a separate test connection URL in a private file and explicitly name the authorized database:

```sh
WEFT_INTEGRATION_DATABASE_URL_FILE=/absolute/path/to/private-test-url \
WEFT_INTEGRATION_DATABASE_NAME=authorized_test_database \
poetry run pytest tests/test_matching_postgres.py -q
```

The suite skips without that opt-in and refuses a database-name mismatch. It creates synthetic organization/event/guest records inside an outer transaction, binds API/worker sessions and the real Console adapter to that connection, and rolls back all fixtures. It does not run migrations or drain the shared worker queue. Targeted processing sets a lease only on its own uncommitted run. It does not cover separate-process queue claiming, crash recovery, concurrent connections/publication, or deployment role grants.

For the 2026-10-19 check, Antonio explicitly authorized the existing `weft_console_test` database on Neon's `dev` branch instead of a local database. That exception permits these transaction-isolated fixtures, not resets or migration changes to the shared target. See the [active plan](exec-plans/active/2026-10-19-f06-live-ai-matching.md) for results and remaining acceptance.

## F06 evidence and current limits

F06 depends on deployment-specific PostgreSQL role provisioning and provider spend configuration. Benchmark quality cannot be accepted from mocks or model self-grading; it requires reviewed expert labels and at least 60 synthetic profiles / 200 labeled pairs. The 300-guest live benchmark also requires approved provider spend.

On 2026-10-19, Python 3.14.6 / Poetry 2.4.1 passed `poetry check --lock --strict` and `make verify`: documentation checker, Ruff lint/format, strict mypy, and 33 pytest tests. Branch-aware total coverage was 38%; database-backed adapter/worker paths are intentionally not covered without an explicitly isolated disposable PostgreSQL target. Alembic offline SQL rendered with `weft_engine` creation before its version table, without connecting to a database. A local Uvicorn smoke with injected test settings returned the expected `/health` payload and HTTP 200 for OpenAPI, then stopped. The [active F06 plan](exec-plans/active/2026-10-19-f06-live-ai-matching.md) records the exact outstanding database, live-provider, and expert-label acceptance gates.

Subsequently on 2026-10-19, all seven opt-in PostgreSQL cases passed on the explicitly user-authorized Neon `dev` database `weft_console_test` in 135.32 seconds, with fixture rollback and a synthetic provider transport. They exposed and verified fixes for heartbeat parameter typing and embedding-fingerprint serialization. A separate normal-factory ASGI smoke verified real database pools and lifespan cleanup. `poetry check --lock --strict` and `make verify` passed again (33 passed, seven opt-in skips in the default suite). Read-only migration inspection found revision `0002_f07`, newer than this checkout's `0001_f06`; no migrations were executed. Live-provider/quality acceptance, migration isolation, separate-process queue recovery, concurrency, and deployment grants remain pending.

Historical foundation baseline from before F06 implementation: Python 3.14 documentation checks and eight standard-library harness tests passed; supplemental Python 3.12 checks were not evidence for the declared runtime. At that time the lockfile was missing and Ruff was unavailable. Those setup gaps are resolved by the current evidence above.
