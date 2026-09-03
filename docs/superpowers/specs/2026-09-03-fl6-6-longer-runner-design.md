# FL6.6 Longer-Runner Baseline Design

**Date:** 2026-09-03

## Goal

Implement FL6.6 as the final deterministic Fast Lane baseline required by the FL6 build order:

> Continue holding only while cost/risk-adjusted expected continuation remains favorable; protective exits remain backstops.

FL6.6 evaluates an already-open position and emits only:

- `HOLD`,
- `REDUCE`,
- `SELL`.

It never emits `BUY` or `SKIP`.

## Core economic decision

For an open position, historical entry cost is sunk and must not be charged again when deciding whether to keep holding.

The relevant comparison is:

```text
EXIT NOW
    versus
HOLD THROUGH THE CONTINUATION HORIZON, THEN EXIT
```

Both alternatives must include realistic exit costs. The hold alternative must additionally subtract:

- expected holding/opportunity cost supplied at decision time, and
- an explicit downside-risk penalty.

The baseline therefore does **not** reuse FL3 entry economics as though the position were being bought again.

## Base and scope

Base: sealed FL6.5 merged-main commit `b3e7bc2b99e99c324e86125ef592e16d637f67bd`, proven by fresh merged-main CI run `33739006181`.

Production scope:

```text
crates/shreks-core/src/fast_lane/longer_runner.rs
crates/shreks-core/src/fast_lane/mod.rs
crates/shreks-core/src/lib.rs
```

Tests:

```text
crates/shreks-core/tests/fl6_longer_runner.rs
```

No provider, storage, observer/runtime, PAPER execution, position sizing, risk authority, signer, submission, deployment, secret, or LIVE-authority change belongs in FL6.6.

## Forecast boundary

The longer-runner baseline consumes a caller-supplied point-in-time **expected continuation forecast**. It does not train or infer a forecast inside this module.

This is deliberate:

- Rust owns latency-sensitive Fast Lane action evaluation.
- Research/training remains outside the evaluator.
- The input carries an explicit source-version string so replay can identify the deterministic forecast family that produced it.
- Future-path and counterfactual labels are forbidden inside the evaluator.

No production forecast or threshold defaults are introduced in FL6.6.

## Public contract

### Versions

```rust
pub const LONGER_RUNNER_EVIDENCE_VERSION: u16 = 1;
pub const LONGER_RUNNER_BASELINE_VERSION: u16 = 1;
```

### `LongerRunnerProtectiveState`

Protective exits remain explicit backstops:

```rust
pub struct LongerRunnerProtectiveState {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub hard_stop_triggered: bool,
    pub risk_limit_exit_required: bool,
    pub liquidity_exit_required: bool,
}
```

Any true flag forces `SELL` regardless of favorable continuation economics.

This structure does not define the upstream stop/risk/liquidity policy. It only ensures the longer-runner baseline cannot override an already-triggered protective exit.

### `LongerRunnerContinuationEvidence`

```rust
pub struct LongerRunnerContinuationEvidence {
    pub version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub forecast_source_version: String,
    pub forecast_horizon_ms: u64,
    pub base_quantity: f64,
    pub current_executable_exit_price_quote: f64,
    pub expected_future_exit_price_quote: f64,
    pub downside_exit_price_quote: f64,
    pub current_exit_capacity_base: f64,
    pub expected_future_exit_capacity_base: f64,
    pub expected_holding_cost_quote: f64,
    pub current_exit_costs: ExecutionLegCostInput,
    pub future_exit_costs: ExecutionLegCostInput,
}
```

All prices and quantities are point-in-time caller-supplied inputs. `expected_future_exit_price_quote` is the forecast expected exit price at the configured horizon; `downside_exit_price_quote` is the explicit adverse scenario used by the risk penalty.

`expected_holding_cost_quote` may include opportunity/carry costs chosen by the caller’s approved policy. It is finite and non-negative.

The current and future exit capacities must be positive. Capacity smaller than the intended base quantity is valid adverse evidence, not malformed input.

### `LongerRunnerPolicy`

```rust
pub struct LongerRunnerPolicy {
    pub version: u16,
    pub downside_risk_weight: f64,
    pub min_risk_adjusted_continuation_bps_for_hold: f64,
    pub max_risk_adjusted_continuation_bps_for_sell: f64,
}
```

Validation:

- version == `LONGER_RUNNER_BASELINE_VERSION`;
- downside risk weight finite and non-negative;
- hold threshold finite;
- sell threshold finite;
- sell threshold <= hold threshold.

No default policy instance exists.

## Exit-cost calculation

FL6.6 uses `ExecutionLegCostInput` but only for exit legs.

For each exit scenario:

```text
variable_bps = fee + impact + slippage + latency
fixed_quote = network + priority + expected failure cost
net_exit_quote = base_quantity * price * (1 - variable_bps / 10_000) - fixed_quote
```

Validation mirrors FL3 execution-economics rules:

- each component bps <= 10,000;
- combined variable exit bps < 10,000;
- all fixed costs finite and non-negative;
- resulting values finite.

The same future exit-cost assumptions are applied to expected and downside future exits.

## Derived continuation economics

Let:

```text
current_gross_exit_quote = base_quantity * current_exit_price
current_net_exit_quote = net after current exit costs
expected_future_net_exit_quote = net after future exit costs
downside_future_net_exit_quote = net after future exit costs
```

Then:

```text
gross_expected_continuation_quote =
    expected_future_net_exit_quote
    - current_net_exit_quote
    - expected_holding_cost_quote
```

The downside loss relative to exiting now is:

```text
downside_loss_quote = max(
    current_net_exit_quote - downside_future_net_exit_quote,
    0
)
```

Risk penalty:

```text
risk_penalty_quote = downside_loss_quote * downside_risk_weight
```

Risk-adjusted continuation:

```text
risk_adjusted_continuation_quote =
    gross_expected_continuation_quote - risk_penalty_quote
```

Normalize against current **gross** exit value, which is always positive for valid price/quantity inputs:

```text
risk_adjusted_continuation_bps =
    risk_adjusted_continuation_quote
    / current_gross_exit_quote
    * 10_000
```

This metric is an auditable economic margin, not a probability of profit.

## Capacity semantics

A full-position continuation forecast is only favorable if both alternatives remain executable for the intended base quantity.

- current exit capacity < position quantity => `SELL` with explicit current-capacity reason;
- expected future exit capacity < position quantity => `SELL` with explicit future-capacity reason.

The downstream execution layer may still only be able to sell available capacity; this baseline is advisory and does not size or submit transactions.

## Missing evidence

If no continuation evidence is available and no protective exit has triggered:

- action = `REDUCE`;
- reason includes `ContinuationEvidenceUnavailable`.

Missing forecast evidence can never justify `HOLD`, because the build-order requirement is to continue holding **only while** cost/risk-adjusted expected continuation remains favorable.

A protective trigger can still force `SELL` even when continuation evidence is missing.

## Deterministic action precedence

### 1. Protective backstop => `SELL`

Any protective flag wins immediately:

- hard stop,
- risk-limit exit,
- liquidity exit.

### 2. Capacity failure => `SELL`

If current or expected future full-position exit capacity is insufficient, continuation is not treated as favorable.

### 3. Risk-adjusted continuation <= sell threshold => `SELL`

Strongly unfavorable expected continuation produces `SELL`.

### 4. Risk-adjusted continuation >= hold threshold => `HOLD`

Only sufficiently favorable cost/risk-adjusted expected continuation earns `HOLD`.

### 5. Otherwise => `REDUCE`

Marginal continuation between sell and hold thresholds yields `REDUCE`.

This creates a deterministic deadband between full continuation and full exit.

## Stable reasons

`LongerRunnerReason` includes canonical audit reasons for:

- continuation evidence unavailable,
- hard stop triggered,
- risk-limit exit required,
- liquidity exit required,
- current exit capacity insufficient,
- future exit capacity insufficient,
- continuation at/above hold threshold,
- continuation at/below sell threshold,
- continuation between thresholds,
- hold conditions met,
- reduce conditions met,
- sell conditions met.

Reasons are emitted in fixed canonical order.

## Assessment output

`LongerRunnerAssessment` retains:

- version and policy version,
- market/as-of,
- action and ordered reasons,
- evidence version/source/horizon when available,
- base quantity,
- current gross exit quote,
- current net exit quote,
- expected future net exit quote,
- downside future net exit quote,
- expected holding cost quote,
- downside loss quote,
- risk penalty quote,
- gross expected continuation quote,
- risk-adjusted continuation quote,
- risk-adjusted continuation bps,
- current/future capacity.

Protective-only or missing-evidence assessments leave continuation-economic fields `None` rather than fabricating zeros.

## Error handling

`LongerRunnerError` fails closed on structural contradictions:

- invalid policy,
- invalid snapshot timestamp,
- protective market mismatch,
- protective timestamp mismatch,
- invalid continuation evidence/version/source/numeric state,
- continuation market mismatch,
- continuation timestamp mismatch,
- invalid exit-cost components or arithmetic.

Capacity shortfall is not an error; it is valid adverse evidence and produces `SELL`.

## Leakage and determinism

The evaluator must not read:

- wall clock,
- providers,
- databases,
- Python process state,
- future-path labels,
- counterfactual labels,
- randomness,
- mutable globals.

Identical validated inputs must produce identical output and reason order.

## TDD proof requirements

Tests must prove at minimum:

1. favorable net continuation => `HOLD`;
2. marginal continuation => `REDUCE`;
3. unfavorable continuation => `SELL`;
4. hard stop overrides highly favorable continuation => `SELL`;
5. risk-limit exit overrides favorable continuation => `SELL`;
6. liquidity exit overrides favorable continuation => `SELL`;
7. missing continuation evidence => `REDUCE`, never `HOLD`;
8. protective trigger with missing evidence => `SELL`;
9. insufficient current capacity => `SELL`;
10. insufficient future capacity => `SELL`;
11. expected exit costs and holding cost can turn superficially positive price continuation into REDUCE/SELL;
12. downside-risk penalty can turn gross-positive continuation into REDUCE/SELL;
13. market/timestamp contradictions fail closed;
14. NaN/non-finite or invalid cost state fails closed;
15. no representative scenario emits `BUY` or `SKIP`;
16. identical input produces identical output/reason order.

## FL6 exit criterion

When FL6.6 is sealed, FL6 contains independently measurable deterministic baseline families capable of emitting the full action vocabulary without ML:

- entry families: `BUY / SKIP`,
- continuation/exit families: `HOLD / REDUCE / SELL`.

The FL6 exit criterion is then satisfied at the contract/evaluator layer. Profitability remains unproven until later PAPER/shadow evaluation under realistic costs and independent trade samples.

LIVE remains disabled.