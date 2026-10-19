# Repository skills

These portable Markdown procedures capture repeated repository workflows. Read the relevant `SKILL.md` manually when needed; automatic discovery depends on the host. They live in `skills/` because the setup workspace protects `.agents/` as read-only. General requirements remain in [AGENTS.md](../AGENTS.md), not solely in optional procedures.

| Skill | Trigger |
| --- | --- |
| [Harness maintenance](harness-maintenance/SKILL.md) | Requested maintenance or demonstrated drift in docs, instructions, commands, or plans |
| [Verification handoff](verification-handoff/SKILL.md) | Validate a change or finish with actual evidence and explicit limits |
| [Contextual commits](contextual-commits/SKILL.md) | The user explicitly requests commits or coherent grouping of changes |

Examples: “Use verification-handoff to validate this configuration change” or “Use harness-maintenance to repair the documentation map.” Load the procedure and the references it routes to; no specific model or agent tool is required.

Add specialized skills only for demonstrated repeated work. Do not preload provider, database, authentication, or frontend catalogs without an implemented need. Keep dependency management in Poetry and verification policy in [Verification](../docs/VERIFICATION.md).
