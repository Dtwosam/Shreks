# FL3 PumpSwap Effective Fee Normalization — Implementation Plan

**Date:** 2026-09-05
**Base:** `be7c6193796195189858c26cff32c9e62dfbf314`

## Step 1 — RED contract

- [ ] Add focused storage tests for BUY and SELL exact fee deltas.
- [ ] Prove exact integer bps only; non-integral ratio remains unknown.
- [ ] Prove a negative/net-benefit delta remains signed and does not become a fee.
- [ ] Prove migration-15 component sidecar values do not alter the raw user-vs-market result.
- [ ] Prove conflict-quarantined identity fails closed.
- [ ] Prove missing source returns `None`.

## Step 2 — GREEN read-only normalization

- [ ] Add `PumpSwapEffectiveFeeEvidence`.
- [ ] Add read-only `ShreksDb::pump_swap_effective_fee_evidence`.
- [ ] Reuse existing raw PumpSwap source replay.
- [ ] Check exact conflict table before deriving evidence.
- [ ] Use checked signed/raw arithmetic.
- [ ] Require exact integer-bps divisibility; never round.
- [ ] Add no migration and write no derived state.

## Step 3 — Verification

- [ ] Focused Rust tests GREEN.
- [ ] Repository safety GREEN.
- [ ] Full Rust workspace GREEN.
- [ ] Python suite GREEN.
- [ ] native ARM64 release build GREEN.
- [ ] Review exact diff.
- [ ] Merge only exact reviewed GREEN head.
- [ ] Require fresh merged-main four-gate GREEN.
- [ ] Seal and release.

## Following slice

Build runtime training-bundle execution enrichment without changing immutable FL4 rows.

LIVE remains disabled.
