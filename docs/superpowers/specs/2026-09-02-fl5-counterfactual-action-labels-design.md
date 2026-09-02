# FL5 Counterfactual Action Labels Design

**Base proof:** `6d3fee812bbe61a27b93d48883c3a339b6deb194` (FL4 merged-main four-gate GREEN)

## Goal

Create deterministic, point-in-time-safe action-learning records that compare realistic alternatives available to Shreks at a decision point: BUY vs SKIP vs evidence-supported delayed entry, and HOLD vs caller-sized REDUCE vs SELL for an already-open position.

FL5 converts source-backed future-path and execution evidence into research labels. It must teach action selection without pretending that an observed future price, candle extreme, or current protocol constant was an achievable historical fill.

## Ownership boundary

FL5 is Python research/learning work. Rust and SQLite remain authoritative for canonical FastEvents, immutable source evidence, conflict quarantine, and FL3/FL4 execution/future-path facts. Python may read/export those facts but does not mutate canonical Fast Lane state and receives no capital authority.

FL5 does not add or modify strategy scoring, PAPER orders, LIVE orders, signing, transaction submission, provider fallback topology, release/deploy topology, or LIVE authorization.

## Evidence rule: executability is explicit

Every non-SKIP counterfactual requires contemporaneous execution evidence. A price observation by itself is not execution evidence.

Version 1 represents execution evidence with immutable, validated records carrying:

- canonical source identity and observation time,
- side (`buy` or `sell`),
- base quantity the quote/evidence applies to,
- executable gross/total quote values needed to evaluate the action,
- optional capacity evidence when known,
- explicit execution status: `executable`, `not_executable`, or `unknown`,
- provenance/version fields sufficient for deterministic fingerprints.

Missing evidence remains `unknown`. Unknown fee, slippage, latency, capacity, route, or failure-cost assumptions are never converted to zero. `not_executable` means the contemporaneous evidence explicitly proves the action was unavailable; it is distinct from `unknown`.

A record marked `executable` must contain the exact monetary quantity required by the action calculation. An action is not labelable merely because a source price exists.

## Utility convention

Counterfactual utilities are expressed in quote-asset units and, where meaningful, return basis points relative to the same capital/position basis.

The pure labeler does not choose portfolio capital allocation, opportunity-cost assumptions, or risk thresholds. It emits per-action outcomes for downstream research.

### SKIP

`SKIP` is an explicit within-opportunity baseline:

- net PnL = `0` quote,
- return = `0` bps,
- execution status = executable by definition because it means taking no trade.

This is not a claim that capital had no alternative use elsewhere.

### BUY_NOW

For an entry opportunity, BUY_NOW is labelable only when:

1. decision-time buy evidence is `executable`,
2. the buy evidence applies to the requested base quantity,
3. a source-backed executable exit outcome exists for the comparison horizon,
4. the future-path horizon is complete.

The entry basis is the exact all-in entry quote amount from execution evidence. The exit value is exact executable net quote proceeds from future execution evidence.

```text
net_pnl_quote = exit_net_quote - entry_total_quote
return_bps = (exit_net_quote / entry_total_quote - 1) * 10_000
```

If either side is unknown, BUY_NOW utility is unknown. If contemporaneous evidence says entry or required exit is not executable, the action is explicitly not executable rather than assigned a fabricated loss or fill.

### DELAY_ENTRY

A delayed-entry alternative is admitted only for a caller-supplied later decision point with its own explicit executable buy evidence and an execution-supported exit outcome for the requested comparison horizon.

The labeler must not create delayed entries from:

- future minimum observed price,
- candle lows,
- FL4 MFE/MAE extrema,
- later trade prices lacking executable buy evidence.

Delay length is derived from canonical observation timestamps and must be positive.

### Entry-price efficiency

Entry-price efficiency compares actual executable alternatives only. For two labelable entry alternatives with the same requested base quantity and same comparison horizon, the record may expose the difference in all-in entry quote and resulting net return.

No synthetic “better acceptable price” row is created unless a source-backed executable quote/evidence record actually supports it at that time and size.

## Open-position counterfactuals

Open-position labels require an explicit immutable position state:

- base quantity currently held,
- total quote cost basis assigned to that quantity,
- canonical action timestamp/identity.

### SELL_NOW

SELL_NOW is labelable only with executable sell evidence for the full requested position quantity. Utility is realized net PnL relative to the supplied cost basis:

```text
net_pnl_quote = sell_net_quote - position_cost_basis_quote
return_bps = (sell_net_quote / position_cost_basis_quote - 1) * 10_000
```

### REDUCE_NOW

REDUCE_NOW never invents a reduction fraction. The caller supplies a positive reduction quantity strictly less than or equal to the open base quantity.

Executable sell evidence must apply to that exact reduction quantity. Cost basis is allocated pro rata to the reduced quantity:

```text
reduced_cost_basis_quote = position_cost_basis_quote * reduce_quantity / position_quantity
realized_net_pnl_quote = reduce_sell_net_quote - reduced_cost_basis_quote
remaining_quantity = position_quantity - reduce_quantity
remaining_cost_basis_quote = position_cost_basis_quote - reduced_cost_basis_quote
```

FL5 v1 records the immediate realized component and the remaining position basis explicitly. A downstream HOLD-on-remainder comparison may be composed only when source-backed future execution evidence exists for that remainder. The labeler never assumes a default 50% reduction or a future exit for the remainder.

### HOLD

HOLD is labelable for a horizon only when that horizon is complete and source-backed executable future sell evidence exists for the full held quantity at the comparison endpoint/action point. It uses the supplied position cost basis and future executable net proceeds.

Observed future price alone is insufficient.

## Point-in-time and source integrity

Counterfactual records must be constructed only from evidence that was available at the action timestamp for the immediate leg, plus explicitly future evidence used as a training outcome.

The research adapter must preserve:

- canonical FastEvent identity/sequence/time,
- FL4 horizon/version/completeness,
- exact execution-evidence source identity/time/version,
- action quantity and quote asset identity,
- provenance sufficient to reproduce the label.

The adapter must reject contradictory source joins, market/quote mismatches, non-monotonic delay times, incomplete future horizons for outcome labels, and any attempt to use conflict-quarantined canonical evidence.

Historical missing execution inputs remain unknown; FL5 must not backfill them with present-day protocol fees or guessed latency/slippage.

## Pure Python API

Add a focused research module, initially `shreks_brain.research.counterfactuals`, with frozen dataclasses and stable literal values. Version 1 should expose at least:

- `COUNTERFACTUAL_ACTION_LABEL_VERSION = 1`
- `CounterfactualAction`
- `ExecutionStatus`
- `ExecutableTradeEvidence`
- `EntryCounterfactualContext`
- `OpenPositionCounterfactualContext`
- `CounterfactualActionOutcome`
- pure entry/open-position labeling functions
- deterministic validation/fingerprint helpers.

Public records use finite positive values for prices/notionals/quantities where applicable. Invalid identities, mismatched quantities, non-finite numerics, impossible timestamps, and inconsistent executable-status payloads fail closed with a dedicated research error.

The first implementation should return per-action outcomes rather than autonomously selecting a “best” action. Ranking/policy thresholds belong to later learning/policy phases.

## Determinism

For the same validated input records, FL5 must emit the same ordered outcomes and the same logical fingerprint.

Canonical action ordering in version 1 is stable and explicit, not dependent on Python set/dict iteration. Floating-point inputs must be finite; the fingerprint serializes normalized field names/values with canonical JSON conventions already used by the learning/research package.

## Research dataset export

FL5.5 uses a dedicated versioned Parquet artifact rather than widening the existing general research dataset schema in place.

Proposed metadata identity:

- schema name: `shreks.counterfactual_action_labels`
- schema version: `1`
- label version: `1`

The artifact contains one row per action alternative and retains:

- decision/source identity,
- market/quote identity,
- action and action timestamp,
- horizon/delay metadata,
- requested base quantity,
- execution status,
- exact source-backed entry/exit quote amounts when known,
- PnL/return when labelable,
- remaining quantity/cost basis for REDUCE,
- provenance/version fields,
- logical dataset fingerprint.

Rows have deterministic ordering. Reader and writer validate exact Arrow metadata/schema and reject unsupported versions. PyArrow is already an optional research dependency; FL5 adds no new heavy runtime dependency.

## SQLite/research adapter

After the pure action model and Parquet contract are proven, add a read-only adapter that joins canonical FL4/FL3 evidence into FL5 inputs where—and only where—the stored evidence is sufficient.

Important limitation: existing historical FL4 rows may lack optional capacity/cost-adjusted execution annotations, and full historical FL3 latency/network/failure-cost assumptions are not universally persisted. The adapter must therefore surface those counterfactuals as unknown/not labelable instead of reconstructing old execution conditions from current constants.

The adapter is read-only and has no write path into canonical Fast Lane or execution authority.

## TDD/proof requirements

Required RED/GREEN coverage includes:

1. BUY_NOW produces exact PnL/return only from explicit executable entry + exit evidence.
2. SKIP is the explicit zero within-opportunity baseline.
3. Missing entry or exit execution evidence leaves BUY_NOW unknown rather than zero-filled.
4. Explicit non-executability is distinguishable from unknown.
5. DELAY_ENTRY requires a later explicit executable entry; future price extrema alone cannot create it.
6. Entry-price efficiency compares only same-size, same-horizon executable alternatives.
7. SELL_NOW uses exact executable full-position proceeds and supplied cost basis.
8. REDUCE_NOW requires caller-supplied quantity, allocates cost basis pro rata, and never assumes a reduction fraction.
9. HOLD requires complete future coverage plus executable future sell evidence.
10. Invalid quantity/time/identity/non-finite/status payloads fail closed.
11. Same inputs produce deterministic ordered outcomes/fingerprint.
12. Dedicated Parquet v1 round-trips exactly and rejects incompatible schema/version metadata.
13. Read-only source adapter never fabricates missing historical execution economics.
14. No changes to strategy/PAPER/signing/submission/provider topology/deployment/LIVE authority.

Final FL5 completion requires the established four gates on the exact PR head and again on the merged-main commit:

- Repository safety,
- Rust workspace,
- Python suite,
- native ARM64 release build + bundle verification.

## Exit criterion

FL5 is complete when Shreks can export deterministic research records that truthfully compare BUY/SKIP/evidence-supported delayed entry and HOLD/caller-sized REDUCE/SELL from contemporaneous executable evidence, preserving unknowns whenever execution cannot be proven. The resulting dataset can train action-selection research without impossible fills or capital authority.