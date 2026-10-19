# Technical debt and setup gaps

Product features are not setup debt. [F06 has an active implementation plan](active/2026-10-19-f06-live-ai-matching.md); [F07 has an active plan](active/2026-10-19-f07-automatic-matching-updates.md); F08 remains deferred. The following table tracks setup gaps and an explicitly deferred F06 integration limitation.

| Gap | Impact | Next action |
| --- | --- | --- |
| `.agents/` is read-only in the setup workspace | Conventional automatic repository-skill discovery is unavailable here | Read the three procedures in [skills](../../skills/README.md) manually; if discovery is desired in another environment, relocate them and update canonical links/checker paths |
| Full matching support for linked duplicate groups is unresolved | F06 will hold groups containing multiple guest records for one person and expose `identity_resolution_required`; canonical profile, conflicting exclusions, combined restrictions, and existing introduction disposition are not defined | Review the [Draft change specification](../changes/2026-10-19-linked-duplicate-matching.md), agree on Console ownership/versioning, then implement full group support in separately authorized work; do not silently release the temporary hold |
| Automatic F07 runs use an empty lifecycle | Prior decisions, protected pairs and completed pairs are not considered because the Console stores none (`lifecycle_source: console_none_recorded`) | F08/F10 must add a Console lifecycle reader before authoritative introductions exist |
| Revoked pairs are never re-issued | A pair revoked by an exclusion or block stays out even after the guest is restored or the block removed | Decide with product whether restoration should allow re-recommendation, then lift the prior-pair rule |
| Spend is capped per run only | Frequent changes can start many capped runs; there is no per-event or daily ceiling | Add an event/day spend ceiling before enabling automatic processing broadly |
| Unlogged Console changes only make runs stale | Settings and Wefter edits write no change row and cause a stale re-run rather than a trigger | Add change kinds if they should trigger matching |
| Availability-triggered matching is undecided | Availability changes do not start runs | Resolve the open product question |
| Abandoned batches retry only on the next change | After retries are exhausted or a configuration failure, the event waits for a new change | Add operator-visible alerting or a manual retry if this proves too quiet |

Prepared Git hooks still require a Git checkout and deliberate activation; see [hooks](../HOOKS.md). Future provider, storage, and worker decisions are tracked in [Product](../product.md), not treated as implemented systems.
