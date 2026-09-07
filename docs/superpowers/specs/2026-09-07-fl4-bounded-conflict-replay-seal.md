# FL4 Bounded Conflict-Quarantine Replay — Production Seal

**Date:** 2026-09-07  
**Behavior merge:** `cac606ffe544d8b5d6b153457786a698d95bdd8c`  
**Implementation PR:** #233  
**Intentional RED PR:** #234

## Physical production evidence

FL9 immutable FL4 population on the production VPS first committed session 55 exactly:

- decisions: 512;
- inserted FL4 labels: 6,144;
- already-existing labels: 0.

Session 56 then failed before any write with:

`FastEvent market replay blocked by 1 conflict-quarantined canonical identities for venue 'pump_fun_bonding_curve'`.

A read-only production localization audit proved:

- session 55: CLEAN;
- session 56: BLOCKED by one market containing one quarantined canonical identity from before the selected session;
- session 57: BLOCKED by one different market containing one quarantined canonical identity from before the selected session;
- sessions 58–61: CLEAN;
- the quarantined canonical identities affecting sessions 56 and 57 were not themselves inside sessions 55–61;
- session 56 had only one selected-window event on its blocked market;
- session 57 had only one selected-window event on its blocked market;
- no target values or model performance were inspected;
- session 56 failure was atomic and wrote zero FL4 rows;
- PAPER runtime restoration remained healthy.

The affected quarantine rows remain preserved and unresolved.

## Root cause

The covered FL4 writer needs market evidence only from the selected decision start through the authenticated coverage-session watermark.

However, it used the unbounded `fast_events_for_market` API. That API intentionally fails closed when any canonical identity anywhere in a market's full history later enters conflict quarantine.

Therefore an old quarantined identity, irrelevant to the selected decisions and all complete FL4 horizons, could poison a much later independent covered replay.

## Sealed behavior

A new bounded quarantine-aware replay API reads exactly one inclusive observation-time interval.

Covered FL4 population now replays:

`request.from_observed_at_unix_ms <= observed_at_unix_ms <= coverage.complete_through_unix_ms`.

Within that interval:

- any conflict-quarantined canonical identity still fails closed;
- all canonical identity/provenance checks remain authoritative;
- no conflict is deleted, rewritten, resolved, or silently accepted.

Outside that interval:

- a quarantined identity cannot poison an independent covered FL4 replay because it cannot contribute a selected decision or any complete future-path label.

The original unbounded `fast_events_for_market` contract remains unchanged and globally fail-closed.

## RED evidence

Correct intentional RED head:

`2fda0657d8f77e10e8e35e46d2d2abe03c3a901e`

CI run:

`34119023637`

Results:

- repository safety: GREEN;
- Python: GREEN;
- native ARM64 release build: GREEN;
- Rust: RED.

Focused Rust result:

- `covered_population_ignores_quarantine_before_required_replay_window`: FAILED with the old global quarantine block;
- `covered_population_rejects_quarantine_inside_required_replay_window`: PASSED.

This proves the missing behavior was specifically bounded independence from stale quarantine, while the relevant in-window fail-closed rule already held.

## GREEN evidence

Exact implementation/docs head:

`cb65c65f664b3d684873a64a960b137b12dd1ba8`

PR CI run:

`34118989698`

All four gates GREEN. Focused covered-population suite:

- 7 passed;
- stale pre-window quarantine regression: GREEN;
- in-window quarantine fail-closed regression: GREEN.

Behavior merge:

`cac606ffe544d8b5d6b153457786a698d95bdd8c`

Merged-main CI run:

`34119304370`

All four gates GREEN:

- repository safety;
- Python;
- Rust workspace;
- native ARM64 release build.

## FL9 evidence state

Durable fresh FL4 state before deploying this seal:

- established session-54 fresh slice: 43,776 decisions / 525,312 labels;
- session 55: 512 decisions / 6,144 labels;
- sessions 56–61: not populated;
- remaining sessions 56–61 target: 102,144 decisions / 1,225,728 labels;
- intended final fresh cohort: 146,432 decisions / 1,757,184 labels.

The retired historical 512-decision population remains excluded from first-champion evidence.

## Authority boundary

No:

- conflict resolution or conflict-row deletion;
- raw/canonical evidence rewrite;
- outcome filtering;
- cohort-floor adaptation;
- strategy threshold;
- safety/risk/sizing change;
- PAPER execution behavior;
- model training or promotion;
- signing or submission;
- LIVE authority.

## Production next gate

Build and deploy the exact sealed ARM64 release through `production-paper`.

After deployment:

1. verify exact release identity and all core PAPER services;
2. re-preflight sessions 56–61 without inspecting targets/model performance;
3. populate immutable sessions 56–61 through the same atomic/idempotent FL4 CLI;
4. require 102,144 remaining decisions and 1,225,728 remaining labels;
5. require total fresh identity 146,432 decisions and 1,757,184 labels;
6. only then continue to authenticated training-economics/runtime-bundle and first-champion planning.

LIVE remains disabled.
