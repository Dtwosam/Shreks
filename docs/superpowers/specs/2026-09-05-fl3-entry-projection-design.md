# FL3 Entry Projection — Design

**Date:** 2026-09-05
**Base:** `0ccd390a1b524c69c7bc37a76bdc08df7d69bfeb`

## Goal

Add the missing deterministic BUY-side reserve projection needed to evaluate a caller-supplied
counterfactual Fast Lane base quantity at an exact canonical reserve state.

The existing FL3 `project_exit` answers the SELL side. This slice adds the symmetric entry
projection only. It does not add fee policy, training labels, strategy logic, PAPER fills, signing,
submission, or LIVE authority.

## Contract

Add:

`project_entry(reserves, base_quantity_raw) -> EntryProjection`

with:

- exact requested base quantity;
- exact quote input in raw units;
- scaled base quantity;
- scaled quote input;
- average entry price in quote/base units.

## Constant-product formula

For effective reserves `b` base and `q` quote, buying `x` base from the pool uses:

`quote_input_raw = ceil(q * x / (b - x))`

The ceiling is required because an entry must supply enough quote to receive the requested integer
base quantity. SELL projection remains floor-based because it returns quote output.

## Reserve semantics

Pump bonding curve:

- effective base reserve = `virtual_base_reserve_raw`;
- effective quote reserve = `virtual_quote_reserve_raw`;
- physical base inventory = `real_base_reserve_raw`.

PumpSwap:

- effective base reserve = `pool_base_reserve_raw`;
- physical base inventory = `pool_base_reserve_raw`;
- effective quote reserve =
  `pool_quote_reserve_raw + virtual_quote_reserve_raw`.

Missing PumpSwap virtual quote reserve remains unknown and fails closed exactly like SELL capacity.

## Fail-closed rules

Reject:

- zero requested base quantity;
- requested base quantity greater than physical base inventory;
- requested base quantity greater than or equal to effective base reserve;
- missing PumpSwap virtual quote reserve;
- non-positive effective reserves;
- checked-integer overflow;
- invalid decimal scaling or non-finite derived values.

No fee, slippage, latency, network, priority, or failure cost is inferred here.

## Why this is needed

The covered FL4 event-population slice intentionally did not treat another wallet's observed trade
size as Shreks' hypothetical size. A later bundle-time economics overlay can combine this exact
entry projection, existing exact SELL projection, immutable source fee evidence, and explicit
non-source cost policy for one counterfactual quantity.

This slice is pure algebra and does not mutate SQLite.

LIVE remains disabled.
