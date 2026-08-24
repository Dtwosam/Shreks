# Phase E4 Time-Aware Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, leakage-safe chronological validation that trains a fresh sealed-E3 model per explicit fold and predicts every row in the next unseen interval without computing evaluation metrics.

**Architecture:** Add `shreks_brain.validation` with immutable contracts in `models.py` and orchestration in `engine.py`. E4 validates logical D6 rows and explicit half-open folds, withholds training targets that were not knowable by each validation boundary, delegates fitting/prediction unchanged to sealed E3, and returns canonical fold results plus a provenance-only run fingerprint.

**Tech Stack:** Python 3.12+, standard library dataclasses/hashlib/json/math, sealed D6 research schema, sealed E3 learning APIs, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-e4-time-validation-design.md`

## Global Constraints

- Base exactly on sealed E3 head `1328efce85464f3f1b1636d837bcefb1193c2eac`; do not modify E3 production files.
- Schema version is exactly `e4-time-validation-v1`.
- Caller supplies all fold boundaries, model features, target, model version, and hyperparameters; E4 invents no defaults.
- Training and validation intervals are half-open.
- A training-window row may train only when its selected target is valid and `completed_at_unix_ms <= validation_started_at_unix_ms`.
- Validation membership depends only on decision timestamp, never target state.
- Every validation row is predicted; future validation labels cannot affect model, prediction, membership, or fingerprint.
- E4 computes no predictive/trading/cost/promotion metric.
- Input row/fold order must not change canonical output or fingerprint.
- Importing `shreks_brain.validation` must not eagerly import sklearn.
- Production E4 code performs no SQLite, PyArrow, filesystem, network, wall-clock, or random access.
- Every branch move is single-purpose: tests-only RED, implementation GREEN, or docs-only seal.

---

### Task 1: Public validation contracts

**Files:**
- Create: `python/src/shreks_brain/validation/models.py`
- Create: `python/src/shreks_brain/validation/__init__.py`
- Create: `python/tests/test_time_validation_models.py`
- Create: `python/tests/test_time_validation_public_api.py`

**Interfaces:**
- Produces `TIME_AWARE_VALIDATION_SCHEMA_VERSION`.
- Produces frozen/slotted `ChronologicalValidationFold`, `TimeAwareValidationPolicy`, `ValidationFoldResult`, `TimeAwareValidationRun`.
- Task 1 public API contains those five real contract symbols only. Task 2 RED expands it to the final six-symbol API by requiring `run_time_aware_validation`; no placeholder engine function is allowed.

- [ ] **Step 1: Write contract RED tests**

Tests import `shreks_brain.validation`, require schema `e4-time-validation-v1`, and prove exact contract validation:

```python
ChronologicalValidationFold(
    name="fold-1",
    training_started_at_unix_ms=1_000,
    training_ended_at_unix_ms=2_000,
    validation_started_at_unix_ms=2_000,
    validation_ended_at_unix_ms=3_000,
)
```

Reject empty names, bool/negative timestamps, empty intervals, `training_end > validation_start`, and empty validation. `TimeAwareValidationPolicy` requires a non-empty tuple of exact folds, unique names, and non-overlapping validation intervals after canonical sort `(validation_start, validation_end, name)`; adjacent `[2000,3000)` and `[3000,4000)` is valid.

Construct a valid sealed-E3 artifact/prediction fixture and prove `ValidationFoldResult` reconciliation: `mature == model.training_row_count`, `window == mature + unavailable`, `validation_row_count == len(predictions)`, model versions match, predictions are `(as_of,mint)` sorted and inside the validation interval. Mutate each invariant and require `ValueError`.

`TimeAwareValidationRun` requires exact schema, non-empty policy version, exact `ModelTrainingRequest`, non-empty canonical fold results with unique names, and lowercase 64-char SHA-256.

Task 1 `__all__` test requires exactly:

```python
(
    "TIME_AWARE_VALIDATION_SCHEMA_VERSION",
    "ChronologicalValidationFold",
    "TimeAwareValidationPolicy",
    "ValidationFoldResult",
    "TimeAwareValidationRun",
)
```

- [ ] **Step 2: Run RED**

Attach tests-only commit. Expected Python failure: missing `shreks_brain.validation`. Require no unrelated failure.

- [ ] **Step 3: Implement contracts**

Use exact-type validation patterns consistent with E3. `ChronologicalValidationFold` enforces:

```python
training_start < training_end <= validation_start < validation_end
```

`TimeAwareValidationPolicy` accepts overlapping training intervals but rejects overlapping validation intervals. `ValidationFoldResult` and `TimeAwareValidationRun` enforce the spec reconciliation/canonical-order rules. `__init__.py` exports only the five Task 1 contract symbols.

- [ ] **Step 4: Verify GREEN**

Run full CI: repository safety, `python -m pytest python/tests -q`, `cargo metadata --no-deps --format-version 1`, `cargo test --workspace`.

- [ ] **Step 5: Commit**

`feat: define E4 validation contracts`

---

### Task 2: Leakage-safe chronological engine

**Files:**
- Create: `python/src/shreks_brain/validation/engine.py`
- Modify: `python/src/shreks_brain/validation/__init__.py`
- Create: `python/tests/test_time_validation_engine.py`
- Modify: `python/tests/test_time_validation_public_api.py`

**Interfaces:**
- Produces `run_time_aware_validation(rows: tuple[dict[str, object], ...], request: ModelTrainingRequest, policy: TimeAwareValidationPolicy) -> TimeAwareValidationRun`.
- Reuses sealed `train_logistic_regression` and `predict_positive_probability` unchanged.

- [ ] **Step 1: Write engine RED tests**

Use D6 row fixtures built from the exact `RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS` physical set. Use a 300-second target and explicit two-class synthetic training populations. Prove separately:

- shuffled rows/folds produce equal run; half-open boundary membership is correct;
- a historical target completing 1ms after validation start is withheld and counted unavailable;
- completion exactly at validation start is eligible;
- pending selected target is withheld;
- every validation row is predicted regardless of target state;
- changing validation labels cannot change fold models, predictions, membership, or fingerprint;
- changing non-target future labels cannot change artifacts/predictions/fingerprint;
- an earlier validation row may train a later fold only after selected-target maturity;
- each fold trains a fresh artifact from its own mature population;
- malformed row tuple/schema/physical columns/identity/duplicates fail closed;
- empty validation, too-few/one-class/all-missing training fail with fold name context;
- result models expose no accuracy/AUC/calibration/expectancy/PnL/profit-factor/drawdown/win-rate/turnover/cost/promotion fields;
- fresh import of `shreks_brain.validation` leaves sklearn unloaded;
- `engine.py` contains no SQLite/PyArrow/pathlib/requests/random/wall-clock imports.

Update public API test to require final six symbols:

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

Expected Python failure: missing `run_time_aware_validation` / engine module only.

- [ ] **Step 3: Validate and canonicalize D6 rows**

Require non-empty tuple; each row exact `dict`; exact physical key set; `dataset_schema_version == RESEARCH_DATASET_SCHEMA_VERSION`; non-empty string mint; non-negative non-bool integer `as_of_unix_ms`; unique `(mint,as_of)` identity. Sort by `(as_of_unix_ms, candidate_mint)`.

- [ ] **Step 4: Implement target-maturity classification**

For `prefix = f"label_{horizon}s_"`, mature requires status `COMPLETED`, baseline equal decision time, due equal `as_of + horizon*1000`, checkpoint integer `>= due`, completed integer `>= checkpoint`, completed `<= validation_start`, and finite non-bool return.

Non-COMPLETED, absent target value, or completion after split is unavailable-at-split. A `COMPLETED` target with contradictory baseline/due/checkpoint/completion/value chronology is an error with fold-name context, not silently withheld.

- [ ] **Step 5: Execute canonical folds**

For each canonical fold, select training window by half-open decision time, partition mature/unavailable rows, train only mature rows via sealed E3, select validation rows only by validation decision time, reject empty validation, and predict every validation row via sealed E3 inference. Wrap E3 training errors with `fold '<name>': ...` context.

- [ ] **Step 6: Fingerprint provenance only**

SHA-256 canonical JSON includes schema/policy version, canonical fold boundaries, exact E3 request provenance, each fold's E3 training fingerprint, and prediction model-version/mint/as_of/exact finite probability. Encode finite floats with `float.hex()`. Include no validation target or metric.

- [ ] **Step 7: Export and verify GREEN**

Export final six-symbol API. Run focused engine/API tests, all Python tests, cargo metadata, cargo workspace tests, repository safety CI.

- [ ] **Step 8: Commit**

`feat: add E4 leakage-safe validation`

---

### Task 3: Diff audit, documentation seal, and freeze

**Files:**
- Modify additions-only: `README.md`
- Replace: `docs/superpowers/plans/2026-08-24-phase-e4-time-validation.md`

- [ ] **Step 1: Verify exact behavior GREEN**

Require fresh full CI on exact engine GREEN; record run ID and Python pass count.

- [ ] **Step 2: Audit sealed-E3 -> E4 behavior diff**

Allowed pre-seal paths only:

```text
docs/superpowers/specs/2026-08-24-phase-e4-time-validation-design.md
docs/superpowers/plans/2026-08-24-phase-e4-time-validation.md
python/src/shreks_brain/validation/*
python/tests/test_time_validation_*.py
```

Reject changes to E3 learning production, D6 research, E2 baselines, B7/B8/B9, paper/exits, dependencies, Rust source, or migrations.

- [ ] **Step 3: Build docs seal detached**

Append README `## Time-aware challenger validation` explaining explicit folds, label-maturity boundary, validation membership independent of labels, fresh E3 model per fold, no metrics/profitability claim, and E5 ownership.

Replace this plan with a verification record containing E3 base SHA, design commit, both RED/GREEN cycles and CI evidence, behavior diff audit, seal audit, and explicit profitability/live-money boundary. Do not put the final seal SHA or final seal CI inside tracked files.

- [ ] **Step 4: Audit detached seal**

Require exactly README + this verification record. README additions > 0, deletions == 0. No third file.

- [ ] **Step 5: Attach seal and exact-head CI**

Move branch to audited seal and require repository safety, Python, Rust/workspace all green.

- [ ] **Step 6: Stacked PR metadata and freeze**

Create/update draft PR targeting `feat/phase-e3-model-training`, recording exact E3 base seal, TDD evidence, final E4 seal SHA/CI/pass count, leakage invariants, metric firewall, diff scope, profitability unproven/live disabled, and E5 as next step. No tracked E4 changes afterward.
