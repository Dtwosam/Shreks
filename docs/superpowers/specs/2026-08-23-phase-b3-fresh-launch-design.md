# Phase B3 Fresh Launch Continuation Design

**Status:** Approved by standing autonomous-build instruction  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`

## 1. Purpose

Phase B3 implements the first explicit Shreks setup family: **Fresh Launch Continuation**.

The setup is designed for newly launched Solana memecoins, especially candidates discovered through the Pump.fun/PumpSwap lifecycle already observed by Shreks. It intentionally avoids first-second blind sniping. A candidate must survive B1 safety, satisfy minimum executability constraints, and show enough point-in-time participation, flow, momentum, liquidity, and price-structure confirmation before the setup can become `READY`.

B3 does not place trades. It produces an auditable setup assessment that later paper-trading decision logic can consume.

## 2. Profitability Objective

The setup is designed around a simple hypothesis that must later be tested against Shreks' own outcomes:

> very fresh tokens with improving liquidity, sustained transaction participation, buy-heavy recent flow, positive short-term momentum, and price holding near recent highs may have better continuation expectancy than blind launch entries, provided execution quality remains acceptable.

This is a research hypothesis, not a claim of profitability. All thresholds are explicit policy configuration and must later be calibrated on unseen point-in-time outcome data.

B3 avoids two common sources of false paper profitability:

1. entering before enough evidence exists;
2. chasing already-extreme moves simply because momentum is positive.

## 3. Inputs and Dependencies

B3 is a pure Python setup evaluator. It depends only on the stable B2 `FeatureVector` and B1 `SafetyDecision` already embedded in that vector.

It does not:

- query SQLite;
- call providers;
- inspect raw Pump.fun payloads;
- infer missing features;
- use future outcome checkpoints;
- create a position or trade intent.

Package:

```text
python/src/shreks_brain/setups/
  __init__.py
  models.py
  fresh_launch.py
python/tests/
  test_setup_models.py
  test_fresh_launch_setup.py
  test_setup_public_api.py
```

## 4. Stable Setup Types

### `SetupState`

A string enum with exactly:

- `BLOCKED`
- `WATCH`
- `READY`

Semantics:

- `BLOCKED`: a current hard setup/executability condition makes entry consideration invalid at this timestamp.
- `WATCH`: no hard setup blocker is present, but the candidate is too young, evidence is missing, or one or more continuation confirmations are not yet satisfied.
- `READY`: all hard setup gates and all required continuation confirmations pass at this timestamp.

B3 never emits `ENTER`. `READY` means only that this setup is eligible to be considered by later decision/risk/paper-trading layers.

### `FreshLaunchReasonCode`

Stable reason codes, grouped by role.

Hard blockers:

- `SAFETY_NOT_PASS`
- `SETUP_WINDOW_EXPIRED`
- `SOURCE_DATA_TOO_OLD`
- `LIQUIDITY_BELOW_MINIMUM`
- `EXIT_PRICE_IMPACT_TOO_HIGH`
- `MOVE_TOO_EXTENDED`

Watch / confirmation reasons:

- `SETUP_TOO_YOUNG`
- `TOKEN_AGE_UNKNOWN`
- `SOURCE_AGE_UNKNOWN`
- `LIQUIDITY_UNKNOWN`
- `EXIT_PRICE_IMPACT_UNKNOWN`
- `TX_COUNT_M5_UNKNOWN`
- `TX_COUNT_M5_BELOW_MINIMUM`
- `VOLUME_VELOCITY_UNKNOWN`
- `VOLUME_VELOCITY_BELOW_MINIMUM`
- `BUY_FRACTION_M5_UNKNOWN`
- `BUY_FRACTION_M5_BELOW_MINIMUM`
- `BUY_PRESSURE_ACCELERATION_UNKNOWN`
- `BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM`
- `RETURN_1M_UNKNOWN`
- `RETURN_1M_BELOW_MINIMUM`
- `RETURN_5M_UNKNOWN`
- `RETURN_5M_BELOW_MINIMUM`
- `LIQUIDITY_CHANGE_5M_UNKNOWN`
- `LIQUIDITY_CHANGE_5M_BELOW_MINIMUM`
- `DISTANCE_FROM_LOCAL_HIGH_UNKNOWN`
- `TOO_FAR_BELOW_LOCAL_HIGH`
- `RANGE_POSITION_UNKNOWN`
- `RANGE_POSITION_BELOW_MINIMUM`

Ready marker:

- `ALL_CONFIRMATIONS_PASSED`

Reason-code order is deterministic and part of the audit contract.

### `SetupFinding`

Immutable dataclass:

- `code: FreshLaunchReasonCode`
- `message: str`
- `observed_value: float | int | str | None = None`
- `threshold_value: float | int | None = None`

Consumers use `code` for logic; `message` is explanatory only.

## 5. `FreshLaunchPolicy`

Immutable, versioned configuration with no trading defaults embedded in the evaluator:

- `version: str`
- `min_age_seconds: float`
- `max_age_seconds: float`
- `max_source_age_ms: int`
- `min_liquidity_usd: float`
- `max_exit_price_impact_pct: float`
- `max_return_5m_pct: float`
- `min_tx_count_m5: int`
- `min_volume_velocity_ratio: float`
- `min_buy_fraction_m5: float`
- `min_buy_pressure_acceleration: float`
- `min_return_1m_pct: float`
- `min_return_5m_pct: float`
- `min_liquidity_change_5m_pct: float`
- `min_distance_from_local_high_pct: float`
- `min_range_position_pct: float`

Validation:

- version is non-empty;
- numeric values are finite;
- age, source age, liquidity, exit impact, maximum return, transaction count, and volume velocity are non-negative;
- `max_age_seconds > min_age_seconds`;
- `min_buy_fraction_m5` is within `[0, 1]`;
- `min_range_position_pct` is within `[0, 100]`;
- `min_distance_from_local_high_pct <= 0` because B2 defines zero as exactly at the local high;
- `max_return_5m_pct >= min_return_5m_pct`.

The evaluator contains no hard-coded numerical trading thresholds. Tests construct explicit policies. A later calibration/configuration layer will choose production candidate values using Shreks' dataset.

## 6. `FreshLaunchAssessment`

Immutable result:

- `setup_name: str` — exactly `fresh_launch_continuation`
- `policy_version: str`
- `feature_schema_version: str`
- `as_of_unix_ms: int`
- `state: SetupState`
- `confirmation_score: float`
- `confirmations_passed: int`
- `confirmations_required: int`
- `findings: tuple[SetupFinding, ...]`

`confirmation_score` is:

```text
(confirmations_passed / confirmations_required) * 100
```

It measures checklist completeness only. It is not a probability, expected return, or final trade score.

For B3-v1, `confirmations_required` is exactly **9**.

## 7. Evaluation Order

Public function:

```python
def assess_fresh_launch(
    features: FeatureVector,
    policy: FreshLaunchPolicy,
) -> FreshLaunchAssessment:
    ...
```

The function is pure and deterministic.

### 7.1 Hard gates

Hard blockers are evaluated in this fixed order:

1. safety decision is not `PASS` -> `SAFETY_NOT_PASS`;
2. token age is known and above `max_age_seconds` -> `SETUP_WINDOW_EXPIRED`;
3. source age is above `max_source_age_ms` -> `SOURCE_DATA_TOO_OLD`;
4. liquidity is known and below `min_liquidity_usd` -> `LIQUIDITY_BELOW_MINIMUM`;
5. exit price impact is known and above `max_exit_price_impact_pct` -> `EXIT_PRICE_IMPACT_TOO_HIGH`;
6. 5-minute return is known and above `max_return_5m_pct` -> `MOVE_TOO_EXTENDED`.

Any hard blocker makes the state `BLOCKED`, regardless of confirmation score.

Unknown token age, liquidity, or exit impact do not become optimistic passes; they create watch findings in the next stage.

`source_age_ms` is always present in B2 and therefore has no normal unknown case, but the stable reason-code set includes `SOURCE_AGE_UNKNOWN` for future schema compatibility. B3-v1 does not emit it.

### 7.2 Minimum-age gate

If token age is unknown, append `TOKEN_AGE_UNKNOWN`.

If token age is known and below `min_age_seconds`, append `SETUP_TOO_YOUNG`.

Either condition prevents `READY` but is not a hard `BLOCKED` state when no hard blocker exists; the candidate remains `WATCH` because more evidence can arrive later.

### 7.3 Required executability evidence

If liquidity is unknown, append `LIQUIDITY_UNKNOWN`.

If exit price impact is unknown, append `EXIT_PRICE_IMPACT_UNKNOWN`.

These missing fields prevent `READY` and keep the state `WATCH`.

Known values that violate their hard gates were already classified as `BLOCKED`.

### 7.4 Nine continuation confirmations

Each confirmation contributes exactly one point. Missing values count as not passed and generate an `UNKNOWN` finding. Known values that fail generate the matching threshold finding.

The nine confirmations are evaluated in this order:

1. `tx_count_m5 >= min_tx_count_m5`;
2. `volume_velocity_ratio >= min_volume_velocity_ratio`;
3. `buy_fraction_m5 >= min_buy_fraction_m5`;
4. `buy_pressure_acceleration >= min_buy_pressure_acceleration`;
5. `return_1m_pct >= min_return_1m_pct`;
6. `return_5m_pct >= min_return_5m_pct`;
7. `liquidity_change_5m_pct >= min_liquidity_change_5m_pct`;
8. `distance_from_local_high_pct >= min_distance_from_local_high_pct`;
9. `range_position_pct >= min_range_position_pct`.

Boundary equality passes.

B3 does not reward values beyond the threshold with extra score. That is intentional: the initial setup should measure whether a transparent hypothesis is confirmed, not assume that “more momentum” is always better. The explicit `max_return_5m_pct` chase gate handles excessive extension.

## 8. State Resolution

After all findings and confirmation results are collected:

```text
if any hard blocker:
    BLOCKED
elif age/executability evidence is incomplete:
    WATCH
elif confirmations_passed < 9:
    WATCH
else:
    READY
```

If state is `READY`, append exactly one final `ALL_CONFIRMATIONS_PASSED` finding after all other evaluation stages.

A `READY` assessment therefore has:

- B1 safety `PASS`;
- valid setup age window;
- fresh B2 source data;
- acceptable minimum liquidity;
- acceptable exit price impact;
- non-extended 5-minute move;
- all nine continuation confirmations.

## 9. Missing Data / Fail-Closed Semantics

Missing setup evidence never passes a condition and never turns into zero.

This is especially important for:

- missing seller counts embedded in flow features;
- missing 1m/5m return anchors;
- missing liquidity-change baseline;
- missing local range evidence;
- missing exit-impact evidence.

A candidate with incomplete evidence remains `WATCH` until sufficient data arrives or the setup window expires.

## 10. Safety Precedence

B1 remains absolute.

Any `SafetyDecision.REJECT` or `SafetyDecision.INCOMPLETE` produces the B3 hard blocker `SAFETY_NOT_PASS`. A high confirmation score cannot override it.

The evaluator still calculates the nine confirmation results for research/audit even when state is `BLOCKED`, so later analysis can measure whether safety filters rejected otherwise-strong-looking setups. This preserves rejected-token research data.

## 11. Invalidation Semantics

B3 does not maintain hidden historical state. Its current hard blocker findings are the setup's current invalidation conditions.

A later position/exit engine may reuse analogous signals, but B3 itself only answers whether a fresh-launch setup is currently blocked, waiting, or ready.

## 12. Testing Strategy

Development is test-first.

### Model tests

Prove:

- stable enum/reason strings;
- policy validation and immutability;
- assessment immutability;
- no future-outcome or trade-result fields.

### Setup evaluator tests

Use an explicit policy fixture and hand-built B2 vectors to prove:

- all nine passing confirmations -> `READY`, score 100;
- each hard blocker independently -> `BLOCKED`;
- safety rejection/incomplete cannot be overridden by strong features;
- too-young and unknown age -> `WATCH`;
- missing liquidity/exit impact -> `WATCH`;
- each of the nine confirmation thresholds independently produces `WATCH` and score 8/9 * 100;
- equality at every threshold passes;
- missing confirmation values generate the matching `UNKNOWN` reason and do not pass;
- excessive 5m return triggers anti-chase blocker;
- multiple findings are deterministically ordered;
- repeated assessment produces equal results;
- blocked candidates still receive confirmation counts for research.

### Public API tests

All stable symbols import from `shreks_brain.setups`.

Final verification remains full repository CI.

## 13. Calibration / Profitability Discipline

B3 deliberately ships **without a production default policy**.

The thresholds are hypotheses. The later research/paper phase must evaluate policy candidates using point-in-time feature rows and future outcomes, including:

- net expectancy after realistic costs;
- drawdown;
- trade frequency/sample size;
- performance by Pump.fun/PumpSwap/Meteora venue/lifecycle where available;
- sensitivity to threshold changes;
- out-of-sample stability.

A threshold is not promoted merely because it maximizes in-sample PnL.

## 14. Non-Trading Guarantee

B3 creates no wallet, signer, trade intent, order, fill, position, or transaction. `READY` is not an execution command. Paper/live entry remains disabled until the later decision, risk, execution, and proof stages exist and pass their gates.
