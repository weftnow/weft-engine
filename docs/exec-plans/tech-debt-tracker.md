# Technical debt and setup gaps

Product features are not setup debt. [F06 has an active implementation plan](active/2026-10-19-f06-live-ai-matching.md); F07 and F08 remain deferred. The following table tracks setup gaps and an explicitly deferred F06 integration limitation.

| Gap | Impact | Next action |
| --- | --- | --- |
| `.agents/` is read-only in the setup workspace | Conventional automatic repository-skill discovery is unavailable here | Read the three procedures in [skills](../../skills/README.md) manually; if discovery is desired in another environment, relocate them and update canonical links/checker paths |
| Full matching support for linked duplicate groups is unresolved | F06 will hold groups containing multiple guest records for one person and expose `identity_resolution_required`; canonical profile, conflicting exclusions, combined restrictions, and existing introduction disposition are not defined | Review the [Draft change specification](../changes/2026-10-19-linked-duplicate-matching.md), agree on Console ownership/versioning, then implement full group support in separately authorized work; do not silently release the temporary hold |

Prepared Git hooks still require a Git checkout and deliberate activation; see [hooks](../HOOKS.md). Future provider, storage, and worker decisions are tracked in [Product](../product.md), not treated as implemented systems.
