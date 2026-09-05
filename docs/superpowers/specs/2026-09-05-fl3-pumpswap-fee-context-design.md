# FL3 PumpSwap Causal Fee Context — Design

**Date:** 2026-09-05  
**Base:** `9e1837ffb9ac3e43f66d1bc4a8b693e21a0dbaa6`

## Goal

Add one deterministic, read-only lookup that provides the latest **same-side** PumpSwap effective-fee
context available causally at a requested canonical Fast Lane decision point.

This slice exists to prevent later counterfactual training economics from:

- using SELL fee evidence for a hypothetical BUY;
- using BUY fee evidence for a hypothetical SELL;
- peeking at future events;
- silently skipping a recent unknown/stale/conflicted fee observation in favor of an older cleaner one.

No schema change is required.

## Public contract

Add:

`ShreksDb::pump_swap_effective_fee_context(...)`

Inputs:

- `mint`;
- `quote_mint`;
- `is_buy`;
- `as_of_sequence`;
- `as_of_observed_at_unix_ms`;
- `maximum_age_ms`.

Return one explicit status:

- `Missing`
- `Stale`
- `RateUnknown`
- `Available`

The three non-missing statuses retain the exact selected source identity, canonical sequence,
observation timestamp, age, and normalized `PumpSwapEffectiveFeeEvidence`.

## Causal selection

The source candidate is the single latest canonical event satisfying all of:

- same `mint`;
- same `quote_mint`;
- venue = `pump_swap`;
- same side as requested;
- `sequence <= as_of_sequence`;
- `observed_at_unix_ms <= as_of_observed_at_unix_ms`.

Selection order is canonical `sequence DESC`, one row only.

No future event is eligible.

## No fallback rule

After the latest same-side candidate is selected:

1. if its exact source identity is conflict-quarantined, fail closed;
2. if its age exceeds `maximum_age_ms`, return `Stale`;
3. if its normalized integer fee bps is unavailable, return `RateUnknown`;
4. otherwise return `Available`.

Do **not** search backward for another event after steps 1–3.

This prevents outcome- or cleanliness-biased fee context selection.

## Age semantics

`age_ms = as_of_observed_at_unix_ms - source_observed_at_unix_ms`

Age must be non-negative by query construction and checked arithmetic.

Age equal to `maximum_age_ms` is still usable.
Only strictly greater age is stale.

## Source integrity

Canonical PumpSwap FastEvents already require immutable PumpSwap raw evidence.
The lookup still delegates fee normalization to the sealed
`pump_swap_effective_fee_evidence(signature, ordinal)` API so conflict quarantine and exact raw
delta semantics remain centralized.

A canonical event whose raw fee source unexpectedly disappears is invalid data, not `Missing`.

The normalized raw side must match the requested/canonical side.

## Validation

Fail closed on:

- empty mint or quote mint;
- zero `as_of_sequence`;
- negative `as_of_observed_at_unix_ms`;
- arithmetic overflow;
- canonical/raw side mismatch;
- quarantined selected source;
- canonical source missing from raw evidence.

`maximum_age_ms = 0` is valid and means only same-observation-time evidence is fresh.

## Authority boundary

This slice adds no:

- migration or stored derived fee state;
- provider/network call;
- current fee schedule;
- historical fee backfill;
- FL4 mutation;
- training;
- strategy threshold;
- PAPER execution;
- risk/promotion;
- signing;
- transaction submission;
- LIVE authority.

## Following work

Use this lookup only as one input to a separately versioned size-aware training economics overlay.
That overlay must still combine explicit counterfactual size, deterministic reserve projections, and
explicit non-source cost policy without mutating FL4.

LIVE remains disabled.
