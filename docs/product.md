# Product

Weft Engine is the backend for automatic one-to-one networking matches at events. It supports Weft staff and organizers through service integrations; it is not an attendee application. Matching is separate from guests accepting an introduction and from confirmation that they physically met.

## Current delivery

A runnable FastAPI service with an F06 matching engine implementation, typed configuration, health endpoint, tests, verification tooling, and engineering harness. F06 remains active pending isolated PostgreSQL migration/worker acceptance, live-provider and labeled-quality benchmarks, and deployment-specific budget and credential setup. [The active F06 plan](exec-plans/active/2026-10-19-f06-live-ai-matching.md) records implementation evidence and outstanding gates. F07 is implemented behind a default-off switch; [its active plan](exec-plans/active/2026-10-19-f07-automatic-matching-updates.md) records the remaining acceptance gates. F08 remains deferred.

## Confirmed rules for future features

All imported guests enter matching by default unless explicitly excluded or held for unresolved identity. Goals, background, and LinkedIn content are optional. Information completeness affects the strength/priority of supported connections, never admission to matching. Unknown details remain unknown; a LinkedIn URL does not prove its content was read. Matching starts from relevant saved data changes without a manual start button or human match approval.

### F06 — Live AI matching

Use a configured live AI service against a saved copy of eligible event inputs. Save run/attempt status, service/model version, input/profile versions, selected pairs, provenance, and failures. Each result must identify both guests, a benefit to each, supporting known facts, missing information, and uncertainty.

Reject malformed output, self-matches, duplicate unordered pairs, unknown identities, ineligible guests, prohibited pairs, and outdated results. Prioritize relevant supporting information rather than counting filled fields. Return no match when there is no supported useful connection. Recalculation must respect guest decisions, active commitments, and completed-pair history. Placeholder or fixed-rule results without a live AI call cannot count as successful live matching.

### F07 — Automatic matching updates

Completed imports and relevant saved profile, exclusion, restoration, restriction, attendee-correction, and identity-link changes trigger recalculation automatically. Use current profiles and event-local inclusion/identity rules; completeness is not a ready status. Keep explicit links to authoritative organization/event/guest IDs if internal identifiers differ. Never identify people by name, list position, or similar-looking IDs.

Expose waiting, running, failed, finished, and invalid-result states with result source. Repeated notifications, retries, and repeated result delivery must not duplicate jobs or pair records. Coalesce rapid related changes where appropriate. Reject unknown IDs and outdated profiles automatically. Ordinary recalculation preserves accepted/active introductions; withdrawals and invalid identity require explicit cancellation handling. Availability-triggered recalculation remains an open question.

**Implemented behavior (default off, `WEFT_MATCHING_AUTOMATIC_ENABLED`).** The engine reads the Console's saved-change log; there is no start button and no approval step. Changes for one event wait for a 30 second quiet period (at most 300 seconds) and then produce one run, with never more than one waiting or running run per event. Transient failures retry after 1, 5 and 15 minutes (three retries); configuration and budget failures do not retry, and a stale snapshot re-runs immediately within the same cap. Existing recommendations are revoked, with a recorded reason and freed capacity, only when a guest is excluded or missing, a do-not-match block is added, or an identity hold applies; profile edits keep them, and a revoked pair is never recommended again. Results leave the engine through a pull feed of `issued` and `revoked` recommendations that F08 will consume. Automatic runs currently use an empty, explicitly stated lifecycle (no recorded decisions, protected pairs or completed pairs) because the Console stores none yet.

### F08 — Automatic pair creation and match list

Valid selected pairs become authoritative product matches automatically, without an approval queue. A+B and B+A represent the same pair within an event; retries and later meeting attempts must not create duplicate introductions. Pair creation records current profile versions, mutual reasons, run/source, and introduction path. Reject stale or ineligible results with a visible reason.

Two regular attendees use message coordination outside this scope. A pair containing a networking sponsor/VIP uses a Wefter; a mixed pair still requires the regular guest's acceptance under later acceptance rules. Automatic selection is neither guest acceptance nor evidence of a meeting. Match-list/detail presentation and authoritative introduction lifecycle are separate product responsibilities; this foundation implements neither.

## Scope exclusions

No UI redesign, attendee questionnaire/app, automatic invitations or communications, call/SMS administration, communication logs, operator task management, GPS/automatic presence detection, group/table matching, custom model training, or new sponsor dashboard. Guest acceptance, Wefter booking, physical-meeting confirmation, feedback, and reports are later capabilities.

## Open decisions before feature implementation

- Deployment-specific PostgreSQL role provisioning, OpenAI credentials, current model prices, and an approved per-run spend ceiling.
- Live 300-guest performance/cost evidence and expert-reviewed precision, candidate-recall, coverage, privacy, and eligibility results.
- Authoritative lifecycle context and freshness ownership for F08 pair creation; F06 requires callers to supply complete lifecycle context and F07 automatic runs supply an empty one until the Console records lifecycle data.
- How current availability affects recalculation, introduction limits, and explicit cancellation/replacement integration.

These decisions are not silently defaulted by the scaffold. See [architecture](../ARCHITECTURE.md) and [domain](domain.md) for boundaries.

## Authorized matching cost revision (2026-10-25)

Retain the existing candidate judgments and reciprocal allocation policy while replacing verbose
per-candidate reports with compact evidence-backed judgments. Longer shareable explanations are
generated only for selected pairs. Missing-information lists use recorded missing details; unknown
facts are not invented. A failed evidence explanation excludes that pair and permits selection
from remaining evaluated candidates. Candidate-count reduction and alternate ranking/models are
deferred. This is authorized behavior; live cost and semantic-quality acceptance remain pending
in the [optimization plan](exec-plans/active/2026-10-24-matching-engine-optimization.md).
