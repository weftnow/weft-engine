# Event language for shareable reasons

Status: Ready — decisions settled with the user on 2026-10-25; implementation in progress
Plan: [Event language plan](../exec-plans/active/2026-10-25-event-language.md)
Console counterpart: `weft-console-front` `docs/changes/2026-10-25-console-translations.md`

## Problem

Match reasons shown to organizers are always English. Spanish-language events need reasons in Spanish.

## Requirements

- The Console owns `public.events.language` (`en` | `es`). The engine reads it in `snapshot()` and never writes it.
- The snapshot carries `language`. It is part of the fingerprint, so a language change produces a new fingerprint and a new run.
- The reason verification pass in `src/matching/worker.py` writes `shareable_reasons` in the event language. Quoted evidence stays verbatim in its original language; reason codes remain codes and are never translated.
- Run provenance records `language`.
- `matching_prompt_version` is bumped so older runs are distinguishable.
- Evaluation prompts stay language-agnostic. Scoring, candidate selection and reciprocal allocation are unchanged.
- An unknown or missing value falls back to `en`.

## Out of scope

Other locales, per-guest language, dual-language generation, translating organizer-only evidence.

## Observable behavior

A Spanish event's results contain Spanish `shareableReasons` with exact quotes, a different fingerprint from the same data in English, and provenance `language: "es"`.

## Acceptance scenarios

- Snapshot includes `language` and the fingerprint changes when it changes.
- The verification prompt contains the Spanish instruction and the verbatim-quote rule for `es`.
- Provenance records the language.
- On an isolated database, a Spanish event yields Spanish reasons with verbatim quotes; an expert sample review follows [matching quality](../matching-quality.md).
