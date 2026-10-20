# F06 — Live AI matching for Weft Engine

Status: Active — implementation in progress; external and quality acceptance pending
Owner: Antonio
Created: 2026-10-19

## Goal and acceptance criteria

Build F06 in this FastAPI repository, using the Console's PostgreSQL database with a separate `weft_engine` schema and a separate worker process.

- Support events with up to **300 eligible guests**.
- Automatically select **up to three matches per guest**, returning fewer when evidence is weak.
- Require a **70-point minimum compatibility score** and a supported benefit for both people. Scores express connection strength, not a probability of success.
- A request for more opens three additional slots for that guest and returns at most three new connections. Previous matches remain.
- Both people need available slots. Ana does not receive a fourth automatic match unless she requested more. Explicitly choosing someone beyond this limit remains future scope.
- Missing profile fields never exclude a guest. Unsupported connections return no match.
- Use OpenAI API billing. Subscription integration remains deferred.
- Implement engine operations and contracts only. F07 triggers, F08 Console match creation, attendee controls, invitations, and introduction workflows remain outside this change.

The product choices above were confirmed in the planning conversation. The pipeline, model defaults, interfaces, and release gates below are the proposed implementation baseline. Research results do not establish matching quality for Weft.

## Context and constraints

- Source backlog: `/Users/antoniopertuz/Downloads/Weft_Console_Implementation_Backlog.md`, F06. This plan is self-contained; that external file is not required to execute it.
- Client inspected read-only: `/Users/antoniopertuz/Documents/surnx/weft-console-frontend`. It owns authoritative organization/event identities, attendees, profiles, exclusions, and restrictions. No changes to that checkout are authorized by this plan.
- At plan start, the engine implemented only its FastAPI foundation; the matching, authentication, persistence, and worker work is tracked in the progress and verification sections below.
- The Console currently uses PostgreSQL tables declared with Drizzle `pgTable`, without an explicitly named Console schema. Keep those tables where they are; the illustrative schema diagram was not a request to migrate them.
- The Console has profile versions, organizer-only fields, networking versions, canonical blocked pairs, and an `event_matching_changes` log. The log is a placeholder F07 contract, not a consumer to implement in F06.
- Identity links can change `personId` without incrementing attendee revisions. Choosing group-wide profiles and propagating exclusions across linked records remain unresolved.
- The Console has no authoritative introduction, guest-decision, or meeting-history implementation yet. Do not fabricate those capabilities to claim F06 integration acceptance.
- Preserve the existing unrelated untracked `.serena/` directory.
- Follow Python 3.14, Poetry, thin routers, domain-local matching logic, async I/O, explicit migrations, and isolated integration-test requirements in repository instructions.
- See the [duplicate-group change specification](../../changes/2026-10-19-linked-duplicate-matching.md) and [follow-up tracker](../tech-debt-tracker.md).

## Research-informed matching approach

| Reference | Application to F06 |
| --- | --- |
| [Reciprocal Recommenders](https://luiz.pizzato.cc/assets/pdf/papers/UMAP2010-ITWP-Pizzato-ReciprocalRecommender.pdf) | Evaluate benefit in both directions and account for limited recipient capacity. |
| [Fair Reciprocal Recommendation — paper and implementation](https://github.com/CyberAgentAILab/FairReciprocalRecommendation) | Evaluate recommendation distribution and avoid concentrating opportunities on a few guests. Its two-sided market algorithms serve as references rather than direct replacements for Weft's general guest network. |
| [Sentence Transformers: Retrieve & Re-Rank](https://sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html) | Separate broad candidate retrieval from more expensive pair evaluation. |
| [RankGPT](https://github.com/sunnweiwei/RankGPT) and [position-bias research](https://arxiv.org/abs/2604.03642) | Benchmark AI ranking and test sensitivity to guest order and candidate order. |
| [eventOS](https://github.com/rohan2025/eventOS) | Reference its distinction between "looking for" and "can offer." Its documented fixed-rule scorer cannot satisfy F06's live AI requirement. |

Implement this pipeline:

1. **Create an immutable input snapshot.** Read current Console data through a narrow, read-only adapter. Save source identifiers, versions, restrictions, privacy labels, and lifecycle context before any provider call.
2. **Apply eligibility and history rules.** Remove excluded guests, held identities, self-pairs, blocked pairs, previously issued pairs, and completed pair history. Preserve existing guest decisions and commitments.
3. **Retrieve candidates broadly.** Use [`text-embedding-3-large`](https://developers.openai.com/api/docs/models/text-embedding-3-large) with separate representations for sought connections, supplied capabilities, and background. Combine semantic and lexical rankings. Compare needs against capabilities in both directions; shared interests provide another retrieval channel.
4. **Use exact similarity search.** At 300 guests, compute similarities in the worker using cached embeddings stored in PostgreSQL arrays. Do not require an approximate index, vector database, or database extension. Start with 20 candidates per guest, include reverse candidates, and expand to 40 for guests with unfilled slots.
5. **Evaluate shortlisted pairs with live AI.** Use [`gpt-6.1-sol`](https://developers.openai.com/api/docs/models/gpt-6.1-sol) through the Responses API with strict structured output. Evaluate pairs independently against an anchored rubric, batching at most four pairs per request.
6. **Validate and select.** Reject unsupported or prohibited results, then use OR-Tools CP-SAT to select pairs under both guests' remaining capacities. Maximize total qualifying connection strength; use coverage as the secondary objective. Record solver status and preserve existing selections.

The AI returns separate benefit scores for A and B, evidence references, restriction findings, missing information, and uncertainty. The pair score is the **lower directional score**:

- Below 50: no useful supported connection.
- 50–69: plausible, but insufficient for selection.
- 70–84: clear, fact-supported mutual value.
- 85–100: especially strong, specific mutual value.

Each selected pair also receives a separate evidence-verification pass. No score can override a restriction or missing support. Profile completeness contributes through relevant evidence, never field counts. Unknown goals and offers remain unknown; a role or company does not prove an unstated goal.

## Storage, Console adapter, and execution

- Keep the Console's existing tables in their current schema. Do not move them or share mutable ORM models.
- Use SQLAlchemy async and Alembic for engine-owned snapshots, runs, attempts, embeddings, evaluations, batch grants, and selected recommendations.
- Restrict Alembic discovery and its version table to `weft_engine`. Supply explicit migration and runtime-role setup commands; never migrate at startup.
- Grant engine runtime credentials read access only to the required Console tables and write access only to engine tables.
- Retain Console organization, event, guest, and person UUIDs. Normalize unordered pairs consistently with the Console: lowercase UUID text, sorted lexically within an event.
- Snapshot attendee revisions, profile versions—including version `0`—networking versions, identity mappings, blocked pairs, and relevant context. Include identity mappings and restriction content in freshness fingerprints because identity linking does not increment the attendee revision.
- Hold every group containing multiple guest records for one `personId`. Return a visible `identity_resolution_required` reason.
- Re-read matching inputs before publishing results. Changed inputs invalidate publication; preserve the attempt for diagnosis and require a fresh calculation.
- Store durable jobs in PostgreSQL. Workers claim jobs with leases, heartbeat during processing, and fence completion writes so an expired worker cannot publish.
- Serialize selection and slot allocation per event. Retried submissions and worker recovery must not create another slot grant or duplicate recommendation.
- Cache embeddings and evaluations by tenant, source content/version, model, prompt, and matching-policy version. Every reused evaluation retains its original live-call provenance.
- Bound provider concurrency, timeouts, and transient retries. Require an explicit deployment spend ceiling and record token usage and estimated cost. Budget exhaustion and provider failures must remain visible failures, not a successful empty recommendation list.
- Keep profile text, organizer-only content, credentials, and provider payloads out of logs. Save structured provider/run provenance in protected engine storage; no chain-of-thought collection is needed.

Organizer-only facts may inform matching. Generate shareable explanations separately using only shareable facts; omit a public rationale when those facts cannot support one. Validate cited field references and quotations against the snapshot. Send no contact details to the model and perform no LinkedIn fetching. Treat profile content as untrusted data, not instructions.

## Service interfaces and feature boundaries

Add authenticated, versioned service endpoints under:

`/v1/organizations/{organizationId}/events/{eventId}/matching-runs`

- `POST`: accept an idempotency key, calculation mode (`event` or `more`), the target guest for `more`, and versioned authoritative lifecycle context. Persist the snapshot/job and return `202` with the run ID.
- `GET /{runId}`: return run status, progress, provenance, usage, and sanitized failure information.
- `GET /{runId}/results`: return selected recommendations and per-guest reasons for receiving fewer matches.

Results include stable recommendation IDs, canonical guest IDs, profile versions, directional and pair scores, benefits, evidence, uncertainty, snapshot fingerprint, and source run. Distinguish insufficient support, recipient capacity, identity holds, and bounded search from operational failures. Expose waiting, running, failed, finished, and invalid-result states; do not publish results from an invalidated snapshot.

Use server-configured service credentials mapped to allowed organization scopes. Verify the event's actual organization in PostgreSQL and scope every run/result lookup. Browser clients continue through the Console's authorization boundary. UUID possession is not authorization.

Lifecycle context explicitly supplies prior decisions, protected pairs, and completed history. Missing context fails closed; an empty context must be explicitly declared. The current Console has no introduction records, so tests must exercise nonempty context synthetically. F07/F08 must later provide current lifecycle data and atomically recheck eligibility, versions, and pair uniqueness when creating authoritative matches. F06 cannot establish the freshness of lifecycle changes it has not received; keep that integration limit visible.

Engine recommendations remain separate from authoritative introductions, guest acceptance, and physical meetings. Recommendation slots also remain separate from the Console's `softMaxIntroductionsPerGuest` setting. Initial slots and each additional three-slot grant are durable and idempotent; ordinary recalculation does not create another grant or silently revoke earlier issued recommendations. Each new pair consumes a slot for both guests. A `more` calculation selects at most three new pairs incident to its target guest.

## Steps and progress

- [x] Inspect the engine foundation, working tree, planning policy, and relevant canonical docs.
- [x] Inspect the adjacent Console's product, architecture, identities, profiles, restrictions, settings, repositories, and change-log boundaries read-only.
- [x] Confirm event scale, provider access, quality floor, batch/capacity behavior, shared-database schema ownership, read-only input access, and linked-group holds with Antonio.
- [x] Research reciprocal recommendation, retrieval/reranking, ranking bias, and relevant open-source implementations.
- [x] Save this implementation plan and the explicit duplicate-group follow-up.
- [x] Restore the reproducible Python 3.14/Poetry baseline. Resolve dependencies with Poetry; never fabricate a lockfile or silently weaken constraints/checks.
- [x] Implement storage, migrations, the Console adapter, service authorization, and versioned contracts.
- [x] Implement durable execution, retrieval, live AI evaluation, validation, evidence verification, and capacity-aware selection.
- [x] Add contract examples, operational commands, and a reviewed-label quality evaluation tool; update canonical product, domain, architecture, engineering, verification, and service docs to reflect actual implementation.
- [x] Execute available verification and record evidence, skipped suites, and remaining acceptance. Keep this plan active until all acceptance passes.

## Verification

Required cases:

- Tenant isolation, unauthorized access, unknown IDs, malformed output, reversed duplicate pairs, exclusions, restrictions, and stale inputs.
- Version-zero and sparse profiles, URL-only LinkedIn data, complementary needs, one-sided benefit, privacy filtering, and prompt injection in profile text.
- One 80-point candidate with all others below 50 returns exactly one match; unsupported candidates never fill empty slots.
- Initial three-slot limits, additional batches, Ana/Ben capacity behavior, prior-pair preservation, and repeated/concurrent requests.
- Worker crashes, expired leases, retries, provider refusal/timeouts, spend exhaustion, and concurrent publication.
- Engine migrations leave Console tables unchanged. Database tests use an explicitly disposable PostgreSQL target containing representative Console tables and the engine schema. Never inherit production credentials or use a shared development/preview database as a disposable test target.
- A domain benchmark containing at least 60 synthetic profiles and 200 labeled pairs, including held-out examples reviewed by Antonio/Sheary. Initial release gates: at least 90% precision among selected recommendations, at least 95% candidate recall on labeled strong connections, and zero eligibility, privacy, or fabricated-evidence violations. Report coverage alongside precision so returning no recommendations cannot satisfy quality acceptance by itself.
- A 300-guest live-provider benchmark recording actual cost, latency, coverage, and provider/model provenance. Compare against semantic-only and fixed-rule baselines; do not claim quality acceptance from mocks or model self-grading.
- `poetry check --lock --strict`, `make verify`, and affected API/worker runtime checks. Record actual model identifiers, prompt/policy versions, live-call versus cache provenance, and redacted benchmark evidence.

Historical setup evidence from planning on 2026-10-19, before implementation:

| Command | Actual result |
| --- | --- |
| `git status --short` in engine | Only unrelated untracked `.serena/` before saving this plan |
| `git status --short` in Console | Clean during inspection |
| `poetry check --lock --strict` | Failed: `poetry.lock` was not found |
| `make verify` | Documentation checker passed; stopped at lint because `ruff` was not installed; later checks did not run |

Current implementation evidence:

| Check | Actual result |
| --- | --- |
| Python / Poetry baseline | Python 3.14.6, Poetry 2.4.1; generated `poetry.lock` with Poetry and installed dependencies via Poetry |
| `poetry check --lock --strict` | Passed |
| `make verify` | Passed on Python 3.14.6 after database fixes: docs checker, Ruff lint/format, strict mypy (21 source files), and pytest (33 passed, 7 opt-in database tests skipped; 38% default-suite total branch-aware coverage). The database suite passed separately below. |
| Alembic offline SQL generation | Passed; verified `weft_engine` schema creation precedes its Alembic version table; no database connection was made |
| Local Uvicorn smoke | Passed on loopback with injected test settings and no database/provider credentials: `/health` returned the expected payload and `/openapi.json` returned 200; process stopped |
| Console checkout | Inspected read-only; no files changed |
| PostgreSQL migration state | Independently read `weft_engine.alembic_version` = `0002_f07` and confirmed the F06 tables on `weft_console_test`, project `aged-recipe-59178735`, branch `dev` (`br-proud-base-ayz7tqp8`). This checkout contains only `0001_f06`; no migration or schema reset was run. Migration-isolation acceptance remains unexecuted. |
| PostgreSQL API-worker integration | Passed all 7 opt-in cases on the explicitly user-authorized Neon target in 135.32 seconds, using transaction-isolated synthetic fixtures and a synthetic provider transport; all fixtures rolled back. Covered API submission/results, repeated requests and one-time slot grants, recalculation preserving prior recommendations, sparse/version-zero profiles, excluded/linked guests, blocked pairs, authorization/scope, stale snapshots, missing spend budget, fabricated evidence, provider failure, and lease-owner fencing. |
| Actual application database pools/lifespan | Passed a separate read-only ASGI smoke using the normal factory and real Neon-backed pools: health/docs/OpenAPI 200, scoped unknown event 404, engine database/revision queries succeeded, and pools disposed after lifespan. |
| Live provider / 300-guest benchmark | Not run: no explicitly supplied OpenAI credential and approved spend budget |
| Expert quality benchmark | Harness implemented; no 60-profile / 200-label reviewed dataset supplied, so precision, recall, coverage, and violation gates remain unmeasured |

Database/API/worker verification above has run. No live-provider matching or full F06 acceptance has run. The generated quality-evaluation fixtures and synthetic provider responses are test mechanics only, not quality acceptance evidence. Migration isolation, separate-process queue claiming/crash recovery, concurrent requests/publication, and deployment role grants remain unverified. No production operations, paid provider calls, schema changes, committed test data, or Console checkout changes were performed.

Commands for this check:

- `WEFT_INTEGRATION_DATABASE_URL_FILE=<private test URL file> WEFT_INTEGRATION_DATABASE_NAME=weft_console_test poetry run pytest tests/test_matching_postgres.py -x -q --tb=short` — initially exposed two worker defects, then passed all 7 cases after fixes. The URL was retrieved explicitly for this test database through the Neon connector, never inherited from ambient production settings; the private temporary file was removed after use.
- `poetry check --lock --strict` — passed.
- `make verify` — passed with the normal opt-in database skips described above.
- The read-only ASGI smoke used `create_app`, its lifespan, real PostgreSQL pools, and injected test settings; it did not submit or mutate existing events.

The worker fixes add an explicit text cast for the heartbeat's PostgreSQL JSON value and serialize embedding-attempt fingerprints as JSON-compatible records instead of tuple-keyed dictionaries. Both failures were reproduced against Neon before correction; the successful full worker pipeline now covers them in the opt-in suite. Provider/model identifiers used by the suite are `synthetic-integration-embedding` and `synthetic-integration-evaluation`, with policy `f06-policy-v1` and prompt `f06-rubric-v1`; they do not denote live calls.

### Integration with main, 2026-10-19

Fast-forwarded to `0b3d968` and restored the local F06 PostgreSQL suite and verification evidence. Preserved main's F07 implementation and shared heartbeat fix; resolved the embedding-attempt fingerprint overlap using the local JSON-compatible named records. `poetry check --lock --strict` and `make verify` passed on Python 3.14.6 / Poetry 2.4.1: documentation, Ruff lint/format, strict mypy (25 source files), and pytest (79 passed, 18 opt-in PostgreSQL skips; 43% total branch-aware coverage). No database or provider checks were rerun during integration; the acceptance gates above remain open. Next action remains the bounded integration and live-provider/quality checks described below.

## Decisions, follow-up, and handoff

2026-10-19: Antonio explicitly authorized database/API/worker checks against `weft_console_test` on Neon's `dev` branch and rejected a local database. Use transaction-isolated synthetic fixtures with rollback; do not migrate, reset, or modify existing records. Read-only inspection found Alembic revision `0002_f07` and additional engine tables beyond this checkout's `0001_f06`; leave that external schema unchanged and keep F07/F08 outside this task. Live-provider acceptance still requires separately supplied credentials and approved spend.

Full matching support for linked duplicate groups requires a later explicit design and implementation covering canonical profile selection, conflicting exclusions, combined restrictions, identity freshness, existing recommendations, and introduction disposition. Track this in the [Draft change specification](../../changes/2026-10-19-linked-duplicate-matching.md) and [follow-up tracker](../tech-debt-tracker.md). Keep the temporary hold until that work is completed; do not guess a canonical profile or silently propagate settings.

Next action: supply an explicit OpenAI test credential, configured prices, and approved spend for live-provider checks; obtain the expert-reviewed synthetic benchmark dataset. Remaining database acceptance includes migration isolation, separate-process queue/crash recovery, concurrency, and restricted deployment roles; the current transaction-isolated suite deliberately does not claim those gates. Use Antonio's authorized Neon target for bounded synthetic checks, without migrating/resetting it or draining unrelated jobs. Keep F06 active until all acceptance gates pass. Full linked duplicate-group matching remains deferred; preserve the temporary hold.
