# FL6.4 Graduation / Migration Flow Baseline Design

**Status:** Approved by standing autonomous-build instruction  
**Phase:** FL6.4 — Deterministic Fast Lane baselines  
**Base:** sealed FL6.3 merged main `cac03c19577942f6049cd504a65a05b059699a7b`

## Goal

Implement an independently measurable deterministic Fast Lane BUY/SKIP baseline for the **Pump bonding-curve -> PumpSwap graduation/migration transition**.

The baseline measures three point-in-time phases without future leakage:

1. **before** — recent Pump bonding-curve flow retained in the Pump-curve Fast Lane snapshot,
2. **during** — one verified `PumpGraduation` lifecycle event on the decision-safe detection clock,
3. **after** — recent PumpSwap flow for the same mint/quote after migration.

It then applies explicit PumpSwap execution economics. Graduation itself is never treated as proof of profit.

## Non-goals

FL6.4 does not:

- create `TradeIntent` objects,
- size capital,
- execute PAPER or LIVE trades,
- sign or submit transactions,
- call providers or read storage,
- consume future-path or counterfactual labels,
- add machine learning,
- hard-code production thresholds,
- treat `can_boost` as an observed BOOST purchase/action,
- change provider/storage/runtime/deployment/risk/signer/LIVE authority.

LIVE remains disabled.

## Cross-venue evidence model

The evaluator receives two point-in-time `FastMarketSnapshot` values at the **same decision timestamp**:

- `pre_snapshot`: `VenueId::PumpFunBondingCurve`,
- `post_snapshot`: `VenueId::PumpSwap`.

They must share the same mint and quote mint.

Both snapshots are expected to carry the same verified lifecycle truth when available. The lifecycle event must be:

- `LifecycleEventKind::PumpGraduation`,
- the same mint and quote mint,
- `from_venue = PumpFunBondingCurve`,
- `to_venue = PumpSwap`,
- detected no later than the decision timestamp.

If lifecycle evidence is absent, the baseline SKIPs. Conflicting lifecycle evidence or cross-market/timestamp contradictions fail closed.

The policy supplies `max_graduation_age_ms`; graduation older than this decision window SKIPs rather than being treated as a current migration-flow opportunity.

## Flow measurements

A single explicit `flow_window_ms` is read from both venue snapshots. No production default is supplied.

### Before migration

The Pump-curve window records at least:

- buy count,
- quote-flow velocity.

The baseline can require minimum pre-graduation participation/velocity so the post-migration behavior is compared with a meaningful active launch rather than an empty predecessor.

### After migration

The PumpSwap window can require configurable minimums/maximums for:

- buy count,
- unique buy actors,
- buy arrival rate,
- sell arrival rate ceiling,
- count imbalance,
- quote-flow imbalance,
- quote-flow velocity,
- quote-flow acceleration.

The evaluator also computes:

`post_quote_flow_velocity / pre_quote_flow_velocity`

when the pre velocity is positive. Policy supplies a minimum retention/expansion ratio. If pre velocity is non-positive, the explicit pre-velocity gate fails and no ratio is fabricated.

This keeps the family independent from FL6.1/6.2/6.3 while reusing canonical Fast Lane evidence.

## BOOST context

Authoritative PumpSwap trade economics already exposes `can_boost`, but current `FastReserveContext::PumpSwapPool` intentionally does not copy that provider/source-specific suffix into rolling state.

FL6.4 therefore accepts optional explicit provider-neutral `GraduationBoostContext` containing:

- PumpSwap market identity,
- decision timestamp,
- `can_boost: bool`.

This field is **context only in FL6.4-v1**. It is retained in the assessment for later replay/segmentation, but it does not automatically increase or decrease the trading decision.

This is deliberate: `can_boost` means the current PumpSwap economics say boosting is possible; it is not evidence that a BOOST action occurred or that BOOST flow is profitable. Actual BOOST event/flow logic requires actual observable event evidence and is not fabricated here.

Missing optional BOOST context does not block the baseline. Contradictory BOOST market/timestamp identity fails closed.

## Execution economics

Optional `GraduationFlowExecutionInput` is bound to the post-migration PumpSwap market and the common decision timestamp. It reuses existing:

- `ExecutionCostModel`,
- `ExecutionTradeInput`,
- `ExecutionEconomics::assess`.

Rules:

- missing economics => `SKIP`,
- insufficient exit capacity => `SKIP`,
- non-positive forecast net PnL => `SKIP`,
- executable entry above maximum acceptable entry price => `SKIP`,
- identity contradictions => error,
- malformed economics => fail closed.

No missing cost is zero-filled.

## Public contract

Add a dedicated Rust module exposing:

- `GRADUATION_FLOW_BASELINE_VERSION`,
- `GraduationFlowPolicy`,
- `GraduationBoostContext`,
- `GraduationFlowExecutionInput`,
- `GraduationFlowReason`,
- `GraduationFlowAssessment`,
- `GraduationFlowError`,
- `assess_graduation_flow`.

The shared `FastLaneAction` vocabulary is reused; FL6.4-v1 emits only BUY or SKIP.

## Determinism / leakage boundary

The evaluator is pure over supplied point-in-time snapshots/context/policy. It may not use wall clock, provider calls, DB reads, future labels, counterfactual labels, randomness, or mutable global state.

Identical validated inputs must produce identical semantic output and stable reason ordering.

## Required tests

TDD must prove at least:

1. verified recent migration + active pre-flow + strong post-PumpSwap flow + profitable economics => BUY,
2. missing lifecycle evidence => SKIP,
3. stale graduation => SKIP,
4. wrong pre/post venue or mint/quote mismatch => error,
5. snapshot decision timestamps disagree => error,
6. conflicting lifecycle events => error,
7. weak pre-flow => SKIP,
8. weak post-flow / excessive selling => canonical multi-reason SKIP,
9. low post/pre velocity retention => SKIP,
10. optional `can_boost` true/false is preserved but does not independently flip the decision,
11. BOOST context identity mismatch => error,
12. missing execution economics => SKIP without fabricated outputs,
13. insufficient exit capacity => SKIP,
14. non-positive post-cost value => SKIP,
15. entry above max acceptable entry => SKIP,
16. invalid policy => error,
17. identical inputs => identical output.

## Scope boundary

Expected files are one new FL6.4 evaluator module, Fast Lane/public re-exports, one Rust test file, this design, and an implementation plan. No state schema or provider/storage mutation is expected for v1.
