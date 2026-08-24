# Phase D5 Smart-Wallet Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a point-in-time `d5-wallet-v1` feature vector that combines D2 candidate chronology, D3 historical wallet quality, D4 independence evidence, and optional D1 creator/deployer observations without changing `b2-v1` or trading behavior.

**Architecture:** Add immutable wallet-feature policy/input/output models plus one pure reducer under `shreks_brain.features`. Existing B2 market features remain untouched; D5 is a parallel feature contract for later Smart Wallet Cluster research and D6 dataset export.

**Tech Stack:** Python 3.12+, stdlib only, frozen/slots dataclasses, `StrEnum`, existing D1-D4 domain types, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-d5-smart-wallet-features-design.md`

## Global Constraints

- Base exactly sealed D4 head `6cef1a3d2095569a74388963c4bfae415ba549fb`.
- Keep `FEATURE_SCHEMA_VERSION == "b2-v1"`, `FeatureVector`, `FeatureInputs`, and `build_feature_vector` unchanged.
- D5 schema is exactly `WALLET_FEATURE_SCHEMA_VERSION == "d5-wallet-v1"`.
- No provider/RPC/SQLite/wall-clock/price/FX/token-decimal reads inside D5.
- Every D2 reconstruction, D3 profile, and D4 assessment uses exact D5 `as_of_unix_ms`.
- D4 wallet set equals the candidate reconstruction/profile wallet set.
- No production wallet-strength policy or thresholds ship.
- Missing optional strength evidence remains `UNKNOWN`.
- Missing/UNKNOWN D4 relationship evidence never becomes independence.
- No composite smart-wallet score, Smart Wallet Cluster trade eligibility, B7/B8/B9 change, signer, transaction submission, or live-money authority.
- TDD RED -> exact failure -> GREEN -> frozen exact-head seal.

---

### Task 1: Combined D5 RED contract

**Files:**
- Create: `python/tests/test_wallet_feature_models.py`
- Create: `python/tests/test_wallet_feature_engine.py`
- Create: `python/tests/test_wallet_feature_public_api.py`

**Interfaces:**
- Consumes: sealed D1 `WalletObservation`, D2 `WalletTradeReconstruction`, D3 `WalletProfile`, D4 `WalletIndependenceAssessment`.
- Produces: exact D5 model/reducer/public contract before production symbols exist.

- [ ] **Step 1: Write policy/model RED tests**

Pin a valid policy:

```python
WalletFeaturePolicy(
    version="d5-test-v1",
    entry_window_ms=300_000,
    exit_window_ms=300_000,
    creator_activity_window_ms=900_000,
    minimum_effective_closed_sample_size=5.0,
    minimum_evidence_sample_confidence=0.5,
    minimum_median_return_pct=10.0,
    minimum_win_rate=0.55,
    maximum_rug_exposure_rate=0.10,
    maximum_median_drawdown_pct=35.0,
)
```

Require rejection of empty version; zero/negative/bool windows; non-finite values; non-positive minimum sample/confidence/return; rates outside `0..1`; and drawdown outside `0..100`.

Pin exact enum values `STRONG`, `NOT_STRONG`, `UNKNOWN` and frozen/slots dataclasses.

Validate `WalletStrengthAssessment` count/metric/check-name consistency and `WalletFeatureVector` non-negative count, weighted-count, pair-count, strength-row, schema, and missing-feature invariants.

- [ ] **Step 2: Write structural input RED tests**

Require:

1. empty wallet set is valid only with empty profiles and empty D4 assessment;
2. reconstruction as-of mismatch raises;
3. reconstruction candidate-mint mismatch raises;
4. duplicate reconstruction wallet raises;
5. profile as-of mismatch raises;
6. duplicate profile wallet raises;
7. profile wallet set must exactly match reconstruction wallet set;
8. mixed D3 profile-policy versions raise;
9. mixed non-`None` context versions raise;
10. D4 as-of mismatch raises;
11. D4 wallet-set mismatch raises;
12. D1 future observation raises;
13. D1 candidate-mint mismatch raises;
14. malformed tuple/domain inputs raise.

- [ ] **Step 3: Write wallet-strength RED tests**

Require:

1. all configured checks passing => STRONG;
2. low effective sample => NOT_STRONG;
3. low evidence confidence => NOT_STRONG;
4. median return below threshold => NOT_STRONG;
5. win rate below threshold => NOT_STRONG;
6. excessive known rug exposure => NOT_STRONG;
7. excessive known drawdown => NOT_STRONG;
8. configured rug threshold + missing rug evidence => UNKNOWN when no known failure exists;
9. configured drawdown threshold + missing drawdown => UNKNOWN when no known failure exists;
10. a known failed check outranks missing optional checks and remains NOT_STRONG;
11. optional thresholds set to `None` do not require those context metrics;
12. strength rows sort lexically and carry stable failed/missing check names.

- [ ] **Step 4: Write current-activity and quality-aggregate RED tests**

Use D2-valid candidate reconstructions and require:

1. episode opened exactly at the entry-window boundary counts as recent entry;
2. older entry does not count;
3. CLOSED episode exactly at exit-window boundary counts as recent exit;
4. a wallet may count in both recent entry and recent exit sets;
5. UNRESOLVED chronology does not fabricate an entry/exit;
6. strong-entry/strong-exit counts use the strength state;
7. confidence-weighted strong counts sum D3 evidence confidence and are bounded by raw strong counts;
8. entry quality uses only entrants with positive evidence confidence and known D3 return/win-rate metrics;
9. weighted median return uses deterministic `(value, wallet)` ordering;
10. weighted entry win rate is a weighted mean;
11. no usable entrant profile quality => both quality aggregates `None` and appear in `missing_features`.

- [ ] **Step 5: Write D4 independence/cluster RED tests**

For STRONG recent entrants require:

1. zero entrants => exact independent count `0`, all-pairs flag `None`;
2. one entrant => exact independent count `1`, flag `True`;
3. every pair explicitly INDEPENDENT => exact count equals strong entrants, flag `True`;
4. one LINKED pair => exact count `None`, flag `False`;
5. one CONFLICTING pair => exact count `None`, flag `False`;
6. only UNKNOWN ambiguity => exact count `None`, flag `None`;
7. linked/conflicting/unknown pair counts are exact;
8. coordination-cluster count includes D4 components with >=2 strong entrants;
9. a non-entrant bridge inside a D4 component still keeps strong entrants in one coordination component;
10. maximum independent-group upper bound counts D4 components containing >=1 strong entrant and is never mislabeled as proof.

- [ ] **Step 6: Write creator/deployer RED tests**

Require only D1 `CREATOR_ACTION` observations inside the inclusive configured local-time window to increment `creator_deployer_action_observation_count`. Other actions, older creator actions, and optional chain occurrence time do not affect the count.

- [ ] **Step 7: Write exact public API RED test**

Require the existing sealed feature API as exact prefix:

```text
ANCHOR_1M_MAX_AGE_MS
ANCHOR_1M_MIN_AGE_MS
ANCHOR_5M_MAX_AGE_MS
ANCHOR_5M_MIN_AGE_MS
ANCHOR_15M_MAX_AGE_MS
ANCHOR_15M_MIN_AGE_MS
FEATURE_SCHEMA_VERSION
FeatureInputs
FeatureVector
MarketFeaturePoint
build_feature_vector
```

followed by exactly:

```text
WALLET_FEATURE_SCHEMA_VERSION
WalletHistoricalStrengthState
WalletFeaturePolicy
WalletFeatureInputs
WalletStrengthAssessment
WalletFeatureVector
build_wallet_feature_vector
```

Pin `FEATURE_SCHEMA_VERSION == "b2-v1"`, `WALLET_FEATURE_SCHEMA_VERSION == "d5-wallet-v1"`, and exact reducer signature `build_wallet_feature_vector(inputs)`.

- [ ] **Step 8: Commit combined RED**

Commit only the three D5 tests plus a narrow predecessor public-API-prefix maintenance edit if an exact-size guard exists.

Expected CI: safety GREEN, Rust/workspace GREEN, Python RED only because D5 public symbols do not exist.

---

### Task 2: Immutable D5 wallet-feature models

**Files:**
- Create: `python/src/shreks_brain/features/wallet_models.py`
- Modify: `python/src/shreks_brain/features/__init__.py`
- Test: `python/tests/test_wallet_feature_models.py`
- Test: `python/tests/test_wallet_feature_public_api.py`

**Interfaces:**
- Produces `WALLET_FEATURE_SCHEMA_VERSION`, `WalletHistoricalStrengthState`, `WalletFeaturePolicy`, `WalletFeatureInputs`, `WalletStrengthAssessment`, and `WalletFeatureVector`.

- [ ] **Step 1: Implement schema constant, enum, and policy**

Implement exactly the spec fields and fail-closed validation. Reuse no production default thresholds.

- [ ] **Step 2: Implement `WalletFeatureInputs` validation**

Validate tuple/domain types, exact as-of/candidate identity, exact reconstruction/profile/D4 wallet-set equality, unique wallets, one D3 profile policy version, one non-`None` context version, and D1 future/candidate mismatch rejection.

- [ ] **Step 3: Implement `WalletStrengthAssessment`**

Validate stable check names, disjoint failed/missing checks, lexical tuples, state consistency (`STRONG` has neither, `NOT_STRONG` has failures, `UNKNOWN` has no failures and at least one missing check), bounded profile metrics, and immutable audit fields.

- [ ] **Step 4: Implement `WalletFeatureVector` invariants**

Validate identity/version fields, non-negative counts, raw/strong count bounds, confidence-weighted counts `<=` raw strong counts, strength row order/count reconciliation, pair-count feasibility among strong entrants, independence flag/count consistency, cluster upper-bound consistency, nullable quality fields, and fixed-order `missing_features`.

- [ ] **Step 5: Wire public exports without changing B2 symbols/order**

Append the seven D5 symbols after the sealed B2 prefix in `features.__all__`.

---

### Task 3: Pure D5 wallet-feature reducer

**Files:**
- Create: `python/src/shreks_brain/features/wallet_engine.py`
- Modify: `python/src/shreks_brain/features/__init__.py`
- Test: `python/tests/test_wallet_feature_engine.py`

**Interfaces:**
- Consumes: one validated `WalletFeatureInputs`.
- Produces: `build_wallet_feature_vector(inputs: WalletFeatureInputs) -> WalletFeatureVector`.

- [ ] **Step 1: Implement deterministic strength classification**

For each lexical profile wallet, evaluate the exact configured checks and apply `known failure -> NOT_STRONG`, else `missing required metric -> UNKNOWN`, else `STRONG`.

- [ ] **Step 2: Derive recent entry/exit wallet sets**

Use inclusive D2 episode chronology boundaries from the spec. Do not inspect providers or recompute D2 trades.

- [ ] **Step 3: Aggregate strong and weighted quality evidence**

Compute raw strength/activity counts, confidence-weighted strong entry/exit counts, weighted entrant median-return and weighted entrant win-rate helpers. Return `None` when usable weight is zero.

- [ ] **Step 4: Derive strong-entry D4 pair features**

Filter D4 pair rows to the strong entrant set, count states, apply exact tri-state independence rules, and derive coordination/upper-bound cluster counts from D4 components.

- [ ] **Step 5: Count creator/deployer observations**

Count supplied `WalletActionKind.CREATOR_ACTION` rows inside the inclusive creator activity window using local `observed_at_unix_ms` only.

- [ ] **Step 6: Build deterministic missing feature list and output**

Use the fixed missing order from the spec and return lexical strength assessments.

- [ ] **Step 7: Run focused GREEN**

```bash
python -m pytest \
  python/tests/test_wallet_feature_models.py \
  python/tests/test_wallet_feature_engine.py \
  python/tests/test_wallet_feature_public_api.py -q
```

Expected: GREEN.

- [ ] **Step 8: Run full GREEN**

```bash
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: all GREEN.

- [ ] **Step 9: Commit focused implementation**

Commit only:

```text
python/src/shreks_brain/features/__init__.py
python/src/shreks_brain/features/wallet_models.py
python/src/shreks_brain/features/wallet_engine.py
```

plus no other production files.

---

### Task 4: Documentation, audit, and immutable seal

**Files:**
- Modify: `README.md` additions-only D5 section
- Replace: `docs/superpowers/plans/2026-08-24-phase-d5-smart-wallet-features.md` with verification record

- [ ] **Step 1: Append README semantics**

Document parallel `d5-wallet-v1`, exact D2/D3/D4 point-in-time composition, confidence-weighted historical quality, tri-state strength/independence, creator observation semantics, and no B2/trading-policy changes.

- [ ] **Step 2: Replace plan with verification record**

Record base, RED/CI, GREEN/CI, test count, integrity properties, scope boundaries, and seal procedure. Do not back-write eventual final D5 SHA/run into tracked docs.

- [ ] **Step 3: Validate seal docs off-branch**

Require seal commit diff from GREEN to touch exactly README + verification record and README deletions `0`.

- [ ] **Step 4: Freeze branch on validated seal commit**

After moving the branch, perform no more tracked D5 writes.

- [ ] **Step 5: Audit exact D4 -> D5 diff**

Expected files exactly:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-d5-smart-wallet-features.md
docs/superpowers/specs/2026-08-24-phase-d5-smart-wallet-features-design.md
python/src/shreks_brain/features/__init__.py
python/src/shreks_brain/features/wallet_models.py
python/src/shreks_brain/features/wallet_engine.py
python/tests/test_wallet_feature_models.py
python/tests/test_wallet_feature_engine.py
python/tests/test_wallet_feature_public_api.py
```

plus only a test-only predecessor feature public-API compatibility edit if required by the sealed B2 test contract.

Require README additions-only and no wallet D1-D4 production, B2 market engine/model, setup/score/decision/risk, Rust/storage, signer, or live-execution file changes.

- [ ] **Step 6: Run fresh exact-head seal CI**

Require repository safety, Python, Rust tests, and workspace metadata all GREEN on the frozen exact head.

- [ ] **Step 7: Record final SHA/run in draft PR metadata only**

Leave PR draft/unmerged and stack D6 from the exact sealed D5 head.
