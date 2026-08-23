# Phase B6 Regime Engine Design

**Status:** Approved under the standing autonomous-build instruction  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`  
**Branch:** `feat/phase-b6-regime-engine`

## 1. Purpose

This phase repairs a source-order gap: the project build order calls for an explainable `HOT / NORMAL / WEAK / DEAD` memecoin regime engine before deterministic scoring. The setup work was implemented first, so this branch adds the missing regime intelligence before Shreks proceeds to a unified score/decision layer.

The branch label is B6 only to preserve repository chronology. Functionally, this implements the build order's B3 regime-engine requirement.

The regime engine answers one narrow question:

> Given point-in-time aggregate Solana memecoin market evidence, and optional sufficiently sampled recent after-cost strategy performance, what broad trading environment is Shreks observing right now?

It does not decide to enter a token, size a position, create a `TradeIntent`, simulate a fill, or execute capital.

## 2. Design Principles

1. **Explainable before clever.** V0 uses explicit threshold bands and stable reason codes, not an opaque weighted model.
2. **Point-in-time only.** No evidence later than the market source observation or decision timestamp may influence a historical regime label.
3. **Market evidence is primary.** Opportunity frequency, executable breadth, median liquidity, and median five-minute volume establish the base market regime.
4. **Recent strategy performance is downgrade-only.** Sufficiently sampled negative after-cost expectancy may downgrade the base regime. Strong recent performance never upgrades a weak market into `HOT`.
5. **Fail closed on critical market-data quality.** Future/stale source data, too-short windows, too-small samples, or missing liquidity/volume evidence classify as `DEAD` with explicit reasons so later entry logic can pause safely.
6. **No production defaults.** Every numeric threshold belongs to an explicit versioned policy and remains a research hypothesis until calibrated on unseen data.
7. **No B2 schema migration.** Existing `FeatureVector` remains `b2-v1`. Regime is a separate timestamped/versioned assessment consumed beside B2 by later scoring/decision layers.
8. **No circular setup dependency.** The regime engine does not count `READY` setups to decide whether the market is hot. A later scorer may consume both setup and regime outputs.
9. **No wallet-data fiction.** Smart-wallet evidence remains unavailable until the wallet-intelligence data phase exists.
10. **No execution authority.** No output field can encode side, notional, wallet, order, fill, signer, transaction, or realized future outcome.

## 3. Package Boundary

Create a focused Python package:

```text
python/src/shreks_brain/regime/
  __init__.py
  models.py
  engine.py
```

The package is dependency-light and pure. It does not read SQLite, call providers, inspect wall-clock time, or mutate shared state.

Stable public API:

```python
from shreks_brain.regime import (
    MarketRegime,
    RecentStrategyPerformance,
    RegimeAssessment,
    RegimeFinding,
    RegimeMarketWindow,
    RegimePolicy,
    RegimeReasonCode,
    assess_regime,
)
```

## 4. Market Input Contract

`RegimeMarketWindow` is immutable, normalized aggregate evidence prepared by an upstream observer/research/decision caller.

```python
@dataclass(frozen=True, slots=True)
class RegimeMarketWindow:
    as_of_unix_ms: int
    source_observed_at_unix_ms: int
    window_started_at_unix_ms: int
    candidate_count: int
    executable_candidate_count: int
    median_liquidity_usd: float | None
    median_volume_m5_usd: float | None
```

Validation:

- timestamps are non-negative integers, never bool/float;
- `window_started_at_unix_ms < source_observed_at_unix_ms`;
- `candidate_count >= 0`;
- `0 <= executable_candidate_count <= candidate_count`;
- medians, when present, are finite and non-negative;
- `source_observed_at_unix_ms` may be later than `as_of_unix_ms` so the evaluator can classify that contradiction fail-closed instead of construction hiding it.

`candidate_count` means candidates included in the aggregate market-quality window under one stable upstream sampling definition. `executable_candidate_count` means candidates for which the upstream system had contemporaneous evidence sufficient to consider execution feasible. The regime engine does not invent or re-derive those upstream facts.

## 5. Optional Recent Strategy Performance

Recent strategy performance is a separate optional immutable context:

```python
@dataclass(frozen=True, slots=True)
class RecentStrategyPerformance:
    observed_through_unix_ms: int
    closed_trade_count: int
    net_expectancy_after_costs_pct: float | None
```

Rules:

- timestamp and trade count are non-negative integers;
- expectancy, when present, is finite and may be negative;
- if performance evidence is later than `as_of_unix_ms` or later than the market source observation, it is contradictory look-ahead evidence and the final regime is fail-closed `DEAD`;
- if the closed-trade sample is below policy minimum, performance does not alter the base market regime;
- if expectancy is missing, performance does not alter the base regime and the missing fact is recorded;
- sufficiently sampled negative expectancy can only downgrade;
- positive recent expectancy never upgrades the base market regime.

This gives the later paper system somewhere to feed recent after-cost performance without making regime classification depend on paper infrastructure today.

## 6. Policy Contract

`RegimePolicy` is immutable and has no production default instance.

```python
@dataclass(frozen=True, slots=True)
class RegimePolicy:
    version: str
    max_source_age_ms: int
    min_window_seconds: float
    min_candidate_samples: int

    dead_max_candidate_rate_per_hour: float
    weak_min_candidate_rate_per_hour: float
    hot_min_candidate_rate_per_hour: float

    dead_max_executable_fraction: float
    weak_min_executable_fraction: float
    hot_min_executable_fraction: float

    weak_min_median_liquidity_usd: float
    hot_min_median_liquidity_usd: float
    weak_min_median_volume_m5_usd: float
    hot_min_median_volume_m5_usd: float

    min_performance_sample_count: int
    dead_performance_expectancy_pct: float
    weak_performance_expectancy_pct: float
```

Validation requires:

- non-empty version;
- non-negative finite source/window/market thresholds where applicable;
- integer sample thresholds;
- fraction thresholds inside `[0, 1]`;
- `dead_max_candidate_rate_per_hour <= weak_min_candidate_rate_per_hour <= hot_min_candidate_rate_per_hour`;
- `dead_max_executable_fraction <= weak_min_executable_fraction <= hot_min_executable_fraction`;
- weak liquidity <= hot liquidity;
- weak volume <= hot volume;
- finite performance thresholds with `dead_performance_expectancy_pct <= weak_performance_expectancy_pct`.

No numeric policy is exported as a default.

## 7. Derived Metrics

When timestamp integrity permits, the engine derives:

```text
source_age_ms = as_of_unix_ms - source_observed_at_unix_ms
window_seconds = (source_observed_at_unix_ms - window_started_at_unix_ms) / 1000
candidate_rate_per_hour = candidate_count / window_seconds * 3600
executable_fraction = executable_candidate_count / candidate_count
```

`executable_fraction` is `None` when `candidate_count == 0`; a zero denominator is never silently converted into a market-quality value.

The assessment preserves input medians and derived metrics for later audit/research.

## 8. Base Market Classification

Classification is deterministic and ordered.

### 8.1 Critical data-quality gates -> `DEAD`

The base regime is `DEAD` if any of these holds:

1. source observation is later than `as_of_unix_ms`;
2. source age exceeds `max_source_age_ms`;
3. aggregate window duration is below `min_window_seconds`;
4. `candidate_count == 0`;
5. candidate sample is below `min_candidate_samples`;
6. median liquidity is missing;
7. median five-minute volume is missing.

These reasons mean “do not permit new entries from this global state,” not necessarily that the external market literally has zero activity.

### 8.2 Market conditions

With usable data:

- `DEAD` if either candidate rate is at or below `dead_max_candidate_rate_per_hour` **or** executable fraction is at or below `dead_max_executable_fraction`;
- otherwise `WEAK` if any one of candidate rate, executable fraction, median liquidity, or median five-minute volume is below its configured weak minimum;
- otherwise `HOT` if all four metrics meet or exceed their configured hot minima;
- otherwise `NORMAL`.

Threshold equality is intentional:

- equality with a dead maximum is `DEAD`;
- equality with a weak minimum passes that weak test;
- equality with every hot minimum is sufficient for `HOT`.

This is deliberately not a weighted score. A single weak dimension is visible rather than being hidden by strength elsewhere.

## 9. Performance Overlay

The base market regime is preserved separately as `base_regime`.

Performance processing happens after base classification:

1. `performance is None` -> no change, record `PERFORMANCE_UNAVAILABLE`;
2. future-dated performance -> final `DEAD`;
3. sample below `min_performance_sample_count` -> no change;
4. expectancy missing -> no change;
5. expectancy <= `dead_performance_expectancy_pct` -> final `DEAD`;
6. expectancy < `weak_performance_expectancy_pct` -> downgrade `HOT` or `NORMAL` to `WEAK`; existing `WEAK`/`DEAD` remains unchanged;
7. expectancy >= weak floor -> no upgrade.

The final label can therefore be equal to or more conservative than `base_regime`, never more aggressive.

## 10. Domain Types

```python
class MarketRegime(StrEnum):
    HOT = "HOT"
    NORMAL = "NORMAL"
    WEAK = "WEAK"
    DEAD = "DEAD"
```

`RegimeReasonCode` has stable deterministic ordering grouped as:

1. source/data-quality failures;
2. base market classification findings;
3. performance evidence findings.

Required codes:

```text
SOURCE_AFTER_AS_OF
SOURCE_DATA_TOO_OLD
WINDOW_TOO_SHORT
NO_CANDIDATES
CANDIDATE_SAMPLE_TOO_SMALL
MEDIAN_LIQUIDITY_UNKNOWN
MEDIAN_VOLUME_M5_UNKNOWN
OPPORTUNITY_RATE_DEAD
EXECUTABLE_FRACTION_DEAD
OPPORTUNITY_RATE_WEAK
EXECUTABLE_FRACTION_WEAK
LIQUIDITY_WEAK
VOLUME_WEAK
ALL_HOT_MARKET_THRESHOLDS_PASSED
NORMAL_MIXED_MARKET
PERFORMANCE_UNAVAILABLE
PERFORMANCE_AFTER_AS_OF
PERFORMANCE_AFTER_MARKET_SOURCE
PERFORMANCE_SAMPLE_INSUFFICIENT
PERFORMANCE_EXPECTANCY_UNKNOWN
PERFORMANCE_EXPECTANCY_DEAD
PERFORMANCE_EXPECTANCY_WEAK
```

A `RegimeFinding` contains code, message, observed value, and optional threshold.

## 11. Assessment Contract

```python
@dataclass(frozen=True, slots=True)
class RegimeAssessment:
    policy_version: str
    as_of_unix_ms: int
    source_observed_at_unix_ms: int
    window_started_at_unix_ms: int
    source_age_ms: int | None
    window_seconds: float
    candidate_count: int
    candidate_rate_per_hour: float
    executable_fraction: float | None
    median_liquidity_usd: float | None
    median_volume_m5_usd: float | None
    base_regime: MarketRegime
    regime: MarketRegime
    performance_sample_count: int | None
    performance_net_expectancy_after_costs_pct: float | None
    performance_applied: bool
    findings: tuple[RegimeFinding, ...]
```

The assessment is immutable and contains no order/execution/future-outcome authority.

`performance_applied` is true only when sufficiently sampled expectancy actually changes or constrains the final label (`WEAK`/`DEAD`). An adequately sampled non-negative performance observation that causes no downgrade remains false because it did not determine a more permissive regime.

## 12. Deterministic Finding Order

Findings are appended in this fixed stage order:

1. source timestamp/freshness;
2. window/sample/data completeness;
3. base market classification findings in metric order: opportunity rate, executable breadth, liquidity, volume;
4. one base summary marker for HOT or NORMAL when no weak/dead marker applies;
5. performance evidence/findings.

Repeated calls with equal inputs must return equal assessments.

## 13. Relationship to Existing Setups

B3/B4b/B5 setup code remains unchanged.

The regime package does not import setup evaluators and setup evaluators do not import the regime package in this phase. This avoids a circular architecture and preserves independent measurability.

The next deterministic scoring/decision work will consume:

- B1 safety evidence,
- unchanged B2 features,
- one setup assessment,
- this `RegimeAssessment`,
- wallet evidence only when it genuinely exists.

Strategy enable/disable rules by regime belong in that later decision/scoring policy, not inside regime classification.

## 14. Test Contract

Tests must prove at minimum:

- exact enum/reason-code ordering and frozen model validation;
- future/stale source fail closed;
- zero candidates, too-small sample, too-short window, or missing market medians fail closed;
- exact candidate-rate and executable-fraction derivation;
- dead-threshold equality -> `DEAD`;
- any weak dimension -> `WEAK`;
- all hot dimensions at equality -> `HOT`;
- mixed healthy dimensions -> `NORMAL`;
- missing performance does not alter the base regime;
- insufficient performance sample does not alter the base regime;
- future performance fails closed and never leaks into historical labels;
- sufficiently sampled poor after-cost expectancy downgrades only;
- strong performance never upgrades `WEAK`/`NORMAL` to `HOT`;
- deterministic finding order and repeatability;
- assessment fields contain no execution authority;
- all existing B1/B2/setup/Rust tests remain green.

## 15. Non-Goals

This phase does not:

- build wallet intelligence;
- implement Smart Wallet Cluster;
- aggregate windows from SQLite;
- widen `FeatureVector` beyond `b2-v1`;
- create deterministic trade scores;
- create `TradeDecision` or `TradeIntent`;
- size risk;
- paper trade;
- sign or submit Solana transactions;
- enable live money.

## 16. Completion Criteria

The phase is complete when:

1. the public regime package and immutable contracts exist;
2. market classification is deterministic and point-in-time safe;
3. optional recent performance is downgrade-only and leakage-safe;
4. no production default thresholds exist;
5. no existing setup/B2 behavior changes;
6. full Python and Rust CI plus repository safety pass on the exact final head;
7. the stacked PR remains draft/unmerged with verification evidence recorded in PR metadata.
