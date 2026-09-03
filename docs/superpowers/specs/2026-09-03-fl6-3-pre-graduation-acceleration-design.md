# FL6.3 Pre-Graduation Acceleration Baseline Design

**Status:** Approved by standing autonomous-build instruction  
**Phase:** FL6.3 — Deterministic Fast Lane baselines  
**Base:** sealed FL6.2 merged main `be8a2404051903e2b4ec6abf47a902e577d165d4`

## Goal

Implement an independently measurable, deterministic Fast Lane BUY/SKIP baseline for **accelerating Pump bonding-curve participation approaching graduation**.

The baseline must not assume graduation itself is profitable. It must require both point-in-time curve-state proximity and accelerating order-flow evidence, then pass the same explicit execution-economics boundary used by prior FL6 baselines.

## Non-goals

FL6.3 does not:

- create `TradeIntent` objects,
- size capital,
- execute PAPER or LIVE trades,
- sign or submit transactions,
- call providers,
- read databases,
- consume future-path/counterfactual labels,
- introduce machine learning,
- hard-code production strategy thresholds,
- assume a protocol graduation reserve target without explicit policy evidence,
- change provider, storage, deployment, risk, signer, or LIVE authority.

LIVE remains disabled.

## Evidence model

### Curve proximity

`FastMarketSnapshot.last_reserve_context` already preserves the latest point-in-time reserve evidence from canonical Pump trade events. For `VenueId::PumpFunBondingCurve`, the context contains `real_base_reserve_raw`, `virtual_base_reserve_raw`, and decimals.

FL6.3 uses `real_base_reserve_raw` as authoritative current curve inventory evidence. It does **not** hard-code that any particular raw value equals graduation.

Instead, versioned `PreGraduationPolicy` supplies:

- `graduation_target_real_base_reserve_raw`, and
- `maximum_pre_graduation_real_base_reserve_raw`.

The evaluator requires:

`graduation_target_real_base_reserve_raw < current_real_base_reserve_raw <= maximum_pre_graduation_real_base_reserve_raw`.

This explicitly means “near but not at/past the configured graduation boundary.” Thresholds remain replay hypotheses until separately verified for production.

### Participation acceleration

The baseline uses a short signal window and a longer context window. It requires configurable minimums for signal buy count, unique buy actors, buy arrival rate, count imbalance, quote-flow imbalance, quote-flow velocity, quote-flow acceleration, and signal/context velocity expansion ratio.

It also computes the fraction of configured remaining curve distance represented by signal-window buy base quantity:

`signal_buy_base_quantity / normalized(current_real_base_reserve_raw - graduation_target_real_base_reserve_raw)`.

This is a deterministic participation-intensity feature, not a claim that every buy monotonically advances graduation or that sells cannot reverse progress.

### Lifecycle boundary

If point-in-time lifecycle evidence already records a Pump graduation for the market, FL6.3 must SKIP. A pre-graduation baseline cannot reinterpret post-graduation state as an entry opportunity.

## Execution economics

FL6.3 receives optional explicit point-in-time execution input containing market identity, decision timestamp, the existing `ExecutionCostModel`, and existing `ExecutionTradeInput`.

Rules:

- missing execution evidence => `SKIP`,
- insufficient exit capacity => `SKIP`,
- non-positive forecast net PnL => `SKIP`,
- executable entry above `maximum_acceptable_entry_price_quote` => `SKIP`,
- market/timestamp contradictions => error,
- malformed execution economics => fail closed.

No costs are zero-filled or inferred from price observations.

## Public contract

Add a dedicated Rust module exposing:

- `PRE_GRADUATION_BASELINE_VERSION`,
- `PreGraduationPolicy`,
- `PreGraduationExecutionInput`,
- `PreGraduationReason`,
- `PreGraduationAssessment`,
- `PreGraduationError`,
- `assess_pre_graduation_acceleration`.

The shared `FastLaneAction` vocabulary is reused. FL6.3 emits only `BUY` or `SKIP`.

## Determinism and leakage boundary

The evaluator is a pure function of one point-in-time `FastMarketSnapshot`, optional point-in-time execution economics input, and one explicit versioned policy.

It may not use wall clock, provider calls, database reads, future-path labels, counterfactual labels, randomness, or mutable global state.

Identical validated inputs must produce identical semantic output and stable reason ordering.

## Validation

Policy validation rejects at least unsupported version, zero/equal/reversed signal/context windows, graduation target greater than or equal to the maximum pre-graduation reserve boundary, zero participation count thresholds, non-finite/invalid numeric thresholds, invalid imbalance bounds, and velocity expansion below 1.

Snapshot evaluation fails closed on malformed numeric state and never fabricates missing reserve evidence.

## Required tests

1. Near configured graduation boundary + accelerating participation + profitable executable economics => `BUY`.
2. Wrong venue => `SKIP`.
3. Missing/non-Pump reserve evidence => `SKIP`.
4. Configured graduation target already reached => `SKIP`.
5. Too far from graduation => `SKIP`.
6. Weak participation/acceleration/velocity expansion => `SKIP` with canonical reason ordering.
7. Existing Pump graduation lifecycle evidence => `SKIP`.
8. Missing execution evidence => `SKIP` without fabricated economics.
9. Insufficient exit capacity => `SKIP`.
10. Non-positive post-cost value => `SKIP`.
11. Entry above maximum acceptable entry => `SKIP`.
12. Execution identity mismatch => fail closed.
13. Invalid policy => fail closed.
14. Identical input => identical output.

## Scope boundary

Expected implementation files are limited to one new FL6.3 evaluator module, Fast Lane module/public re-exports, one FL6.3 Rust test file, this design, and the implementation plan. No state-schema expansion is required unless TDD proves current snapshot evidence insufficient.
