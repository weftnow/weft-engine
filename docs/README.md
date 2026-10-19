# Documentation index

[AGENTS.md](../AGENTS.md) is the short entry point. These documents are self-contained; no adjacent checkout or external private file is required.

| Reference | Ownership and use |
| --- | --- |
| [Product](product.md) | Purpose, F06–F08 requirements, delivery boundary, open questions |
| [Architecture](../ARCHITECTURE.md) | Implemented structure and labeled future direction |
| [Domain](domain.md) | Identity, capability ownership, privacy, trust boundaries |
| [Engineering](engineering.md) | Runtime, configuration, dependencies, FastAPI conventions |
| [Design](design/design.md) | API presentation and no-UI boundary |
| [F06 service API](matching-api.md) | Authenticated run, status, result, and camelCase wire examples |
| [F06 quality evaluation](matching-quality.md) | Reviewed benchmark inputs, release gates, and evidence limits |
| [Plans](PLANS.md) | Thresholds, template, progress, acceptance, archive policy |
| [Change specifications](changes/README.md) | Recording unresolved behavior before implementation |
| [Active plans](exec-plans/active/) | [F06 live AI matching](exec-plans/active/2026-10-19-f06-live-ai-matching.md), implementation active; acceptance pending |
| [Completed plans](exec-plans/completed/) | Verified historical work; currently empty |
| [Debt tracker](exec-plans/tech-debt-tracker.md) | Concrete nonblocking gaps, not the product backlog |
| [Verification](VERIFICATION.md) | Check commands, change matrix, evidence limits |
| [Hooks](HOOKS.md) | Prepared Git hooks, activation, recovery |
| [Repository skills](../skills/README.md) | Maintenance, verification handoff, contextual commits |

Maintain canonical docs as part of authorized changes. Distinguish product requirements, implemented behavior, and unresolved proposals. There is no separate ADR or competing specifications tree. Run `make check-docs` after changing documentation or links. Procedures work by manual reading; automatic instruction/skill discovery depends on the host.
