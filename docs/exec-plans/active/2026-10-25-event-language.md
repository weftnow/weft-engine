# Event language for shareable reasons

Status: Active
Owner: current agent
Created: 2026-10-25
Specification: [Event language](../../changes/2026-10-25-event-language.md)
Counterpart: `weft-console-front` `docs/exec-plans/active/2026-10-25-console-translations.md` (steps 4 and 6)

## Goal and acceptance criteria

Reasons are written in the event's language (`en` | `es`) read from `public.events.language`. See the specification. Affected boundary: the Console adapter snapshot only; no new endpoints or roles.

## Context

`src/matching/console.py` `snapshot()` selects from `public.events`; the verification prompt is in `src/matching/worker.py`; the prompt version is in `src/config.py`. The Console migration adding `events.language` must be applied before the engine reads it.

## Steps and progress

- [x] Write specification and this plan (2026-10-25).
- [x] Read `language` in `snapshot()` and add it to provenance (2026-10-25). `Language` alias added to `schemas.py`; run provenance is an untyped JSON column, so no Alembic migration.
- [x] Add the Spanish instruction to the verification prompt; bump the verification cache version (2026-10-25). `matching_prompt_version` was deliberately not bumped, see Decisions.
- [x] Tests: `tests/test_event_language.py` (fallback, fingerprint, prompt text, provenance) and a database test for language-scoped verification caching (skipped without a disposable database).
- [ ] `make verify` and isolated-database Spanish run with expert sample review.

## Decisions and discoveries

- 2026-10-25: Work happens in the worktree `../weft-engine-translations` because the main checkout holds unrelated uncommitted DeepSeek provider edits to `worker.py` and `config.py`, and `main` rewrites `worker.py`.

- 2026-10-25: `matching_prompt_version` was not bumped, unlike the Console plan's step 6 text. It keys `EvaluationCache`; bumping it would discard every cached pair evaluation and re-run live evaluations for all events, although the evaluation prompts did not change. The changed prompt is the verification pass, whose cache is keyed by `verifier_version` (now `f06-selected-explanation-v3`) and by the new `language` field in the verification payload. Revisit if reviewers want attempt records labeled with a new prompt version.
- 2026-10-25: Dependency on the Console migration. `snapshot()` now selects `public.events.language`, so the Console migration `0015` must be applied to the target database before this engine version runs; otherwise snapshots fail with an undefined-column error.

## Verification

- 2026-10-25, worktree `weft-engine-translations`: `make verify` could not run (pyenv has no Python 3.14 for this directory). Ran its parts with the main checkout's venv: `ruff check` passed, `ruff format --check` passed, `mypy src tests` passed (30 files), `pytest` 100 passed, 24 skipped (database suites need an authorized disposable database), `python3 scripts/check_harness.py` passed.
- Not run: database-backed tests, isolated-database Spanish run, expert sample review.

## Handoff or outcome

Next action: apply Console migration 0015 to an isolated database, run the database suites, then a Spanish event end to end and the expert sample review in `docs/matching-quality.md`.
