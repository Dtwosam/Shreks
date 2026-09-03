# FL9 Learned Continuous Action Policy — Design

## Status and base

Approved for autonomous implementation under the canonical build order.

Base: SEALED FL8.6 merged-main `ffcc87a38ae9484e4cc050a105ab4068801f0c34` with merged-main four-gate GREEN CI `33808678017`.

## Goal

Use the approved learned forecast champion to choose the currently applicable `BUY`, `SKIP`, `HOLD`, `REDUCE`, or `SELL` action with the highest explicit risk-adjusted expected value, subject to hard execution/risk constraints.

FL9 must compare applicable actions, dynamically reevaluate horizon, reduce exposure under uncertainty where warranted, and never silently retrain/promote itself. It is a pure decision-policy phase. FL10 owns live runtime wiring; FL11 owns independent shadow proof/promotion.

## Source-of-truth objective and honesty boundary

The master source asks which available action maximizes expected net account growth after costs and risk. V1 cannot truthfully calculate whole-account growth without full account/risk-allocation state, so FL9 uses a narrower auditable comparison score in basis points of normalized exposure. It is not presented as guaranteed PnL, calibrated utility, or Kelly-optimal account growth.

## Existing contracts reused

FL9 reuses:

- `FastLaneAction::{Buy, Skip, Hold, Reduce, Sell}` from FL6;
- `FastForecastPrediction` and exact target/horizon semantics from SEALED FL8.6;
- forecast targets:
  - `endpoint_cost_adjusted_return_bps`;
  - `endpoint_return_bps`;
  - `mae_bps`;
  - `reversal_occurred`;
  - `route_unavailability_observed`;
- caller-supplied point-in-time execution/risk evidence;
- FL5 counterfactual outcomes only after decisions for evaluation/proof, never as runtime policy input.

No parallel action enum is created.

## Critical entry-versus-open economics distinction

FL4 defines `endpoint_cost_adjusted_return_bps` as future executable exit net quote relative to **entry total quote**. It therefore includes the entry leg.

That target is appropriate for a new `BUY`, because the entry cost has not yet been paid.

It is not appropriate as the direct continuation reward for an already-open position, because its entry cost is sunk. Using it for `HOLD/REDUCE/SELL` would systematically double-charge the entry leg.

Therefore:

- flat `BUY` comparison uses `endpoint_cost_adjusted_return_bps`;
- open-position continuation uses `endpoint_return_bps` minus current caller-supplied expected future exit cost;
- immediate `REDUCE` and `SELL` candidates explicitly subtract current caller-supplied execution costs.

This makes the action comparison cost-aware without duplicating FL3 internals or pretending historical entry costs are still avoidable.

## Rust placement

Add `crates/shreks-core/src/fast_lane/action_policy.rs` and update `fast_lane/mod.rs` plus crate-root `lib.rs`. No new Rust dependency is required.

## Why policy consumes forecasts rather than live state

FL9 consumes point-in-time forecast predictions plus explicit current constraints. FL10 later wires live Fast Lane state, loaded champion inference, execution economics, and preserved risk systems into these inputs. This keeps policy math deterministic/replayable and excludes provider/storage/runtime concerns.

## Required forecast evidence per horizon

A configured horizon is complete only when exactly one prediction exists for each of five targets:

1. `endpoint_cost_adjusted_return_bps` — all-in reward for a prospective new entry;
2. `endpoint_return_bps` — raw future price return used for already-open continuation economics;
3. `mae_bps` — adverse excursion; V1 uses `max(0, -mae_bps)` as downside magnitude;
4. `reversal_occurred` — probability in `[0,1]`;
5. `route_unavailability_observed` — probability in `[0,1]`.

Predictions group by exact `horizon_ms`. Missing targets never borrow from a neighboring horizon. Duplicate target/horizon predictions fail closed.

## Forecast-set contract

`FastActionForecastSet` fields:

- `champion_version: String`;
- `champion_fingerprint_sha256: String`;
- `predictions: Vec<FastForecastPrediction>`.

Rules: non-empty champion version; lowercase 64-char SHA-256 fingerprint; non-empty predictions; no duplicate `(target,horizon)`; finite values; binary probabilities within `[0,1]`; non-empty prediction model versions.

The policy records champion identity but cannot load, mutate, rank, retrain, or promote it.

## Policy configuration

`FastContinuousActionPolicy` fields:

- `version: u16`, exactly `CONTINUOUS_ACTION_POLICY_VERSION`;
- `horizons_ms: Vec<u64>` sorted, unique, non-empty, positive;
- `entry_exposure_candidates: Vec<f64>` sorted unique in `(0,1]`, non-empty;
- `reduce_target_exposure_candidates: Vec<f64>` sorted unique in `(0,1)`; may be empty only when missing-forecast safe action is `SELL`;
- non-negative finite weights:
  - `adverse_excursion_weight`;
  - `reversal_penalty_bps`;
  - `route_unavailability_penalty_bps`;
  - `horizon_disagreement_weight`;
- non-negative finite thresholds:
  - `minimum_buy_value_bps`;
  - `minimum_hold_value_bps`;
- `missing_forecast_open_action: FastLaneAction`, restricted to `REDUCE` or `SELL`.

These are immutable caller configuration, not self-tuning weights.

## Current execution/risk evidence

### `FastReduceExecutionCost`

Exact current reduction evidence for one configured target exposure:

- `target_exposure_fraction: f64` in `(0,1)`;
- `execution_cost_bps: f64 >= 0`, finite.

The vector of reduction costs must be sorted and unique by target exposure. Presence means that exact reduction target is currently executable; absence means it is not a legal reduction candidate. This allows size-specific reduction economics instead of one global boolean.

### `FastActionConstraints`

Fields:

- `max_exposure_fraction: f64` in `[0,1]`;
- `buy_economically_allowed: bool`;
- `expected_future_exit_cost_bps: f64 >= 0`, finite;
- `reduce_execution_costs: Vec<FastReduceExecutionCost>`;
- `sell_executable: bool`;
- `sell_now_cost_bps: f64 >= 0`, finite;
- `force_sell: bool`.

The caller derives these from the current execution/risk layers. FL9 never fabricates an executable route or substitutes missing execution cost with zero.

Hard constraints dominate learned value:

- open `force_sell` requires `SELL` when executable;
- `force_sell` with unavailable sell is a fail-closed error;
- flat buy veto or zero cap cannot BUY;
- open exposure above max cannot HOLD;
- REDUCE is legal only for an exact configured target that also has current execution-cost evidence;
- SELL is legal only when currently executable.

## Position state

`FastActionPositionState` is either:

- `Flat`;
- `Open { current_exposure_fraction: f64 }`, requiring `(0,1]`.

Exposure is normalized policy/risk exposure, not token quantity. FL10 maps real sizing/account state into this boundary.

## Shared horizon risk

For each complete configured horizon:

```text
entry_reward_bps = endpoint_cost_adjusted_return_bps
raw_endpoint_return_bps = endpoint_return_bps
adverse_bps = max(0, -mae_bps)
base_risk_bps =
    adverse_excursion_weight * adverse_bps
    + reversal_penalty_bps * reversal_probability
    + route_unavailability_penalty_bps * route_unavailability_probability
```

Cross-horizon uncertainty uses raw endpoint-return disagreement so it is not distorted by whether a candidate is flat/open:

```text
disagreement_bps = max(raw_endpoint_return_bps) - min(raw_endpoint_return_bps)
risk_bps = base_risk_bps + horizon_disagreement_weight * disagreement_bps
```

This is an explicit uncertainty proxy, not a statistical confidence claim; FL8.4 remains authoritative calibration measurement.

## Flat BUY/SKIP value

For target exposure `e`:

```text
buy_value_bps(h,e) = e * entry_reward_bps(h) - e^2 * risk_bps(h)
skip_value_bps = 0
```

BUY candidates require `buy_economically_allowed`, `e <= max_exposure_fraction`, complete horizon evidence, and `buy_value_bps >= minimum_buy_value_bps`. SKIP is always legal.

Quadratic risk allows high-risk/uncertain forecasts to rationally select a smaller configured entry exposure.

## Open HOLD/REDUCE/SELL value

For current exposure `c`, target retained exposure `e`, and current expected future exit cost `x`:

```text
open_reward_bps(h) = raw_endpoint_return_bps(h) - expected_future_exit_cost_bps
retained_value_bps(h,e) = e * open_reward_bps(h) - e^2 * risk_bps(h)
```

HOLD at current exposure `c`:

```text
hold_value_bps(h) = retained_value_bps(h,c)
```

HOLD is legal only when `c <= max_exposure_fraction`; it is eligible for selection only when value is at least `minimum_hold_value_bps`.

REDUCE from `c` to configured target `r` with exact current execution cost `k_r`:

```text
reduced_fraction = c - r
reduce_value_bps(h,r) =
    retained_value_bps(h,r)
    - reduced_fraction * k_r
```

Only `0 < r < c`, `r <= max_exposure_fraction`, and exact matching current reduction-cost evidence are legal.

SELL now:

```text
sell_value_bps = -c * sell_now_cost_bps
```

SELL has target exposure zero and no selected forecast horizon. It is legal only when `sell_executable`.

These values compare incremental action economics from the current marked state. Sunk entry PnL/cost is intentionally excluded because it is common to all current choices and cannot be recovered by changing the action now.

## Dynamic horizon and exposure

Every call evaluates every complete configured horizon. No horizon is fixed at entry. A new forecast set can change selected horizon, action, and target exposure without mutating policy weights.

## Deterministic selection

Candidates record an `eligible` flag. Selection considers eligible legal candidates only.

Tie-breaking:

1. higher comparison value;
2. lower target exposure;
3. shorter horizon (`None` immediate actions sort before forecast horizons only after value/exposure ties);
4. lexical `FastLaneAction::as_str()`.

Equal-value ties therefore never silently prefer more exposure.

## Missing/incomplete forecasts

If no configured horizon has all five required targets:

- flat state returns `SKIP` with `ForecastEvidenceIncomplete`;
- open state follows explicit `missing_forecast_open_action`:
  - `REDUCE`: choose the **largest** configured/executable target exposure below current exposure and within max cap (least aggressive reduction that still de-risks), recording its current execution cost;
  - `SELL`: require executable sell;
- if the configured safe action cannot execute, return a fail-closed error rather than inventing HOLD.

Missing learned evidence never becomes zero reward/risk.

## Audit output

`FastHorizonActionEvidence` records per complete horizon:

- horizon;
- five model versions;
- entry cost-adjusted reward;
- raw endpoint return;
- MAE/adverse magnitude;
- reversal/route probabilities;
- disagreement and total risk.

`FastActionCandidateAssessment` records:

- action;
- optional horizon;
- target exposure;
- reward;
- risk;
- immediate execution-cost penalty;
- comparison value;
- eligibility.

`FastContinuousActionAssessment` records:

- policy version;
- champion version/fingerprint;
- position state;
- selected action/reason/horizon;
- current and target exposure;
- selected reward/risk/execution-cost/value;
- canonical horizon evidence;
- canonical candidate assessments.

## Public API

Export:

```text
CONTINUOUS_ACTION_POLICY_VERSION
FastActionForecastSet
FastContinuousActionPolicy
FastReduceExecutionCost
FastActionConstraints
FastActionPositionState
FastHorizonActionEvidence
FastActionCandidateAssessment
FastContinuousActionAssessment
FastContinuousActionReason
FastContinuousActionError
assess_continuous_action
```

Reuse existing `FastLaneAction`, `FastForecastPrediction`, and `FastForecastTarget`. No train/promote/execute/submit/live API is added.

## Counterfactual evaluation boundary

FL5 future outcomes are evaluation evidence only. Production Rust must not import/consume them. A later evaluation may join recorded FL9 decisions to matured executable outcomes after the decision timestamp to measure selected-action economics, regret, action distribution, uncertainty behavior, and comparison with deterministic baselines.

Fixture tests do not prove edge.

## Authority firewall

Production `action_policy.rs` must not contain/import providers/network, storage/SQLite/filesystem, wall-clock/randomness/environment, FL4 labels/FL5 counterfactuals, training/Python, PAPER executor/ledger writes, `TradeIntent`, signer/submission, registry/promotion, or LIVE/runtime-mode enablement.

It is a pure function over caller-supplied point-in-time values.

## Determinism

Equivalent policy, forecast set, position, and constraints produce exactly equal assessment values/order. No current time, randomness, mutable cache, I/O, or environment enters the function.

## TDD and seal procedure

1. design;
2. plan;
3. Rust RED contracts before `action_policy.rs` exists;
4. intentional compile RED while unrelated suites remain green;
5. minimal implementation + authority test;
6. four-gate candidate GREEN;
7. scope audit;
8. clean history `design -> plan -> consolidated RED -> implementation` preserving exact verified tree;
9. fresh clean-head four-gate GREEN;
10. guarded merge;
11. merged-main four-gate GREEN.

The implementation merge does **not** itself satisfy FL9's economic exit criterion. Full FL9 proof requires independent PAPER/shadow evidence that the approved champion+policy beats the best deterministic baseline under realistic costs/risk. Without that evidence, record the policy implementation as sealed but economic exit pending, and do not manufacture an edge claim.

LIVE remains disabled.