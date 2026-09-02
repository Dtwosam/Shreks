# FL6.2 Micro Pullback / Reclaim Baseline Design

**Base proof:** `b13a6898e6c1382f6900cfdb8a8eb068694fdc7c` (FL6.1 merged-main four-gate GREEN, run `33690287679`)

## Goal

Add the second independently measurable deterministic Fast Lane baseline: **Micro Pullback / Reclaim**.

FL6.2 detects a point-in-time sequence of:

`impulse -> controlled pullback -> reclaim with seller exhaustion / renewed demand`

and combines that structure with the existing explicit execution-economics contract before emitting `BUY` or `SKIP`.

FL6.2 is strategy/research evidence only. It does not size capital, create a `TradeIntent`, execute PAPER, sign, submit, alter provider topology, deploy services, or enable LIVE.

## Source-of-truth alignment

The master source of truth defines Micro Pullback / Reclaim as entering after an impulse retraces and sellers weaken while demand reappears, with entry based on favorable structure/executability rather than a token score.

The observer/build-order requirements also call for point-in-time path summaries including rolling/local highs and lows plus time of peak/trough. The current `FastWindowSummary` stores high/low prices but not enough ordering information to prove that the high occurred before the pullback trough. FL6.2 must not infer that sequence from unordered extrema.

Therefore the smallest required foundation change is to make peak/trough ordering explicit in the existing Fast Lane rolling state.

## Foundation extension: ordered path evidence

Extend `FastWindowSummary` with deterministic point-in-time path identity:

- `local_high_sequence: Option<u64>`
- `local_high_observed_at_unix_ms: Option<i64>`
- `local_low_sequence: Option<u64>`
- `local_low_observed_at_unix_ms: Option<i64>`
- `post_high_low_price_quote: Option<f64>`
- `post_high_low_sequence: Option<u64>`
- `post_high_low_observed_at_unix_ms: Option<i64>`

Semantics:

1. `local_high_*` identifies the first event that established the final maximum price in the window.
2. `local_low_*` identifies the first event that established the final minimum price in the window.
3. `post_high_low_*` identifies the lowest price observed **after the current local high was established**.
4. If a later strictly higher high occurs, the post-high trough evidence resets because the relevant impulse peak changed.
5. Equal-price retests do not rewrite the original extrema identity.
6. All fields are derived only from events already admitted into the point-in-time window; no future data or wall clock is used.

This lets FL6.2 require an auditable ordering such as:

`pre-impulse local low sequence < impulse high sequence < post-high trough sequence < latest sequence`

rather than guessing order from high/low values alone.

## FL6.2 inputs

### `FastMarketSnapshot`

Use one longer **structure window** and one shorter **reclaim window**.

The structure window supplies:

- pre-impulse local low,
- impulse local high,
- post-high trough,
- current/last price,
- event ordering needed to prove the sequence.

The reclaim window supplies current demand/seller behavior:

- buy count,
- unique buy actors,
- buy arrival rate,
- sell arrival rate,
- count imbalance,
- quote-flow imbalance,
- quote-flow velocity,
- quote-flow acceleration.

Exact window sizes are policy inputs and are not hard-coded trading law. The reclaim window must be strictly shorter than the structure window.

### Explicit execution input

FL6.2 uses its own small input wrapper with:

- market identity,
- as-of timestamp,
- existing `ExecutionCostModel`,
- existing `ExecutionTradeInput`.

Observed trade prices never become assumed executable fills. Missing execution evidence produces `SKIP`, not zero-filled costs.

Market/timestamp contradictions or malformed economics fail closed as errors.

## Derived structure metrics

When the ordered path is available, compute:

### Impulse move

`(local_high - pre_impulse_local_low) / pre_impulse_local_low`

This is valid only when `local_low_sequence < local_high_sequence`.

### Pullback depth

`(local_high - post_high_low) / local_high`

This is valid only when the post-high trough occurs after the high.

### Reclaim fraction

`(last_price - post_high_low) / (local_high - post_high_low)`

This expresses how much of the pullback has been reclaimed. It is valid only when the pullback range is positive and the current event occurs after the trough.

These are point-in-time path descriptors, not forecasts.

## Policy

`MicroPullbackPolicy` is explicit and versioned. There is no production default instance.

Version 1 configures:

- `reclaim_window_ms`
- `structure_window_ms`
- minimum impulse move fraction,
- minimum pullback depth fraction,
- maximum pullback depth fraction,
- minimum reclaim fraction,
- minimum reclaim buy count,
- minimum reclaim unique buy actors,
- minimum reclaim buy-arrival rate,
- maximum reclaim sell-arrival rate,
- minimum reclaim count imbalance,
- minimum reclaim quote-flow imbalance,
- minimum reclaim quote-flow velocity,
- minimum reclaim quote-flow acceleration.

Policy validation rejects:

- unsupported/zero version,
- zero windows,
- reclaim window >= structure window,
- zero required counts,
- non-finite thresholds,
- non-positive required impulse/velocity/buy-arrival values,
- negative sell-arrival ceiling,
- fractions outside `[0, 1]`,
- minimum pullback depth greater than maximum pullback depth.

Thresholds remain replay hypotheses, not claims of edge.

## Signal semantics

A `BUY` requires all conditions below.

### Ordered structure

1. both configured windows exist,
2. structure high/low/trough evidence is complete,
3. pre-impulse local low occurs before the local high,
4. post-high trough occurs after the local high,
5. the latest event occurs after the trough,
6. impulse move meets the minimum,
7. pullback depth is not too shallow,
8. pullback depth is not too deep,
9. current price has reclaimed at least the configured fraction of the pullback.

### Seller exhaustion / demand return

10. reclaim-window buy count meets the minimum,
11. reclaim-window unique buyers meet the minimum,
12. reclaim-window buy arrival rate meets the minimum,
13. reclaim-window sell arrival rate stays below the configured ceiling,
14. reclaim-window count imbalance is sufficiently positive,
15. reclaim-window quote-flow imbalance is sufficiently positive,
16. reclaim-window quote-flow velocity is sufficiently positive,
17. reclaim-window quote-flow acceleration meets the configured positive threshold.

The seller-exhaustion claim in V1 is deliberately narrow: after a proven pullback, **recent** seller arrival must be low while recent buy participation and net flow have turned positive. FL6.2 does not pretend the current rolling summary can reconstruct every individual pullback sell phase.

## Execution semantics

Signal quality never bypasses tradeability.

With valid execution evidence:

- insufficient exit capacity -> `SKIP`,
- non-positive post-cost forecast PnL -> `SKIP`,
- executable entry above `maximum_acceptable_entry_price_quote` -> `SKIP`,
- otherwise execution economics passes.

The assessment retains the maximum acceptable entry price so a later event-resolution PAPER/runtime layer can abort rather than chase.

`ExecutionEconomicsError::InsufficientExitCapacity` is a normal `SKIP` reason. Other malformed economics errors remain hard errors.

## Output

Add:

- `MicroPullbackPolicy`
- `MicroPullbackExecutionInput`
- `MicroPullbackReason`
- `MicroPullbackAssessment`
- `assess_micro_pullback(...)`
- `MICRO_PULLBACK_BASELINE_VERSION = 1`

Reuse the existing `FastLaneAction` vocabulary. FL6.2 emits only `BUY` or `SKIP` because it evaluates a flat-position entry opportunity.

The assessment retains:

- baseline/policy version,
- market and as-of identity,
- action and canonical reasons,
- reclaim/structure window identities,
- derived impulse move,
- derived pullback depth,
- derived reclaim fraction,
- available intended quantity,
- executable entry price,
- forecast exit price,
- exit capacity,
- forecast net PnL,
- break-even move,
- maximum acceptable entry price.

## Module boundaries

Keep FL6.1 and FL6.2 independently readable.

- Existing FL6.1 implementation remains in `fast_lane/baseline.rs`.
- FL6.2 lives in a new focused `fast_lane/micro_pullback.rs` module.
- Ordered path evidence is added to existing `fast_lane/state.rs` because it is canonical point-in-time state, not strategy-specific state.
- `fast_lane/mod.rs` and root `lib.rs` only re-export the new public API.

Do not expand `baseline.rs` into a multi-strategy giant file.

## Determinism and point-in-time safety

For identical validated snapshot, policy, and execution input, FL6.2 must return identical output and reason ordering.

No provider call, SQLite read, wall clock, randomness, mutable global state, future-path label, or counterfactual label is allowed inside the evaluator.

FL4/FL5 future outcomes remain evaluation/training targets only.

## TDD / proof requirements

### Ordered path foundation

RED/GREEN coverage must prove:

1. peak/trough sequence and observation timestamps are deterministic,
2. post-high trough occurs only after the current high,
3. a new strictly higher high resets post-high trough evidence,
4. equal-price retests do not rewrite extrema identity,
5. replaying the same events yields byte/structurally identical summaries.

### FL6.2 evaluator

RED/GREEN coverage must prove:

1. valid ordered impulse/pullback/reclaim + positive economics -> `BUY`,
2. high-before-low ordering is required,
3. a trough at the latest event is not yet a reclaim,
4. weak impulse -> `SKIP`,
5. too-shallow pullback -> `SKIP`,
6. too-deep pullback -> `SKIP`,
7. insufficient reclaim -> `SKIP`,
8. weak buy participation -> `SKIP`,
9. excessive recent seller arrival -> `SKIP`,
10. weak/negative reclaim flow or acceleration -> `SKIP`,
11. missing execution evidence -> `SKIP` with unknown economic fields,
12. insufficient exit capacity -> `SKIP`,
13. non-positive post-cost forecast -> `SKIP`,
14. executable entry above maximum acceptable price -> `SKIP`,
15. market/timestamp mismatch -> error,
16. invalid policy/economics -> error,
17. repeated identical inputs produce identical assessment/reason ordering,
18. FL6.1 behavior remains green and unchanged.

Every final implementation head must pass:

- Repository safety,
- Rust workspace,
- Python suite,
- native ARM64 release build + bundle verification.

## FL6.2 exit criterion

FL6.2 is complete when Shreks can deterministically prove an ordered impulse/pullback/reclaim structure from point-in-time Fast Lane state, require recent seller exhaustion and renewed demand, combine that evidence with explicit execution economics, and emit auditable `BUY`/`SKIP` assessments with an entry-price boundary and no capital authority.