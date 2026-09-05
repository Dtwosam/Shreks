# FL3 PumpSwap Causal Fee Context — Implementation Plan

**Date:** 2026-09-05  
**Base:** `9e1837ffb9ac3e43f66d1bc4a8b693e21a0dbaa6`

## Step 1 — RED contract

- [ ] Add tests selecting latest same-side canonical PumpSwap fee evidence.
- [ ] Prove opposite-side events are ignored.
- [ ] Prove future sequence/time events are ignored.
- [ ] Prove exact max-age boundary remains available.
- [ ] Prove stale latest source returns `Stale`.
- [ ] Prove latest non-integral fee returns `RateUnknown` without fallback.
- [ ] Prove selected conflict-quarantined source fails closed.
- [ ] Prove no eligible source returns `Missing`.

## Step 2 — GREEN lookup

- [ ] Add explicit context/status types.
- [ ] Add one bounded canonical SQL lookup ordered by sequence descending.
- [ ] Reuse sealed `pump_swap_effective_fee_evidence`.
- [ ] Preserve source identity, sequence, observation timestamp, and age.
- [ ] Enforce no-fallback semantics.
- [ ] Add no migration and no writes.

## Step 3 — Verification

- [ ] Focused Rust tests GREEN.
- [ ] Repository safety GREEN.
- [ ] Full Rust workspace GREEN.
- [ ] Python suite GREEN.
- [ ] native ARM64 release build GREEN.
- [ ] Review exact diff.
- [ ] Merge exact reviewed GREEN head only.
- [ ] Require fresh merged-main GREEN.
- [ ] Seal and release.

## Following slice

Build the size-aware training economics overlay without mutating immutable FL4 rows.

LIVE remains disabled.
