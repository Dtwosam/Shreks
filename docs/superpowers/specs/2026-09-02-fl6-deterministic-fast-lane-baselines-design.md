# FL6 Deterministic Fast Lane Baselines Design

**Base proof:** `2b03514ad95b95a98baa2e4a1ff0f6c6e14aaf35` (FL5 merged-main four-gate GREEN)

## Goal

Build simple, interpretable Fast Lane strategies that can be replayed, measured, and later beaten by learned challengers. FL6 starts with the **Impulse Scalp** entry baseline and then adds the remaining deterministic baseline families without granting capital authority.

The first implementation unit is FL6.1 only. It consumes point-in-time `FastMarketSnapshot` state plus explicit execution-economics inputs and emits an auditable `BUY` or `SKIP` research/strategy assessment. It does not create a `TradeIntent`, size capital, call PAPER, sign, submit, or enable LIVE.

## Ownership boundary

The current source of truth allows latency-sensitive approved strategy evaluation in Rust. Therefore FL6.1 lives in `shreks-core::fast_lane` beside the already-proven rolling state, exit-capacity, and execution-economics contracts.

Python remains the research/training/evaluation plane. FL6 Rust output is deterministic baseline evidence suitable for replay and later comparison; it is not a live-money authority.

## Why the first baseline is narrow

FL6 contains several families. Do not build them all into one scorer. Each family must be independently measurable and disableable.

FL6.1 answers one question:

> Given a current Fast Lane snapshot and explicit executable economics for a proposed size/forecast, does a short continuation impulse meet this baseline's configured flow/path conditions strongly enough to classify the opportunity as BUY rather than SKIP?

It does not claim profitability and does not choose portfolio size.

## Inputs

### `FastMarketSnapshot`

Use the existing canonical point-in-time snapshot and configured rolling windows. FL6.1 consumes only information already present at `snapshot.as_of_unix_ms`.

The first baseline uses:

- buy count,
- unique buy actors,
- count imbalance,
- quote-flow imbalance,
- quote-flow velocity,
- quote-flow acceleration,
- recovery from local low,
- drawdown from local high,
- a shorter signal window and a longer context window.

The signal window must be strictly shorter than the context window. Exact window lengths are policy, not hard-coded trading law.

### Explicit execution input

Execution economics must remain separate from observed trade prices. The caller may provide a versioned execution input containing:

- market identity,
- action timestamp,
- `ExecutionCostModel`,
- `ExecutionTradeInput` with intended quantity, executable entry price, explicit forecast exit price, exit capacity, required edge, and risk margin.

The existing `ExecutionEconomics::assess` remains authoritative for round-trip economics and maximum acceptable entry price.

If execution evidence is unavailable, FL6.1 returns `SKIP`; it does not replace missing costs/capacity with zero.

Contradictory market/timestamp identity or malformed numeric/model input fails closed with a baseline error.

## Policy

`ImpulseScalpPolicy` is explicit and versioned. There is **no production default instance**.

Version 1 configures at least:

- signal window,
- context window,
- minimum buy count,
- minimum unique buyers,
- minimum positive count imbalance,
- minimum positive quote-flow imbalance,
- minimum positive quote-flow velocity,
- minimum positive quote-flow acceleration,
- minimum signal-vs-context velocity expansion ratio,
- minimum recovery from the local low,
- maximum drawdown from the local high.

Thresholds are hypotheses for replay. They are not claims of edge.

Policy validation rejects:

- zero version/windows,
- signal window >= context window,
- zero required buyer counts,
- non-finite thresholds,
- imbalance thresholds outside `[0, 1]`,
- non-positive velocity/acceleration/expansion thresholds,
- negative recovery threshold,
- drawdown threshold outside `[0, 1]`.

## Signal semantics

The baseline evaluates conditions independently and records stable reasons in canonical order.

A BUY requires all configured signal conditions:

1. both configured windows exist in the snapshot,
2. signal buy count meets the threshold,
3. independently observed buy actors meet the threshold,
4. count imbalance meets the threshold,
5. quote-flow imbalance meets the threshold,
6. quote-flow velocity meets the threshold,
7. quote-flow acceleration meets the threshold,
8. signal velocity is at least `context_velocity * min_velocity_expansion_ratio`,
9. local-low recovery meets the threshold,
10. local-high drawdown stays within the ceiling.

This intentionally combines participation, directional flow, acceleration, and current path position rather than using one raw pump metric.

## Execution semantics

Signal strength never bypasses economics.

For valid execution input:

- insufficient exit capacity for intended quantity -> `SKIP`,
- non-positive forecast net PnL after costs -> `SKIP`,
- executable entry price above `maximum_acceptable_entry_price_quote` -> `SKIP`,
- otherwise economics passes.

The maximum acceptable entry price is retained in the assessment so a later PAPER/runtime layer can abort rather than chase. FL6.1 itself does not submit anything.

`ExecutionEconomicsError::InsufficientExitCapacity` is a normal tradeability `SKIP` reason. Malformed/contradictory economics inputs remain errors, because treating bad evidence as an ordinary weak signal would hide a data defect.

## Output

Version 1 exposes a stable action enum containing the eventual Fast Lane action vocabulary:

- `BUY`
- `SKIP`
- `HOLD`
- `REDUCE`
- `SELL`

FL6.1 emits only `BUY` or `SKIP` because it evaluates a flat-position entry opportunity. Later FL6 units may reuse the action vocabulary for open-position baselines.

`ImpulseScalpAssessment` retains at least:

- assessment/baseline version,
- policy version,
- market identity,
- as-of timestamp,
- action,
- canonical reasons,
- signal/context window identities,
- intended quantity when known,
- executable entry price when known,
- explicit forecast exit price when known,
- exit capacity when known,
- forecast net PnL when computable,
- break-even move when computable,
- maximum acceptable entry price when computable.

No autonomous ranking or strategy arbitration is introduced in FL6.1.

## Determinism and point-in-time safety

For the same validated snapshot, policy, and execution input, FL6.1 must return the same assessment and reason ordering.

No wall clock, provider call, SQLite read, future-path label, counterfactual label, random number, or mutable global state is allowed inside the pure evaluator.

FL4/FL5 future outcomes are training/evaluation targets only and must never enter the FL6.1 decision input.

## TDD / proof requirements

Required RED/GREEN coverage for FL6.1:

1. strong short-window impulse plus valid positive economics produces `BUY`,
2. each weak flow/path condition produces `SKIP` with stable reason(s),
3. signal velocity must expand versus the context window,
4. missing execution evidence produces `SKIP` without zero-filled economics,
5. insufficient exit capacity produces `SKIP`,
6. non-positive post-cost forecast economics produces `SKIP`,
7. executable entry above the computed maximum acceptable entry price produces `SKIP`,
8. market/timestamp mismatch fails closed,
9. invalid policy/economic numerics fail closed,
10. repeated identical inputs produce identical assessments/reason ordering,
11. no strategy/PAPER/risk/signer/submission/provider/deployment/LIVE authority changes.

Each implementation head must pass the canonical four gates:

- Repository safety,
- Rust workspace,
- Python suite,
- native ARM64 release build + bundle verification.

## FL6.1 exit criterion

FL6.1 is complete when Shreks can deterministically classify a flat-position impulse opportunity as BUY or SKIP from point-in-time Fast Lane flow/path state plus explicit execution economics, retaining a maximum acceptable entry boundary and auditable reasons, with no capital authority.

FL6 as a whole remains open until the additional deterministic families in the build order are implemented and independently measurable.