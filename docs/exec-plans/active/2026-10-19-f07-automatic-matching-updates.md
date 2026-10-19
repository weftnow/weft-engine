# F07 — Automatic matching updates

Status: Active — engine and Console implemented; database suites pass; provider end-to-end and browser acceptance pending
Owner: unassigned (the backlog lists Antonio as the F07 owner)
Created: 2026-10-19

## Goal and acceptance criteria

When saved Console data changes, matching starts automatically and the results come back to the Console. The changes that count are imports, profile edits, exclusions, restorations, do-not-match restrictions and identity links. There is no start button and no human approval.

**Acceptance criteria**
- Each saved change leads to exactly one coalesced engine run per event once a short quiet period has passed:
  - quiet period 30s;
  - maximum wait 300s;
  - never more than one waiting or running run per event.
- Repeated change rows, crashes and concurrent workers never duplicate runs, receipts or feed entries.
- Transient failures retry with backoff (1, 5 and 15 minutes; cap 3). Configuration and budget failures never retry. `snapshot_stale` re-runs immediately, within the cap.
- Exclusion, a new do-not-match block or an identity hold revokes each affected issued recommendation, with a reason, and frees that capacity. Profile edits keep existing recommendations. A revoked pair is never re-issued.
- The engine exposes per-event status (`idle | waiting | running | failed | finished | invalid_result`) with the result source.
- The engine also exposes a cursor-based feed of `issued` and `revoked` recommendations, which F08 will consume.
- The Console records the missing change kinds and shows a read-only matching status panel on the event page.
- Automatic processing is off by default (`WEFT_MATCHING_AUTOMATIC_ENABLED=false`).

**Out of scope**
- F08 pair storage and the match list.
- F10 acceptance.
- F13 cancellation and replacement.
- Availability-triggered matching, which is still an open product decision.

**Tenants and roles:** every engine query is scoped by organization and event. Console status reads are limited to Owners and Organizers, checked at the service boundary.

## Context

**Current state**
- F06 creates runs only through `POST /matching-runs`. Every failure is final, and re-runs only add pairs; they never revoke any.
- The Console writes `public.event_matching_changes` rows in the same transaction as each change. Its kinds are `guest_excluded`, `guest_restored`, `match_block_added`, `match_block_removed` and `profile_updated`.
- Nothing reads those rows yet. CSV imports, attendee corrections and identity links write no row.
- The Console has no introduction, decision or completed-pair tables.

**Decisions**
- **Trigger:** the engine polls the change table. The Console sends no HTTP calls.
- **Results:** the engine exposes a pull feed.
- **Existing recommendations:** revoked only on hard ineligibility.
- **Scope:** work in both repos.

**Console repo:** a sibling checkout, `weft-console-front`, using Next.js 16, Drizzle and pnpm. Follow its `AGENTS.md`.

## Steps and progress

### Engine (this repo)

- [x] **Establish the baseline.** Poetry is not installed in this environment. Python 3.14 is at `/opt/homebrew/bin/python3.14`, and `uv` is available. Get `make verify` running, without editing the lockfile by hand, and record the baseline result. *Done: `.venv` built by `uv` from the pins in `poetry.lock`; a throwaway `poetry run` shim outside the repo lets `make verify` run unchanged. Baseline: 33 passed, 38% coverage.*
- [x] **Migration `migrations/versions/0002_f07_change_consumption.py`** (`weft_engine` only). Mirror every change in `src/matching/models.py`.
  - New `matching_change_receipts` table:
    - columns `change_id` (PK, the Console change id), `organization_id`, `event_id`, `kind`, `guest_ids uuid[]`, `change_created_at`, `received_at`, `batch_id` (nullable FK);
    - index `(event_id, batch_id, change_created_at)`.
  - New `matching_change_batches` table: `id`, `organization_id`, `event_id`, `created_at`, `attempt`, `next_attempt_at`, `state` (`scheduled | completed | abandoned`), `last_run_id` (FK to runs).
  - New `matching_feed_entries` table:
    - columns `seq bigserial` (PK), `organization_id`, `event_id`, `kind` (`issued | revoked`), `recommendation_id` (FK), `run_id`, `created_at`;
    - index `(organization_id, event_id, seq)`.
  - `matching_runs`: add `trigger` (`api | change`, default `api`) and `change_batch_id` (nullable FK).
  - `recommendations`: add `revoked_at`, `revocation_reason` (`guest_excluded | pair_blocked | identity_resolution_required | guest_missing`) and `revoked_by_run_id`. Keep the unique `(event_id, guest_low_id, guest_high_id)`.
- [x] **New module `src/matching/changes.py`.**
  - **Pure functions:**
    - `due_batches(pending_by_event, active_runs, now, quiet, max_wait)`.
    - `retry_decision(failure_code, attempt)`. These codes never retry: `spend_budget_unconfigured`, `provider_pricing_unconfigured`, `worker_configuration_changed`, `event_guest_limit_exceeded` and `spend_budget_exceeded`. Check the code that actually raises each of these in `worker.py`.
    - `revocations(active_recommendations, console_snapshot)`.
  - **`ingest()`:**
    - read up to `matching_change_poll_limit` rows where `processed_at IS NULL`, ordered by `created_at`;
    - resolve each event's organization with `ConsoleAdapter.event_organization`;
    - insert receipts with `ON CONFLICT DO NOTHING`;
    - then set `processed_at=now()` on the Console connection.
  - **`schedule()`:** for each due event, under `pg_advisory_xact_lock(hashtextextended(event,0))`, in one engine transaction:
    - create a batch;
    - attach the unbatched receipts;
    - apply `revocations()` against a fresh Console snapshot, and append `revoked` feed entries;
    - create the run with `trigger='change'` and idempotency key `f07:{batch_id}:{attempt}`.

    The automatic lifecycle is `complete=true` with empty lists, plus provenance `lifecycle_source: "console_none_recorded"`.
  - **`settle()`:** once a batch's run reaches a terminal state, a `finished` run completes the batch; any other outcome goes to `retry_decision()`, which either schedules the next attempt or abandons the batch.
- [x] **Refactor existing code.**
  - Split `storage.py::submit_run` into an internal `create_run(session, …, trigger, change_batch_id)` and the existing API wrapper, whose behavior stays the same.
  - In `worker.py`, `serve_worker` calls `ingest`, `schedule` and `settle` when `matching_automatic_enabled` is true, before `process_one()`.
  - In the publication transaction:
    - apply `revocations()` to the fresh snapshot;
    - exclude revoked rows from capacity counts;
    - append `issued` feed entries under the event advisory lock.
  - `_recommendations()` returns active rows only. Revoked pairs still count as prior pairs.
- [x] **Config (`src/config.py`).** Add:
  - `matching_automatic_enabled=False`
  - `matching_change_quiet_seconds=30`
  - `matching_change_max_wait_seconds=300`
  - `matching_change_retry_limit=3`
  - `matching_change_poll_limit=500`

  Add each one to `.env.example`.
- [x] **API.** Add a router at `/v1/organizations/{organizationId}/events/{eventId}/matching`. It reuses `authorize_organization`, `resources()` and `scoped_console()`.
  - `GET /status` returns `state`, `pendingChanges`, `latestRun {runId, status, trigger, failure, createdAt, finishedAt}`, `lastFinishedRunId`, `nextAttemptAt` and `automaticEnabled`.
  - `GET /feed?after=<seq>&limit<=200` returns `{entries: [{seq, kind, runId, recommendation}], nextCursor}`.
  - Extract a shared `result_item(row, snapshot_guests)` from `get_results`. Its output adds `revokedAt` and `revocationReason`, and the organizer-only evidence filtering stays in that single function.
- [x] **Tests.** *(unit tests and the opt-in Postgres suite pass; see Verification)*
  - `tests/test_changes.py` covers the pure functions, feed serialization and auth on the new endpoints (401 and 403).
  - Add opt-in Postgres integration tests behind `WEFT_ENGINE_DATABASE_TEST=1` and an explicit disposable URL. They create minimal Console-shaped `public` tables, run migrations 0001–0002 and fake the provider. They check:
    - receipts are idempotent;
    - a crash between receipt and `processed_at` leaves no duplicates;
    - two workers never double-schedule;
    - a transient failure retries;
    - a stale snapshot re-runs;
    - an exclusion appends a `revoked` feed entry;
    - feed paging works.
- [x] **Docs.** *(AGENTS.md, README.md, ARCHITECTURE.md, product, domain, matching-api, engineering, VERIFICATION, PLANS, docs index and debt tracker updated.)* Update `AGENTS.md`, `ARCHITECTURE.md`, `docs/product.md`, `docs/domain.md` and `docs/matching-api.md`. Update `docs/engineering.md` with the grants and environment variables, and record the debt below in `docs/exec-plans/tech-debt-tracker.md`.

### Console (`weft-console-front`)

- [x] **Record the missing change kinds.**
  - Add enum values `attendees_imported`, `attendee_corrected` and `identity_linked` in `src/infrastructure/database/schema/events.ts`.
  - Relax `event_matching_changes_guests_valid`: event-level kinds (`attendees_imported`, `identity_linked`) use an empty `guest_ids`, and the other kinds keep 1–2 guests.
  - Generate the migration with `pnpm db:generate --name=f07_matching_change_kinds` and review it.
- [x] **Write the new change rows.** Call the existing `recordChange(tx, …)` from `src/modules/attendees/server/networking-repository.ts` inside these existing transactions:
  - `attendee-import-repository.ts`, only when at least one guest is stored;
  - `attendee-record-service.ts::replaceAttendee`, with `[guestId]`;
  - `attendee-record-service.ts::linkAttendees`.
- [x] **Engine client.** Add `src/modules/network/server/matching-engine-client.ts`, marked `server-only`.
  - It uses `fetch` with `AbortSignal.timeout` and validates the response with zod.
  - It reads the env vars `WEFT_ENGINE_URL` and `WEFT_ENGINE_SERVICE_TOKEN`. Add both to `.env.example` without values.
- [x] **Status route and panel.**
  - Route `src/app/api/events/[eventId]/matching-status/route.ts`, then a handler and a service, following the networking pattern. Only Owners and Organizers may read it. When the engine can't be reached, return a typed `unavailable` response.
  - A read-only status panel in `event-detail-page.tsx`, built with the Console's design system. It has no start button and shows no fabricated results.
- [x] **Tests.** *(regex, handler/service/client and panel tests pass; the `WEFT_DATABASE_TEST=1` suite passes on a scratch database)*
  - A regex test on the migration.
  - DB tests behind `WEFT_DATABASE_TEST=1`: import, correction and link each write exactly one change row, and a no-op writes none.
  - Handler tests for allowed, denied and unavailable access.
- [x] **Docs.** *(done, plus the Console active plan `docs/exec-plans/active/2026-10-19-f07-automatic-matching-updates.md`.)* Update `docs/backend/networking-participation.md` with the grants and the fact that F07 now consumes the log. Also update `docs/backend/attendee-profiles.md` and `docs/product.md`. Add a Console active plan.

## Decisions and discoveries

- **2026-10-19 (deviation): the plan's no-retry list was corrected against the code.** The worker raises `spend_budget_exhausted`, not `spend_budget_exceeded`. `event_guest_limit_exceeded` is raised at schedule time (the batch is abandoned and revocations still apply), not by the worker. `tests/test_changes.py` checks every never-retry code appears in `worker.py` or `storage.py`.
- **2026-10-19 (deviation): additive schema beyond the plan.** `matching_change_batches.abandon_reason` records why a batch stopped; `matching_feed_entries` has `UNIQUE(recommendation_id, kind)` and a nullable `run_id` (a revocation can happen when no run could be created); `recommendations` has check constraints tying `revoked_at` to `revocation_reason`; a `(organization_id, event_id, created_at)` index on runs; migration 0002 back-fills an `issued` feed entry for each F06 recommendation.
- **2026-10-19 (deviation): cycle order is ingest → settle → schedule** (the plan listed schedule before settle) so a batch that just finished is closed before the next one is scheduled.
- **2026-10-19: quiet period and maximum wait are measured on Console `created_at`** against the database clock, so a backlog after downtime is immediately due. Retry attempts count toward the cap, including immediate `snapshot_stale` re-runs. Changes received during a backoff are attached to the retry's fresh snapshot.
- **2026-10-19: `status.pendingChanges` also counts Console rows the worker has not read yet**, which needs only the `SELECT` grant already required.
- **2026-10-19: all other runs sharing an event's lock** — API-created and automatic runs — are serialized by the existing per-event advisory lock; `schedule` re-checks for an active run or unfinished batch under that lock.

- **2026-10-19: the engine polls the change table.** The Console's transactional change log already exists. Grant the engine's Console role `SELECT` on `public.event_matching_changes` and a column-level `UPDATE (processed_at)`. Operators apply these grants; no migration creates roles.
- **2026-10-19: results go out through a pull feed.** The engine never writes Console tables.
- **2026-10-19: revocation happens only on hard ineligibility.** It runs at schedule time and again at publication, and both are idempotent. That way an exclusion takes effect even if the provider run fails.
- **2026-10-19: within an event, feed `seq` order matches commit order.** Feed entries are inserted under the per-event advisory lock.

## Verification

**Engine, 2026-10-19 (Python 3.14.6, packages from `poetry.lock` via `uv`, `poetry` shim)**
- Baseline before changes: `make verify` → 33 passed, total coverage 38%.
- After F07: `make verify` → documentation check, Ruff lint and format, strict mypy all clean; **79 passed, 11 skipped**, coverage 43%. The 11 skips are `tests/test_changes_database.py` (opt-in Postgres suite): no disposable database was provided, so receipts, crash recovery, double-scheduling, retry, stale re-run, revocation, never-re-issue and feed-paging scenarios are **written but not executed**.
- `alembic upgrade 0001_f06:0002_f07 --sql` rendered the expected DDL offline (no connection).
- Not run: `poetry check --lock --strict` (Poetry is not installed); live-provider and end-to-end checks.

**Console, 2026-10-19:** `pnpm verify` → 336 tests, 309 passed, 0 failed, 27 skipped (database-gated, including the new suite); `pnpm build` passed through the guarded local wrapper. Migration 0012 was generated and reviewed but **not applied anywhere**. Details are in the Console plan.

**Still to run (needs a disposable database and your approval):** the two opt-in Postgres suites, signed-in browser acceptance of the panel, and the end-to-end run below.

**Disposable-database run, 2026-10-19 (throwaway local Postgres on port 55432, created for this check and removed afterwards; no Neon or shared database touched):**
- Engine `tests/test_changes_database.py` → **11 passed** (receipts idempotent, crash between receipt and `processed_at`, coalescing, no double-scheduling across 4 concurrent schedulers, backoff retry, config failure abandoned, stale re-run, exclusion revokes and the pair is never re-issued, revocation before any provider work, feed paging and scoping, status/feed over HTTP).
- Console: migrations 0000–0012 applied to the scratch database only; `tests/matching-change-log-database.test.mjs` → **passed**. Existing `attendee-import-database` (4) and `attendee-record-database` (1, on a `weft_f03_scratch` database) still pass. `networking-database` and `profile-database` fail on a fixture that inserts guests without `person_id` — an existing gap unrelated to F07.
- The first engine run found **two latent F06 bugs that made every worker run fail** (`matching_processing_failed`), both fixed: `heartbeat()` used an untyped parameter inside `jsonb_build_object` (now `CAST(:stage AS text)`), and the embedding attempt fingerprint used a dict with tuple keys (now a list). F06 had never run against Postgres. The test helper also sets Alembic `path_separator=os` to avoid a deprecation warning that pytest treats as an error.
- Engine `make verify` afterwards: 79 passed, 11 skipped (the skips are the opt-in suite when no database is configured).

Still not run: live provider, signed-in browser acceptance of the panel, and the end-to-end run below.

Planned checks:
- `make verify` in the engine.
- `pnpm verify` and `pnpm build` in the Console.
- Opt-in Postgres suites in both repos, each against an explicitly disposable database.
- A local end-to-end run with automatic processing enabled and a small approved spend ceiling:
  1. Edit a profile.
  2. Confirm one run is created after the quiet period.
  3. Confirm the panel moves from waiting to running to finished.
  4. Confirm the feed contains `issued` entries.
  5. Exclude a guest and confirm a `revoked` entry appears.

## Handoff or outcome

**Next action:** the end-to-end run below with a small approved spend ceiling and real provider credentials, plus the signed-in browser check of the panel.

**Known limits to record as debt:**
- Automatic runs use an empty lifecycle until F08/F10 add tables. F08/F10 must add a Console lifecycle reader before authoritative introductions exist.
- Revoked pairs are never re-issued.
- Spend is capped only per run; there is no per-event or daily ceiling.
- Changes that are not logged, such as settings and Wefter edits, only make runs stale.
- Availability triggers are still undecided.
