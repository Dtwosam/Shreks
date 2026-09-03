# FL8.4 Forecast Calibration Implementation Plan

**Goal:** Build deterministic measurement-only evaluation for sealed FL8.3 unseen forecasts, including continuous quality, binary calibration, and explicit point-in-time segmentation by fold, regime, strategy family, executable liquidity, and expected round-trip cost.

**Architecture:** Add isolated `shreks_brain.fast_evaluation`. It consumes exact FL8.1 bundle evidence, exact FL8.3 validation runs, explicit point-in-time context keyed by decision identity, and an explicit versioned policy. It joins only the selected validation or test partition to exact FL4 targets and emits immutable metrics/report evidence. It never trains, calibrates weights, promotes, selects actions, or executes.

**Tech Stack:** Python 3.12, frozen dataclasses, enum, hashlib/json/math/pathlib, existing FL8.1/FL8.2/FL8.3 types, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-03-fl8-4-forecast-calibration-design.md`

## Global constraints

- Base only on SEALED FL8.3 merged-main `e233870fc2fa62b8a94869472e63f4a2b5e9c52e`.
- Exact FL8.1 bundle fingerprint must match the FL8.3 validation run.
- Score exactly one partition: VALIDATION or TEST.
- Never mix validation and test into one population.
- Join targets by exact seven-field identity + exact horizon + exact FL4 label version.
- Incomplete/null targets are unavailable, never zero-filled or imputed.
- Context must be point-in-time and cover the union of validation/test prediction identities exactly.
- No model fitting or recalibration transform.
- No champion comparison/promotion; FL8.5 owns that.
- No action policy, PAPER authority, provider, signer, transaction submission, or LIVE authority.
- LIVE remains disabled.

---

### Task 1: Evaluation contracts and policy

**Files:**
- Create: `python/src/shreks_brain/fast_evaluation/models.py`
- Test: `python/tests/test_fast_forecast_evaluation_models.py`

- [ ] Write RED tests for schema constants and exact enum.
- [ ] Prove context requires exact identity timestamp, sorted unique strategy families, non-negative finite optional liquidity/cost values.
- [ ] Prove policy validates partition, probability bucket count, strict numeric boundaries, and log-loss epsilon.
- [ ] Prove metric dataclasses reconcile arithmetic and metric kind.
- [ ] Prove report contract has no champion/promotion/action fields and validates fingerprints/count dimensions.
- [ ] Run targeted RED; expected missing `shreks_brain.fast_evaluation`.
- [ ] Implement minimal frozen/slotted models and validation helpers.
- [ ] Run targeted GREEN.

### Task 2: Exact target join and partition isolation

**Files:**
- Create: `python/src/shreks_brain/fast_evaluation/engine.py`
- Test: `python/tests/test_fast_forecast_evaluation_engine.py`
- Fixture: `python/tests/fast_forecast_evaluation_fixtures.py`

- [ ] Build deterministic FL8.1 + FL8.3 in-memory fixtures with validation/test predictions and labels.
- [ ] RED: selected partition uses only its predictions.
- [ ] RED: exact identity/horizon joins are mandatory.
- [ ] RED: incomplete/null selected target increments unavailable count and is excluded.
- [ ] RED: missing/duplicate target identity fails closed.
- [ ] RED: zero scored observations fails closed.
- [ ] Implement canonical prediction selection and exact FL4 join.
- [ ] Prove validation and test metric populations never mix.

### Task 3: Continuous forecast quality

**Files:**
- Modify: `python/src/shreks_brain/fast_evaluation/engine.py`
- Test: `python/tests/test_fast_forecast_evaluation_continuous.py`

- [ ] RED exact hand-calculated mean prediction/actual/bias/MAE/RMSE fixture.
- [ ] RED negative and positive target values.
- [ ] RED non-finite contradiction fails closed.
- [ ] Implement standard-library deterministic arithmetic with `math.fsum`.
- [ ] Mark only FL4 cost-adjusted targets as `target_is_cost_adjusted=True`.
- [ ] Prove no second synthetic cost subtraction occurs.

### Task 4: Binary calibration metrics

**Files:**
- Modify: `python/src/shreks_brain/fast_evaluation/engine.py`
- Test: `python/tests/test_fast_forecast_evaluation_binary.py`

- [ ] RED hand-calculated Brier score.
- [ ] RED clipped binary log loss with policy epsilon.
- [ ] RED equal-width calibration bucket boundaries including exact `0.0` and `1.0`.
- [ ] RED ECE arithmetic.
- [ ] Implement generic binary measurement without importing legacy promotion/evaluation report types.
- [ ] Prove probability outside `[0, 1]` fails closed through existing prediction/report contracts.

### Task 5: Point-in-time context and segmentation

**Files:**
- Modify: `python/src/shreks_brain/fast_evaluation/engine.py`
- Test: `python/tests/test_fast_forecast_evaluation_segments.py`

- [ ] RED exact all-partition context coverage.
- [ ] RED duplicate/missing/extra context fails closed.
- [ ] RED context timestamp must equal decision identity timestamp.
- [ ] RED deterministic regime segments and reconciliation.
- [ ] RED overlapping strategy-family segments without overall-count duplication.
- [ ] RED liquidity bucket lower-bound/equality/unknown behavior.
- [ ] RED cost bucket lower-bound/equality/unknown behavior.
- [ ] RED fold populations reconcile to overall.
- [ ] Implement canonical grouping and stable names.

### Task 6: Provenance and validation/test isolation

**Files:**
- Modify: `python/src/shreks_brain/fast_evaluation/engine.py`
- Test: `python/tests/test_fast_forecast_evaluation_provenance.py`

- [ ] RED context fingerprint independent of input tuple ordering.
- [ ] RED report fingerprint deterministic.
- [ ] RED validation-label-only mutation cannot change TEST scored target values or TEST metric payloads when TEST labels/predictions/context are unchanged.
- [ ] Preserve whole-source provenance differences from sealed FL8.2/FL8.3 rather than masking them.
- [ ] Include fold model artifact fingerprints in report provenance.

### Task 7: Immutable report codec and public API

**Files:**
- Create: `python/src/shreks_brain/fast_evaluation/codec.py`
- Create: `python/src/shreks_brain/fast_evaluation/__init__.py`
- Test: `python/tests/test_fast_forecast_evaluation_codec.py`
- Test: `python/tests/test_fast_forecast_evaluation_authority.py`

- [ ] RED exact public API.
- [ ] RED clean subprocess import does not load sklearn or NumPy.
- [ ] RED canonical JSON round trip and byte determinism.
- [ ] RED overwrite refusal.
- [ ] RED unknown/missing key and fingerprint tamper rejection.
- [ ] RED production source has no promotion/registry/provider/PAPER/signer/transaction/LIVE authority.
- [ ] Implement canonical exact-key codec and focused root exports.

### Task 8: Real FL8.1 + FL8.3 integration

**Files:**
- Test: `python/tests/test_fast_forecast_evaluation_integration.py`

- [ ] Reuse actual FL8.1 bundle writer/reader pattern.
- [ ] Generate leakage-resistant FL8.3 validation/test predictions.
- [ ] Evaluate mean/ridge continuous forecasts and prior/logistic binary forecasts.
- [ ] Include explicit point-in-time regime/strategy/liquidity/cost context.
- [ ] Prove continuous and binary reports persist/read exactly.
- [ ] Prove incomplete/no-trade target evidence remains unavailable rather than fabricated.
- [ ] Prove a cost-adjusted target report is flagged and measured without double-costing.

### Task 9: Candidate verification and seal

- [ ] Run focused Python FL8.4 tests.
- [ ] Run full Python suite.
- [ ] Obtain four-gate candidate CI GREEN: repository safety, Python, Rust, native ARM64.
- [ ] Audit exact diff against SEALED FL8.3.
- [ ] Collapse authoring history to `design -> plan -> consolidated RED -> implementation` preserving verified final tree.
- [ ] Obtain fresh exact-clean-head four-gate GREEN.
- [ ] Update PR proof and mark ready only at exact verified head.
- [ ] Guarded merge with `expected_head_sha` and merge method `merge`.
- [ ] Obtain fresh merged-main four-gate GREEN.
- [ ] Mark FL8.4 SEALED only after merged-main proof.

FL8.4 does not prove champion status or profitability and grants no capital-changing authority. FL8.5 is the next phase after sealing.
