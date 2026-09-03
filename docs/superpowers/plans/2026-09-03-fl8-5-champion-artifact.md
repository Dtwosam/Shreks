# FL8.5 Champion Artifact Implementation Plan

**Goal:** Build a deterministic immutable multi-horizon Fast Lane forecast champion bundle that embeds exact FL8.2 runtime model artifacts and cross-links exact FL8.3 chronological validation plus FL8.4 TEST evaluation evidence, without automatic ranking/promotion or trading authority.

**Base:** SEALED FL8.4 merged-main `1d74121b2c75f674ac902700610c18ac8d919ab9`, merged-main four-gate GREEN CI `33803190407`.

**Package:** `shreks_brain.fast_champion`

**Spec:** `docs/superpowers/specs/2026-09-03-fl8-5-champion-artifact-design.md`

## Global constraints

- Exact FL8.2 runtime artifacts only.
- Exact FL8.3 validation runs only.
- Exact FL8.4 TEST evaluation reports only.
- No training, metric ranking, thresholding, or automatic promotion.
- Explicit caller-supplied selection reference/time/reason is mandatory.
- One member per `(target, horizon_ms)`.
- All members use the same feature schema, FL8.1 source bundle fingerprint, and FL4 label version.
- Runtime artifact may be a final refit aligned to the same sealed request/source evidence; it need not equal any fold-specific model fingerprint.
- The stored FL8.3 run fingerprint is treated as sealed upstream evidence and must cross-link exactly to FL8.4. FL8.5 does not duplicate FL8.3 training/replay merely to regenerate that fingerprint.
- Embedded FL8.2 artifact and FL8.4 report fingerprints are independently recomputed before packaging.
- No provider/DB/PAPER/risk/signer/transaction/legacy-registry mutation/LIVE authority.
- LIVE remains disabled.

---

### Task 1: Champion contracts

**Files:**
- Create `python/src/shreks_brain/fast_champion/models.py`
- Test `python/tests/test_fast_forecast_champion_models.py`

- [ ] RED exact schema constants and frozen/slotted types.
- [ ] RED explicit selection field validation.
- [ ] RED canonical member keys `{target}@{horizon}ms` and unique target/horizon.
- [ ] RED common feature schema/source bundle/label version invariants.
- [ ] RED canonical lexical member ordering and exact lookup/no fallback.
- [ ] RED champion fingerprint shape and top-level count/invariant reconciliation.
- [ ] Implement minimal contracts.

### Task 2: Evidence-aligned builder

**Files:**
- Create `python/src/shreks_brain/fast_champion/builder.py`
- Test `python/tests/test_fast_forecast_champion_builder.py`
- Fixture `python/tests/fast_forecast_champion_fixtures.py`

- [ ] RED exact input-type requirements.
- [ ] RED FL8.4 report must select TEST.
- [ ] RED report validation fingerprint equals FL8.3 run fingerprint.
- [ ] RED artifact/run/report source bundle fingerprints match.
- [ ] RED model version/family/target/horizon align across artifact, run request, and report.
- [ ] RED artifact training-policy version equals run request policy version.
- [ ] RED feature schema and FL4 label version align with fold artifacts.
- [ ] RED embedded FL8.2 artifact fingerprint recomputes exactly.
- [ ] RED FL8.4 report fingerprint recomputes exactly.
- [ ] RED duplicate target/horizon sources fail closed.
- [ ] RED input source ordering is non-semantic.
- [ ] Implement packaging only; no training/ranking.

### Task 3: Immutable codec/runtime loadability

**Files:**
- Create `python/src/shreks_brain/fast_champion/codec.py`
- Test `python/tests/test_fast_forecast_champion_codec.py`

- [ ] RED canonical deterministic JSON bytes and trailing newline.
- [ ] RED write refuses overwrite.
- [ ] RED read enforces exact keys/enums/types and embedded artifact fingerprints.
- [ ] RED champion fingerprint tamper/unknown/missing key rejection.
- [ ] RED loaded embedded artifact produces identical FL8.2 Python reference prediction to source artifact.
- [ ] Implement exact embedded FL8.2 artifact reconstruction; no pickle/joblib.

### Task 4: Public API and authority firewall

**Files:**
- Create `python/src/shreks_brain/fast_champion/__init__.py`
- Test `python/tests/test_fast_forecast_champion_authority.py`

- [ ] RED exact eight-name public API.
- [ ] RED import does not eagerly load sklearn/NumPy/PyArrow.
- [ ] RED production source has no provider/network/sqlite/PAPER/risk/TradeIntent/signer/transaction/registry mutation/LIVE code.
- [ ] RED no API names implying rank/compare/promote/approve/live.
- [ ] Implement focused exports only.

### Task 5: Real Fast Lane integration

**Files:**
- Test `python/tests/test_fast_forecast_champion_integration.py`

- [ ] Build/read an actual FL8.1 bundle fixture.
- [ ] Train final refit FL8.2 continuous and binary runtime artifacts.
- [ ] Run FL8.3 chronological validation for matching requests.
- [ ] Build FL8.4 TEST reports with explicit point-in-time context.
- [ ] Package at least two target/horizon members under one champion version.
- [ ] Persist/read champion exactly.
- [ ] Prove loaded member Python predictions equal direct source-artifact predictions.
- [ ] Prove no real registry status transition or production promotion is created.

### Task 6: Candidate verification and seal

- [ ] Run focused FL8.5 Python tests.
- [ ] Run full Python suite.
- [ ] Four-gate candidate CI GREEN.
- [ ] Exact scope audit against SEALED FL8.4.
- [ ] Collapse history to `design -> plan -> consolidated RED -> implementation` preserving verified final tree.
- [ ] Fresh exact-clean-head four-gate GREEN.
- [ ] Update PR proof and mark ready.
- [ ] Guarded merge using expected head SHA.
- [ ] Fresh merged-main four-gate GREEN.
- [ ] Mark FL8.5 SEALED only after merged-main proof.

FL8.5 does not prove economic edge, profitability, Rust inference parity, shadow performance, LIVE eligibility, or action-policy quality. FL8.6 is next.