# Phase B7 Deterministic Score Design

**Project:** Shreks  
**Repository:** `Dtwosam/Shreks`  
**Branch:** `feat/phase-b7-deterministic-score`  
**Base:** verified B6 head `23edc450431ede1b9d83bacef89b9e46f1c61fe0`  
**Status:** approved design, pre-implementation

## 1. Purpose

Phase B7 adds the first deterministic candidate scoring layer to the Python brain.

The source build order calls this capability **B5 Deterministic score**. The repository already used chronological phase labels B3/B4a/B4b/B5/B6 for setup and regime work, so this branch is called B7 without changing the source-of-truth meaning: this is the deterministic score that must exist before the later decision and risk engines.

The scorer exists to turn already-computed point-in-time evidence into an interpretable, reproducible research score. It does **not** decide to enter a trade and it does not bypass safety, setup eligibility, regime policy, or later risk controls.

The primary design objective is calibration discipline: score only evidence Shreks can actually observe now, expose missing evidence explicitly, and preserve enough component detail to evaluate whether each score family contributes positive expectancy after realistic costs later.

## 2. Source-of-truth constraints

B7 preserves these project rules:

- Solana-only V1.
- Python owns scoring and decision intelligence.
- B1 safety retains veto power.
- Critical uncertainty cannot become implicit bullish evidence.
- Rejected/blocked candidates remain useful research data.
- B2 remains exactly `b2-v1`; B7 does not widen the shared feature schema.
- Existing B3 Fresh Launch, B4b Graduation/Breakout, B5 First Pullback, and B6 regime behavior remain unchanged.
- Smart-wallet quality is not fabricated before Phase D wallet intelligence exists.
- Scoring is deterministic, versioned, point-in-time safe, and explainable.
- There are no production scoring weights, normalization bands, or entry thresholds in code.
- B7 adds no decision, sizing, paper-fill, wallet/signing, transaction, or live-money authority.

## 3. Chosen architecture

Create a focused package:

```text
python/src/shreks_brain/scoring/
    __init__.py
    models.py
    engine.py
```

B7 consumes three already-normalized inputs:

1. one B2 `FeatureVector`;
2. one explicit setup assessment from the existing setup package;
3. one B6 `RegimeAssessment`.

B7 returns one immutable `ScoreAssessment`.

The scorer does not read SQLite, providers, wall clock, outcome checkpoints, realized PnL, paper fills, or future observations. It has no side effects.

### Rejected alternatives

**Setup-specific scorers** were rejected because they duplicate normalization and weighting logic across setup families and make cross-setup research harder to compare.

**One monolithic raw-feature formula** was rejected because it obscures which evidence family created a score and makes missing-data behavior and later ablation research less auditable.

**Adding wallet quality now** was rejected because the current repository has no statistically credible wallet-profile/independence pipeline. A missing future feature family must not be represented by an invented constant or a fake zero.

## 4. Score families

Score-v1 has exactly four candidate-level families, each represented on a `0..100` scale when computable:

1. `safety_quality_score`
2. `money_flow_score`
3. `setup_quality_score`
4. `liquidity_executability_score`

The final `total_score` is an explicit weighted sum of these four families.

The B6 market regime is carried into `ScoreAssessment` for auditability but is **not** a fifth weighted family in score-v1. The same global liquidity and volume conditions already influence several candidate features, so weighting regime again here would create avoidable double counting. The later Decision Engine owns regime-specific entry permission and threshold policy.

### 4.1 Safety quality

B1 hard/data-quality decisions remain separate from scoring. The safety subscore uses only the four current B2 soft-safety booleans:

- `safety_liquidity_weak`
- `safety_holder_concentration_elevated`
- `safety_creator_concentration_elevated`
- `safety_exit_price_impact_elevated`

Start from `100`. Subtract the explicit policy penalty associated with each active soft flag, then clamp to `[0, 100]`.

The scorer does **not** use `safety_soft_finding_count` as an additional penalty because that would double-count the same soft findings already represented by the four booleans.

A candidate with B1 `REJECT` or `INCOMPLETE` may still receive a research score if the score inputs are otherwise complete. The assessment must preserve the non-PASS `safety_decision` and append a stable research-only finding. A high research score cannot change or reinterpret the B1 decision.

### 4.2 Money flow

Money flow uses exactly three B2 fields:

- `volume_velocity_ratio`
- `buy_fraction_m5`
- `buy_pressure_acceleration`

Each metric is mapped independently through an explicit policy range to `0..100` with a clamped piecewise-linear transform:

```text
value <= zero_floor  -> 0
value >= full_ceiling -> 100
between -> linear interpolation
```

The family score is the arithmetic mean of the three normalized values.

If any required money-flow metric is `None`, `money_flow_score` is `None`. Missing evidence is never converted to zero.

### 4.3 Setup quality

`setup_quality_score` is the existing setup assessment's `confirmation_score` passed through unchanged.

B7 accepts exactly the three currently implemented setup assessment families:

- `FreshLaunchAssessment`
- `GraduationBreakoutAssessment`
- `FirstPullbackAssessment`

All three already expose deterministic `0..100` confirmation completeness. B7 does not reinterpret their individual confirmations.

`BLOCKED` and `WATCH` setup assessments may still be scored for research. `ScoreAssessment` preserves `setup_name`, `setup_policy_version`, and `setup_state`, and appends a research-only finding when state is not `READY`. The later Decision Engine must independently require whatever setup state its policy permits.

### 4.4 Liquidity / executability

This family uses:

- `liquidity_usd` — higher is better within an explicit policy range;
- `exit_price_impact_pct` — lower is better within an explicit inverse policy range.

Liquidity uses the same upward clamped linear normalization as money-flow metrics.

Exit impact uses an inverse clamped transform:

```text
value <= full_score_max -> 100
value >= zero_score_min -> 0
between -> linear interpolation downward
```

The family score is the arithmetic mean of the two normalized values.

If either required metric is `None`, `liquidity_executability_score` is `None`.

## 5. Score policy

`ScorePolicy` is immutable and fully explicit. B7 ships no production instance.

Required fields:

```python
version: str
required_feature_schema_version: str

safety_weight: float
money_flow_weight: float
setup_quality_weight: float
liquidity_executability_weight: float

safety_liquidity_weak_penalty: float
safety_holder_concentration_elevated_penalty: float
safety_creator_concentration_elevated_penalty: float
safety_exit_price_impact_elevated_penalty: float

volume_velocity_zero: float
volume_velocity_full: float
buy_fraction_m5_zero: float
buy_fraction_m5_full: float
buy_pressure_acceleration_zero: float
buy_pressure_acceleration_full: float

liquidity_usd_zero: float
liquidity_usd_full: float
exit_price_impact_full: float
exit_price_impact_zero: float
```

Validation rules:

- `version` and `required_feature_schema_version` are non-empty;
- every weight is finite and in `[0, 1]`;
- at least one weight is positive;
- the four weights sum to `1.0` within a strict floating-point tolerance;
- safety penalties are finite in `[0, 100]`;
- every upward normalization requires `full > zero`;
- buy-fraction bounds remain within `[0, 1]`;
- liquidity normalization values are finite and non-negative;
- exit-impact normalization values are finite and non-negative with `exit_price_impact_zero > exit_price_impact_full`.

Zero family weights are allowed for controlled ablation research. They do not renormalize the other configured weights; the configured weights already sum to one.

## 6. Missing-data semantics

Each family is computed independently when possible.

For the final weighted score:

- every family with a **positive** policy weight must have a computable family score;
- if any positive-weight family is `None`, `total_score` is `None`;
- a missing zero-weight family does not block `total_score`;
- weights are never silently renormalized around missing evidence;
- no missing value is converted to zero.

This preserves the economic meaning of a policy across candidates and avoids making a token appear stronger simply because a difficult-to-observe family disappeared.

## 7. Point-in-time and compatibility gates

The score engine validates that its three inputs describe one coherent historical decision point.

The following conditions make `total_score=None` and append deterministic findings:

1. `features.schema_version != policy.required_feature_schema_version`;
2. `features.source_observed_at_unix_ms > features.as_of_unix_ms`;
3. `features.source_age_ms != features.as_of_unix_ms - features.source_observed_at_unix_ms`;
4. `setup.as_of_unix_ms != features.as_of_unix_ms`;
5. `setup.feature_schema_version != features.schema_version`;
6. `regime.as_of_unix_ms != features.as_of_unix_ms`.

These are compatibility/data-integrity failures, not opportunities to guess.

The engine does not require the regime market-source timestamp to equal the token feature-source timestamp because the regime is an independently aggregated global window. It does require the same decision `as_of` time.

## 8. Stable domain model

### 8.1 Score reason codes

`ScoreReasonCode` uses this deterministic order:

```text
FEATURE_SCHEMA_UNSUPPORTED
FEATURE_SOURCE_AFTER_AS_OF
FEATURE_SOURCE_AGE_MISMATCH
SETUP_AS_OF_MISMATCH
SETUP_FEATURE_SCHEMA_MISMATCH
REGIME_AS_OF_MISMATCH
SAFETY_NOT_PASS_RESEARCH_ONLY
SETUP_NOT_READY_RESEARCH_ONLY
VOLUME_VELOCITY_UNKNOWN
BUY_FRACTION_M5_UNKNOWN
BUY_PRESSURE_ACCELERATION_UNKNOWN
LIQUIDITY_UNKNOWN
EXIT_PRICE_IMPACT_UNKNOWN
SAFETY_SOFT_PENALTIES_APPLIED
TOTAL_SCORE_INCOMPLETE
TOTAL_SCORE_AVAILABLE
```

Compatibility findings always come first, followed by research-only context, missing component evidence in family/metric order, then score-completion status.

### 8.2 Finding

```python
@dataclass(frozen=True, slots=True)
class ScoreFinding:
    code: ScoreReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None
```

### 8.3 Assessment

`ScoreAssessment` fields are exactly:

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

All numeric score values must be finite and within `[0, 100]` when present.

There is intentionally no wallet-quality field in score-v1. Wallet intelligence can become a new versioned score family only after Phase D creates point-in-time wallet evidence and proves it useful.

There is also intentionally no `confidence`, `win_probability`, `expected_return`, entry threshold, or position size. `total_score` is an interpretable deterministic ranking/decision input, not a profitability claim.

## 9. Scoring algorithm

`score_candidate(features, setup, regime, policy)` executes in this fixed order:

```text
validate input compatibility / point-in-time coherence
record safety/setup research-only context
compute safety quality
normalize money-flow metrics and compute money-flow family
copy setup confirmation score
normalize liquidity/executability metrics and compute family
compute total only if all positive-weight families are available
append completion finding
construct immutable ScoreAssessment
```

### 9.1 Linear normalization

For an upward metric:

```python
if value <= zero:
    score = 0.0
elif value >= full:
    score = 100.0
else:
    score = (value - zero) / (full - zero) * 100.0
```

For inverse exit impact:

```python
if value <= full:
    score = 100.0
elif value >= zero:
    score = 0.0
else:
    score = (zero - value) / (zero - full) * 100.0
```

Equality behavior is therefore explicit and testable.

### 9.2 Weighted total

When every positive-weight family is available:

```python
total_score = (
    safety_quality_score * safety_weight
    + money_flow_score * money_flow_weight
    + setup_quality_score * setup_quality_weight
    + liquidity_executability_score * liquidity_executability_weight
)
```

A zero-weight family contributes exactly zero and need not be available.

The result is bounded to `[0, 100]` by validated component ranges and weights; implementation may clamp only for floating-point edge noise, not to hide invalid inputs.

## 10. Regime semantics

B6 `RegimeAssessment` is input context, not a score booster.

B7 records:

- `regime_policy_version`
- final `market_regime`

It does not award points for `HOT` or subtract points for `WEAK/DEAD`.

This separation is intentional. The later Decision Engine can apply explicit policy such as disabling new entries in `DEAD`, increasing score requirements in `WEAK`, or allowing a strategy only in selected regimes. Those rules are entry policy, not candidate-score evidence.

## 11. Safety and setup semantics

B7 must be useful for both operation and research without blurring authority:

- safety `PASS` is not required to calculate a research score;
- setup `READY` is not required to calculate a research score;
- the assessment always preserves safety decision and setup state;
- non-PASS safety and non-READY setup append explicit research-only findings;
- no score can mutate a safety or setup assessment;
- the future Decision Engine must independently enforce safety/setup/regime policy.

This prevents survivorship/selection bias while preserving hard control boundaries.

## 12. Public API

Stable imports from `shreks_brain.scoring` will be:

```python
ScoreAssessment
ScoreFinding
ScorePolicy
ScoreReasonCode
score_candidate
```

No production policy constant is exported.

## 13. Testing strategy

B7 is implemented strict RED -> GREEN.

### Model/policy tests

Pin:

- exact reason-code order;
- immutable/frozen models;
- score bounds;
- policy string/number validation;
- weight bounds and sum-to-one rule;
- zero-weight ablation support;
- upward/inverse normalization range ordering;
- no wallet-quality, decision, risk, execution, outcome, or PnL fields.

### Engine tests

Pin:

- feature-schema compatibility;
- future feature-source rejection;
- source-age arithmetic mismatch;
- setup/feature timestamp mismatch;
- setup feature-schema mismatch;
- regime/feature timestamp mismatch;
- exact normalization equality at zero/full boundaries;
- interpolation arithmetic;
- each safety soft-flag penalty and clamping;
- no double-penalty from `safety_soft_finding_count`;
- money-flow mean arithmetic;
- setup confirmation pass-through for all three setup families;
- liquidity/executability inverse impact arithmetic;
- missing component behavior;
- zero-weight missing-family behavior;
- no weight renormalization;
- exact weighted-total arithmetic;
- blocked/WATCH and safety-non-PASS research scoring;
- regime carried but not weighted;
- deterministic finding order;
- repeated equal inputs return equal assessments.

### Public API regression tests

Prove:

- stable `shreks_brain.scoring` imports;
- B1/B2/B3/B4b/B5/B6 public APIs remain importable;
- scoring output has no `TradeDecision`, `TradeIntent`, side, notional, size, wallet, order, fill, signer, transaction, realized-PnL, MFE, or MAE authority.

Full repository CI must remain green before B7 is sealed.

## 14. Out of scope

B7 does not implement:

- Smart Wallet Cluster;
- wallet profiles or wallet-quality scoring;
- entry thresholds;
- `TradeDecision` or `TradeIntent`;
- `REJECT/WATCH/ENTER/HOLD/REDUCE/EXIT` action selection;
- risk limits or position sizing;
- portfolio state;
- paper execution/fills;
- exit management;
- backtesting/model training;
- wallet/signing/Jupiter transaction submission;
- live trading.

Those remain later phases in the required build progression.

## 15. Completion criteria

B7 is complete only when:

1. the immutable scoring domain and explicit policy are implemented;
2. the pure scorer passes all point-in-time, normalization, missing-data, family, and weighted-total tests;
3. all three current setup families are supported without modifying them;
4. B6 regime context is preserved without score double-counting;
5. absent wallet intelligence is not fabricated;
6. no production weights/thresholds exist;
7. no decision/risk/execution authority appears in scoring models;
8. README documents the semantics;
9. full exact-head CI passes;
10. the final diff is audited against verified B6 and the draft PR remains unmerged.