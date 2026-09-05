# FL3 Entry Projection — Implementation Plan

**Date:** 2026-09-05
**Base:** `0ccd390a1b524c69c7bc37a76bdc08df7d69bfeb`

## Step 1 — RED contract

- [ ] Add entry projection tests beside FL3 exit-capacity tests.
- [ ] Prove Pump integer ceiling and worsening average price with size.
- [ ] Prove PumpSwap signed virtual quote reserve is used.
- [ ] Prove physical/effective base exhaustion fails closed.
- [ ] Prove zero quantity and missing virtual quote reserve fail closed.

## Step 2 — GREEN algebra

- [ ] Add `EntryProjection` and `EntryProjectionError`.
- [ ] Extend internal reserve view with physical base inventory.
- [ ] Implement checked ceiling constant-product entry projection.
- [ ] Export the API from `shreks-core`.
- [ ] Keep existing SELL behavior unchanged.

## Step 3 — Verification

- [ ] Focused Rust tests GREEN.
- [ ] Full Rust workspace GREEN.
- [ ] Repository safety GREEN.
- [ ] Python suite GREEN.
- [ ] native ARM64 release build GREEN.
- [ ] Merge only exact reviewed GREEN head.
- [ ] Seal merged main.

## Following slice

Normalize exact per-event protocol fee evidence without inventing missing fee semantics, then combine
entry/exit reserve projections with explicit non-source cost policy at runtime training-bundle
construction.

LIVE remains disabled.
