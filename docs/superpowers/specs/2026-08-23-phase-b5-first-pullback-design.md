# Phase B5 First Pullback Design

**Status:** Approved under standing autonomous-build instruction on 2026-08-23  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`  
**Base:** verified Phase B4b head `58c4cb660c10fd73b97fc2fa2ab892c5e9b0ab9f`

## 1. Purpose

Phase B5 implements Shreks' third explicit setup family: **First Pullback**.

The master design defines First Pullback as a strong initial move followed by a controlled retracement, seller absorption, and renewed demand. A single current momentum snapshot cannot prove that chronology. B5 therefore keeps the shared B2 `FeatureVector` unchanged and adds a small setup-specific `PullbackContext` containing raw, point-in-time structural facts for the impulse start, peak, and first post-peak trough.

The evaluator combines that structure with current B2 market evidence to decide whether the setup is `BLOCKED`, `WATCH`, or `READY`. It does not place trades.

## 2. Profitability Hypothesis

B5 tests a narrow hypothesis:

> after a sufficiently strong initial impulse, a token that retraces enough to reset extension but not enough to invalidate the move, retains liquidity, shows reduced seller dominance versus the trough, and then regains participation and short-term demand may offer better continuation expectancy than chasing the initial impulse or buying an uncontrolled decline.

This is a research hypothesis, not a claim of profitability. Numerical thresholds remain explicit policy hypotheses and must later be calibrated on unseen, point-in-time, post-cost outcomes.

The setup is designed to reject three common false positives:

1. **no real pullback** — price barely retraced and the entry is still a momentum chase;
2. **falling knife** — the recorded trough has already broken or the drawdown is too deep;
3. **fake recovery** — price bounces without liquidity retention, participation, seller absorption, or renewed demand.

## 3. Chosen Architecture

B5 uses the same purity principle as B3/B4b:

```python
def assess_first_pullback(
    features: FeatureVector,
    pullback: PullbackContext | None,
    policy: FirstPullbackPolicy,
) -> FirstPullbackAssessment:
    ...
```

B2 remains exactly `b2-v1`.

The `PullbackContext` contains **raw structural observations**, not pre-scored claims. In particular it stores the impulse-start price, peak price, trough price, timestamps, optional peak/trough liquidity, trough buy fraction, and the number of market observations used to establish the structure. The evaluator derives impulse return, pullback depth, current recovery, distance from the impulse peak, liquidity retention, and buy-fraction improvement itself.

This is preferred over adding fields such as `pullback_score` or `seller_absorption=True`, because those would hide assumptions and make later research harder to audit.

B5 does not:

- query SQLite;
- call providers;
- inspect raw DEX/provider payloads;
- alter the B2 schema;
- infer missing values;
- use future outcomes;
- create an order, position, or execution request.

## 4. Why B2 Alone Is Not Enough

The existing B2 vector exposes current point-in-time features including 1m/5m/15m returns, current liquidity, 5m liquidity change, transaction counts, volume velocity, buy fractions, buy-pressure acceleration, local-high distance, and range position.

Those fields do not establish the exact chronology:

```text
impulse start -> peak -> trough -> current recovery
```

A high current buy fraction and positive 1m return can occur during both a genuine first pullback recovery and a noisy launch with no prior retracement. B5 therefore refuses to silently reinterpret B2 momentum as pullback structure.

## 5. `PullbackContext`

Immutable structural context:

```python
@dataclass(frozen=True, slots=True)
class PullbackContext:
    impulse_started_at_unix_ms: int
    peak_at_unix_ms: int
    trough_at_unix_ms: int
    impulse_start_price_usd: float
    peak_price_usd: float
    trough_price_usd: float
    peak_liquidity_usd: float | None
    trough_liquidity_usd: float | None
    trough_buy_fraction_m5: float | None
    sample_count: int
```

Internal chronology is strict:

```text
impulse_started_at_unix_ms < peak_at_unix_ms < trough_at_unix_ms
```

Price validation:

- impulse-start, peak, and trough prices are finite and positive;
- peak price must be at least the impulse-start price;
- peak price must be strictly above trough price.

Optional liquidity values are finite and non-negative. `trough_buy_fraction_m5`, when present, is within `[0, 1]`.

`sample_count` is an integer of at least 3 because the structure requires at minimum distinct start, peak, and trough observations. A policy may require more than three observations before allowing `READY`.

The context itself does not claim that the impulse was strong enough or the retracement was controlled enough; those are policy decisions made by the evaluator.

## 6. Decision-Time Alignment

B5 combines the context with the current B2 `FeatureVector`.

The latest structural timestamp is the trough time. Decision-time integrity requires:

1. `trough_at_unix_ms <= features.as_of_unix_ms`;
2. `trough_at_unix_ms <= features.source_observed_at_unix_ms`.

If the trough is later than `as_of_unix_ms`, the context contains future information and the setup is `BLOCKED`.

If the trough is not in the future relative to `as_of_unix_ms` but is later than `features.source_observed_at_unix_ms`, the evaluator would be mixing later structural evidence with an older “current” market snapshot. That is contradictory point-in-time evidence and is also `BLOCKED`.

The pullback age used by the setup is:

```text
seconds_since_trough =
    (features.source_observed_at_unix_ms - pullback.trough_at_unix_ms) / 1000
```

Using the actual current market observation time rather than wall clock or `as_of_unix_ms` prevents stale market data from falsely creating additional apparent recovery time. Source staleness is handled independently by the normal source-age gate.

## 7. Derived Structural Metrics

When a context exists, B5 derives:

### Initial impulse return

```text
impulse_return_pct =
    (peak_price_usd / impulse_start_price_usd - 1) * 100
```

### Pullback depth

Positive drawdown magnitude from peak to trough:

```text
pullback_depth_pct =
    (1 - trough_price_usd / peak_price_usd) * 100
```

### Recovery from trough

Requires current B2 `price_usd`:

```text
recovery_from_trough_pct =
    (current_price_usd / trough_price_usd - 1) * 100
```

### Current position versus impulse peak

Requires current B2 `price_usd`:

```text
current_vs_peak_pct =
    (current_price_usd / peak_price_usd - 1) * 100
```

Negative means still below the prior impulse peak; positive means price has broken above it.

### Liquidity retention through pullback

When both context liquidity values exist and peak liquidity is positive:

```text
liquidity_retention_pct =
    trough_liquidity_usd / peak_liquidity_usd * 100
```

Retention may exceed 100 if liquidity increased during the retracement. Zero peak liquidity does not produce infinity; retention remains unknown.

### Buy-fraction improvement versus trough

When both the trough buy fraction and current B2 `buy_fraction_m5` exist:

```text
buy_fraction_improvement =
    current_buy_fraction_m5 - trough_buy_fraction_m5
```

This is the setup's first explicit seller-absorption measurement: renewed demand must improve relative to the pullback trough instead of merely being positive in isolation.

Missing derived inputs stay `None` and never become zero.

## 8. Stable Setup Identity

Setup name:

```text
first_pullback
```

B5 reuses shared `SetupState`:

- `BLOCKED`
- `WATCH`
- `READY`

Semantics:

- `BLOCKED` — a hard safety, timing, structural invalidation, freshness, or executability condition currently invalidates this pullback context;
- `WATCH` — the candidate may still develop into a valid first pullback, but evidence is missing, the retracement/recovery is not mature, or one or more confirmations are not yet satisfied;
- `READY` — all hard gates pass and all required First Pullback confirmations are satisfied.

`READY` is not `ENTER` and carries no execution authority.

## 9. `FirstPullbackReasonCode`

Stable reason codes are evaluated in deterministic order.

### Hard blockers

- `SAFETY_NOT_PASS`
- `PULLBACK_AFTER_AS_OF`
- `PULLBACK_AFTER_MARKET_SOURCE`
- `PULLBACK_WINDOW_EXPIRED`
- `INITIAL_IMPULSE_TOO_WEAK`
- `PULLBACK_TOO_DEEP`
- `PULLBACK_LOW_BROKEN`
- `BREAKOUT_TOO_EXTENDED`
- `SOURCE_DATA_TOO_OLD`
- `LIQUIDITY_BELOW_MINIMUM`
- `EXIT_PRICE_IMPACT_TOO_HIGH`
- `MOVE_TOO_EXTENDED`

### Watch / evidence reasons

- `PULLBACK_NOT_OBSERVED`
- `INSUFFICIENT_STRUCTURE_SAMPLES`
- `PULLBACK_TOO_RECENT`
- `PULLBACK_NOT_DEEP_ENOUGH`
- `CURRENT_PRICE_UNKNOWN`
- `LIQUIDITY_UNKNOWN`
- `EXIT_PRICE_IMPACT_UNKNOWN`
- `LIQUIDITY_RETENTION_UNKNOWN`
- `TROUGH_BUY_FRACTION_UNKNOWN`
- `TX_COUNT_M5_UNKNOWN`
- `TX_COUNT_M5_BELOW_MINIMUM`
- `VOLUME_VELOCITY_UNKNOWN`
- `VOLUME_VELOCITY_BELOW_MINIMUM`
- `BUY_FRACTION_M5_UNKNOWN`
- `BUY_FRACTION_M5_BELOW_MINIMUM`
- `BUY_FRACTION_IMPROVEMENT_UNKNOWN`
- `BUY_FRACTION_IMPROVEMENT_BELOW_MINIMUM`
- `BUY_PRESSURE_ACCELERATION_UNKNOWN`
- `BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM`
- `RETURN_1M_UNKNOWN`
- `RETURN_1M_BELOW_MINIMUM`
- `RECOVERY_FROM_TROUGH_UNKNOWN`
- `RECOVERY_FROM_TROUGH_BELOW_MINIMUM`
- `CURRENT_VS_PEAK_UNKNOWN`
- `CURRENT_VS_PEAK_BELOW_MINIMUM`
- `LIQUIDITY_RETENTION_BELOW_MINIMUM`

### Ready marker

- `ALL_CONFIRMATIONS_PASSED`

## 10. `FirstPullbackPolicy`

Immutable and versioned, with no production defaults:

```python
@dataclass(frozen=True, slots=True)
class FirstPullbackPolicy:
    version: str
    min_seconds_since_trough: float
    max_seconds_since_trough: float
    max_source_age_ms: int
    min_structure_samples: int
    min_initial_impulse_pct: float
    min_pullback_depth_pct: float
    max_pullback_depth_pct: float
    min_recovery_from_trough_pct: float
    min_current_vs_peak_pct: float
    max_current_vs_peak_pct: float
    min_liquidity_retention_pct: float
    min_liquidity_usd: float
    max_exit_price_impact_pct: float
    min_tx_count_m5: int
    min_volume_velocity_ratio: float
    min_buy_fraction_m5: float
    min_buy_fraction_improvement: float
    min_buy_pressure_acceleration: float
    min_return_1m_pct: float
    max_return_1m_pct: float
```

Validation:

- version is non-empty;
- all numeric values are finite;
- age, source-age, sample-count, impulse, pullback depth, recovery, liquidity retention, liquidity, exit impact, transaction count, and volume velocity thresholds are non-negative where their semantics require non-negative values;
- `min_structure_samples >= 3`;
- `max_seconds_since_trough > min_seconds_since_trough`;
- `0 <= min_pullback_depth_pct <= max_pullback_depth_pct < 100`;
- `min_buy_fraction_m5` is within `[0, 1]`;
- `max_current_vs_peak_pct >= min_current_vs_peak_pct`;
- `max_return_1m_pct >= min_return_1m_pct`.

`min_current_vs_peak_pct`, `min_buy_fraction_improvement`, `min_buy_pressure_acceleration`, and `min_return_1m_pct` may be negative research thresholds but must be finite.

No production policy is embedded in B5.

## 11. `FirstPullbackAssessment`

Immutable result:

```python
@dataclass(frozen=True, slots=True)
class FirstPullbackAssessment:
    setup_name: str
    policy_version: str
    feature_schema_version: str
    as_of_unix_ms: int
    state: SetupState
    seconds_since_trough: float | None
    impulse_return_pct: float | None
    pullback_depth_pct: float | None
    recovery_from_trough_pct: float | None
    current_vs_peak_pct: float | None
    liquidity_retention_pct: float | None
    buy_fraction_improvement: float | None
    confirmation_score: float
    confirmations_passed: int
    confirmations_required: int
    findings: tuple[FirstPullbackFinding, ...]
```

For B5-v1:

```text
confirmations_required = 9
confirmation_score = confirmations_passed / 9 * 100
```

The score is evidence completeness only. It is not expected return, win probability, confidence, or position size.

When no context exists, all structural metrics are `None` and state remains `WATCH` unless safety/freshness/executability independently hard-block the candidate.

## 12. Evaluation Order

The evaluator does not short-circuit confirmation calculation merely because another hard blocker exists. Computable evidence remains available for research.

### 12.1 Safety and context timing

Fixed order:

1. safety not `PASS` -> hard `SAFETY_NOT_PASS`;
2. context missing -> watch `PULLBACK_NOT_OBSERVED`;
3. context trough later than `as_of_unix_ms` -> hard `PULLBACK_AFTER_AS_OF`;
4. context trough later than `source_observed_at_unix_ms` -> hard `PULLBACK_AFTER_MARKET_SOURCE`.

Derived structural metrics are calculated when their inputs are available and point-in-time-valid.

### 12.2 Pattern age and sample quality

For valid context timing:

- `sample_count < min_structure_samples` -> watch `INSUFFICIENT_STRUCTURE_SAMPLES`;
- seconds since trough below `min_seconds_since_trough` -> watch `PULLBACK_TOO_RECENT`;
- seconds since trough above `max_seconds_since_trough` -> hard `PULLBACK_WINDOW_EXPIRED`.

Boundary equality passes.

### 12.3 Structural hard gates

When context exists:

- `impulse_return_pct < min_initial_impulse_pct` -> hard `INITIAL_IMPULSE_TOO_WEAK`;
- `pullback_depth_pct > max_pullback_depth_pct` -> hard `PULLBACK_TOO_DEEP`.

If current price is known:

- current price below the recorded trough price -> hard `PULLBACK_LOW_BROKEN`;
- `current_vs_peak_pct > max_current_vs_peak_pct` -> hard `BREAKOUT_TOO_EXTENDED`.

A broken recorded trough means the context no longer describes the current first pullback; B5 refuses to call a new low “seller absorption.”

### 12.4 Pullback maturity watch gate

If pullback depth is below `min_pullback_depth_pct`, append watch `PULLBACK_NOT_DEEP_ENOUGH`.

This is not a hard rejection because the pullback can deepen later without invalidating the original impulse.

### 12.5 Current freshness and executability hard gates

- `source_age_ms > max_source_age_ms` -> hard `SOURCE_DATA_TOO_OLD`;
- known `liquidity_usd < min_liquidity_usd` -> hard `LIQUIDITY_BELOW_MINIMUM`;
- known `exit_price_impact_pct > max_exit_price_impact_pct` -> hard `EXIT_PRICE_IMPACT_TOO_HIGH`;
- known `return_1m_pct > max_return_1m_pct` -> hard `MOVE_TOO_EXTENDED`.

### 12.6 Required evidence

Missing current price -> watch `CURRENT_PRICE_UNKNOWN`.

Missing current liquidity -> watch `LIQUIDITY_UNKNOWN`.

Missing exit price impact -> watch `EXIT_PRICE_IMPACT_UNKNOWN`.

Unknown liquidity retention -> `LIQUIDITY_RETENTION_UNKNOWN` and prevents READY.

Missing trough buy fraction -> `TROUGH_BUY_FRACTION_UNKNOWN` and prevents READY because seller absorption cannot be measured.

## 13. Nine Equal-Weight Confirmations

B5-v1 uses exactly nine confirmations in this order:

1. `recovery_from_trough_pct >= min_recovery_from_trough_pct`;
2. `current_vs_peak_pct >= min_current_vs_peak_pct`;
3. `liquidity_retention_pct >= min_liquidity_retention_pct`;
4. `tx_count_m5 >= min_tx_count_m5`;
5. `volume_velocity_ratio >= min_volume_velocity_ratio`;
6. `buy_fraction_m5 >= min_buy_fraction_m5`;
7. `buy_fraction_improvement >= min_buy_fraction_improvement`;
8. `buy_pressure_acceleration >= min_buy_pressure_acceleration`;
9. `return_1m_pct >= min_return_1m_pct`.

Each contributes one point. Equality passes.

Missing values do not pass and append their matching `UNKNOWN` reason. Known values below threshold append their matching threshold reason.

No value earns more than one point for being extreme. The hard upper extension guards prevent the checklist from rewarding unlimited chasing.

## 14. Seller Absorption Semantics

B5 does not claim to observe hidden order-book absorption.

Its first deterministic proxy is intentionally narrow and auditable:

```text
current 5m buy fraction - trough 5m buy fraction
```

A positive improvement means the recent transaction mix has shifted away from the seller-heavy trough state. This proxy must later be evaluated against outcomes; it is not assumed to be universally predictive.

If either fraction is unavailable, the absorption confirmation is unknown, not zero.

## 15. State Resolution

```text
if any hard blocker:
    BLOCKED
elif no pullback context or any watch/required-evidence condition:
    WATCH
elif confirmations_passed < 9:
    WATCH
else:
    READY
```

If `READY`, append exactly one final `ALL_CONFIRMATIONS_PASSED` finding.

READY therefore requires:

- safety PASS;
- point-in-time-valid chronological pullback context;
- sufficient observations;
- a sufficiently strong initial impulse;
- a retracement deep enough to qualify but not too deep;
- the recorded trough still intact;
- pattern age inside policy window;
- fresh market data;
- acceptable liquidity and exit price impact;
- no excessive one-minute chase;
- current price not too far above the original impulse peak;
- known structural/current evidence for all nine confirmations;
- all nine confirmations passing.

## 16. Missing Data and Research Preservation

Missing data never becomes zero and never passes a gate.

Hard-blocked candidates still retain all computable structural metrics and confirmation counts. This allows later research to measure questions such as:

- whether maximum pullback-depth rules reject profitable recoveries;
- whether liquidity-retention requirements improve exitability;
- whether buy-fraction recovery adds value beyond current buy fraction;
- whether the anti-chase ceilings reduce adverse excursion;
- whether minimum structure sample requirements are too conservative.

This reduces selection bias in later policy calibration.

## 17. Determinism

No wall clock is read inside the evaluator.

Given equal `FeatureVector`, `PullbackContext`, and policy inputs, repeated evaluation returns equal results with deterministic finding order.

All derived metrics use only information available no later than the current B2 source observation.

## 18. File Boundary

```text
python/src/shreks_brain/setups/
  __init__.py
  models.py
  fresh_launch.py
  graduation_breakout.py
  first_pullback.py

python/tests/
  test_first_pullback_models.py
  test_first_pullback_setup.py
  test_first_pullback_public_api.py
```

B5 does not modify B2 feature code or Rust lifecycle/storage code.

## 19. Testing Strategy

Development is strict TDD.

### Model tests

Prove:

- stable setup name, confirmation count, and reason strings/order;
- strict timestamp chronology;
- positive finite price validation;
- peak/start/trough price relationships;
- optional liquidity validation;
- trough buy-fraction bounds;
- sample count >= 3;
- policy validation and immutability;
- assessment metric validation and immutability;
- no execution or future-outcome fields.

### Evaluator tests

Prove:

- canonical structure plus all nine confirmations -> READY / 100;
- missing context -> WATCH, not fabricated structure;
- safety rejection/incomplete -> BLOCKED;
- future trough -> BLOCKED;
- context later than market source -> BLOCKED;
- too few structural samples -> WATCH;
- exact min/max trough-age boundaries pass;
- stale pullback -> BLOCKED;
- weak initial impulse -> BLOCKED;
- too-shallow pullback -> WATCH;
- too-deep pullback -> BLOCKED;
- current price below trough -> BLOCKED;
- excessive breakout above old peak -> BLOCKED;
- stale source / low liquidity / high exit impact / overextended 1m move -> BLOCKED;
- missing price/liquidity/exitability/retention/trough flow -> WATCH;
- all nine confirmation below-threshold cases independently -> 8/9 and WATCH;
- all nine missing cases -> matching UNKNOWN reason;
- threshold equality passes;
- zero peak liquidity leaves retention unknown rather than infinite;
- blocked candidates retain confirmation counts;
- finding order deterministic;
- repeated calls equal.

### Public API tests

All stable B5 symbols import from `shreks_brain.setups` without breaking B3 or B4b imports.

Final verification is full repository CI.

## 20. Calibration Discipline

B5 ships no production policy.

Later paper/research evaluation must compare policy candidates on unseen point-in-time data using realistic entry/exit costs and at least:

- net expectancy;
- drawdown and MAE;
- MFE capture;
- failed-exit frequency;
- sample size/trade frequency;
- sensitivity to impulse-strength and retracement-depth thresholds;
- sensitivity to trough age;
- incremental value of seller-absorption confirmation;
- performance by market regime and venue/lifecycle;
- out-of-sample stability.

A configuration is not promoted because it maximizes in-sample PnL.

## 21. Explicit Non-Goals

B5 does not:

- alter `b2-v1`;
- create a generic weighted trade score;
- implement Smart Wallet Cluster;
- create wallet intelligence;
- create `TradeDecision` or `TradeIntent`;
- size positions;
- paper trade;
- request or execute Jupiter swaps;
- create wallets or signers;
- submit transactions;
- enable live money.

## 22. Exit Criteria

B5 is complete only when:

1. First Pullback cannot be inferred from a single B2 snapshot without explicit chronological structure;
2. context chronology and decision-time alignment are fail-closed;
3. broken troughs and excessive retracements invalidate the setup;
4. shallow retracements remain WATCH rather than being mislabeled as pullbacks;
5. seller absorption is measured relative to trough flow and remains missing-safe;
6. all nine confirmations are deterministic and auditable;
7. blocked candidates preserve structural/confirmation evidence for research;
8. B3 and B4b behavior remain unchanged;
9. the public assessment has no execution authority;
10. full Rust/Python/repository-safety CI passes on the exact final head.
