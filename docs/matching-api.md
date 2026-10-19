# F06 matching service API

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

The Console adapter reads only `public.events`, `public.event_guests`, `public.event_guest_profile_versions`, and `public.event_guest_match_blocks`. It does not read contact details or the F07 change log. Results omit evidence fields marked organizer-only; shareable reasons are generated from shareable evidence in a separate verification pass.
