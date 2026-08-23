# Phase B2 Deterministic Feature Engine Design

**Status:** Approved by standing autonomous-build instruction  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`

## 1. Purpose

Phase B2 adds the first deterministic feature-engine layer to the Python brain. Its job is to transform point-in-time normalized market observations plus the already-computed B1 `SafetyAssessment` into a versioned `FeatureVector` suitable for explicit setup detection, scoring, research, and later model training.

The feature engine is not a strategy and does not decide whether to trade. It deliberately avoids an opaque composite score. Its purpose is to expose reproducible raw/derived facts whose relationship to post-cost trading outcomes can be measured using the Phase A outcome dataset.

B2 therefore optimizes for three things that matter directly to eventual profitability:

1. **signal quality** — capture liquidity, participation, flow, momentum, structure, and executability information that can plausibly affect trade expectancy;
2. **look-ahead safety** — use only observations available at or before the feature timestamp;
3. **research honesty** — preserve missing values as unknown instead of converting them to optimistic zeros.

## 2. Source-of-Truth Requirements

This design implements the approved master-design requirements that V0 uses deterministic, explainable features before machine learning and that feature families include:

- market quality;
- flow;
- momentum;
- wallet quality when available later;
- distribution/safety;
- market regime later;
- timestamping and versioning to prevent look-ahead leakage.

B2 implements only the feature families that can be represented cleanly from the point-in-time market/safety evidence already available. Wallet intelligence and market-regime construction remain separate later subsystems.

## 3. Chosen Architecture

Three approaches were considered.

### A. Pure point-in-time feature engine — chosen

A dependency-free Python package accepts normalized point-in-time inputs and returns a frozen `FeatureVector`. It does not query SQLite or providers.

Advantages:

- deterministic and easy to test;
- no storage/provider coupling;
- straightforward backtest parity;
- easiest design for preventing data leakage;
- allows raw features to be calibrated against actual future outcomes before assigning score weights.

### B. SQLite-coupled feature builder — rejected for B2

This would query operational tables directly inside feature code. It would shorten later integration but couple research logic to the operational schema and make leakage/selection bugs harder to isolate.

### C. DataFrame/ML feature pipeline first — rejected for B2

A vectorized analytics pipeline may be useful later for training, but introducing it before deterministic feature definitions are proven would add complexity and encourage premature optimization or overfitting.

## 4. Package Boundary

B2 adds:

```text
python/src/shreks_brain/features/
  __init__.py
  models.py
  engine.py
python/tests/
  test_feature_models.py
  test_feature_engine.py
  test_feature_public_api.py
```

The package depends only on the Python standard library and `shreks_brain.safety`.

- `models.py` owns immutable feature input/output types and validation.
- `engine.py` owns pure deterministic calculations.
- `__init__.py` exposes the stable public contract.

A later assembler may read SQLite and construct these inputs, but no database/provider code enters B2.

## 5. Feature Schema Version

The first schema version is exactly:

```python
FEATURE_SCHEMA_VERSION = "b2-v1"
```

The schema version is part of every `FeatureVector` and is immutable. Any future semantic change to a feature definition requires a new version rather than silently changing historical meaning.

## 6. Domain Types

### `MarketFeaturePoint`

Immutable point-in-time normalized market evidence:

- `observed_at_unix_ms: int`
- `price_usd: float | None`
- `liquidity_usd: float | None`
- `volume_m5_usd: float | None`
- `volume_h1_usd: float | None`
- `buys_m5: int | None`
- `sells_m5: int | None`
- `buys_h1: int | None`
- `sells_h1: int | None`

Validation:

- timestamp must be a non-negative integer;
- known monetary values must be finite and non-negative;
- known count values must be non-negative integers;
- `None` means unknown and is never converted to zero.

### `FeatureInputs`

Immutable point-in-time input bundle:

- `as_of_unix_ms: int`
- `current: MarketFeaturePoint`
- `one_minute_ago: MarketFeaturePoint | None`
- `five_minutes_ago: MarketFeaturePoint | None`
- `fifteen_minutes_ago: MarketFeaturePoint | None`
- `pair_created_at_unix_ms: int | None`
- `local_high_price_usd: float | None`
- `local_low_price_usd: float | None`
- `exit_price_impact_pct: float | None`
- `safety: SafetyAssessment`

All supplied observations must have `observed_at_unix_ms <= as_of_unix_ms`. Future observations raise `ValueError` instead of being accepted as feature evidence.

`pair_created_at_unix_ms` must be non-negative and cannot be later than `as_of_unix_ms`.

Known local high/low prices and exit-price-impact values must be finite and non-negative. If both local high and local low are known, high must be greater than or equal to low. If current price is known and extrema are supplied, extrema are treated as historical path evidence and current price may equal either boundary.

The B1 `SafetyAssessment` must have `as_of_unix_ms <= FeatureInputs.as_of_unix_ms`; a future safety assessment raises `ValueError`.

B2 accepts no future outcome checkpoint, realized return, future MFE/MAE, or trade-result fields.

### `FeatureVector`

Immutable output with:

Identity/audit fields:

- `schema_version: str`
- `as_of_unix_ms: int`
- `source_observed_at_unix_ms: int`
- `safety_policy_version: str`
- `safety_decision: SafetyDecision`

Market-quality features:

- `token_age_seconds: float | None`
- `price_usd: float | None`
- `liquidity_usd: float | None`
- `liquidity_change_5m_pct: float | None`
- `exit_price_impact_pct: float | None`

Participation/volume features:

- `volume_m5_usd: float | None`
- `volume_h1_usd: float | None`
- `volume_velocity_ratio: float | None`
- `tx_count_m5: int | None`
- `tx_count_h1: int | None`

Flow features:

- `buy_fraction_m5: float | None`
- `buy_fraction_h1: float | None`
- `buy_sell_ratio_m5: float | None`
- `buy_sell_ratio_h1: float | None`
- `buy_pressure_acceleration: float | None`

Momentum features:

- `return_1m_pct: float | None`
- `return_5m_pct: float | None`
- `return_15m_pct: float | None`
- `momentum_acceleration_1m_vs_5m: float | None`

Path/structure features:

- `distance_from_local_high_pct: float | None`
- `range_position_pct: float | None`

Safety-derived research features:

- `safety_soft_finding_count: int`
- `safety_liquidity_weak: bool`
- `safety_holder_concentration_elevated: bool`
- `safety_creator_concentration_elevated: bool`
- `safety_exit_price_impact_elevated: bool`

Data-availability metadata:

- `missing_features: tuple[str, ...]`

`missing_features` contains the public feature-field names whose values are `None`, in the exact canonical field order defined by this spec. It does not list boolean safety flags or identity fields.

## 7. Deterministic Calculations

All percentage values use percentage points.

### 7.1 Safe percentage change

For current value `x` and earlier value `b`:

```text
pct_change = ((x / b) - 1) * 100
```

Return `None` when either value is unknown or `b <= 0`. Never produce infinity or substitute zero.

Used for:

- liquidity change over 5 minutes;
- 1m/5m/15m returns.

### 7.2 Token age

```text
token_age_seconds = (as_of_unix_ms - pair_created_at_unix_ms) / 1000
```

Return `None` when pair creation time is unknown.

### 7.3 Transaction counts

For a window, if both buy and sell counts are known:

```text
tx_count = buys + sells
```

Otherwise return `None`.

### 7.4 Buy fraction

If both counts are known and total transactions are positive:

```text
buy_fraction = buys / (buys + sells)
```

Otherwise return `None`.

This produces a `[0, 1]` fraction, not percentage points.

### 7.5 Buy/sell ratio

If buys and sells are known and `sells > 0`:

```text
buy_sell_ratio = buys / sells
```

If sells are zero, return `None`; do not manufacture an arbitrarily large ratio.

### 7.6 Buy-pressure acceleration

When both window buy fractions are known:

```text
buy_pressure_acceleration = buy_fraction_m5 - buy_fraction_h1
```

Positive values mean recent transaction-count pressure is more buy-heavy than the broader hour.

### 7.7 Volume velocity

When both current rolling volumes are known and hourly volume is positive:

```text
volume_velocity_ratio = (volume_m5_usd * 12) / volume_h1_usd
```

Interpretation:

- `1.0` means the most recent 5-minute pace is equal to the average pace implied by the last hour;
- `>1.0` means recent volume pace is elevated;
- `<1.0` means recent volume pace is slower.

Return `None` when hourly volume is zero/unknown.

### 7.8 Momentum acceleration

When 1-minute and 5-minute returns are known:

```text
momentum_acceleration_1m_vs_5m = return_1m_pct - (return_5m_pct / 5)
```

This compares the latest one-minute return with the average per-minute return implied by the five-minute move. It is intentionally simple and explainable.

### 7.9 Distance from local high

When current price and a positive local high are known:

```text
distance_from_local_high_pct = ((price / local_high) - 1) * 100
```

Typical values are `<= 0`. The engine does not clamp positive values because inconsistent path evidence should remain visible rather than silently altered.

### 7.10 Range position

When current price, local high, and local low are known and `high > low`:

```text
range_position_pct = ((price - low) / (high - low)) * 100
```

The value is not clamped. A result below 0 or above 100 indicates the supplied local extrema do not bracket the current price and remains auditable.

When `high == low`, return `None`.

## 8. Safety Integration

B1 safety remains the hard gate and B2 cannot override it.

The feature engine copies:

- safety policy version;
- safety decision;
- count of `SOFT` findings;
- four stable soft-reason flags.

The flags are true when the corresponding `SafetyReasonCode` exists in the B1 findings:

- `LIQUIDITY_WEAK`;
- `HOLDER_CONCENTRATION_ELEVATED`;
- `CREATOR_CONCENTRATION_ELEVATED`;
- `EXIT_PRICE_IMPACT_ELEVATED`.

B2 still computes a feature vector for `REJECT` and `INCOMPLETE` candidates because rejected observations are valuable research data and reduce selection bias. Later entry logic must independently require a safety `PASS` before permitting an entry.

## 9. Missing Data and Fail-Closed Research Semantics

Unknown inputs remain `None` all the way through derived calculations. No missing numeric value is imputed to zero.

This matters to profitability because zero-filling can create false signals, for example:

- unknown sells appearing as zero sells and therefore extreme buy pressure;
- unknown historical price appearing as a zero denominator;
- unknown liquidity looking like a real liquidity collapse;
- missing volume appearing as a low-volume regime.

B2 never guesses these values.

The feature vector records which derived/public numeric features are missing so later strategy and research code can explicitly decide whether a setup has enough evidence.

## 10. Point-in-Time / Look-Ahead Protection

The public B2 API accepts only current/earlier observations and B1 safety state at or before the feature timestamp.

Tests must prove:

- a future market point is rejected;
- a future pair creation timestamp is rejected;
- a future safety assessment is rejected;
- no future-outcome fields exist on `FeatureInputs`;
- repeated calls with identical inputs produce equal vectors.

The engine has no access to Phase A future outcome checkpoints.

## 11. What B2 Does Not Implement

B2 intentionally does not implement:

- setup detection;
- entry/exit score weights;
- `TradeDecision`;
- wallet quality;
- market regime;
- holder/creator inference;
- strategy thresholds;
- SQLite reads/writes;
- provider calls;
- paper fills;
- execution;
- model training.

Those remain separate stages so each can be measured independently.

## 12. Testing Strategy

Development is test-first.

### Model tests

Prove:

- immutable types;
- validation of timestamps, monetary values, counts, extrema, and future observations;
- safety timestamp ordering;
- absence of future-outcome fields.

### Engine tests

Use fixed numerical fixtures to prove exact calculations for:

- age;
- liquidity change;
- returns;
- volume velocity;
- transaction totals;
- buy fractions;
- buy/sell ratios;
- flow acceleration;
- momentum acceleration;
- local-high distance;
- range position;
- safety soft flags/count;
- deterministic `missing_features` ordering.

Boundary/edge cases prove:

- zero denominators return `None`;
- zero sells do not become infinity;
- high == low range returns `None`;
- rejected/incomplete safety still produces features for research;
- missing data is never silently zero-filled;
- repeated evaluation is equal.

### Public API tests

The complete stable interface must import from `shreks_brain.features` without depending on internal modules.

Final verification remains the full repository CI: Rust workspace tests, Python tests, workspace metadata validation, and repository secret-safety.

## 13. Profitability Rationale

B2 is intentionally built before setup scoring because a profitable system needs to distinguish **signal definition** from **signal weight**.

These features let Shreks later measure questions such as:

- Does rising 5-minute volume pace improve expectancy after costs?
- Is high buy pressure useful only when liquidity is also growing?
- Do strong 1-minute returns after already-extended 5-minute moves mean continuation or exhaustion?
- Does a controlled pullback near the local high outperform blind breakout buying?
- Which B1 soft safety risks reduce realized expectancy enough to deserve stronger penalties?

The answer will come from Shreks' own point-in-time outcomes rather than assumptions.

## 14. Non-Trading Guarantee

B2 creates no wallet secret, signer, trade intent, paper fill, swap request, position, or transaction. It changes no runtime mode behavior and does not enable live trading.
