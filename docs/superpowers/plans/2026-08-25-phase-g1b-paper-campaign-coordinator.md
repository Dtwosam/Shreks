# Phase G1B Paper Campaign Coordinator — Implementation Plan

**Base:** sealed G1 `945c66d3ea725a0aebd8ba86bb71ad8c4f3e0463`  
**Design:** `docs/superpowers/specs/2026-08-25-phase-g1b-paper-campaign-coordinator-design.md`

## Goal

Add one restart-safe, multi-token observer-backed PAPER campaign coordinator that assembles all required candidate/position evidence at one point-in-time timestamp, ranks entry opportunities with the sealed B7 score, runs C5 exactly once, and commits E11/C6 evidence exactly once.

No live, signer, submission, promotion, registry-mutation, or provider-credential authority is in scope.

## Task 1 — read-only campaign candidate selection

Files:
- add `python/src/shreks_brain/observer_campaign/coordinator.py`
- add `python/tests/test_observer_campaign_coordinator_selection.py`

RED first:
- exact policy type and explicit nonzero operational bounds;
- point-in-time recent candidate discovery excludes future rows;
- deterministic latest-observation selection and duplicate-mint handling;
- OPEN managed-position mints and pending-entry mint are always included even outside recent bounds;
- ambiguous required mint identity fails closed;
- missing DB/schema/malformed rows fail closed;
- selector is read-only and does not create a missing database.

GREEN minimally with a runtime-local SQLite read-only selector. Do not widen `ObserverMarketStore` or `ObserverCampaignStore` public surfaces.

## Task 2 — multi-candidate aggregate assembly and ranking

Files:
- extend `coordinator.py`
- add `python/tests/test_observer_campaign_coordinator_assembly.py`

RED first:
- derive candidate-specific ENTRY identities without changing caller-supplied policy values;
- assemble every selected mint against the same `PaperLoopState` and `as_of`;
- preserve all OPEN-position exit observations;
- preserve pending-entry quote semantics;
- rank regular entry candidates by sealed Fresh Launch assessment + B7 total score descending, then `candidate_id`, then mint;
- merge unique quotes and exit observations;
- contradictory duplicate mint/quote/position evidence fails closed;
- aggregate audit is immutable/versioned and fingerprints component E15 audits/order.

GREEN using sealed E15 assembler + B3/B7 calculations only. Do not duplicate thresholds or alter C5.

## Task 3 — restart-safe coordinator runner

Files:
- extend `coordinator.py`
- minimally refactor `python/src/shreks_brain/observer_campaign/runner.py` only if needed to share private C5/E11/C6 commit logic without changing its public behavior
- add `python/tests/test_observer_campaign_coordinator_runner.py`
- rerun all existing E15 runner tests unchanged

RED first:
- first aggregate cycle records E11 evidence and one checkpoint;
- multiple token candidates feed one C5 cycle and consume at most one new BUY slot;
- multiple OPEN positions receive same-timestamp exit observations;
- restart reconstructs identical state/accounting;
- exact completed timestamp replay is idempotent;
- time reversal fails closed;
- E11 attribution conflict/corruption fails closed;
- checkpoint collision/reload mismatch/restart mismatch fails closed.

GREEN with one shared paper run/candidate attribution and one checkpoint sequence per aggregate cycle.

## Task 4 — restricted public API and authority firewall

Files:
- update `python/src/shreks_brain/observer_campaign/__init__.py`
- add/update `python/tests/test_observer_campaign_public_api.py`
- add coordinator-specific authority tests if clearer

RED first:
- exact coordinator exports are absent;
- public coordinator surface must not expose registry mutation, promotion, live execution, transaction/signing/submission, provider credentials, or raw write-store methods.

GREEN by export-only package change. Existing E15 public methods remain unchanged.

## Task 5 — freeze, audit, verification seal

Before seal:
- run full repository CI on the frozen behavior SHA;
- compare sealed G1 -> frozen G1B and inspect every changed file;
- verify no Rust/provider/storage/live/promotion code drift unless explicitly required by this plan (none expected);
- verify existing E15 runner/public API regressions remain GREEN;
- record RED/GREEN anchors and exact behavior CI in this document.

Seal:
- replace this plan with the final verification record as the only post-behavior file change;
- prove behavior -> seal is exactly one commit, zero behind, and exactly this one file;
- run fresh exact-seal CI;
- update the stacked draft PR with behavior SHA, seal SHA, CI IDs, scope audit, and `LIVE TRADING: DISABLED`.

## Deferred after G1B seal

A subsequent G1 runtime-bootstrap slice will provide an immutable campaign configuration artifact/codec plus a supervised Python process. It must consume the sealed G1B coordinator and cannot hard-code strategy/risk/economic thresholds. Then G2 can add GitHub -> VPS deployment mechanics.
