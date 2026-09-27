# Fast PAPER Shadow Durable Raw Inventory — Design

**Date:** 2026-09-27  
**Base main SHA:** `6a20036f3b2bbe711ec7fc2b72700af634baf44d`

## Purpose

Preserve exact raw base-token inventory for every learned OPEN position.

Decision evidence v4 now seals the exact raw amounts from persisted observer
quotes. The durable learned posture still stores only normalized float exposure,
while the canonical PAPER ledger stores normalized float quantity. Unattended
REDUCE/SELL authority must not reconstruct token raw amounts from either float.

This slice carries exact raw inventory through the existing isolated PAPER
executor and durable shadow runtime state. It adds no observer writer and no
reduction-source publication yet.

## Runtime-state schema

Advance:

`shreks.fast_paper_shadow_runtime_state` from version `2` to version `3`.

Extend `FastPaperShadowMarketPosition` with:

`current_base_quantity_raw: int`

Requirements:

- exact positive u64;
- canonical runtime-state fingerprint/SQLite payload binding;
- restart round-trip preserves the exact value;
- every canonical OPEN PAPER position still has exactly one learned mapping;
- no raw quantity exists for FLAT posture.

## BUY inventory authority

A filled learned BUY may create raw inventory only when:

- ENTRY quote evidence is executable;
- ENTRY quote `output_amount_raw` is present and positive;
- entry authority intended normalized quantity equals the sealed ENTRY
  `quoted_base_quantity` exactly within existing execution tolerance.

Fresh BUY and pending-BUY retry both seed
`current_base_quantity_raw` from the exact ENTRY quote raw output.

No normalized fill quantity is converted into raw units.

## OPEN transition authority

### HOLD

Preserve exact raw inventory unchanged.

### REDUCE

On an actually `REDUCED` PAPER outcome:

1. identify the exact shadow reduction quote actually used for the active exit,
   including pending REDUCE restart resolution;
2. require positive raw input authority;
3. require raw input < current raw inventory;
4. set:
   `next_raw = current_raw - executed_quote.input_amount_raw`;
5. reconcile the raw remaining ratio against the canonical PAPER position
   quantity ratio within the existing numeric tolerance;
6. fail closed on mismatch before any durable transition commit.

This is subtraction of explicit persisted raw authority, not float-to-raw
derivation.

Deferred/aborted position actions preserve raw inventory unchanged.

### SELL

A successful `SOLD` outcome removes the learned mapping. Full SELL quote raw
input must equal current raw inventory before execution may be treated as exact
full-position authority.

## Execution-input tightening

For BUY, require:

`entry_authority.intended_base_quantity == decision.entry_quote.quoted_base_quantity`

within existing numeric tolerance.

The production BUY-authority writer already derives the intended quantity from
that exact persisted quote. This closes the manual-source ambiguity at the
executor boundary.

## Authority boundary

```text
RAW_INVENTORY_SOURCE=SEALED_PERSISTED_QUOTE_ONLY
FLOAT_TO_RAW_DERIVATION=FORBIDDEN
BUY_SIZE_BINDING=EXACT_QUOTE_QUANTITY
REDUCE_RAW_UPDATE=EXACT_QUOTE_INPUT_SUBTRACTION
SELL_RAW_AUTHORITY=EXACT_CURRENT_RAW
PAPER_LEDGER=EXISTING_ISOLATED_ONLY
RISK=UNCHANGED
ACTION_SELECTION=UNCHANGED
REDUCTION_SOURCE_PUBLICATION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- runtime-state schema version `3`;
- `FastPaperShadowMarketPosition.current_base_quantity_raw` positive-u64
  contract and canonical restart round-trip;
- BUY input rejects intended-size drift from the sealed ENTRY quote;
- fresh BUY seeds raw inventory from ENTRY raw output;
- deferred/retry BUY seeds the same raw inventory after restart;
- HOLD preserves raw inventory;
- REDUCE subtracts only the exact selected reduction quote raw input and
  reconciles raw/ledger remaining ratios;
- SELL removes the mapping and refuses mismatched full raw authority;
- executor/runtime source contains no float-to-raw conversion helper.

## Following slice

Use durable raw inventory to produce write-once reduction/exit quote-source
authority from persisted observer quotes before the supervised OPEN decision
cycle, then prove BUY -> HOLD/REDUCE/SELL end to end in the isolated PAPER
ledger.
