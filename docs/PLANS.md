# Execution plans

The foundation is delivered and [F06 implementation](exec-plans/active/2026-10-19-f06-live-ai-matching.md) is active, with external database/provider and expert-quality acceptance pending. [F07 automatic updates](exec-plans/active/2026-10-19-f07-automatic-matching-updates.md) is active, with isolated-database and end-to-end acceptance pending. F08 remains deferred. This document defines the plan workflow and does not authorize unrelated feature implementation or external operations by itself.

For future nontrivial, risky, cross-boundary, or multi-session work, inspect [active plans](exec-plans/active/) and resume relevant work rather than creating competing plans. Small clear changes may proceed with a conversational plan. Explicit user instructions about deferring planning take precedence.

When planning is requested or applicable to later authorized work, create `docs/exec-plans/active/YYYY-MM-DD-short-name.md` before implementation. Include observable acceptance, scope/non-goals, affected organization/event/actor boundaries, constraints, verification, and the next action. Label proposals and unknowns; neither historical plans nor code establish requirements. Use a [change specification](changes/README.md) for consequential unresolved behavior.

Update the plan after material progress and before handoff. Record commands and actual results, including skipped tests and prerequisite failures. Any unmet acceptance keeps it active. After all acceptance passes, set Status to Complete and move the same filename to `docs/exec-plans/completed/`. Repair incoming/relative links, update any linked specification, and record concrete nonblocking follow-ups in the [debt tracker](exec-plans/tech-debt-tracker.md). Completed plans are historical; canonical docs remain authoritative.

## Template for future work

```markdown
# Change title

Status: Active
Owner: person or current agent
Created: YYYY-MM-DD

## Goal and acceptance criteria
Observable success, scope/non-goals, affected tenants/roles, unresolved proposals.

## Context
Baseline, relevant paths, constraints, dependencies, optional specification link.

## Steps and progress
- [ ] Establish baseline and resolve material decisions.
- [ ] Implement the smallest coherent change.
- [ ] Verify acceptance and update affected docs.

## Decisions and discoveries
Dated decisions, evidence, reasons, and deviations.

## Verification
Actual commands/scenarios/results, blockers, outstanding checks.

## Handoff or outcome
Next concrete action while active; final behavior and limits when complete.
```
