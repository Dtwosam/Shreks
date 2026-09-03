# FL8.2 Practical Model Baselines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train deterministic naive, ridge, prior, and logistic Fast Lane forecast baselines from the sealed FL8.1 bundle and emit immutable standard-library reference artifacts with pure-Python inference.

**Architecture:** Add a new isolated `shreks_brain.fast_learning` package. It consumes only `FastTrainingBundle` / `FastTrainingFeatureRecord` / FL4 label types, flattens a versioned point-in-time numeric feature vector, trains one explicit horizon/target model at a time, and serializes immutable JSON artifacts. Scikit-learn is lazy-loaded only for ridge/logistic fitting; inference uses stored transforms/weights and the Python standard library.

**Tech Stack:** Python 3.12+, dataclasses/enums/hashlib/json/math/statistics, existing `pyarrow==25.0.*` research bundle path, existing `scikit-learn>=1.7,<2` learning extra, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-fl8-2-practical-model-baselines-design.md`

## Global Constraints

- Base is SEALED FL8.1 merged-main `74f6041a62d47451e339458dcdc0dc643fbb7570`.
- Rust remains the Fast Lane feature-calculation authority; Python must not recompute event windows.
- FL8.1 bundle joins/fingerprints remain the input authority.
- FL4 labels are the only FL8.2 training targets; FL5 counterfactual rows are not action-policy inputs yet.
- No random or chronological split is added; FL8.3 owns time-aware validation.
- No calibration, champion selection/promotion, trading threshold, sizing, `TradeIntent`, PAPER authority, provider/signing, transaction submission, or LIVE authority.
- Scikit-learn must remain optional/lazy and absent from reference inference imports.
- Artifacts must contain standard-library values only and refuse overwrite.
- LIVE remains disabled.

---

### Task 1: Canonical Fast Lane forecast feature schema

**Files:**
- Create: `python/src/shreks_brain/fast_learning/__init__.py`
- Create: `python/src/shreks_brain/fast_learning/features.py`
- Test: `python/tests/test_fast_forecast_features.py`

**Interfaces:**
- Consumes: `FastTrainingFeatureRecord` from `shreks_brain.research.fast_training_features`.
- Produces: `FAST_FORECAST_FEATURE_SCHEMA_VERSION`, `FAST_FORECAST_FEATURE_NAMES`, `extract_fast_forecast_features(record) -> tuple[float | None, ...]`, `FastForecastFeatureTransform`, `fit_feature_transforms(rows)`, and `apply_feature_transforms(raw, transforms)`.

- [ ] **Step 1: Write failing feature-contract tests**

Create deterministic FL8.1 feature fixtures and assert:

```python
raw = extract_fast_forecast_features(feature_record())
assert len(raw) == len(FAST_FORECAST_FEATURE_NAMES)
assert FAST_FORECAST_FEATURE_SCHEMA_VERSION == 1
assert "decision_signature" not in FAST_FORECAST_FEATURE_NAMES
assert "decision_observed_at_unix_ms" not in FAST_FORECAST_FEATURE_NAMES
assert all("endpoint_return_bps" not in name for name in FAST_FORECAST_FEATURE_NAMES)
```

Also assert two equivalent records produce identical vectors; changing only actor/signature/absolute timestamp does not create identity features; future-target values are structurally unavailable to this function; window order is exactly the sealed seven-window order; lifecycle age is non-negative and reserve missing values remain `None` until transform fitting.

- [ ] **Step 2: Run the targeted tests and verify RED**

Run: `python -m pytest python/tests/test_fast_forecast_features.py -q`

Expected: import/module failures because `shreks_brain.fast_learning` does not yet exist.

- [ ] **Step 3: Implement the exact V1 feature schema**

Create an immutable tuple of names covering the top-level numeric/context indicators and every numeric FL8.1 rolling-window field from the design. Exclude decision identity, actor identity, absolute time, sequence/slot, FL4 targets, and FL5 rows.

Implement:

```python
def extract_fast_forecast_features(
    record: FastTrainingFeatureRecord,
) -> tuple[float | None, ...]:
    ...
```

Reject non-exact records, non-finite numeric evidence, unknown event kinds/venues/reserve kinds, future lifecycle ages, or sealed-window mismatches.

- [ ] **Step 4: Add transform fitting/application**

`fit_feature_transforms` must median-impute each column, compute mean and population standard deviation after imputation, replace zero scale with `1.0`, and return frozen transforms in exact feature order. `apply_feature_transforms` must reject name/order mismatch and produce finite floats.

- [ ] **Step 5: Run targeted tests GREEN and commit**

Run: `python -m pytest python/tests/test_fast_forecast_features.py -q`

Commit target: `feat(fl8.2): add canonical forecast feature schema`

---

### Task 2: Training request and immutable artifact contracts

**Files:**
- Create: `python/src/shreks_brain/fast_learning/models.py`
- Test: `python/tests/test_fast_forecast_models.py`

**Interfaces:**
- Produces enums `FastForecastModelFamily`, `FastForecastTarget`, `FastForecastTargetKind`; frozen `FastForecastTrainingPolicy`, `FastForecastTrainingRequest`, `FastForecastBaselineArtifact`, `FastForecastPrediction`; `fast_forecast_artifact_fingerprint_sha256`.

- [ ] **Step 1: Write RED contract tests**

Assert exact schema constants and family/target compatibility:

```python
assert FAST_FORECAST_ARTIFACT_SCHEMA_NAME == "shreks.fast_lane_forecast_baseline"
assert FAST_FORECAST_ARTIFACT_SCHEMA_VERSION == 1
```

Continuous targets accept only `MEAN_REGRESSOR` / `RIDGE_REGRESSION`; binary targets accept only `PRIOR_CLASSIFIER` / `LOGISTIC_REGRESSION`. Reject booleans as integers, non-positive horizon, empty model/policy versions, invalid alpha/C/tolerance/iterations, malformed SHA-256 values, non-finite coefficients/constants, coefficient/transform length mismatch, binary constants outside `[0, 1]`, and artifacts carrying the wrong feature schema.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest python/tests/test_fast_forecast_models.py -q`.

- [ ] **Step 3: Implement frozen contracts and fingerprint**

Use only dataclasses/enums/standard-library values. The fingerprint must canonicalize all artifact fields except the fingerprint itself using sorted compact JSON with `allow_nan=False`.

- [ ] **Step 4: Verify GREEN and commit**

Run targeted tests and commit target: `feat(fl8.2): define forecast baseline artifacts`.

---

### Task 3: Exact bundle-to-training-row construction and naive baselines

**Files:**
- Create: `python/src/shreks_brain/fast_learning/trainer.py`
- Test: `python/tests/test_fast_forecast_trainer.py`

**Interfaces:**
- Produces `train_fast_forecast_baseline(bundle, request) -> FastForecastBaselineArtifact`.
- Internal helper `_prepare_fast_forecast_training_data` returns canonical feature rows, target values, counts/timestamps, and deterministic training fingerprint.

- [ ] **Step 1: Write RED tests using exact FL8.1 dataclasses**

Construct a small in-memory `FastTrainingBundle` fixture with at least four decisions and two horizons. Prove:

- only the requested horizon participates;
- incomplete rows are excluded rather than converted to zero;
- null target rows are counted unavailable and excluded;
- exact feature/label decision identities are required;
- target-only mutations change training fingerprint but not the feature dataset fingerprint;
- unknown horizons/no eligible targets fail closed.

For naive families assert mean/prior constants exactly.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest python/tests/test_fast_forecast_trainer.py -q`.

- [ ] **Step 3: Implement canonical eligibility/fingerprint logic**

Map features by `decision_identity`; use FL4 labels only; preserve FL8.1 canonical decision order; include request target/horizon/family, bundle fingerprint, decision identities, raw feature vector, and target values in the training-data fingerprint.

- [ ] **Step 4: Implement `MEAN_REGRESSOR` and `PRIOR_CLASSIFIER`**

Require at least one eligible target row. Store `constant_prediction`, no coefficients, and no transforms. Record eligible/unavailable counts and min/max decision timestamps.

- [ ] **Step 5: Targeted GREEN and commit**

Commit target: `feat(fl8.2): train naive forecast baselines`.

---

### Task 4: Ridge and logistic fitted baselines

**Files:**
- Modify: `python/src/shreks_brain/fast_learning/trainer.py`
- Test: `python/tests/test_fast_forecast_sklearn.py`

**Interfaces:**
- Extends `train_fast_forecast_baseline` for `RIDGE_REGRESSION` and `LOGISTIC_REGRESSION`.

- [ ] **Step 1: Write RED fit tests**

Use synthetic FL8.1 records where one sealed feature has a known monotonic relationship with a continuous target and a binary target. Assert:

- ridge returns transforms + coefficient vector + intercept and no constant;
- logistic returns transforms + coefficient vector + intercept and no constant;
- ridge requires at least two eligible rows;
- logistic requires at least two rows and both classes;
- importing `shreks_brain.fast_learning` does not import `sklearn`;
- a forced missing-sklearn import raises a clear runtime error rather than changing family.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest python/tests/test_fast_forecast_sklearn.py -q`.

- [ ] **Step 3: Implement lazy sklearn fitting**

Ridge:

```python
from sklearn.linear_model import Ridge
estimator = Ridge(alpha=policy.ridge_alpha, fit_intercept=True)
```

Logistic:

```python
from sklearn.linear_model import LogisticRegression
estimator = LogisticRegression(
    solver="lbfgs",
    C=policy.logistic_regularization_c,
    max_iter=policy.logistic_max_iterations,
    tol=policy.logistic_tolerance,
    class_weight="balanced" if policy.logistic_balanced_class_weight else None,
    fit_intercept=True,
)
```

Convert coefficients/intercept to finite Python floats immediately. Treat convergence warnings as errors. Do not store the estimator.

- [ ] **Step 4: Verify GREEN and commit**

Commit target: `feat(fl8.2): fit linear forecast baselines`.

---

### Task 5: Pure-Python reference inference parity

**Files:**
- Create: `python/src/shreks_brain/fast_learning/inference.py`
- Test: `python/tests/test_fast_forecast_inference.py`

**Interfaces:**
- Produces `predict_fast_forecast(artifact, record) -> FastForecastPrediction`.

- [ ] **Step 1: Write RED tests**

For naive artifacts, prediction equals the stored constant. For ridge/logistic artifacts, compare the pure-Python result against the sklearn reference prediction from the same fitted fixture with absolute tolerance `1e-10` for ridge and `1e-10` for logistic probability.

Assert inference import leaves `sklearn` and `numpy` absent when they were absent before import.

- [ ] **Step 2: Verify RED**

Run targeted inference tests.

- [ ] **Step 3: Implement reference inference**

Use the Task 1 extractor/transforms. Compute linear score using `math.fsum(weight * value ...)`. For logistic use stable sigmoid:

```python
if score >= 0:
    z = math.exp(-score)
    probability = 1.0 / (1.0 + z)
else:
    z = math.exp(score)
    probability = z / (1.0 + z)
```

Validate finite output and binary range.

- [ ] **Step 4: Verify GREEN and commit**

Commit target: `feat(fl8.2): add pure python forecast inference`.

---

### Task 6: Immutable canonical JSON codec

**Files:**
- Create: `python/src/shreks_brain/fast_learning/codec.py`
- Modify: `python/src/shreks_brain/fast_learning/__init__.py`
- Test: `python/tests/test_fast_forecast_codec.py`

**Interfaces:**
- Produces `write_fast_forecast_artifact(artifact, path)`, `read_fast_forecast_artifact(path)`.

- [ ] **Step 1: Write RED codec tests**

Prove byte-identical writes for equal artifacts to separate fresh paths; exact round trip; overwrite refusal; unknown/missing keys rejected; enum/schema/fingerprint tampering rejected; JSON contains no `pickle`, `joblib`, sklearn class path, provider/signing/execution fields.

- [ ] **Step 2: Verify RED**

Run targeted codec tests.

- [ ] **Step 3: Implement canonical codec**

Serialize `asdict` with enum `.value`, sorted keys, compact separators, `ensure_ascii=False`, `allow_nan=False`, plus trailing newline. Refuse an existing output path. Reader requires exact key sets and recomputes the artifact fingerprint.

- [ ] **Step 4: Export only focused public symbols**

`fast_learning.__init__` may export contracts/training/inference/codec. It must not import sklearn eagerly and must not expose registry promotion or execution authority.

- [ ] **Step 5: Verify GREEN and commit**

Commit target: `feat(fl8.2): add immutable forecast artifact codec`.

---

### Task 7: FL8.1 on-disk integration and authority proof

**Files:**
- Test: `python/tests/test_fast_forecast_integration.py`
- Test: `python/tests/test_fast_forecast_authority.py`

**Interfaces:**
- Uses `read_fast_training_bundle` from FL8.1 and all FL8.2 public APIs.

- [ ] **Step 1: Build an actual FL8.1 bundle fixture**

Reuse the existing Rust/Python FL8.1 integration fixture pattern where practical, or construct a deterministic on-disk FL8.1 bundle with enough complete labels/classes to fit all four FL8.2 families.

- [ ] **Step 2: Prove end-to-end training**

Read the bundle from disk, fit mean/ridge/prior/logistic requests for explicit horizons/targets, write/read each JSON artifact, and run reference inference on known feature records.

- [ ] **Step 3: Prove target-only fingerprint separation**

Change only one FL4 future target, rebuild the bundle, and assert:

```python
changed.manifest.feature_logical_fingerprint_sha256 == original.manifest.feature_logical_fingerprint_sha256
changed_artifact.training_data_fingerprint_sha256 != original_artifact.training_data_fingerprint_sha256
changed_artifact.artifact_fingerprint_sha256 != original_artifact.artifact_fingerprint_sha256
```

- [ ] **Step 4: Prove authority boundary**

Reject public names/source imports associated with providers, signing, transaction submission, `TradeIntent`, PAPER execution, registry promotion, or LIVE enablement.

- [ ] **Step 5: Run full Python suite**

Run: `python -m pytest python/tests -q`.

Expected: all tests green with the real learning extra installed by CI.

---

### Task 8: Candidate verification, clean history, merge, and seal

**Files:**
- Update PR description only; no production authority expansion.

- [ ] **Step 1: Run candidate four-gate CI**

Require repository safety, Python, Rust, and native ARM64 release GREEN.

- [ ] **Step 2: Audit changed files**

Confirm scope is limited to FL8.2 docs, `python/src/shreks_brain/fast_learning/**`, and FL8.2 tests unless a demonstrated compatibility fix is required.

- [ ] **Step 3: Clean history**

Collapse authoring noise to exactly:

```text
design -> plan -> RED contracts -> implementation
```

while preserving the verified final tree.

- [ ] **Step 4: Run fresh exact-clean-head four-gate CI**

Do not mark ready until all four gates are green on the cleaned exact head.

- [ ] **Step 5: Finish PR and guarded merge**

Document scope/TDD evidence, mark ready, and merge only with `expected_head_sha` equal to the clean verified head. Preserve the four commits with a merge commit.

- [ ] **Step 6: Require merged-main seal**

Require a fresh push-triggered four-gate GREEN CI on the merge commit before marking FL8.2 SEALED.

- [ ] **Step 7: State the correct limit**

FL8.2 establishes practical forecast baselines only. It does not establish chronological generalization, calibration, economic edge, profitability, champion status, or trading authority. LIVE remains disabled.
