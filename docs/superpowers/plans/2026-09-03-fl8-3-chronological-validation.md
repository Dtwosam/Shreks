# FL8.3 Chronological Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic leakage-resistant chronological train/validation/test validation for sealed FL8.2 Fast Lane forecast baselines.

**Architecture:** Add a sibling `shreks_brain.fast_validation` package that consumes exact FL8.1 bundles and FL8.2 requests. Each explicit fold forms chronological raw populations, quarantines shared mint/actor/signature groups across partitions, trains one model from mature post-quarantine training rows only, then predicts validation and test rows without reading their labels. A narrow trainer-submodule helper restricts FL8.2 training to explicit decision identities while preserving the sealed root API and full-bundle behavior.

**Tech Stack:** Python 3.12, frozen dataclasses, hashlib/json/math, existing FL8.1 bundle types, existing FL8.2 trainer/inference, pytest, existing scikit-learn optional dependency.

**Spec:** `docs/superpowers/specs/2026-09-03-fl8-3-chronological-validation-design.md`

## Global Constraints

- Consume only exact FL8.1 `FastTrainingBundle` values.
- Preserve `shreks_brain.fast_learning.__all__` unchanged.
- No random/stratified splitting.
- Explicit half-open train/validation/test intervals only.
- Shared mint, non-null decision actor, or decision signature across partitions quarantines every affected row.
- Training targets must be complete, non-null, exact-horizon, and have elapsed by validation start.
- Validation/test labels must not influence membership, fitted parameters, or predictions. Whole-source FL8.2/FL8.3 provenance fingerprints may change when any source label changes and must remain auditable.
- The same training-only model predicts both validation and test populations.
- FL8.3 computes no quality/calibration/economic metric and performs no promotion.
- No provider, PAPER execution, signer, transaction submission, registry/champion, or LIVE authority.
- LIVE remains disabled.

---

### Task 1: Validation contracts

**Files:**
- Create: `python/src/shreks_brain/fast_validation/models.py`
- Test: `python/tests/test_fast_chronological_models.py`

**Interfaces:**
- Produces: schema constants, `FastChronologicalFold`, `FastChronologicalValidationPolicy`, `FastLeakageQuarantineSummary`, `FastChronologicalFoldResult`, `FastChronologicalValidationRun`.

- [ ] **Step 1: Write failing contract tests**

Prove exact schema constants, frozen/slotted models, interval ordering, unique fold names, non-overlapping evaluation intervals, count reconciliation, prediction/model target/horizon/version equality, canonical prediction order, and SHA-256 fields.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fast_chronological_models.py -q
```

Expected: missing `shreks_brain.fast_validation`.

- [ ] **Step 3: Implement minimal model contracts**

Use exact-type validation and fail closed on malformed intervals/counts/fingerprints.

- [ ] **Step 4: Run GREEN and commit**

```bash
python -m pytest python/tests/test_fast_chronological_models.py -q
git add python/src/shreks_brain/fast_validation/models.py python/tests/test_fast_chronological_models.py
git commit -m "feat(fl8.3): define chronological validation contracts"
```

### Task 2: Decision-identity restricted FL8.2 training

**Files:**
- Modify: `python/src/shreks_brain/fast_learning/trainer.py`
- Test: `python/tests/test_fast_forecast_subset_training.py`

**Interfaces:**
- Produces: `train_fast_forecast_baseline_for_decision_identities(bundle, request, decision_identities)` at the trainer-submodule level only.

- [ ] **Step 1: Write failing subset-training tests**

Prove selected identities only affect training rows/fingerprints, duplicate/unknown/empty identities fail closed, selected incomplete/null targets count as unavailable, and existing `train_fast_forecast_baseline` output remains unchanged.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fast_forecast_subset_training.py python/tests/test_fast_forecast_training.py -q
```

- [ ] **Step 3: Refactor trainer minimally**

Generalize the private preparation path to accept an optional allowed identity set and route both public functions through the same fitting implementation. Do not alter `shreks_brain.fast_learning.__all__`.

- [ ] **Step 4: Run GREEN and commit**

Run the same tests and commit only confirmed changes.

### Task 3: Leakage quarantine and chronological engine

**Files:**
- Create: `python/src/shreks_brain/fast_validation/engine.py`
- Test: `python/tests/test_fast_chronological_engine.py`
- Reuse: `python/tests/fast_forecast_fixtures.py`

**Interfaces:**
- Produces: `run_fast_chronological_validation(bundle, request, policy) -> FastChronologicalValidationRun`.

- [ ] **Step 1: Write failing chronology/quarantine tests**

Cover half-open partition boundaries, raw empty partitions, shared mint quarantine, shared actor quarantine, shared signature quarantine, quarantine union behavior, post-quarantine disjointness, empty-after-quarantine failure, exact horizon maturity at validation start, incomplete/null training targets, deterministic fold ordering, and validation/test label mutation isolation.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fast_chronological_engine.py -q
```

- [ ] **Step 3: Implement raw populations and quarantine**

Build canonical partition row tuples by feature decision time. Derive shared group keys across partitions, remove every affected row, and construct a canonical quarantine fingerprint without exposing raw group lists in result models.

- [ ] **Step 4: Implement mature training and predictions**

Select post-quarantine training identities whose exact-horizon FL4 target is complete/non-null and whose horizon boundary is `<= validation_start`; train via the Task 2 helper; predict validation/test features through sealed FL8.2 pure-Python inference without reading validation/test labels.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest python/tests/test_fast_chronological_engine.py -q
```

### Task 4: Public API and authority firewall

**Files:**
- Create: `python/src/shreks_brain/fast_validation/__init__.py`
- Test: `python/tests/test_fast_chronological_authority.py`

**Interfaces:**
- Produces exact focused `shreks_brain.fast_validation.__all__`.

- [ ] **Step 1: Write failing import/authority tests**

Assert exact public API, clean subprocess import does not load sklearn, and production sources contain no provider/execution/signer/transaction/registry/champion/LIVE authority or metric names.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fast_chronological_authority.py -q
```

- [ ] **Step 3: Implement exact root exports**

Export only schema/models/engine symbols from the spec.

- [ ] **Step 4: Run GREEN and commit**

### Task 5: Real FL8.1 bundle integration and all-family proof

**Files:**
- Test: `python/tests/test_fast_chronological_integration.py`

**Interfaces:**
- Consumes actual FL8.1 bundle writer/reader and all four FL8.2 model families.

- [ ] **Step 1: Build a real disk-bundle fixture**

Create enough distinct mints/actors/signatures across chronological windows to leave clean train/validation/test populations while also inserting quarantined cross-partition examples and incomplete targets.

- [ ] **Step 2: Prove all four families**

Write/read the FL8.1 bundle, run FL8.3 for mean/ridge/prior/logistic requests, assert canonical training-only artifacts and validation/test predictions, and prove validation/test target-only mutations cannot change membership, fitted parameters, or predictions while source/artifact/run provenance fingerprints remain sensitive to the changed source evidence.

- [ ] **Step 3: Run focused and full Python suites**

```bash
python -m pytest python/tests/test_fast_chronological_integration.py -q
python -m pytest python/tests -q
```

- [ ] **Step 4: Commit**

### Task 6: Candidate CI, clean history, merge, and seal

- [ ] Obtain candidate four-gate GREEN: repository safety, Python, Rust, ARM64 release.
- [ ] Audit clean scope against SEALED FL8.2 merged-main `1ec24302951dd154ecbcff577f45fa6e9c673aa6`.
- [ ] Collapse authoring history to exactly `design -> plan -> consolidated RED contracts -> implementation`, preserving the verified final tree.
- [ ] Obtain fresh exact-clean-head four-gate GREEN.
- [ ] Update draft PR with TDD/scope/authority proof and mark ready only at the exact verified head.
- [ ] Guarded merge with `expected_head_sha`, preserving four-commit history via merge commit.
- [ ] Obtain fresh push-triggered merged-main four-gate GREEN.
- [ ] Only then mark FL8.3 SEALED.

FL8.3 does not establish predictive edge or profitability. FL8.4 remains the next required phase.
