# Domain and integration boundaries

## Identity and scope

Organization, event, and guest IDs are explicit UUID references. A guest is event-local; names, contact similarity, array position, and sponsor labels are not identity or authorization evidence. If engine-local IDs are introduced, persist explicit mappings. Validate organization/event scope at ingestion, processing, and result delivery. Unresolved identity blocks affected matching and introductions.

Canonical pairs use lowercase UUID text in lexical order: `(eventId, guestLowId, guestHighId)`. Reject equal guest IDs. A+B and B+A must share an identity; enforce uniqueness in durable storage when introduced. Do not merge people based only on matching names.

## Authoritative inputs for future matching

Guest identity, inclusion/exclusion, do-not-match restrictions, attendee type, current profile version, guest decisions, meeting commitments, and completed history originate in authoritative product records. Exclusions and restrictions survive reimport and identity correction. Attendance and current availability are separate from networking inclusion and profile completeness.

Profile version `0` means no saved profile. Available profile fields include shareable `summary`, `goals`, `offers`, `desiredConnections`, `avoid`, `background`, `linkedinDetails`, and `missingDetails`. Blank/absent content means unknown. Existing profile conventions limit summary to 500 characters and the seven other fields to 2000; confirm the wire schema before integration. `ORGANIZER_ONLY` annotations permit matching use but prohibit inclusion in shareable explanations or attendee projections. Supporting reasons need explicit visibility filtering; model output is untrusted.

LinkedIn content may be `available`, `url_only`, or `missing`; a URL alone provides no profile facts. Completeness must not be a filled-field score or eligibility threshold. Profile snapshots and identity/participation/restriction revisions must be traceable from each run; check freshness again at authoritative pair creation.

## Ownership

The matching domain owns saved run snapshots, provider attempts and metadata, embeddings/evaluation cache, structured-result and evidence validation, capacity selection, run status, and provenance. F06 persists those records in the `weft_engine` schema and reads Console-owned event/profile/restriction records through a read-only adapter. The caller supplies explicit lifecycle context because the Console does not yet own introduction, decision, or completed-pair records. Automatic-update processing will need durable change consumption and delivery under F07. The authoritative match lifecycle owns automatic pair creation, stable introduction IDs, acceptance, attempts, Wefter assignments, cancellation, and meeting outcomes under F08.

Do not implement acceptance, booking, or UI behavior in matching merely because a result mentions a pair. Sponsor/VIP attendee classification does not grant product staff access. Networking staff/Wefters are operational actors, separate from attendee type.

## Contract decisions still required

No change-ingestion/result HTTP endpoints or wire contracts exist yet. Existing change notifications are not a finalized reliable-delivery protocol. Agree on schema versioning, service authentication/authorization, organization/event IDs, snapshot/current revision rules, idempotency, acknowledgments, ordering, stale-result handling, failure codes, and atomic authoritative writes before building integration. A transaction/outbox approach is a candidate, not an implemented guarantee.

Preserve accepted/active introductions during ordinary recalculation. Withdrawal and invalid identity require explicit lifecycle/cancellation rules; silently deleting a pair is not sufficient. Only known eligible current-version inputs may produce new matches. No protected API may rely on possession of an event UUID.
