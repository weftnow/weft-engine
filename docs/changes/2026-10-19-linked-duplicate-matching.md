# Full matching support for linked duplicate groups

Status: Draft — deferred follow-up; behavior is unresolved
Owner: Antonio
Created: 2026-10-19

## Problem and confirmed F06 boundary

The Console can link several stable event guest records to one event-local `personId`. Profiles, exclusions, and blocked pairs still belong to guest records, and identity linking can change `personId` without increasing the attendee revision. The Console has no agreed group-wide profile/exclusion policy or persisted introduction disposition yet.

For [F06](../exec-plans/active/2026-10-19-f06-live-ai-matching.md), Antonio explicitly chose to hold every group containing multiple guest records for one person and expose `identity_resolution_required`. Ordinary single-record identities continue through matching. Missing profile information alone never creates an identity hold.

## Required later review

- Choose an authoritative matching guest/profile for each resolved person while preserving all historical profile references and import provenance.
- Define how conflicting inclusion/exclusion decisions, blocked pairs, and free-text restrictions combine. Reimports and identity fixes must not silently restore an excluded person.
- Version identity-group membership and canonical selection, including links that currently do not change the attendee revision.
- Define explicit disposition for existing recommendations, guest decisions, active commitments, and completed pair history when groups are linked or corrected.
- Prevent self-matches between linked guest records and duplicate introductions through different guest IDs.
- Agree on Console ownership, the engine's read contract, and atomic freshness/uniqueness checks before enabling group matching.

## Compatibility and acceptance

Do not merge profiles, choose the highest profile version across different guests, propagate exclusions, or release held groups implicitly in F06. No Console changes or duplicate-resolution implementation are authorized by saving this note.

A later implementation must cover conflicting profiles, excluded/included linked records, restrictions against any group member, identity changes during a run, preserved commitments/history, retries, and tenant/event isolation. Resolve consequential decisions before marking this specification Ready. F06 acceptance does not depend on completing this follow-up; it depends on correctly implementing and exposing the temporary hold.
