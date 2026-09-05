# FL3/FL8.1 Exact-Rational PumpSwap Training Fees — Design

**Date:** 2026-09-05
**Base:** `5d05bbb5e45d3f7e611e756b152d6b005e6d00f7`
**Branch:** `feat/exact-rational-training-fees`

## Status

Follow-on to the physically accepted training-economics overlay.

Production acceptance for the sealed base proved:

- 512 FL8.1 feature rows;
- 6,144 immutable FL4 decision/horizon rows;
- unchanged FL4 logical fingerprint before/after;
- 2,112 Pump rows correctly unsupported in overlay v1;
- 4,032 PumpSwap rows;
- 121 `exit_projection_unavailable`;
- 336 `no_endpoint`;
- 3,553 `entry_fee_rate_unknown`;
- 22 `exit_fee_rate_unknown`;
- zero `available` PumpSwap rows;
- zero executable BUY_NOW rows;
- all 6,144 SKIP rows executable;
- PAPER services healthy throughout.

The dominant remaining source-economics blocker is therefore the v1 integer-basis-point representation.

FL9 remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

The sealed PumpSwap effective-fee normalizer preserves exact source facts:

- `market_quote_amount_raw`;
- `user_quote_amount_raw`;
- `signed_user_cost_quote_raw`.

For non-negative source cost, these raw integers define an exact rational rate:

`signed_user_cost_quote_raw / market_quote_amount_raw`.

The same normalizer also exposes `effective_fee_bps` only when that exact ratio happens to be representable as an integer number of basis points.

Overlay v1 incorrectly makes integer-bps representability the training executability gate. This is safe but unnecessarily discards exact source evidence. A ratio such as `1 / 3` is exact even though it is not an integer number of basis points.

Rounding to integer bps is still forbidden.

Negative signed user cost remains rebate/benefit-like evidence that the current execution-cost model does not support and must remain unknown.

## Goal

Add overlay schema v2 so training economics can use exact non-negative PumpSwap fee ratios without rounding.

The source fee rate for each leg is exactly:

`signed_user_cost_quote_raw / market_quote_amount_raw`.

The existing optional `effective_fee_bps` remains audit convenience only:

- exact integral-bps ratio -> populated;
- exact non-integral-bps ratio -> null;
- no rounding, floor, ceiling, or floating inference.

## Scope

### Rust

Keep the sealed causal fee-context API unchanged.

In training-economics overlay v2:

- `Available` fee context behaves as today;
- `RateUnknown(value)` with non-negative `signed_user_cost_quote_raw` is accepted as exact-rational fee evidence;
- `RateUnknown(value)` with negative `signed_user_cost_quote_raw` remains `entry_fee_rate_unknown` / `exit_fee_rate_unknown`;
- fee provenance may contain `effective_fee_bps = null`;
- the exact raw delta and market quote remain mandatory provenance;
- no component sidecar summation is introduced.

The overlay schema version increments from 1 to 2.

### Python

Overlay v2 reader:

- requires schema version 2;
- accepts `effective_fee_bps: int | None`;
- validates the raw fee ratio exactly;
- when bps is present, verifies it equals the exact integer-bps representation;
- when bps is absent, verifies the exact non-negative ratio is not integer-bps representable;
- rejects negative fee provenance on any attached fee object.

Cost application uses the exact rational source rate from raw integers.

Policy slippage/latency bps remain explicit versioned non-source assumptions.

No protocol fee is invented in Python.

## Exact arithmetic

For one leg:

`source_fee_rate = signed_user_cost_quote_raw / market_quote_amount_raw`

`policy_variable_rate = (slippage_bps + latency_bps) / 10_000`

Entry:

`entry_total = gross_entry * (1 + source_fee_rate + policy_variable_rate) + fixed_entry_cost`

Exit:

`exit_net = gross_exit * (1 - source_fee_rate - policy_variable_rate) - fixed_exit_cost`

Python should use exact rational arithmetic for the source rate and bps terms before converting the final quote amount to the existing finite float evidence field.

The exit total variable rate must remain strictly below 1.

## Compatibility

Overlay v1 artifacts are historical immutable evidence and are not rewritten.

Current code after this slice reads/writes overlay v2 only. There is no compatibility default or silent v1 interpretation.

First-champion/request schemas do not need another bump because they already authenticate the overlay manifest fingerprint and invoke the current runtime overlay reader. Any v1 overlay is rejected by the current schema constant.

## Non-goals

This slice does not:

- change `pump_swap_effective_fee_context` selection;
- reinterpret negative/rebate-like deltas;
- sum LP/protocol/creator/cashback/buyback sidecars;
- change Pump bonding-curve fee semantics;
- change reserve projection math;
- change counterfactual size;
- mutate FL4;
- alter provider ingestion;
- alter PAPER execution;
- select/promote a champion;
- enable LIVE.

## Required physical proof

After seal/deploy, rebuild the same immutable 512-decision population with:

- counterfactual base quantity `2`;
- PumpSwap fee maximum age `60000 ms`;
- the same explicit verification-only cost policy.

Require:

- 512 features;
- 6,144 overlay rows;
- FL4 fingerprint unchanged;
- Pump unsupported count remains 2,112;
- zero attached negative/rebate fee provenance;
- exact-rational non-integral fee rows decode and apply successfully;
- executable BUY_NOW identities equal overlay `available` identities exactly;
- all unavailable rows remain BUY_NOW UNKNOWN;
- PAPER services remain active.

No favorable profitability threshold is required by this slice.
