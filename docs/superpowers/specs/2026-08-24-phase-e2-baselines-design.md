# Phase E2 Baselines Design

**Base:** sealed E1 historical replay head `6c441e13ad7c186d6356e861b45351be7f99d321`.

## Purpose

Phase E2 creates simple, reproducible comparison strategies so later models and strategy changes have meaningful behavior to beat. E2 does **not** evaluate profitability yet. It produces alternative historical replay runs over the exact E1 decision inputs and D6 future-outcome bundles; E4/E5 will later split and score those runs chronologically and after realistic costs.

The source build order calls for a deterministic V0 baseline, simple threshold variants, and random/naive baselines where useful. E2-v1 implements the deterministic V0 plus two transparent score-threshold comparisons. It deliberately does not add pseudo-random decisions: without E4 chronological validation and E5 trading metrics, a random action generator adds noise without establishing a useful scientific benchmark. A random baseline may be added later under a new baseline schema if E5 demonstrates a concrete need.

## Design principles

1. **No second trading engine.** Every baseline is expressed as an explicit `ReplayPolicySet` and executed by sealed E1 `replay_entry_decisions`.
2. **Same historical evidence.** Every baseline receives the same `ReplayDecisionInput` and `ReplayOutcomeBundle` identities.
3. **Future outcomes remain labels only.** E2 never reads outcome metrics to construct a policy variant or decision.
4. **Transparent perturbations.** E2-v1 changes only B8 score thresholds. Setup policies and B7 scoring remain unchanged.
5. **Immutable provenance.** Derived policy versions identify the baseline transformation so later evaluation can trace every decision.
6. **No profitability claim.** E2 creates comparison runs only; it computes no returns, costs, expectancy, drawdown, win rate, or promotion result.
7. **No runtime authority.** E2 creates no risk size, `TradeIntent`, paper/live fill, signer, transaction, or live-money action.

## Package boundary

Add a new parallel package:

```text
python/src/shreks_brain/baselines/
  __init__.py
  models.py
  engine.py
```

E1 remains sealed. E2 imports E1 public replay types/functions rather than modifying `shreks_brain.backtest`.

The baseline core is pure Python. It performs no SQLite, provider, filesystem, network, PyArrow, random-number, or wall-clock reads.

## Public schema and API

```python
BASELINE_SUITE_SCHEMA_VERSION = "e2-baselines-v1"

class BaselineKind(StrEnum):
    V0 = "V0"
    ZERO_SCORE_THRESHOLD = "ZERO_SCORE_THRESHOLD"
    THRESHOLD_DELTA = "THRESHOLD_DELTA"

@dataclass(frozen=True, slots=True)
class ThresholdDeltaBaselineSpec:
    name: str
    delta_points: float

@dataclass(frozen=True, slots=True)
class BaselineSuitePolicy:
    version: str
    base_replay_policies: ReplayPolicySet
    threshold_variants: tuple[ThresholdDeltaBaselineSpec, ...]

@dataclass(frozen=True, slots=True)
class BaselineReplayResult:
    name: str
    kind: BaselineKind
    threshold_delta_points: float | None
    replay_policy_set_version: str
    replay: ReplayRun

@dataclass(frozen=True, slots=True)
class BaselineSuite:
    schema_version: str
    policy_version: str
    results: tuple[BaselineReplayResult, ...]


def build_baseline_suite(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policy: BaselineSuitePolicy,
) -> BaselineSuite:
    ...
```

`__all__` must export exactly the schema constant, enum, four immutable models, and `build_baseline_suite`.

## Baseline definitions

### 1. V0

Name: `v0`.

V0 is exactly:

```python
replay_entry_decisions(
    decision_inputs,
    outcome_bundles,
    policy.base_replay_policies,
)
```

E2 must not clone or reinterpret the V0 result. Equality with a direct E1 replay is part of the contract.

### 2. Zero score threshold

Name: `zero_score_threshold`.

This baseline keeps:

- all three supplied setup policies unchanged,
- the B7 `ScorePolicy` unchanged,
- every B8 `SetupDecisionRule.enabled` flag unchanged,
- every explicit `None` regime threshold unchanged.

For each enabled numeric HOT/NORMAL/WEAK threshold, the derived B8 policy sets the threshold to `0.0`.

This baseline answers a narrow question for later E5 evaluation: does the configured **numeric score cutoff** add value beyond the existing safety/setup/regime gates and score-availability requirement?

It is intentionally **not** named “setup ready” because B8 still requires a usable B7 total score and still honors disabled setup/regime rules.

### 3. Threshold delta variants

Each caller-supplied `ThresholdDeltaBaselineSpec` applies one signed point delta to every configured numeric HOT/NORMAL/WEAK threshold:

```text
adjusted = clamp(original + delta_points, 0.0, 100.0)
```

`None` remains `None`; `enabled` remains unchanged. Setup policies and B7 scoring remain unchanged.

Examples E5 may later choose to evaluate include `-10` and `+10`, but E2 ships no production delta defaults.

The delta must be finite and non-zero. Each variant name must be non-empty, unique, and must not collide with reserved names `v0` or `zero_score_threshold`.

## Derived policy provenance

E2 never mutates the caller-supplied base policy objects.

Derived policies receive deterministic versions:

```text
zero replay policy set:
  <suite-version>:zero_score_threshold

zero decision policy:
  <base-decision-version>:e2-zero-score-threshold

threshold replay policy set:
  <suite-version>:threshold:<variant-name>

threshold decision policy:
  <base-decision-version>:e2-threshold:<variant-name>:<canonical-delta>
```

The B7 score-policy version remains unchanged because E2-v1 does not change scoring.

Canonical delta text must be deterministic and must distinguish positive from negative values without depending on locale or input string formatting. The implementation may use hexadecimal finite-float representation for version provenance.

## Ordering and determinism

`BaselineSuite.results` uses fixed canonical order:

1. `v0`,
2. `zero_score_threshold`,
3. threshold-delta variants sorted lexically by variant `name`.

Reordering `BaselineSuitePolicy.threshold_variants` therefore cannot change the resulting suite.

The decision-input and outcome-input ordering remains governed by E1 and cannot change any replay result.

## Validation

`BaselineSuitePolicy` must fail closed when:

- `version` is empty,
- `base_replay_policies` is not an exact `ReplayPolicySet`,
- `threshold_variants` is not a tuple,
- an element is not an exact `ThresholdDeltaBaselineSpec`,
- variant names are duplicated,
- a variant name collides with a reserved name,
- a delta is non-finite, boolean, zero, or outside `[-100, 100]`.

The `[-100, 100]` bound keeps variants interpretable as score-threshold perturbations rather than arbitrary numeric abuse. Clamping still defines exact boundary behavior for base thresholds near 0 or 100.

`BaselineSuite` must require:

- schema `e2-baselines-v1`,
- non-empty policy version,
- a tuple of exact `BaselineReplayResult` values,
- at least V0 and zero-threshold results,
- unique result names,
- fixed canonical result ordering,
- V0 kind/name semantics,
- zero-threshold kind/name semantics,
- every contained `ReplayRun` to cover the exact same ordered replay identities.

This last invariant prevents accidental baseline comparisons over different candidate populations.

## Leakage boundary

Outcome bundles are passed through unchanged to E1 only so each baseline emits D6-compatible snapshots with labels attached after the replayed decision.

E2 policy derivation receives only the baseline policy object. It must not inspect:

- `ResearchOutcomeLabel.return_pct`,
- MFE/MAE,
- liquidity/volume outcome changes,
- future buy/sell changes,
- rug/dead-pool labels,
- exitability.

Tests will prove that changing only future outcomes leaves all baseline score/decision outputs unchanged.

## D6 compatibility

Every contained `ReplayRun` remains an E1 run of D6 `ResearchSnapshotInputs` and must pass sealed D6 `build_research_dataset` without conversion.

E2 does not create a new research dataset schema; `e2-baselines-v1` versions the **suite/provenance contract**, while each replay snapshot remains `d6-research-v1` compatible.

## Test contract

### Models/public API

Prove:

- exact schema and enum values,
- immutability,
- finite/non-zero/bounded deltas,
- reserved/duplicate name rejection,
- exact `ReplayPolicySet` requirement,
- tuple/exact-type validation,
- suite identity/population reconciliation,
- exact public exports.

### Behavior

Prove:

1. V0 result equals direct sealed E1 replay exactly.
2. Zero-threshold baseline changes only numeric B8 thresholds and provenance versions.
3. `None` thresholds remain `None`.
4. Disabled rules remain disabled.
5. Threshold deltas apply to every numeric regime threshold.
6. Threshold deltas clamp at 0 and 100.
7. Caller-supplied base policies remain unchanged.
8. Variant declaration order cannot change suite output.
9. All baseline runs cover the same replay identities.
10. REJECT/WATCH/ENTER candidates remain available according to each derived B8 policy.
11. Changing only future labels cannot change any baseline score or decision.
12. Every baseline replay remains accepted by D6 `build_research_dataset`.
13. Repeated identical inputs/policy produce identical suites.
14. Importing/running E2 has no SQLite/provider/filesystem/network/PyArrow/random/wall-clock dependency.

## Non-goals

E2-v1 does not implement:

- pseudo-random entry decisions,
- model training or inference,
- chronological train/validation/test splits,
- return or PnL calculations,
- fees/slippage/latency simulation,
- expectancy/profit factor/drawdown/win-rate metrics,
- statistical tests,
- champion/challenger promotion,
- shadow execution,
- risk sizing,
- paper/live execution,
- signer or transaction submission.

Those remain E3-E8 responsibilities according to the build order.

## Exit criterion

E2 is complete when the same E1 historical evidence can deterministically produce a sealed V0 replay plus transparent zero-threshold and caller-specified threshold-delta comparison runs, all with exact provenance, identical candidate populations, preserved future-label isolation, D6 compatibility, and full repository CI GREEN.
