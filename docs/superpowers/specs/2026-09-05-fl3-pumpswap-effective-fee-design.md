# FL3 PumpSwap Effective Fee Normalization — Design

**Date:** 2026-09-05
**Base:** `be7c6193796195189858c26cff32c9e62dfbf314`

## Status

Follow-on to sealed deterministic FL3 entry projection.

The historical PumpSwap raw event already preserves both:

- `quote_amount_raw`: executed market quote quantity; and
- `user_quote_amount_raw`: the fee-adjusted user quote quantity.

The FL3 source-evidence sidecar also preserves LP/protocol/creator/cashback/buyback fields, but their
combined semantics must not be guessed.

FL9 remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Goal

Add one deterministic read-only normalization API that derives the exact PumpSwap user-vs-market
quote delta for an immutable raw event and exposes integer effective fee basis points only when that
rate is mathematically exact.

No SQLite schema change is needed.

## Source authority

The stable PumpSwap raw event is authoritative for this normalization.

For a BUY:

`signed_user_cost_quote_raw = user_quote_amount_raw - quote_amount_raw`

For a SELL:

`signed_user_cost_quote_raw = quote_amount_raw - user_quote_amount_raw`

Positive values mean the user was economically worse than the market quote by that many raw quote
units.

Negative values are preserved as a net user benefit/rebate-like delta. They are **not** coerced to
zero or converted into a negative fee input because the current FL3 execution model accepts only
non-negative effective fees.

## Exact basis-point derivation

For non-negative signed user cost:

`numerator = signed_user_cost_quote_raw * 10_000`

An integer `effective_fee_bps` is available only when:

`numerator % quote_amount_raw == 0`.

Then:

`effective_fee_bps = numerator / quote_amount_raw`.

If the raw ratio is not exactly representable in integer basis points, the field remains unknown.
No rounding, ceiling, floor, or floating approximation is permitted.

The exact signed raw delta remains available even when integer bps is unavailable.

## Conflict boundary

If `pump_swap_trade_evidence_conflicts` contains the exact `(signature, ordinal)`, normalization
fails closed with an error.

A quarantined raw identity must never become fee evidence.

Missing raw source returns `None`.

## Sidecar boundary

LP/protocol/creator/cashback/buyback source fields are **not** summed.

The normalization result is independent of the migration-15 PumpSwap execution-economics sidecar.
Those component fields remain useful audit evidence, but this slice does not assign them combined
fee semantics.

## Public contract

Add:

`PumpSwapEffectiveFeeEvidence`

with:

- signature;
- ordinal;
- side;
- market quote amount raw;
- user quote amount raw;
- signed user cost quote raw;
- optional exact effective fee bps.

Add:

`ShreksDb::pump_swap_effective_fee_evidence(signature, ordinal)`

returning:

`Result<Option<PumpSwapEffectiveFeeEvidence>, StorageError>`.

## Authority boundary

This slice adds no:

- provider/network call;
- fee schedule;
- current-protocol backfill into history;
- strategy logic;
- FL4 mutation;
- training;
- PAPER execution;
- risk/promotion;
- signing;
- transaction submission;
- LIVE authority.

## Following work

Once sealed, build a separate size-aware training economics overlay that combines:

1. exact FL3 entry projection at the decision reserve state;
2. exact FL3 exit projection at the endpoint reserve state;
3. source-normalized effective fee only when exact;
4. explicit versioned non-source cost assumptions for any impact/slippage/latency/network/failure
   component not recoverable from immutable history.

The overlay must not mutate FL4 rows.

LIVE remains disabled.
