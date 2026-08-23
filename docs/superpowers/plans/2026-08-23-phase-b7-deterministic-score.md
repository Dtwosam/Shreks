# Phase B7 Deterministic Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, versioned, explainable deterministic candidate scorer that combines current safety, money-flow, setup-quality, and liquidity/executability evidence without fabricating wallet intelligence or creating trade authority.

**Architecture:** Create a focused `shreks_brain.scoring` package beside unchanged B2/setup/regime code. Task 1 establishes immutable score/policy domain models. Task 2 adds the pure scorer with point-in-time compatibility gates, explicit normalizers, missing-data semantics, and research-only scoring of blocked candidates. Task 3 seals package exports, documentation, and exact-head verification.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, pytest, existing repository CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b7-deterministic-score-design.md`

## Global Constraints

- Base is verified B6 head `23edc450431ede1b9d83bacef89b9e46f1c61fe0`.
- Existing B2 remains exactly `b2-v1`.
- Score-v1 has exactly four candidate families: safety quality, money flow, setup quality, liquidity/executability.
- B6 regime is audit context and is not a weighted score family.
- Current wallet quality is absent rather than zero-filled or fabricated.
- B1 safety decision and setup state are preserved independently from the score.
- Non-PASS/non-READY candidates may receive research scores but cannot be reclassified by B7.
- Missing positive-weight family evidence makes `total_score=None`; weights are never renormalized.
- All weights, penalties, and normalization ranges live in an explicit versioned `ScorePolicy`; no production instance is allowed.
- No SQLite/provider/wall-clock/outcome/PnL reads from scoring code.
- No entry threshold, `TradeDecision`, `TradeIntent`, sizing, risk, paper fill, wallet/signing, transaction submission, or live execution.
- Existing B1/B2/B3/B4b/B5/B6 behavior remains unchanged.

---

### Task 1: Immutable scoring domain and policy contract

**Files:**
- Create: `python/src/shreks_brain/scoring/models.py`
- Create: `python/tests/test_scoring_models.py`

**Interfaces:**
- Produces:

```python
class ScoreReasonCode(StrEnum): ...

@dataclass(frozen=True, slots=True)
class ScoreFinding: ...

@dataclass(frozen=True, slots=True)
class ScorePolicy: ...

@dataclass(frozen=True, slots=True)
class ScoreAssessment: ...
```

- [ ] **Step 1: Write the failing model-contract test**

Create `python/tests/test_scoring_models.py` importing all Task 1 symbols from `shreks_brain.scoring.models`.

Pin exact reason-code order:

```python
assert tuple(item.value for item in ScoreReasonCode) == (
    "FEATURE_SCHEMA_UNSUPPORTED",
    "FEATURE_SOURCE_AFTER_AS_OF",
    "FEATURE_SOURCE_AGE_MISMATCH",
    "SETUP_AS_OF_MISMATCH",
    "SETUP_FEATURE_SCHEMA_MISMATCH",
    "REGIME_AS_OF_MISMATCH",
    "SAFETY_NOT_PASS_RESEARCH_ONLY",
    "SETUP_NOT_READY_RESEARCH_ONLY",
    "VOLUME_VELOCITY_UNKNOWN",
    "BUY_FRACTION_M5_UNKNOWN",
    "BUY_PRESSURE_ACCELERATION_UNKNOWN",
    "LIQUIDITY_UNKNOWN",
    "EXIT_PRICE_IMPACT_UNKNOWN",
    "SAFETY_SOFT_PENALTIES_APPLIED",
    "TOTAL_SCORE_INCOMPLETE",
    "TOTAL_SCORE_AVAILABLE",
)
```

Use this explicit policy fixture throughout B7 tests:

```python
ScorePolicy(
    version="score-v1-test",
    required_feature_schema_version="b2-v1",
    safety_weight=0.20,
    money_flow_weight=0.30,
    setup_quality_weight=0.30,
    liquidity_executability_weight=0.20,
    safety_liquidity_weak_penalty=20.0,
    safety_holder_concentration_elevated_penalty=25.0,
    safety_creator_concentration_elevated_penalty=15.0,
    safety_exit_price_impact_elevated_penalty=30.0,
    volume_velocity_zero=0.5,
    volume_velocity_full=2.0,
    buy_fraction_m5_zero=0.40,
    buy_fraction_m5_full=0.70,
    buy_pressure_acceleration_zero=-0.10,
    buy_pressure_acceleration_full=0.20,
    liquidity_usd_zero=10_000.0,
    liquidity_usd_full=100_000.0,
    exit_price_impact_full=1.0,
    exit_price_impact_zero=8.0,
)
```

Prove:

- policy/version strings are non-empty;
- each weight is finite and within `[0, 1]`;
- weights must sum to 1 within the implementation tolerance and at least one must be positive;
- all safety penalties are finite within `[0, 100]`;
- every upward range requires `full > zero`;
- buy-fraction endpoints stay in `[0, 1]`;
- liquidity endpoints are finite/non-negative;
- exit-impact endpoints are finite/non-negative with `zero > full`;
- zero-weight ablation policies remain valid if total configured weight is still one;
- dataclasses are frozen.

Construct a canonical assessment:

```python
ScoreAssessment(
    policy_version="score-v1-test",
    feature_schema_version="b2-v1",
    as_of_unix_ms=1_000_000,
    source_observed_at_unix_ms=995_000,
    safety_decision=SafetyDecision.PASS,
    setup_name="fresh_launch_continuation",
    setup_policy_version="fresh-test",
    setup_state=SetupState.READY,
    regime_policy_version="regime-test",
    market_regime=MarketRegime.NORMAL,
    safety_quality_score=90.0,
    money_flow_score=75.0,
    setup_quality_score=80.0,
    liquidity_executability_score=70.0,
    total_score=78.5,
    findings=(
        ScoreFinding(
            code=ScoreReasonCode.TOTAL_SCORE_AVAILABLE,
            message="all positive-weight score families are available",
        ),
    ),
)
```

Prove model validation requires correct enum types, non-empty names/versions, non-negative timestamps, source not after assessment time, and every present score finite in `[0, 100]`.

Assert `ScoreAssessment` fields contain none of:

```text
wallet_quality
confidence
win_probability
expected_return
entry_threshold
trade_decision
trade_intent
side
notional
position_size
risk
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

Open the stacked draft PR after this RED commit. Run full CI.

Expected Python failure:

```text
ModuleNotFoundError: No module named 'shreks_brain.scoring'
```

Rust/workspace/repository safety must remain green.

- [ ] **Step 3: Implement minimal immutable models**

Create `python/src/shreks_brain/scoring/models.py` with only dependency-light dataclasses/enums and validation helpers.

`ScorePolicy` fields must exactly match the spec.

`ScoreAssessment` fields must exactly be:

```python
policy_version: str
feature_schema_version: str
as_of_unix_ms: int
source_observed_at_unix_ms: int
safety_decision: SafetyDecision
setup_name: str
setup_policy_version: str
setup_state: SetupState
regime_policy_version: str
market_regime: MarketRegime
safety_quality_score: float
money_flow_score: float | None
setup_quality_score: float
liquidity_executability_score: float | None
total_score: float | None
findings: tuple[ScoreFinding, ...]
```

Use `math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12)` for policy weight-sum validation.

Do not create a default policy constant.

- [ ] **Step 4: Verify GREEN**

Run full repository CI. Expected all jobs green.

- [ ] **Step 5: Record Task 1 evidence**

Record RED/GREEN SHA and CI IDs in the plan verification section or PR body without changing production semantics.

---

### Task 2: Pure deterministic scoring engine

**Files:**
- Create: `python/src/shreks_brain/scoring/engine.py`
- Create: `python/tests/test_scoring_engine.py`

**Interfaces:**
- Consumes:

```python
FeatureVector
FreshLaunchAssessment | GraduationBreakoutAssessment | FirstPullbackAssessment
RegimeAssessment
ScorePolicy
```

- Produces:

```python
def score_candidate(
    features: FeatureVector,
    setup: FreshLaunchAssessment | GraduationBreakoutAssessment | FirstPullbackAssessment,
    regime: RegimeAssessment,
    policy: ScorePolicy,
) -> ScoreAssessment:
    ...
```

- [ ] **Step 1: Write canonical fixtures**

In `python/tests/test_scoring_engine.py`, create a canonical B2 vector with all B7 inputs present:

```python
FeatureVector(
    schema_version="b2-v1",
    as_of_unix_ms=1_000_000,
    source_observed_at_unix_ms=995_000,
    source_age_ms=5_000,
    safety_policy_version="safety-test",
    safety_decision=SafetyDecision.PASS,
    token_age_seconds=180.0,
    price_usd=0.01,
    liquidity_usd=55_000.0,
    liquidity_change_5m_pct=10.0,
    exit_price_impact_pct=4.5,
    volume_m5_usd=20_000.0,
    volume_h1_usd=80_000.0,
    volume_velocity_ratio=1.25,
    tx_count_m5=50,
    tx_count_h1=200,
    buy_fraction_m5=0.55,
    buy_fraction_h1=0.52,
    buy_sell_ratio_m5=1.22,
    buy_sell_ratio_h1=1.08,
    buy_pressure_acceleration=0.05,
    return_1m_pct=4.0,
    return_5m_pct=12.0,
    return_15m_pct=20.0,
    momentum_acceleration_1m_vs_5m=1.6,
    distance_from_local_high_pct=-3.0,
    range_position_pct=80.0,
    safety_soft_finding_count=0,
    safety_liquidity_weak=False,
    safety_holder_concentration_elevated=False,
    safety_creator_concentration_elevated=False,
    safety_exit_price_impact_elevated=False,
    missing_features=(),
)
```

Create a canonical Fresh Launch assessment:

```python
FreshLaunchAssessment(
    setup_name=FRESH_LAUNCH_SETUP_NAME,
    policy_version="fresh-test",
    feature_schema_version="b2-v1",
    as_of_unix_ms=1_000_000,
    state=SetupState.READY,
    confirmation_score=80.0,
    confirmations_passed=8,
    confirmations_required=9,
    findings=(),
)
```

Create canonical Graduation/Breakout and First Pullback assessment fixtures with the same `as_of_unix_ms`, `b2-v1`, `READY`, and `confirmation_score=80.0`, filling their additional optional research fields with valid values/`None` as allowed by their existing constructors.

Create a canonical B6 assessment:

```python
RegimeAssessment(
    policy_version="regime-test",
    as_of_unix_ms=1_000_000,
    source_observed_at_unix_ms=990_000,
    window_started_at_unix_ms=630_000,
    source_age_ms=10_000,
    window_seconds=360.0,
    candidate_count=12,
    candidate_rate_per_hour=120.0,
    executable_fraction=0.75,
    median_liquidity_usd=80_000.0,
    median_volume_m5_usd=25_000.0,
    base_regime=MarketRegime.NORMAL,
    regime=MarketRegime.NORMAL,
    performance_sample_count=None,
    performance_net_expectancy_after_costs_pct=None,
    performance_applied=False,
    findings=(),
)
```

- [ ] **Step 2: Write failing point-in-time and compatibility tests**

Import `score_candidate` from `shreks_brain.scoring.engine`; this import must fail before implementation.

Pin each compatibility gate independently:

```text
FEATURE_SCHEMA_UNSUPPORTED
FEATURE_SOURCE_AFTER_AS_OF
FEATURE_SOURCE_AGE_MISMATCH
SETUP_AS_OF_MISMATCH
SETUP_FEATURE_SCHEMA_MISMATCH
REGIME_AS_OF_MISMATCH
```

For each case assert `total_score is None` and the expected finding appears in deterministic stage order.

- [ ] **Step 3: Write failing normalization and safety tests**

Using the explicit Task 1 policy, prove upward normalization:

```text
at zero endpoint -> 0
at full endpoint -> 100
midpoint -> 50
below zero -> 0
above full -> 100
```

Prove inverse exit-impact normalization with the equivalent reversed behavior.

Prove each active safety soft flag subtracts only its configured penalty. Prove all four penalties sum and clamp at zero. Prove changing `safety_soft_finding_count` alone does not change `safety_quality_score`.

- [ ] **Step 4: Write failing family/total arithmetic tests**

Canonical metric values above are midpoints under the test policy, so assert:

```python
money_flow_score == 50.0
liquidity_executability_score == 50.0
setup_quality_score == 80.0
safety_quality_score == 100.0
```

Assert exact weighted total:

```python
total_score == 100.0 * 0.20 + 50.0 * 0.30 + 80.0 * 0.30 + 50.0 * 0.20
# 69.0
```

- [ ] **Step 5: Write failing missing-evidence tests**

For each missing money-flow metric, assert its stable UNKNOWN reason and `money_flow_score is None`.

For missing `liquidity_usd` or `exit_price_impact_pct`, assert the stable UNKNOWN reason and `liquidity_executability_score is None`.

With any missing **positive-weight** family, assert `total_score is None` and final `TOTAL_SCORE_INCOMPLETE`.

Create an ablation policy with the missing family weight set to zero and the remaining weights adjusted to sum to one. Assert the missing zero-weight family does not block a total and its absent score remains `None`; there is no renormalization beyond the explicit configured weights.

- [ ] **Step 6: Write failing research-state tests**

Prove B1 `REJECT` and `INCOMPLETE` vectors can still receive a numeric research total when all score evidence is present, while preserving `safety_decision` and appending `SAFETY_NOT_PASS_RESEARCH_ONLY`.

Prove `BLOCKED` and `WATCH` setup assessments can still receive a numeric research total, preserve `setup_state`, and append `SETUP_NOT_READY_RESEARCH_ONLY`.

Prove changing only B6 `regime` among `HOT/NORMAL/WEAK/DEAD` leaves all family scores and `total_score` identical while changing the stored `market_regime`.

- [ ] **Step 7: Write failing setup-family compatibility tests**

Parameterize the three setup assessment fixtures and prove `setup_quality_score == setup.confirmation_score`, with the correct setup name/policy/state copied to the result for each family.

- [ ] **Step 8: Write failing determinism/finding-order tests**

Create an input with:

- safety not PASS;
- setup not READY;
- missing volume velocity;
- missing buy fraction;
- missing exit impact.

Assert exact finding code order:

```text
SAFETY_NOT_PASS_RESEARCH_ONLY
SETUP_NOT_READY_RESEARCH_ONLY
VOLUME_VELOCITY_UNKNOWN
BUY_FRACTION_M5_UNKNOWN
EXIT_PRICE_IMPACT_UNKNOWN
TOTAL_SCORE_INCOMPLETE
```

Call twice with equal inputs and assert equal assessments.

- [ ] **Step 9: Verify RED**

Run full PR CI. Expected Python failure only because `shreks_brain.scoring.engine` / `score_candidate` is absent. Rust/workspace/repository safety remain green.

- [ ] **Step 10: Implement minimal scorer**

Create `python/src/shreks_brain/scoring/engine.py`.

Use this fixed algorithm order:

```text
compatibility findings
research-only safety/setup findings
safety-quality score
money-flow normalization + family mean
setup confirmation-score pass-through
liquidity/executability normalization + family mean
positive-weight availability gate
direct configured weighted sum
completion finding
assessment construction
```

Implement focused private helpers:

```python
def _normalize_up(value: float, zero: float, full: float) -> float: ...
def _normalize_inverse(value: float, full: float, zero: float) -> float: ...
def _mean(values: tuple[float, ...]) -> float: ...
```

Do not query wall clock, SQLite, providers, outcome checkpoints, paper trades, or future PnL.

Do not import or create decision/risk/execution types.

- [ ] **Step 11: Verify GREEN**

Run full repository CI. Expected all jobs green and existing B1/B2/setup/regime behavior unchanged.

- [ ] **Step 12: Record Task 2 evidence**

Record exact RED/GREEN SHAs and CI IDs.

---

### Task 3: Stable package API, documentation, and immutable seal

**Files:**
- Create: `python/src/shreks_brain/scoring/__init__.py`
- Create: `python/tests/test_scoring_public_api.py`
- Modify: `README.md`
- Modify: this plan only for non-self-referential verification evidence

**Interfaces:**
- Stable imports from `shreks_brain.scoring`:

```python
ScoreAssessment
ScoreFinding
ScorePolicy
ScoreReasonCode
score_candidate
```

- [ ] **Step 1: Write failing public API test**

Create `python/tests/test_scoring_public_api.py` importing all stable symbols from `shreks_brain.scoring`.

Construct a valid explicit `ScorePolicy`, B2 vector, Fresh Launch assessment, and B6 regime assessment, then prove:

```python
assert callable(score_candidate)
assert isinstance(score_candidate(...), ScoreAssessment)
```

Prove existing public entry points remain importable from:

```text
shreks_brain.safety
shreks_brain.features
shreks_brain.setups
shreks_brain.regime
```

Inspect `dataclasses.fields(ScoreAssessment)` and assert no wallet-quality, decision, risk, execution, outcome, or PnL authority fields from the spec are present.

- [ ] **Step 2: Verify RED**

Run full CI. Expected Python failure only because package-level scoring exports are absent.

- [ ] **Step 3: Export stable API**

Create `python/src/shreks_brain/scoring/__init__.py`:

```python
from .engine import score_candidate
from .models import ScoreAssessment, ScoreFinding, ScorePolicy, ScoreReasonCode

__all__ = (
    "ScoreAssessment",
    "ScoreFinding",
    "ScorePolicy",
    "ScoreReasonCode",
    "score_candidate",
)
```

Do not export a production policy instance or entry threshold.

- [ ] **Step 4: Verify package GREEN**

Run full repository CI.

- [ ] **Step 5: Document scoring semantics**

Append a focused README section explaining:

- deterministic score is repository B7 / source build-order B5 capability;
- four score-v1 families and their 0..100 meaning;
- explicit policy normalizers/weights with no defaults;
- missing positive-weight evidence yields no total and never renormalizes;
- safety non-PASS/setup non-READY may still be scored only for research;
- regime is context, not weighted in v1;
- wallet quality is absent until Phase D evidence exists;
- score is not probability, expected return, decision, size, or trade permission;
- no execution authority exists.

- [ ] **Step 6: Record verification evidence**

Update this plan with Task 1/2/3 RED/GREEN SHAs and CI IDs plus the last verified tracked-file predecessor. Do not write the final branch SHA into a tracked file.

- [ ] **Step 7: Immutable final seal**

After the last tracked-file commit, run fresh exact-head full CI. Record actual final SHA/run only in draft-PR metadata so no verified branch mutation follows. Audit the diff against verified B6 and keep the PR draft/unmerged.

## Self-Review

- Spec coverage: Tasks 1–3 cover model/policy validation, point-in-time compatibility, every score family, missing-data semantics, setup/regime integration, public API, documentation, and no-authority constraints.
- Placeholder scan: no `TBD`, `TODO`, “similar to”, or unspecified implementation action remains.
- Type consistency: Task 2 consumes only B2/setup/B6 types already present plus Task 1 scoring types; Task 3 exports exactly the Task 1/2 public interface.
- Scope remains one pure scoring subsystem. No wallet intelligence, decision engine, risk engine, paper/live execution, or provider/storage integration is hidden in this plan.