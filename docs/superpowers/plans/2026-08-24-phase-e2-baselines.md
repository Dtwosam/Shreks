# Phase E2 Baselines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic V0, zero-score-threshold, and caller-specified threshold-delta baseline replay suites without creating a second decision engine or computing trading performance.

**Architecture:** Add a new parallel `shreks_brain.baselines` package. Baseline policies are immutable transformations of the sealed E1 `ReplayPolicySet`; every result is produced by the existing E1 `replay_entry_decisions` function over the same historical inputs/outcomes. E2 changes only B8 numeric thresholds and provenance versions; setup policies, B7 scoring, candidate populations, and future-label isolation remain unchanged.

**Tech Stack:** Python 3.12+, stdlib `dataclasses`/`enum`/`math`, existing Shreks B8 decision models, E1 backtest public API, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-e2-baselines-design.md`

## Global Constraints

- Base exactly on sealed E1 head `6c441e13ad7c186d6356e861b45351be7f99d321`.
- Public suite schema is exactly `e2-baselines-v1`.
- E1 `shreks_brain.backtest` production files remain unchanged.
- E2-v1 changes only B8 numeric HOT/NORMAL/WEAK score thresholds and derived provenance versions.
- Setup policies and B7 `ScorePolicy` objects are reused unchanged.
- `None` thresholds remain `None`; `enabled` flags remain unchanged.
- Threshold deltas are finite, non-zero, within `[-100, 100]`, and clamp adjusted numeric thresholds to `[0, 100]`.
- Future outcome values may never be inspected during baseline policy derivation.
- No SQLite, provider, filesystem, network, PyArrow, random-number, or wall-clock dependency.
- No return/PnL/expectancy/drawdown/win-rate/cost metric.
- No risk sizing, `TradeIntent`, paper/live execution, model training/promotion, signer, transaction submission, or live-money authority.
- Use RED -> GREEN TDD and exact-head CI as the acceptance source.

---

### Task 1: Model and public-API RED

**Files:**
- Create: `python/tests/test_baseline_models.py`
- Create: `python/tests/test_baseline_public_api.py`

**Interfaces:**
- Consumes: sealed E1 `ReplayPolicySet`, `ReplayRun`.
- Produces executable contract for the exact E2 public names before production exists.

- [ ] **Step 1: Write public API RED**

`python/tests/test_baseline_public_api.py` must import `shreks_brain.baselines` and require exact exports:

```python
EXPECTED_PUBLIC_API = {
    "BASELINE_SUITE_SCHEMA_VERSION",
    "BaselineKind",
    "ThresholdDeltaBaselineSpec",
    "BaselineSuitePolicy",
    "BaselineReplayResult",
    "BaselineSuite",
    "build_baseline_suite",
}


def test_baseline_public_api_is_exact():
    from shreks_brain import baselines
    assert set(baselines.__all__) == EXPECTED_PUBLIC_API
```

- [ ] **Step 2: Write model RED**

`python/tests/test_baseline_models.py` must construct real sealed E1 policies and prove:

```python
assert BASELINE_SUITE_SCHEMA_VERSION == "e2-baselines-v1"
assert tuple(value.value for value in BaselineKind) == (
    "V0",
    "ZERO_SCORE_THRESHOLD",
    "THRESHOLD_DELTA",
)
```

It must also prove:

- all models are frozen,
- `ThresholdDeltaBaselineSpec("looser", -10.0)` and `("stricter", 10.0)` are accepted,
- booleans, zero, infinities/NaN, and values outside `[-100, 100]` are rejected,
- empty/reserved names are rejected,
- `BaselineSuitePolicy` requires an exact `ReplayPolicySet`, tuple variants, exact variant element types, and unique names,
- `BaselineReplayResult` requires kind/name/delta semantics and replay-policy version reconciliation,
- `BaselineSuite` requires schema/version/non-empty results, `v0` then `zero_score_threshold`, lexical threshold-result order, unique names, and identical replay identities across every result.

Use tiny valid `ReplayRun` fixtures built from real E1/D6 models rather than mocks.

- [ ] **Step 3: Attach RED atomically**

Commit only both tests:

```text
test: define E2 baseline model contract
```

- [ ] **Step 4: Verify RED CI**

Require Python collection to fail only because `shreks_brain.baselines` does not exist. Repository safety and unrelated predecessor tests must remain clean.

---

### Task 2: Model and public-API GREEN

**Files:**
- Create: `python/src/shreks_brain/baselines/models.py`
- Create: `python/src/shreks_brain/baselines/engine.py`
- Create: `python/src/shreks_brain/baselines/__init__.py`

**Interfaces:**
- Produces:

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
```

- [ ] **Step 1: Implement `models.py` minimally**

Validation requirements:

```python
RESERVED_BASELINE_NAMES = frozenset({"v0", "zero_score_threshold"})
```

`ThresholdDeltaBaselineSpec.__post_init__`:

```python
_require_non_empty_string("name", self.name)
if self.name in RESERVED_BASELINE_NAMES:
    raise ValueError("threshold baseline name is reserved")
_require_finite_number("delta_points", self.delta_points)
if self.delta_points == 0:
    raise ValueError("delta_points must be non-zero")
if self.delta_points < -100 or self.delta_points > 100:
    raise ValueError("delta_points must be within [-100, 100]")
```

`BaselineSuitePolicy` must require exact E1 policy type, exact tuple/exact spec elements, and unique names.

`BaselineReplayResult` semantics:

```text
V0: name == "v0", delta is None
ZERO_SCORE_THRESHOLD: name == "zero_score_threshold", delta is None
THRESHOLD_DELTA: name not reserved, finite/non-zero delta required
replay_policy_set_version == replay.policy_set_version
```

`BaselineSuite` validates first two fixed results, lexical threshold names, unique names, and exact ordered `(as_of_unix_ms, candidate_mint)` identity equality across all contained `ReplayRun.snapshots`.

- [ ] **Step 2: Add behavior stub**

`engine.py` must expose the exact signature but remain intentionally RED for behavior:

```python
def build_baseline_suite(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policy: BaselineSuitePolicy,
) -> BaselineSuite:
    raise NotImplementedError("E2 baseline behavior is not implemented yet")
```

- [ ] **Step 3: Add exact public exports**

`__init__.py` exports only the seven design names.

- [ ] **Step 4: Run full CI**

Require repository safety, all Python tests, Rust/workspace GREEN. Fix only demonstrated fixture/contract issues; do not implement behavior early.

- [ ] **Step 5: Commit GREEN**

```text
feat: add E2 baseline model contract
```

---

### Task 3: Baseline behavior RED

**Files:**
- Create: `python/tests/test_baseline_suite.py`

**Interfaces:**
- Consumes exact Task 2 public API.
- Defines behavior for the single Task 4 engine replacement.

- [ ] **Step 1: Write V0 equivalence test**

```python
suite = build_baseline_suite(inputs, outcomes, policy)
expected = replay_entry_decisions(
    inputs,
    outcomes,
    policy.base_replay_policies,
)
assert suite.results[0].name == "v0"
assert suite.results[0].replay == expected
```

- [ ] **Step 2: Write zero-threshold transformation tests**

Use a base `DecisionPolicy` containing:

- enabled numeric HOT/NORMAL/WEAK thresholds,
- at least one `None` threshold,
- at least one disabled setup rule.

Prove from the replayed decisions and exposed versions that numeric thresholds become zero while `None` and `enabled` semantics remain untouched. Also assert the original `ReplayPolicySet` object equals a pre-call copy.

- [ ] **Step 3: Write threshold-delta tests**

Use variants declared in reverse lexical order:

```python
(
    ThresholdDeltaBaselineSpec("stricter", 15.0),
    ThresholdDeltaBaselineSpec("looser", -20.0),
)
```

Require output order `looser`, then `stricter`; prove all numeric regime thresholds receive the delta, `None` remains `None`, and edge thresholds clamp to exactly `0.0`/`100.0`.

- [ ] **Step 4: Write population/provenance tests**

Prove every result covers the exact same E1 identities as V0, each derived result has deterministic distinct replay/decision policy versions, score-policy versions remain unchanged, and all replays still pass sealed D6 `build_research_dataset`.

- [ ] **Step 5: Write leakage/determinism tests**

Replay identical decision inputs against outcome bundles that differ only in future `return_pct`; require every corresponding baseline score/decision to remain equal while attached outcomes differ.

Reverse decision inputs, outcome bundles, and threshold-variant declarations; require identical `BaselineSuite` output.

- [ ] **Step 6: Write purity test**

Subprocess import must prove `shreks_brain.baselines` does not eagerly import PyArrow or SQLite. Source inspection of `baselines.engine` must reject references to:

```text
sqlite3
pyarrow
pathlib
requests
random
time.time
datetime.now
open(
```

- [ ] **Step 7: Attach RED**

Commit only `test_baseline_suite.py`:

```text
test: define E2 baseline behavior
```

- [ ] **Step 8: Verify RED CI**

Require failures only from the intentional `NotImplementedError`; all predecessor/model tests remain GREEN.

---

### Task 4: Baseline behavior GREEN

**Files:**
- Modify only: `python/src/shreks_brain/baselines/engine.py`

**Interfaces:**
- Reuses sealed E1 `replay_entry_decisions` for every baseline.

- [ ] **Step 1: Implement threshold helpers**

```python
def _adjust_threshold(value: float | None, delta: float) -> float | None:
    if value is None:
        return None
    return min(100.0, max(0.0, value + delta))
```

Transform each `SetupDecisionRule` with `dataclasses.replace`, changing only `hot_min_score`, `normal_min_score`, and `weak_min_score`.

- [ ] **Step 2: Implement zero policy derivation**

Create a new `DecisionPolicy` with deterministic version:

```text
<base-decision-version>:e2-zero-score-threshold
```

and numeric thresholds adjusted by delta `-100.0` through `_adjust_threshold` so all numeric values become `0.0`; explicit `None` remains `None`.

Create a new `ReplayPolicySet` version:

```text
<suite-version>:zero_score_threshold
```

reusing the exact base setup policies and exact base `ScorePolicy`.

- [ ] **Step 3: Implement delta policy derivation**

For each spec sorted by `name`, derive decision version:

```python
canonical = float(spec.delta_points).hex()
version = (
    f"{base.decision_policy.version}:e2-threshold:"
    f"{spec.name}:{canonical}"
)
```

and replay-policy-set version:

```text
<suite-version>:threshold:<variant-name>
```

Apply the signed delta through `_adjust_threshold` to every numeric regime threshold only.

- [ ] **Step 4: Build V0 first**

Call sealed E1 directly with `policy.base_replay_policies` and wrap it in:

```python
BaselineReplayResult(
    name="v0",
    kind=BaselineKind.V0,
    threshold_delta_points=None,
    replay_policy_set_version=v0.policy_set_version,
    replay=v0,
)
```

- [ ] **Step 5: Build zero and sorted delta results**

Each derived policy must be passed to `replay_entry_decisions` with the **same** decision/outcome tuples. Do not inspect any outcome field in E2.

- [ ] **Step 6: Return validated suite**

```python
return BaselineSuite(
    schema_version=BASELINE_SUITE_SCHEMA_VERSION,
    policy_version=policy.version,
    results=tuple(results),
)
```

- [ ] **Step 7: Run full exact-head CI**

Require repository safety, Python, Rust/workspace GREEN. Any failure gets one demonstrated repair cycle; no speculative refactor.

- [ ] **Step 8: Commit GREEN**

```text
feat: implement E2 baseline suite
```

---

### Task 5: Freeze and audit implementation

**Files:** none unless a demonstrated defect is found.

- [ ] **Step 1: Freeze behavior after GREEN**

No production/test behavior changes are allowed once full CI is GREEN.

- [ ] **Step 2: Audit sealed E1 -> E2 GREEN**

Before documentation seal, require the diff to contain exactly:

```text
docs/superpowers/specs/2026-08-24-phase-e2-baselines-design.md
docs/superpowers/plans/2026-08-24-phase-e2-baselines.md
python/src/shreks_brain/baselines/__init__.py
python/src/shreks_brain/baselines/models.py
python/src/shreks_brain/baselines/engine.py
python/tests/test_baseline_models.py
python/tests/test_baseline_public_api.py
python/tests/test_baseline_suite.py
```

Reject the implementation if any E1/predecessor production file, `python/pyproject.toml`, Rust file, migration, or README change appears.

---

### Task 6: Atomic documentation seal

**Files:**
- Modify additions-only: `README.md`
- Replace plan with verification record: `docs/superpowers/plans/2026-08-24-phase-e2-baselines.md`

- [ ] **Step 1: Prepare README append off-branch**

Append `## Deterministic evaluation baselines` documenting:

- `e2-baselines-v1`,
- V0 exact E1 equivalence,
- zero-score-threshold baseline,
- caller-specified clamped threshold deltas,
- unchanged setup/B7 policies and candidate population,
- future-label isolation,
- no random baseline in v1 and why,
- no metrics/model/execution/live-money change.

Do not rewrite predecessor README lines.

- [ ] **Step 2: Replace plan with verification record off-branch**

Record exact E1 base SHA, design/plan SHA, RED/GREEN commits and CI counts, any demonstrated repairs, exact changed files, threshold/provenance/leakage properties, and scope boundaries. The final seal SHA/CI belongs in PR metadata only.

- [ ] **Step 3: Build detached seal commit**

Parent it exactly on E2 GREEN. Do not move the branch yet.

- [ ] **Step 4: Audit detached seal**

Require exactly:

```text
README.md: additions only, deletions == 0
docs/superpowers/plans/2026-08-24-phase-e2-baselines.md: verification replacement
```

- [ ] **Step 5: Attach and run exact-head CI**

Fast-forward only after the detached diff passes. Require repository safety, Python, Rust/workspace all GREEN.

- [ ] **Step 6: Update stacked draft PR metadata only**

Base: `feat/phase-e1-backtest-replay`.
Head: `feat/phase-e2-baselines`.
Record final frozen SHA and CI without another tracked-file write.

## Plan self-review

- Spec coverage: V0, zero-threshold, delta variants, immutable provenance, population equality, D6 compatibility, future-label isolation, deterministic ordering, purity, and all E2 non-goals map directly to Tasks 1-6.
- Placeholder scan: no TBD/TODO/"implement later" steps remain.
- Type consistency: all public names/signatures match the E2 design and sealed E1 public API.
- Scope: E2 creates comparison replay runs only. E3 model training, E4 chronological validation, E5 trading metrics, E6-E8 promotion/challenger work remain separate phases.
