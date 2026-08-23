# Phase B6 Regime Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, explainable, point-in-time `HOT / NORMAL / WEAK / DEAD` Solana memecoin regime engine with optional downgrade-only recent after-cost strategy-performance evidence.

**Architecture:** Create a focused `shreks_brain.regime` package beside unchanged B2 and setup code. Task 1 establishes immutable market/performance/policy/assessment models. Task 2 adds the deterministic classifier and performance overlay. Task 3 seals stable imports and documentation. No storage/provider/execution integration is permitted.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, pytest, existing repository CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b6-regime-engine-design.md`

## Global Constraints

- Base is verified B5 head `c943fc0c34ae89f29d840287224e3bd84f4f1ac1`.
- Existing B2 remains exactly `b2-v1`.
- Regime labels are exactly `HOT`, `NORMAL`, `WEAK`, `DEAD`.
- Market evidence is primary; recent strategy performance can only downgrade.
- No future-dated market or performance evidence may influence a historical regime.
- Missing critical market evidence fails closed to `DEAD` through the evaluator; model construction still preserves unknown values.
- No production default policy instance.
- No SQLite/provider/wall-clock reads from regime code.
- No setup evaluator imports inside the regime package.
- No wallet intelligence, Smart Wallet Cluster, trade score, `TradeDecision`, `TradeIntent`, sizing, paper fill, wallet/signing, swap submission, or live execution.
- Existing B1/B2/B3/B4b/B5 behavior remains unchanged.

---

### Task 1: Immutable regime domain contract

**Files:**
- Create: `python/src/shreks_brain/regime/models.py`
- Create: `python/tests/test_regime_models.py`

**Interfaces:**
- Produces:

```python
class MarketRegime(StrEnum):
    HOT = "HOT"
    NORMAL = "NORMAL"
    WEAK = "WEAK"
    DEAD = "DEAD"

class RegimeReasonCode(StrEnum): ...

@dataclass(frozen=True, slots=True)
class RegimeMarketWindow: ...

@dataclass(frozen=True, slots=True)
class RecentStrategyPerformance: ...

@dataclass(frozen=True, slots=True)
class RegimePolicy: ...

@dataclass(frozen=True, slots=True)
class RegimeFinding: ...

@dataclass(frozen=True, slots=True)
class RegimeAssessment: ...
```

- [ ] **Step 1: Write the failing model-contract test**

Create `python/tests/test_regime_models.py` importing all Task 1 symbols from `shreks_brain.regime.models`.

Pin exact regime order:

```python
assert tuple(item.value for item in MarketRegime) == (
    "HOT", "NORMAL", "WEAK", "DEAD"
)
```

Pin exact reason-code order:

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

Use this canonical market fixture:

```python
RegimeMarketWindow(
    as_of_unix_ms=1_310_000,
    source_observed_at_unix_ms=1_300_000,
    window_started_at_unix_ms=940_000,
    candidate_count=12,
    executable_candidate_count=9,
    median_liquidity_usd=80_000.0,
    median_volume_m5_usd=25_000.0,
)
```

Prove:

- timestamps reject bool/float/negative;
- window start must be strictly before source observation;
- source may be after `as_of` for evaluator-level contradiction handling;
- counts reject bool/float/negative;
- executable count cannot exceed candidate count;
- optional medians accept `None` and otherwise require finite non-negative numbers;
- dataclass is frozen.

Use this performance fixture:

```python
RecentStrategyPerformance(
    observed_through_unix_ms=1_290_000,
    closed_trade_count=30,
    net_expectancy_after_costs_pct=1.5,
)
```

Prove timestamp/count validation, finite signed expectancy, `None` expectancy allowed, frozen dataclass.

Use this explicit policy fixture in all regime tests:

```python
RegimePolicy(
    version="regime-v1-test",
    max_source_age_ms=30_000,
    min_window_seconds=300.0,
    min_candidate_samples=5,
    dead_max_candidate_rate_per_hour=2.0,
    weak_min_candidate_rate_per_hour=8.0,
    hot_min_candidate_rate_per_hour=20.0,
    dead_max_executable_fraction=0.10,
    weak_min_executable_fraction=0.50,
    hot_min_executable_fraction=0.80,
    weak_min_median_liquidity_usd=25_000.0,
    hot_min_median_liquidity_usd=75_000.0,
    weak_min_median_volume_m5_usd=5_000.0,
    hot_min_median_volume_m5_usd=20_000.0,
    min_performance_sample_count=20,
    dead_performance_expectancy_pct=-5.0,
    weak_performance_expectancy_pct=0.0,
)
```

Prove non-empty version, finite/non-negative market thresholds, integer sample thresholds, fraction bounds, ordered dead/weak/hot bands, ordered weak/hot liquidity/volume thresholds, and finite ordered performance thresholds.

Construct `RegimeFinding` and `RegimeAssessment`; prove both frozen. Assessment validation must require non-empty policy version, valid enum values, non-negative timestamps/counts, finite derived values, optional source age/executable fraction/performance values, executable fraction bounds, and `performance_applied` boolean.

Assert assessment fields do not contain:

```text
trade_intent
side
notional
position_size
wallet
order
fill
signer
transaction
realized_pnl
mfe_pct
mae_pct
```

- [ ] **Step 2: Verify RED**

Open/refresh the stacked draft PR and run full CI. Expected Python failure: `shreks_brain.regime.models` does not exist. Rust/workspace/repository safety remain green.

- [ ] **Step 3: Implement minimal immutable models**

Create `python/src/shreks_brain/regime/models.py` with dependency-free validation helpers scoped to this package. Do not modify existing B2/setup models.

`RegimeAssessment` fields must be exactly:

```python
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

- [ ] **Step 4: Verify GREEN**

Run full repository CI. Expected all jobs green.

- [ ] **Step 5: Commit evidence**

Record RED/GREEN commit SHAs and CI run IDs in the PR body or plan verification section without changing production semantics.

---

### Task 2: Pure regime classifier and performance overlay

**Files:**
- Create: `python/src/shreks_brain/regime/engine.py`
- Create: `python/tests/test_regime_engine.py`

**Interfaces:**
- Consumes Task 1 types.
- Produces:

```python
def assess_regime(
    market: RegimeMarketWindow,
    policy: RegimePolicy,
    performance: RecentStrategyPerformance | None = None,
) -> RegimeAssessment:
    ...
```

- [ ] **Step 1: Write the failing classifier tests**

Create `python/tests/test_regime_engine.py` with canonical market/policy/performance fixtures.

Prove derived metrics exactly:

```python
window_seconds == (source_observed_at_unix_ms - window_started_at_unix_ms) / 1000
candidate_rate_per_hour == candidate_count / window_seconds * 3600
executable_fraction == executable_candidate_count / candidate_count
```

Prove point-in-time/data-quality gates:

1. source after `as_of` -> base/final `DEAD`, `SOURCE_AFTER_AS_OF`, `source_age_ms is None`;
2. source age above policy max -> `DEAD / SOURCE_DATA_TOO_OLD`;
3. window below minimum -> `DEAD / WINDOW_TOO_SHORT`;
4. zero candidates -> `DEAD / NO_CANDIDATES`, executable fraction `None`;
5. sample below minimum -> `DEAD / CANDIDATE_SAMPLE_TOO_SMALL`;
6. missing median liquidity -> `DEAD / MEDIAN_LIQUIDITY_UNKNOWN`;
7. missing median 5m volume -> `DEAD / MEDIAN_VOLUME_M5_UNKNOWN`.

Prove market classification boundaries:

8. candidate rate exactly dead maximum -> `DEAD / OPPORTUNITY_RATE_DEAD`;
9. executable fraction exactly dead maximum -> `DEAD / EXECUTABLE_FRACTION_DEAD`;
10. each market metric independently below weak threshold -> `WEAK` with its matching reason;
11. equality at each weak minimum passes that weak check;
12. all four metrics exactly at hot minima -> `HOT / ALL_HOT_MARKET_THRESHOLDS_PASSED`;
13. healthy but not all-hot mix -> `NORMAL / NORMAL_MIXED_MARKET`.

Prove performance overlay:

14. `performance=None` leaves base regime unchanged and appends `PERFORMANCE_UNAVAILABLE`;
15. performance later than `as_of` -> final `DEAD / PERFORMANCE_AFTER_AS_OF`;
16. performance later than market source but not `as_of` -> final `DEAD / PERFORMANCE_AFTER_MARKET_SOURCE`;
17. insufficient closed-trade sample leaves base unchanged and records `PERFORMANCE_SAMPLE_INSUFFICIENT`;
18. missing expectancy leaves base unchanged and records `PERFORMANCE_EXPECTANCY_UNKNOWN`;
19. sufficiently sampled expectancy exactly at dead floor -> final `DEAD`, `performance_applied=True`;
20. sufficiently sampled expectancy below weak floor -> HOT/NORMAL downgrades to `WEAK`, `performance_applied=True`;
21. weak performance cannot make base `DEAD` less conservative;
22. strong performance never upgrades `WEAK` or `NORMAL` to `HOT`;
23. expectancy exactly at weak floor does not downgrade;
24. repeated equal calls return equal assessments;
25. deterministic multi-finding order matches spec stage order.

- [ ] **Step 2: Verify RED**

Run full PR CI. Expected Python failure only because `shreks_brain.regime.engine` / `assess_regime` is absent.

- [ ] **Step 3: Implement minimal evaluator**

Implement this exact stage order in `engine.py`:

```text
derive timestamp-safe metrics
critical source/data-quality gates
base DEAD market thresholds
base WEAK market thresholds
base HOT-all / NORMAL-mixed resolution
performance timestamp integrity
performance sample/expectancy completeness
performance downgrade-only overlay
assessment construction
```

Do not use a weighted score. Do not query wall clock, SQLite, providers, setup evaluators, or future-outcome tables.

When source is future-dated, expose `source_age_ms=None` but retain safe window/candidate-derived metrics where possible. Critical data-quality blockers dominate the base regime.

For multiple base market weaknesses, append all applicable weak/dead findings in fixed metric order rather than short-circuiting after the first; final base label remains the most conservative implied state.

- [ ] **Step 4: Verify GREEN**

Run full repository CI. Expected all jobs green and all existing setup/B2 behavior unchanged.

- [ ] **Step 5: Commit evidence**

Record exact RED/GREEN SHAs and CI IDs.

---

### Task 3: Stable package API, README, and exact-head seal

**Files:**
- Create: `python/src/shreks_brain/regime/__init__.py`
- Create: `python/tests/test_regime_public_api.py`
- Modify: `README.md`
- Modify: this plan only for non-self-referential predecessor verification evidence

**Interfaces:**
- Stable imports from `shreks_brain.regime`:

```python
MarketRegime
RecentStrategyPerformance
RegimeAssessment
RegimeFinding
RegimeMarketWindow
RegimePolicy
RegimeReasonCode
assess_regime
```

- [ ] **Step 1: Write failing public API tests**

Import every stable symbol from `shreks_brain.regime`. Construct one HOT market assessment with explicit policy and prove:

- `assess_regime` is callable;
- result is `RegimeAssessment`;
- final/base labels are `HOT` without negative performance overlay;
- existing setup entry points remain importable from `shreks_brain.setups`;
- no execution/future-outcome authority exists in `RegimeAssessment` fields.

- [ ] **Step 2: Verify RED**

Run full CI. Expected Python failure only because `shreks_brain.regime` package-level exports are absent.

- [ ] **Step 3: Export stable API**

Create `regime/__init__.py`, importing model types and `assess_regime`. Define deterministic `__all__` containing only the stable symbols above.

- [ ] **Step 4: Verify package GREEN**

Run full repository CI.

- [ ] **Step 5: Document regime semantics**

Add a README section explaining:

- source-order gap repair;
- B2 remains `b2-v1`;
- HOT/NORMAL/WEAK/DEAD are explainable global environment labels;
- opportunity rate, executable breadth, median liquidity, and median 5m volume define base regime;
- critical data-quality failures classify `DEAD` fail-closed;
- sufficiently sampled recent after-cost strategy expectancy can only downgrade;
- no production thresholds are provided;
- regime is not a trade instruction and has no execution authority.

- [ ] **Step 6: Documentation-head verification**

Run full CI and record the verified predecessor head/run in this plan. Do not attempt to write the final branch SHA into a tracked file.

- [ ] **Step 7: Immutable final seal**

After the last tracked-file commit, run fresh exact-head full CI. Record the actual final SHA/run only in draft-PR metadata so the branch is not mutated after verification. Audit the diff against B5 and keep PR draft/unmerged.

## Self-Review

- Spec coverage: Tasks 1–3 cover all model, point-in-time, base classification, downgrade-only performance, public API, documentation, and no-execution requirements.
- Placeholder scan: no `TBD`, `TODO`, “similar to”, or unspecified implementation steps remain.
- Type consistency: every Task 2/3 interface is defined in Task 1 or explicitly produced by the task.
- Scope remains one pure regime subsystem; no storage aggregation, wallet intelligence, scoring, decision, risk, paper, or execution work is hidden here.
