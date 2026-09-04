# FL9 Deterministic Chronological PAPER Campaign Driver — Implementation Plan

**Date:** 2026-09-04
**Base:** `572037aafa790ab8ec78aff180703bfc9e2e400f`

## TDD sequence

1. Add RED tests for whole-campaign preflight and actual-PAPER posture switching.
2. Open draft PR and record the missing package/API RED.
3. Implement immutable campaign-row model.
4. Implement whole-population preflight.
5. Implement sequential runner using only:
   - offline deterministic row adapter;
   - deterministic PAPER session posture;
   - deterministic PAPER session step.
6. Export package API.
7. Run focused Python tests and full four-gate CI.
8. Freeze exact GREEN head and guarded squash merge.

## Authority boundary

The driver orchestrates sealed components only.

It must not contain:

- subprocess/process launch code;
- FL6 policy formulas;
- execution-economics formulas;
- quote acquisition;
- risk calculations;
- PAPER fill/ledger logic;
- E11/E5 calculations;
- superiority logic;
- provider/network/database access;
- promotion/signing/submission/LIVE authority.

## Following work

Build the required deterministic candidate-matrix runner and same-population proof
bundle, then feed real baseline `FastPolicyRunEvidence` into the already-sealed
FL9 superiority evaluator with the learned-candidate run.
