# Weft Engine

FastAPI service for Weft matching and related backend operations. F06 engine matching is implemented; its external database, live-provider, and quality acceptance gates remain active-plan work. F07 automatic updates are implemented behind `WEFT_MATCHING_AUTOMATIC_ENABLED` (off by default; [active plan](docs/exec-plans/active/2026-10-19-f07-automatic-matching-updates.md) holds the open acceptance gates). F08 remains future scope; do not implement it or create competing plans unless requested.

## Documentation map

- [Index](docs/README.md): load only relevant references.
- [Product](docs/product.md) and [domain](docs/domain.md): requirements, scope, ownership, unknowns.
- [Architecture](ARCHITECTURE.md): implemented boundaries and future direction.
- [Engineering](docs/engineering.md): Python, FastAPI, dependencies, local runtime.
- [Design](docs/design/design.md): API presentation; no application UI.
- [Planning policy](docs/PLANS.md), [active work](docs/exec-plans/active/), and [change specifications](docs/changes/README.md).
- [Verification](docs/VERIFICATION.md), [hooks](docs/HOOKS.md), and [debt](docs/exec-plans/tech-debt-tracker.md).
- [Repository skills](skills/README.md): maintenance, verification handoff, contextual commits; read the procedure manually when needed.

## Working agreements

- Inspect instructions, relevant code/callers/tests, and working-tree changes before editing. Preserve unrelated work.
- Read Product for behavior and Architecture before changing boundaries, interfaces, or persistence. Investigate disagreements with implementation.
- Maintain canonical docs within authorized changes. Label proposals and unknowns; code and historical plans do not establish product requirements.
- Follow the plan lifecycle in Planning policy. Inspect active plans before starting nontrivial work. An explicit instruction to defer planning takes precedence.
- Keep routers thin and business logic in its owning domain. Add domain-local files only when needed; do not scaffold empty layers.
- Use explicit cross-domain imports. Validate untrusted data with Pydantic and reusable dependencies at operation boundaries.
- Use async I/O in async code. Offload blocking libraries; durable/CPU-heavy matching work belongs in workers rather than request handlers or FastAPI BackgroundTasks.
- Preserve organization/event isolation and explicit identity/version references. Future protected routes need authenticated service identity and authorization; UUIDs alone grant no access.
- Never equate matching with guest acceptance or a physical introduction. Missing profile information stays unknown and does not gate eligibility.
- Use Poetry and its lockfile. Keep dependency changes deliberate; do not introduce databases, queues, providers, or services solely to populate the architecture.
- Do not edit generated lockfiles by hand, apply migrations at startup, or log profile content, organizer-only information, credentials, or provider payloads.
- Database/integration tests require explicitly isolated disposable resources. Never inherit production credentials for tests.

## Commands and completion

Use Python 3.14 and Poetry 2.2+. Install with `poetry sync` once a lockfile exists; use `poetry lock` when changing dependency constraints. Start development with `make dev` and browse `http://127.0.0.1:8000/docs`.

Run `make verify` before completion: documentation checks, Ruff lint/format check, strict mypy, and pytest. Run affected runtime/integration checks from Verification. Hooks supplement these commands and never replace them.

Report actual results, skipped suites, prerequisite failures, and next steps. Do not weaken checks or claim unexecuted acceptance passed. Stage, commit, push, deploy, activate hooks, or operate external services only within the user's requested scope.
