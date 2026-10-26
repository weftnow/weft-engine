# Matching service API (F06 runs, F07 status and feed)

These endpoints are service-to-service operations. The Console is responsible for browser authorization. Every request requires `X-Weft-Service-Token`, mapped to explicit organization UUID scopes in `WEFT_MATCHING_SERVICE_TOKENS`. Run creation also requires `Idempotency-Key`.

The URL follows the Console's UUID scope and the JSON wire format uses camelCase:

```http
POST /v1/organizations/10000000-0000-0000-0000-000000000001/events/20000000-0000-0000-0000-000000000001/matching-runs
X-Weft-Service-Token: <configured service token>
Idempotency-Key: event-recalculation-2026-10-19-001
Content-Type: application/json
```

```json
{
  "mode": "event",
  "lifecycle": {
    "complete": true,
    "priorDecisions": [],
    "protectedPairs": [],
    "completedPairs": []
  }
}
```

The caller must explicitly state that lifecycle input is complete. Missing decisions, protected pairs, or completed-pair history fail validation. `more` mode requires `targetGuestId`; it durably grants three additional slots once per idempotency key and returns at most three new pairs involving that target.

Creation returns `202 Accepted` with `{ "runId": "…", "status": "waiting" }`. `GET /{run_id}` returns status, progress, provider provenance, token usage, estimated spend, and a sanitized failure. `GET /{run_id}/results` returns status, the snapshot fingerprint, source run, per-guest reason codes, and recommendations. Wire properties are camelCase, including `guestLowId`, `profileVersions`, `directionalScores`, `pairScore`, `missingInformation`, and `shareableReasons`.

Reason codes distinguish `identity_resolution_required`, `excluded`, `recipient_capacity`, `bounded_search`, and `insufficient_support`. These recommendation records are not authoritative introductions and do not represent guest acceptance or a physical meeting. The caller must provide authoritative lifecycle context; F06 cannot detect lifecycle changes the Console has not stored or supplied.

The Console adapter reads `public.events`, `public.event_guests`, `public.event_guest_profile_versions`, and `public.event_guest_match_blocks`, and (F07) reads `public.event_matching_changes` and sets only its `processed_at`. It never reads contact details. Results omit evidence fields marked organizer-only; shareable reasons are generated from shareable evidence in a separate verification pass. Result items now include `revokedAt` and `revocationReason` (both `null` while active).

## F07 status and feed

Both endpoints use the same `X-Weft-Service-Token` and organization scope as above, are read-only, and return 404 `event_not_found` when the event does not belong to the organization.

```http
GET /v1/organizations/{organizationId}/events/{eventId}/matching/status
```

Returns `state` (`idle | waiting | running | failed | finished | invalid_result`), `pendingChanges` (changes the engine has received or the Console has logged but no finished run covers yet), `latestRun` (`runId`, `status`, `trigger` of `api` or `change`, `failure {code, message}`, `createdAt`, `finishedAt`) or `null`, `lastFinishedRunId`, `nextAttemptAt` (when a retry is scheduled), and `automaticEnabled`. The API process and the worker must be started with the same `WEFT_MATCHING_AUTOMATIC_ENABLED` value for `automaticEnabled` to be accurate.

```http
GET /v1/organizations/{organizationId}/events/{eventId}/matching/feed?after=0&limit=100
```

Returns `{ "entries": [{ "seq", "kind", "runId", "recommendation" }], "nextCursor" }` in `seq` order, `limit` at most 200. `kind` is `issued` or `revoked`; `recommendation` has the result-item shape, with `revokedAt` and `revocationReason` (`guest_excluded | pair_blocked | identity_resolution_required | guest_missing`) set on revoked entries. `runId` is the run that issued or revoked it, or `null` when a revocation happened without a run. Pass `nextCursor` as `after` to continue; an empty page returns the same cursor. Within an event `seq` order matches commit order; delivery is at least once and entries are never rewritten, so consumers key on `(recommendationId, kind)`. Recommendations created before F07 were back-filled as `issued` entries by migration 0002.
