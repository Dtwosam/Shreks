# FL8.6 Rust Inference Parity — Implementation Plan

**Goal:** Load sealed FL8.5 champion JSON in Rust, validate its structure/fingerprint, perform sealed FL8.2 inference over the 169-element raw feature vector, and prove Python/Rust parity within explicit tolerances.

**Base:** SEALED FL8.5 merged-main `04483643a9fbb24264c27f87291f5446ff7d466a`, merged-main four-gate GREEN CI `33805473489`.

**Spec:** `docs/superpowers/specs/2026-09-03-fl8-6-rust-inference-parity-design.md`

## Global constraints

- Exact FL8.5 champion JSON/wire values.
- Exact FL8.2 transform/inference semantics.
- No training/calibration fitting.
- No live-state feature extraction; FL10 owns runtime wiring.
- No action policy, sizing, PAPER execution, signer, transaction, registry promotion, or LIVE authority.
- Fail closed on unknown fields, malformed schemas, fingerprint mismatch, missing member, non-finite input, or wrong feature count.
- Add only `serde`, `serde_json`, `sha2` to `shreks-core`.
- Numerical parity tolerance: absolute `1e-12`, relative `1e-12`.

---

### Task 1: Compact cross-language spec and RED contracts

**Files:**
- Create `crates/shreks-core/tests/fixtures/fl8_6_parity_spec.json`
- Create `crates/shreks-core/tests/fast_forecast_parity.rs`
- Create `python/tests/test_fast_forecast_rust_parity_fixture.py`

- [ ] Fixture covers all four model families using sparse coefficient definitions expanded to 169 features.
- [ ] Fixture records Python-authoritative artifact/champion fingerprints.
- [ ] Fixture contains sparse raw feature cases with value overrides/null indices and expected Python predictions.
- [ ] Python test expands full artifacts, verifies sealed FL8.2 artifact fingerprints, builds/writes/reads FL8.5 champion, and verifies expected predictions.
- [ ] Rust test imports the not-yet-existing forecast API and therefore fails compilation intentionally.
- [ ] RED Rust tests cover load, four model families, tolerance rule, test-only binary side-of-0.5 parity, tamper/unknown-field rejection, exact lookup/no fallback, wrong feature count, and non-finite feature rejection.

### Task 2: Rust contracts and loader

**Files:**
- Modify `crates/shreks-core/Cargo.toml`
- Create `crates/shreks-core/src/fast_lane/forecast.rs`
- Modify `crates/shreks-core/src/fast_lane/mod.rs`
- Modify `crates/shreks-core/src/lib.rs`

- [ ] Add `serde`, `serde_json`, `sha2` only.
- [ ] Mirror exact FL8.5/FL8.2 enums/structs with `deny_unknown_fields`.
- [ ] Validate schema/version/strings/counts/SHA shapes/member order/member keys/common provenance.
- [ ] Validate family/target-kind compatibility and trained-vs-naive artifact shape.
- [ ] Validate exact 169 transform names and coefficient count.
- [ ] Implement Python-compatible finite `float.hex()` formatting for signed zero, normal, and subnormal binary64 values.
- [ ] Recompute FL8.5 champion fingerprint from canonical transformed JSON and prove parity against the Python-authored fixture fingerprint.
- [ ] Re-export the narrow forecast surface through `fast_lane/mod.rs` and existing crate-root `lib.rs` convention.

### Task 3: Rust inference

**Files:**
- `crates/shreks-core/src/fast_lane/forecast.rs`

- [ ] Exact target/horizon lookup; no fallback.
- [ ] Require 169 raw features.
- [ ] Reject non-finite present values.
- [ ] Median-impute and apply `(x - mean) / scale`.
- [ ] Use compensated summation.
- [ ] Mean/prior return constants.
- [ ] Ridge returns linear score.
- [ ] Logistic uses Python-equivalent stable sigmoid.
- [ ] Binary outputs remain `[0, 1]`.
- [ ] Return narrow prediction metadata only.

### Task 4: Authority/API boundary

**Files:**
- `crates/shreks-core/src/fast_lane/forecast.rs`
- `crates/shreks-core/src/fast_lane/mod.rs`
- `crates/shreks-core/src/lib.rs`
- `crates/shreks-core/tests/fast_forecast_parity.rs`
- `python/tests/test_fast_forecast_rust_parity_authority.py`

- [ ] Export only forecast contracts/loader/predictor/constants/error type.
- [ ] No rank/compare/promote/action/position/trade/live API.
- [ ] Source test rejects provider/network/database/wall-clock/randomness/training-action/trade/signer/submission/promotion/LIVE dependencies in `forecast.rs`.
- [ ] Dependency test locks `shreks-core` additions to `serde`, `serde_json`, and `sha2`.

### Task 5: Verification and seal

- [ ] Intentional RED CI before production module exists.
- [ ] Candidate Python/Rust/ARM64/safety GREEN.
- [ ] Exact scope audit against SEALED FL8.5.
- [ ] Clean history `design -> plan -> consolidated RED -> implementation` preserving verified final tree.
- [ ] Fresh exact-clean-head four-gate GREEN.
- [ ] Update PR proof and mark ready.
- [ ] Guarded merge using expected head SHA.
- [ ] Fresh merged-main four-gate GREEN.
- [ ] Mark FL8.6 SEALED only after merged-main proof.

FL8.6 proves cross-language inference parity only. It does not prove economic edge, profitability, action-policy quality, live-state runtime latency, shadow performance, or LIVE eligibility.