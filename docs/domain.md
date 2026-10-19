# Domain and integration boundaries

## Identity and scope

Organization, event, and guest IDs are explicit UUID references. A guest is event-local; names, contact similarity, array position, and sponsor labels are not identity or authorization evidence. If engine-local IDs are introduced, persist explicit mappings. Validate organization/event scope at ingestion, processing, and result delivery. Unresolved identity blocks affected matching and introductions.

Canonical pairs use lowercase UUID text in lexical order: `(eventId, guestLowId, guestHighId)`. Reject equal guest IDs. A+B and B+A must share an identity; enforce uniqueness in durable storage when introduced. Do not merge people based only on matching names.

## Authoritative inputs for future matching

Guest identity, inclusion/exclusion, do-not-match restrictions, attendee type, current profile version, guest decisions, meeting commitments, and completed history originate in authoritative product records. Exclusions and restrictions survive reimport and identity correction. Attendance and current availability are separate from networking inclusion and profile completeness.

Profile version `0` means no saved profile. Available profile fields include shareable `summary`, `goals`, `offers`, `desiredConnections`, `avoid`, `background`, `linkedinDetails`, and `missingDetails`. Blank/absent content means unknown. Existing profile conventions limit summary to 500 characters and the seven other fields to 2000; confirm the wire schema before integration. `ORGANIZER_ONLY` annotations permit matching use but prohibit inclusion in shareable explanations or attendee projections. Supporting reasons need explicit visibility filtering; model output is untrusted.

LinkedIn content may be `available`, `url_only`, or `missing`; a URL alone provides no profile facts. Completeness must not be a filled-field score or eligibility threshold. Profile snapshots and identity/participation/restriction revisions must be traceable from each run; check freshness again at authoritative pair creation.

## Ownership

The matching domain owns saved run snapshots, provider attempts and metadata, embeddings/evaluation cache, structured-result and evidence validation, capacity selection, run status, and provenance. F06 persists those records in the `weft_engine` schema and reads Console-owned event/profile/restriction records through a read-only adapter. The caller supplies explicit lifecycle context because the Console does not yet own introduction, decision, or completed-pair records. F07 adds durable change consumption (receipts and coalesced batches), retry state, recommendation revocation, and a pull feed, all in `weft_engine`; the engine never writes Console tables except setting `processed_at` on change rows. The authoritative match lifecycle owns automatic pair creation, stable introduction IDs, acceptance, attempts, Wefter assignments, cancellation, and meeting outcomes under F08.

Do not implement acceptance, booking, or UI behavior in matching merely because a result mentions a pair. Sponsor/VIP attendee classification does not grant product staff access. Networking staff/Wefters are operational actors, separate from attendee type.

## Contract decisions still required

F07 settled change delivery: the Console writes `event_matching_changes` rows in the same transaction as each change, and the engine polls them (no Console-to-engine HTTP call). Results are pulled from the engine's feed, ordered by `seq` within an event. Still undecided before F08: schema versioning of the feed, authoritative lifecycle freshness, and atomic authoritative pair writes. Changes the Console does not log (settings, Wefter edits) only make a run stale; availability triggers are undecided.

Preserve accepted/active introductions during ordinary recalculation. Withdrawal and invalid identity require explicit lifecycle/cancellation rules; silently deleting a pair is not sufficient. Only known eligible current-version inputs may produce new matches. No protected API may rely on possession of an event UUID.
