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
- [ ] Read `language` in `snapshot()` and add it to schemas and provenance.
- [ ] Add the Spanish instruction to the verification prompt; bump `matching_prompt_version`.
- [ ] Tests: snapshot, prompt, fingerprint.
- [ ] `make verify` and isolated-database Spanish run with expert sample review.

## Decisions and discoveries

- 2026-10-25: Work happens in the worktree `../weft-engine-translations` because the main checkout holds unrelated uncommitted DeepSeek provider edits to `worker.py` and `config.py`, and `main` rewrites `worker.py`.

## Verification

Not started.

## Handoff or outcome

Next action: implement the snapshot change after the Console migration for `events.language` exists.
