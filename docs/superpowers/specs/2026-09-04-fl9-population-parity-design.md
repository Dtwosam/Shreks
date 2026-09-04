# FL9 Learned-vs-Baseline Population Parity — Design

**Date:** 2026-09-04

## Status

Design after ordered FL6 baseline batches merged as `07b8639e6cbff9330aefb3f8480485eba6498068` (PR #169).

FL9 economic exit remains **EVIDENCE PENDING**.

## Purpose

Prove that a learned-policy campaign batch and one FL6 baseline decision batch describe the exact same ordered decision population before PAPER economics are compared.

A comparison is invalid if rows, order, market identity, decision clock, source sequence, or FLAT/OPEN posture differ.

## Public contract

Add `crates/shreks-storage/src/fast_population_parity.rs`.

`FAST_BASELINE_POPULATION_PARITY_VERSION = 1`.

Function:

```rust
pub fn prove_fast_baseline_population_parity(
    learned: &FastCampaignDecisionBatchWire,
    baseline: &FastBaselineCampaignBatchAssessment,
) -> Result<FastBaselinePopulationParityProof, FastBaselinePopulationParityError>;
```

Proof records:

- version;
- learned schema version;
- baseline batch version;
- baseline kind/version;
- decision count;
- first/last source event ID.

## Exact row parity

For every index require equality of:

- `source_event_id`;
- `market_key`;
- `source_sequence`;
- `as_of_unix_ms`;
- posture:
  - learned `FLAT` == baseline `FastBaselinePosture::Flat`;
  - learned `OPEN` == baseline `FastBaselinePosture::Open`.

Order is material. The function does not sort either side.

## Fail closed

Reject:

- wrong learned schema name/version;
- empty learned or baseline population;
- decision-count mismatch;
- any row identity mismatch;
- any posture mismatch.

## Non-goals

This proof does not compare:

- actions;
- forecasts;
- execution economics;
- PAPER quotes/fills;
- PnL;
- superiority.

Different actions are expected. Different population/posture is not.

## TDD

RED before production:

1. exact two-row parity succeeds;
2. source ID mismatch fails;
3. market mismatch fails;
4. sequence mismatch fails;
5. timestamp mismatch fails;
6. posture mismatch fails;
7. count mismatch fails;
8. no sorting: reversed learned rows fail;
9. deterministic proof;
10. authority firewall.

## Next

Only parity-proven learned/baseline streams may enter comparable PAPER execution/proof plumbing.
