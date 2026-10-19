# Execution plans

Planning is deferred for the current foundation. The active and completed directories are intentionally empty. This document defines the workflow for future requests; it is not an execution plan or authorization to begin F06–F08.

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
