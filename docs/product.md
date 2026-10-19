# Product

Weft Engine is the backend for automatic one-to-one networking matches at events. It supports Weft staff and organizers through service integrations; it is not an attendee application. Matching is separate from guests accepting an introduction and from confirmation that they physically met.

## Current delivery

A runnable FastAPI foundation, typed configuration, health endpoint, tests, verification tooling, and engineering harness. F06, F07, and F08 are the first intended features, but none is implemented. No feature execution plans are created at this stage.

## Confirmed rules for future features

All imported guests enter matching by default unless explicitly excluded or held for unresolved identity. Goals, background, and LinkedIn content are optional. Information completeness affects the strength/priority of supported connections, never admission to matching. Unknown details remain unknown; a LinkedIn URL does not prove its content was read. Matching starts from relevant saved data changes without a manual start button or human match approval.

### F06 — Live AI matching

Use a configured live AI service against a saved copy of eligible event inputs. Save run/attempt status, service/model version, input/profile versions, selected pairs, provenance, and failures. Each result must identify both guests, a benefit to each, supporting known facts, missing information, and uncertainty.

Reject malformed output, self-matches, duplicate unordered pairs, unknown identities, ineligible guests, prohibited pairs, and outdated results. Prioritize relevant supporting information rather than counting filled fields. Return no match when there is no supported useful connection. Recalculation must respect guest decisions, active commitments, and completed-pair history. Placeholder or fixed-rule results without a live AI call cannot count as successful live matching.

### F07 — Automatic matching updates

Completed imports and relevant saved profile, exclusion, restoration, and restriction changes trigger recalculation automatically. Use current profiles and event-local inclusion/identity rules; completeness is not a ready status. Keep explicit links to authoritative organization/event/guest IDs if internal identifiers differ. Never identify people by name, list position, or similar-looking IDs.

Expose waiting, running, failed, finished, and invalid-result states with result source. Repeated notifications, retries, and repeated result delivery must not duplicate jobs or pair records. Coalesce rapid related changes where appropriate. Reject unknown IDs and outdated profiles automatically. Ordinary recalculation preserves accepted/active introductions; withdrawals and invalid identity require explicit cancellation handling. Availability-triggered recalculation remains an open question.

### F08 — Automatic pair creation and match list

Valid selected pairs become authoritative product matches automatically, without an approval queue. A+B and B+A represent the same pair within an event; retries and later meeting attempts must not create duplicate introductions. Pair creation records current profile versions, mutual reasons, run/source, and introduction path. Reject stale or ineligible results with a visible reason.

Two regular attendees use message coordination outside this scope. A pair containing a networking sponsor/VIP uses a Wefter; a mixed pair still requires the regular guest's acceptance under later acceptance rules. Automatic selection is neither guest acceptance nor evidence of a meeting. Match-list/detail presentation and authoritative introduction lifecycle are separate product responsibilities; this foundation implements neither.

## Scope exclusions

No UI redesign, attendee questionnaire/app, automatic invitations or communications, call/SMS administration, communication logs, operator task management, GPS/automatic presence detection, group/table matching, custom model training, or new sponsor dashboard. Guest acceptance, Wefter booking, physical-meeting confirmation, feedback, and reports are later capabilities.

## Open decisions before feature implementation

- AI provider/model, access credentials, spend limits, supported event sizes, and quality evaluation criteria.
- Durable storage, worker execution/transport, deployment environment, retry/coalescing policy, and failure recovery.
- Authenticated service contracts, authorization and event scoping, change schema/versions, result delivery, and authoritative pair-write ownership.
- How current availability affects recalculation, introduction limits, and explicit cancellation/replacement integration.

These decisions are not silently defaulted by the scaffold. See [architecture](../ARCHITECTURE.md) and [domain](domain.md) for boundaries.
