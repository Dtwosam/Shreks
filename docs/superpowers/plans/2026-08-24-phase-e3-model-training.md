# Phase E3 Model Training Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first deterministic supervised tabular training and pure-Python inference boundary over sealed D6 logical research rows.

**Architecture:** E3-v1 trains one explicit logistic-regression family. Standard-library code validates D6 rows, derives a caller-specified binary return target, computes training-only median/standardization transforms, and exports an immutable portable coefficient artifact. `trainer.py` lazy-loads scikit-learn only for fitting; inference uses stored transforms plus a pure-Python sigmoid. E4 still owns chronological splitting and E5 still owns trading metrics.

**Tech Stack:** Python 3.12+, standard library, scikit-learn `>=1.7,<2` behind an optional `learning` extra, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-e3-model-training-design.md`

## Global Constraints

- Base exactly on sealed E2 head `caeb7b127b39a9c7fd5cf40ca877fbe677ba703f`.
- Keep base `shreks-brain` dependency-free; scikit-learn is optional training infrastructure.
- Consume caller-supplied D6 logical rows only; no Parquet/SQLite/provider/filesystem/network/wall-clock reads.
- Use only E3 allow-listed scalar numeric/boolean columns from `RESEARCH_FEATURE_COLUMNS`; never permit a `label_` column as a feature.
- No production/default feature tuple, target horizon/threshold, or training hyperparameters.
- No chronological split, evaluation metrics, model promotion, risk, execution, or live-money behavior.
- No pickle/joblib/executable model serialization.
- Preserve E1/E2/B7/B8 behavior unchanged.

---

### Task 1: Immutable E3 model and public API contract

**Files:**
- Create: `python/src/shreks_brain/learning/models.py`
- Create: `python/src/shreks_brain/learning/__init__.py`
- Create: `python/tests/test_learning_models.py`
- Create: `python/tests/test_learning_public_api.py`

**Interfaces:**
- Produces `MODEL_TRAINING_SCHEMA_VERSION = "e3-training-v1"`.
- Produces `ModelFamily.LOGISTIC_REGRESSION`.
- Produces `ClassWeightMode.NONE` and `ClassWeightMode.BALANCED`.
- Produces immutable `ResearchReturnTarget`, `LogisticRegressionTrainingPolicy`, `ModelTrainingRequest`, `FeatureTransform`, `TrainedLogisticRegressionModel`, and `ModelPrediction`.
- Later tasks consume these exact types.

- [ ] **Step 1: Add model/public RED tests**

Tests must assert:

```python
from dataclasses import FrozenInstanceError

from shreks_brain.learning import (
    MODEL_TRAINING_SCHEMA_VERSION,
    ClassWeightMode,
    FeatureTransform,
    LogisticRegressionTrainingPolicy,
    ModelFamily,
    ModelPrediction,
    ModelTrainingRequest,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)

assert MODEL_TRAINING_SCHEMA_VERSION == "e3-training-v1"
assert ModelFamily.LOGISTIC_REGRESSION.value == "LOGISTIC_REGRESSION"
assert ClassWeightMode.NONE.value == "NONE"
assert ClassWeightMode.BALANCED.value == "BALANCED"
```

Cover exact type/value validation, approved D6 horizons, finite target thresholds, positive logistic `C/tolerance/max_iterations`, duplicate/empty feature rejection, coefficient/transform dimensional agreement, probability bounds, 64-character lowercase SHA-256 provenance, and frozen dataclasses.

- [ ] **Step 2: Run the RED**

Run:

```bash
python -m pytest python/tests/test_learning_models.py python/tests/test_learning_public_api.py -q
```

Expected: collection failure because `shreks_brain.learning` does not exist.

- [ ] **Step 3: Implement the minimal model/public GREEN**

Create exact immutable validated contracts. `ModelTrainingRequest.feature_columns` is a non-empty duplicate-free tuple of non-empty strings; semantic allow-list validation belongs to Task 2.

`TrainedLogisticRegressionModel` fields:

```python
schema_version: str
model_version: str
model_family: ModelFamily
training_policy_version: str
research_dataset_schema_version: str
target: ResearchReturnTarget
feature_transforms: tuple[FeatureTransform, ...]
coefficients: tuple[float, ...]
intercept: float
training_row_count: int
positive_row_count: int
negative_row_count: int
target_unavailable_row_count: int
min_training_as_of_unix_ms: int
max_training_as_of_unix_ms: int
training_fingerprint_sha256: str
```

`ModelPrediction` fields:

```python
model_version: str
candidate_mint: str
as_of_unix_ms: int
positive_probability: float
```

- [ ] **Step 4: Run model/public tests**

Expected: PASS while no training behavior exists yet.

- [ ] **Step 5: Commit**

```bash
git add python/src/shreks_brain/learning/models.py python/src/shreks_brain/learning/__init__.py python/tests/test_learning_models.py python/tests/test_learning_public_api.py
git commit -m "feat: add E3 learning contracts"
```

---

### Task 2: Point-in-time feature and target preparation

**Files:**
- Create: `python/src/shreks_brain/learning/features.py`
- Create: `python/tests/test_learning_features.py`

**Interfaces:**
- Produces public `TRAINABLE_RESEARCH_FEATURE_COLUMNS`.
- Produces internal deterministic preparation consumed by trainer/inference.
- Must never import scikit-learn.

- [ ] **Step 1: Write feature-preparation RED tests**

Cover:

1. every allowed feature belongs to D6 `RESEARCH_FEATURE_COLUMNS`;
2. no allowed feature starts with `label_`;
3. identity/provenance/categorical/reason/action/required-threshold columns are absent;
4. requested feature columns outside the allow-list fail;
5. duplicate D6 identities fail;
6. pending selected target rows are excluded, not negative;
7. completed selected return labels derive `return_pct >= minimum_return_pct` exactly;
8. feature `None` values use a training-only median;
9. bool becomes `0.0/1.0`;
10. non-finite/unsupported feature values fail;
11. an all-missing selected feature fails;
12. transforms and training fingerprint do not depend on input row order;
13. future non-target labels cannot alter prepared features/target or fingerprint.

Use synthetic dicts with exactly `RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS` so the test does not need provider/storage fixtures.

- [ ] **Step 2: Run RED**

Expected: missing `learning.features` or missing preparation behavior.

- [ ] **Step 3: Implement deterministic preparation**

Create the explicit scalar allow-list described by the spec. Validate every row has the exact sealed D6 column set and `dataset_schema_version == "d6-research-v1"`.

Sort rows by `(as_of_unix_ms, candidate_mint)`. Reject duplicate identities before target filtering.

For selected horizon `H`, use exactly:

```python
status_column = f"label_{H}s_status"
return_column = f"label_{H}s_return_pct"
```

Only `COMPLETED` with a finite numeric return is target-eligible.

Per feature, compute observed-value median, impute, then mean/population standard deviation; use scale `1.0` for zero variance.

Canonicalize floats with `.hex()` while computing the SHA-256 training fingerprint.

- [ ] **Step 4: Run feature tests and the full existing Python suite**

```bash
python -m pytest python/tests/test_learning_features.py -q
python -m pytest python/tests -q
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add python/src/shreks_brain/learning/features.py python/tests/test_learning_features.py
git commit -m "feat: prepare E3 training features"
```

---

### Task 3: Logistic training adapter and pure-Python inference

**Files:**
- Create: `python/src/shreks_brain/learning/trainer.py`
- Create: `python/src/shreks_brain/learning/inference.py`
- Modify: `python/src/shreks_brain/learning/__init__.py`
- Modify: `python/pyproject.toml`
- Create: `python/tests/test_learning_training.py`
- Create: `python/tests/test_learning_inference.py`

**Interfaces:**
- Produces `train_logistic_regression(rows, request) -> TrainedLogisticRegressionModel`.
- Produces `predict_positive_probability(model, row) -> ModelPrediction`.

- [ ] **Step 1: Write training/inference RED tests**

Training tests must prove:

- two-class synthetic data trains successfully;
- input row reordering yields identical artifact coefficients/intercept/transforms/fingerprint;
- `target_unavailable_row_count` is retained;
- one-class eligible data fails;
- fewer than two eligible rows fail;
- all-missing selected feature fails through the Task 2 boundary;
- changing only future non-target label values does not change the trained artifact;
- changing target return evidence can change the target/fingerprint;
- no accuracy/AUC/PnL/evaluation fields exist in the artifact;
- import of `shreks_brain.learning` does not import sklearn.

Inference tests must prove:

- probability is always in `[0, 1]`;
- prediction identity/model version is preserved;
- missing inference feature uses stored training median;
- unsupported/non-finite inference evidence fails;
- mutating any D6 future label leaves prediction unchanged;
- inference source contains no sklearn/NumPy import.

- [ ] **Step 2: Run RED**

Expected: missing trainer/inference functions.

- [ ] **Step 3: Add optional learning dependency**

Update `python/pyproject.toml`:

```toml
[project.optional-dependencies]
research = ["pyarrow==25.0.*"]
learning = ["scikit-learn>=1.7,<2"]
dev = ["pytest>=8,<9", "pyarrow==25.0.*", "scikit-learn>=1.7,<2"]
```

Do not add scikit-learn to base dependencies.

- [ ] **Step 4: Implement lazy sklearn trainer**

`trainer.py` imports no sklearn at module import time. Inside training, lazy-import:

```python
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
```

Fit standardized features with:

```python
LogisticRegression(
    solver="lbfgs",
    C=policy.regularization_c,
    max_iter=policy.max_iterations,
    tol=policy.tolerance,
    class_weight=("balanced" if policy.class_weight_mode is BALANCED else None),
    fit_intercept=True,
)
```

Treat `ConvergenceWarning` as an error. Export finite scalar coefficients/intercept into the immutable artifact; never return the estimator.

- [ ] **Step 5: Implement pure inference**

Use stored transforms and a numerically stable sigmoid:

```python
if z >= 0:
    probability = 1.0 / (1.0 + math.exp(-z))
else:
    exp_z = math.exp(z)
    probability = exp_z / (1.0 + exp_z)
```

No target/label column is read during prediction.

- [ ] **Step 6: Run focused and full verification**

```bash
python -m pytest python/tests/test_learning_training.py python/tests/test_learning_inference.py -q
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add python/pyproject.toml python/src/shreks_brain/learning python/tests/test_learning_training.py python/tests/test_learning_inference.py
git commit -m "feat: train E3 logistic challenger"
```

---

### Task 4: Audit, README, verification record, and immutable seal

**Files:**
- Modify additions-only: `README.md`
- Replace with verification record: `docs/superpowers/plans/2026-08-24-phase-e3-model-training.md`

- [ ] **Step 1: Verify fresh full CI on behavior GREEN**

Require repository safety, Python, Rust tests, and workspace metadata green on the exact behavior head.

- [ ] **Step 2: Audit sealed-E2 -> E3 implementation diff**

Expected implementation scope only:

- E3 design/plan docs;
- `python/src/shreks_brain/learning/*`;
- E3 learning tests;
- `python/pyproject.toml` optional `learning`/dev dependency change.

No E1/E2/B7/B8 production code, migration, or Rust source may change.

- [ ] **Step 3: Build documentation seal detached**

Append an E3 README section without deleting prior text. Replace this plan with the TDD/CI/diff verification record. Build the commit detached from the verified behavior GREEN tree.

- [ ] **Step 4: Audit detached seal**

Require exactly README plus this verification-record file. README deletions must equal zero.

- [ ] **Step 5: Attach seal and run exact-head CI**

After attaching the audited seal, run/observe full CI and require all jobs green. Record final immutable SHA and CI run only in PR metadata.

- [ ] **Step 6: Freeze E3**

No tracked-file changes after final seal. E4 Time-Aware Validation begins from this exact SHA.
