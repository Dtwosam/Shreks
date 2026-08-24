# Phase E4 Time-Aware Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, leakage-safe chronological validation layer that trains a fresh sealed-E3 logistic model per explicit fold and predicts every row in the next unseen interval without computing evaluation metrics.

**Architecture:** Add a new pure-Python `shreks_brain.validation` package with immutable public contracts in `models.py` and orchestration in `engine.py`. E4 validates D6 logical rows and explicit half-open folds, withholds training labels not completed by the validation boundary, delegates fitting and prediction unchanged to sealed E3, and emits canonical fold results plus a provenance-only run fingerprint.

**Tech Stack:** Python 3.12+, standard library dataclasses/hashlib/json/math, sealed `shreks_brain.research` D6 schema, sealed `shreks_brain.learning` E3 training/inference APIs, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-e4-time-validation-design.md`

## Global Constraints

- Base exactly on sealed E3 head `1328efce85464f3f1b1636d837bcefb1193c2eac`; E3 production behavior stays unchanged.
- Public schema version is exactly `e4-time-validation-v1`.
- Folds are caller-supplied; E4 creates no default dates, durations, gaps, feature sets, targets, or hyperparameters.
- Training intervals and validation intervals use half-open semantics.
- A training-window row may train only when its selected target is valid and `completed_at_unix_ms <= fold.validation_started_at_unix_ms`.
- Validation membership depends only on decision timestamp, never label availability.
- Every validation row is predicted; E4 reads no validation label before prediction.
- E4 computes no predictive, trading, cost, or promotion metric.
- Input row/fold order must not alter canonical results or run fingerprint.
- E4 adds no dependency and must not eagerly import sklearn.
- No SQLite, PyArrow, filesystem, network, wall-clock, or random-number access in production E4 modules.
- Every RED/GREEN branch move must be single-purpose and verified by CI before the next production layer is attached.

---

### Task 1: Public validation contracts

**Files:**
- Create: `python/src/shreks_brain/validation/models.py`
- Create: `python/src/shreks_brain/validation/__init__.py`
- Create: `python/tests/test_time_validation_models.py`
- Create: `python/tests/test_time_validation_public_api.py`

**Interfaces:**
- Produces `TIME_AWARE_VALIDATION_SCHEMA_VERSION = "e4-time-validation-v1"`.
- Produces frozen/slotted `ChronologicalValidationFold`, `TimeAwareValidationPolicy`, `ValidationFoldResult`, and `TimeAwareValidationRun`.
- Public `__all__` initially declares the final E4 surface, including `run_time_aware_validation`; the implementation symbol is added in Task 2.

- [ ] **Step 1: Write contract RED tests**

Create tests that import the new package and assert:

```python
assert TIME_AWARE_VALIDATION_SCHEMA_VERSION == "e4-time-validation-v1"
```

For `ChronologicalValidationFold`, prove:

```python
fold = ChronologicalValidationFold(
    name="fold-1",
    training_started_at_unix_ms=1_000,
    training_ended_at_unix_ms=2_000,
    validation_started_at_unix_ms=2_000,
    validation_ended_at_unix_ms=3_000,
)
assert fold.training_ended_at_unix_ms == fold.validation_started_at_unix_ms
```

Reject empty name, bool/negative timestamps, empty intervals, `training_end > validation_start`, and empty validation intervals.

For `TimeAwareValidationPolicy`, prove fold input order is allowed but duplicate names and overlapping validation intervals fail. Adjacent half-open validation intervals must be accepted:

```text
[2000, 3000) and [3000, 4000)
```

For `ValidationFoldResult`, construct a small valid sealed-E3 artifact/prediction fixture and prove row-count reconciliation, prediction model-version compatibility, prediction canonical ordering, and validation-window membership. Mutate each invariant independently and require `ValueError`.

For `TimeAwareValidationRun`, prove schema-version equality, exact `ModelTrainingRequest` type, non-empty canonical fold results, unique fold names, deterministic order requirement, and lowercase 64-character SHA-256 validation.

Public API test must require exactly:

```python
(
    "TIME_AWARE_VALIDATION_SCHEMA_VERSION",
    "ChronologicalValidationFold",
    "TimeAwareValidationPolicy",
    "ValidationFoldResult",
    "TimeAwareValidationRun",
    "run_time_aware_validation",
)
```

- [ ] **Step 2: Run RED**

Run full Python CI path through the branch. Expected Python failure: missing `shreks_brain.validation`; Rust/workspace and repository safety should remain green.

- [ ] **Step 3: Implement immutable contracts**

`models.py` must use exact-type validation patterns consistent with E3. Include helpers for non-empty string, non-negative integer excluding bool, positive integer, and SHA-256 validation.

`ChronologicalValidationFold.__post_init__` enforces:

```python
training_started_at_unix_ms < training_ended_at_unix_ms
training_ended_at_unix_ms <= validation_started_at_unix_ms
validation_started_at_unix_ms < validation_ended_at_unix_ms
```

`TimeAwareValidationPolicy.__post_init__` validates exact fold instances, unique names, and non-overlap after canonical sorting by:

```python
(validation_started_at_unix_ms, validation_ended_at_unix_ms, name)
```

Two validation intervals overlap when:

```python
current.validation_started_at_unix_ms < previous.validation_ended_at_unix_ms
```

`ValidationFoldResult.__post_init__` enforces the reconciliation rules from the spec and requires predictions already sorted by `(as_of_unix_ms, candidate_mint)`.

`TimeAwareValidationRun.__post_init__` requires fold results already canonical by their fold validation tuple, non-empty unique fold names, exact schema version, exact `ModelTrainingRequest`, and a valid SHA-256.

`__init__.py` exports the contract symbols. To preserve the final explicit API before Task 2, do not expose a placeholder implementation; update the public-API RED in Task 2 to fail on the missing engine symbol.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
python -m pytest python/tests/test_time_validation_models.py -q
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: contract tests and entire repository green.

- [ ] **Step 5: Commit**

Commit message:

```text
feat: define E4 validation contracts
```

---

### Task 2: Leakage-safe chronological validation engine

**Files:**
- Create: `python/src/shreks_brain/validation/engine.py`
- Modify: `python/src/shreks_brain/validation/__init__.py`
- Create: `python/tests/test_time_validation_engine.py`
- Modify: `python/tests/test_time_validation_public_api.py`

**Interfaces:**
- Consumes `tuple[dict[str, object], ...]`, exact `ModelTrainingRequest`, exact `TimeAwareValidationPolicy`.
- Produces `run_time_aware_validation(rows, request, policy) -> TimeAwareValidationRun`.
- Uses sealed E3 `train_logistic_regression` and `predict_positive_probability` unchanged.

- [ ] **Step 1: Write engine RED tests**

Build D6 row helpers from `RESEARCH_FEATURE_COLUMNS`, `RESEARCH_LABEL_COLUMNS`, and `RESEARCH_OUTCOME_HORIZONS_SECONDS`, setting every physical column before overriding relevant fields.

Use target horizon 300 seconds and threshold `>= 5.0` for synthetic fixtures. Build at least two folds with enough mature positive/negative rows for E3 training.

Tests must separately prove:

1. **Canonical order and half-open membership**
   - shuffled rows and shuffled folds yield equal `TimeAwareValidationRun`;
   - `as_of == training_start` belongs to training;
   - `as_of == training_end` does not;
   - `as_of == validation_start` belongs to validation;
   - `as_of == validation_end` does not.

2. **Late maturity exclusion**
   - historical row inside training interval with selected target completing one millisecond after validation start is excluded;
   - `training_target_unavailable_at_split_count` increases;
   - its label cannot affect the fold artifact.

3. **Exact maturity boundary inclusion**
   - completion exactly at validation start is eligible for training.

4. **Pending selected target exclusion**
   - pending target in training window is withheld and counted unavailable.

5. **Validation population independence from target state**
   - every row in validation interval receives a prediction whether selected target is pending, completed, or absent;
   - changing only validation target status/return/completion does not change identities, model, probabilities, or fingerprint.

6. **Non-target future-label isolation**
   - changing any non-selected future label anywhere does not alter artifacts, predictions, or run fingerprint.

7. **Sequential walk-forward maturity**
   - a row from fold 1 validation can train fold 2 only when its selected target completion is no later than fold 2 validation start;
   - a later completion keeps it excluded.

8. **Fold-local fresh training**
   - artifacts reflect each fold's own mature training population/fingerprint;
   - model version remains the caller-supplied E3 model version.

9. **Fail-closed inputs**
   - rows must be non-empty tuple of exact dicts;
   - wrong D6 schema, missing/extra physical column, bad identity, duplicate identity fail;
   - empty validation population fails with fold name;
   - one-class/too-few/all-missing training failures surface with fold name.

10. **Metric firewall and purity**
    - result dataclass fields contain none of `accuracy`, `auc`, `calibration`, `expectancy`, `pnl`, `profit_factor`, `drawdown`, `win_rate`, `turnover`, `cost`, `promotion`;
    - importing `shreks_brain.validation` does not put `sklearn` in `sys.modules` in a fresh subprocess;
    - `engine.py` source contains no `sqlite3`, `pyarrow`, `pathlib`, `requests`, `random`, or wall-clock time import.

- [ ] **Step 2: Run engine RED**

Expected Python failure: `run_time_aware_validation` missing from `shreks_brain.validation`; no production engine exists yet.

- [ ] **Step 3: Implement global D6 row validation**

In `engine.py`, define private helpers only. Validate:

```python
expected_columns = set(RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS)
```

Each row must be exact `dict`, with exact keys equal to the sealed physical column set, correct `RESEARCH_DATASET_SCHEMA_VERSION`, non-empty `candidate_mint`, non-negative non-bool `as_of_unix_ms`, and unique `(candidate_mint, as_of_unix_ms)` identity.

Return rows sorted by:

```python
(as_of_unix_ms, candidate_mint)
```

- [ ] **Step 4: Implement selected-target maturity gate**

For the request horizon define:

```python
prefix = f"label_{request.target.horizon_seconds}s_"
```

For a training-window row, classify as mature only when:

```python
status == "COMPLETED"
baseline == as_of
due == as_of + horizon_seconds * 1000
checkpoint is non-negative int and checkpoint >= due
completed is non-negative int and completed >= checkpoint
completed <= fold.validation_started_at_unix_ms
return_pct is finite int/float excluding bool
```

If status is not `COMPLETED`, required target value is absent, or completion is later than split, treat the target as unavailable at this split.

If status is `COMPLETED` but its chronology/schema values contradict the rules, raise `ValueError` with the fold name rather than silently withholding corrupted evidence.

- [ ] **Step 5: Execute each canonical fold**

For each fold sorted by validation boundary/name:

```python
training_window = tuple(
    row for row in rows
    if fold.training_started_at_unix_ms <= row["as_of_unix_ms"] < fold.training_ended_at_unix_ms
)
```

Partition mature rows versus target-unavailable-at-split rows. Call sealed E3:

```python
model = train_logistic_regression(mature_rows, request)
```

Wrap any E3 `ValueError`/training error with `fold {fold.name!r}: ...` while preserving the cause.

Select validation rows only by decision time:

```python
validation_rows = tuple(
    row for row in rows
    if fold.validation_started_at_unix_ms <= row["as_of_unix_ms"] < fold.validation_ended_at_unix_ms
)
```

Reject an empty validation population. Predict every selected row via:

```python
predict_positive_probability(model, row)
```

Build `ValidationFoldResult` with exact counts and canonical predictions.

- [ ] **Step 6: Implement deterministic run fingerprint**

Canonical JSON payload must include only provenance:

```text
schema version
validation policy version
canonical fold boundaries
model training request fields
for each fold: model training fingerprint
for each prediction: model version, mint, as_of, exact probability
```

Finite floats must be encoded deterministically with `float.hex()`; booleans must not be treated as numbers. Use compact sorted-key JSON and lowercase SHA-256.

Do not include any future validation label or evaluation metric in the fingerprint.

- [ ] **Step 7: Export engine and run focused verification**

Update `validation.__init__` so `__all__` is exactly the six symbols in the spec.

Run:

```bash
python -m pytest python/tests/test_time_validation_engine.py python/tests/test_time_validation_public_api.py -q
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: all green.

- [ ] **Step 8: Commit**

Commit message:

```text
feat: add E4 leakage-safe validation
```

---

### Task 3: Diff audit, documentation seal, and freeze

**Files:**
- Modify additions-only: `README.md`
- Replace with verification record: `docs/superpowers/plans/2026-08-24-phase-e4-time-validation.md`

**Interfaces:**
- Consumes the exact verified E4 behavior head.
- Produces an immutable E4 seal commit with documentation only.

- [ ] **Step 1: Verify exact behavior GREEN**

Require one fresh full CI run on the exact behavior head with:

```text
repository safety: success
Python tests: success
Rust tests/workspace metadata: success
```

Record the exact Python pass count and CI run ID.

- [ ] **Step 2: Audit sealed-E3 -> E4 behavior diff**

Allowed pre-seal scope only:

```text
docs/superpowers/specs/2026-08-24-phase-e4-time-validation-design.md
docs/superpowers/plans/2026-08-24-phase-e4-time-validation.md
python/src/shreks_brain/validation/*
python/tests/test_time_validation_*.py
```

Reject any change to E3 learning production files, D6 schema/export code, E2 baselines, B7/B8/B9, paper/exits, Rust source, migrations, or dependencies.

- [ ] **Step 3: Build documentation seal detached**

Append a README section titled `## Time-aware challenger validation` describing:

- explicit chronological folds;
- label-maturity gate at validation start;
- every validation decision receives a prediction independent of label status;
- one fresh E3 model per fold;
- no metrics or profitability claim;
- E5 owns unseen economic evaluation.

README must have zero deletions.

Replace this plan with a verification record containing:

- E3 frozen base SHA;
- design commit;
- contract RED SHA/CI and expected failure;
- contract GREEN SHA/CI;
- engine RED SHA/CI and expected failure;
- engine GREEN SHA/CI with Python pass count;
- sealed-E3 -> E4 behavior diff audit;
- detached seal audit;
- explicit statement that profitability remains unproven and live money disabled.

Do not put the final seal SHA or its CI run inside the tracked verification record; record those only in PR metadata after the seal exists.

- [ ] **Step 4: Audit detached seal**

Require exactly:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-e4-time-validation.md
```

Require README additions > 0 and deletions == 0. No third file is allowed.

- [ ] **Step 5: Attach seal and run exact-head CI**

Move `feat/phase-e4-time-validation` to the audited seal commit. Run/observe full CI and require all three jobs green.

- [ ] **Step 6: Update stacked PR metadata and freeze**

Create/update a draft PR targeting `feat/phase-e3-model-training`. PR metadata must state:

- exact E3 base seal;
- TDD evidence for both RED/GREEN cycles;
- exact final E4 seal SHA;
- exact final CI run and Python pass count;
- leakage invariants;
- metric firewall;
- audited diff scope;
- profitability unproven and live money disabled;
- E5 Trading Evaluation is next and must start from the E4 seal.

After this metadata update, perform no tracked-file change on E4. E5 branches directly from the immutable E4 seal.
