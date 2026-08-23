# Phase B2 Deterministic Feature Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Python feature engine that converts point-in-time normalized market evidence plus a same-timestamp B1 safety assessment into a versioned, auditable `FeatureVector` without strategy scoring or look-ahead leakage.

**Architecture:** `features/models.py` owns immutable inputs/outputs, schema constants, and timing validation. `features/engine.py` owns pure calculations. `features/__init__.py` exposes the stable public API. B2 has no SQLite/provider/network dependency.

**Tech Stack:** Python 3.12+, standard library only, existing `shreks_brain.safety`, pytest 8.x.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b2-feature-engine-design.md`

## Global Constraints

- Feature schema is exactly `b2-v1`.
- 1m/5m/15m anchors obey the versioned timing bands in the spec.
- Safety timestamp equals feature `as_of_unix_ms` exactly.
- Missing values remain `None`; no zero filling.
- Zero/invalid denominators return `None`, never infinity.
- No setup score, trade decision, storage/provider coupling, paper execution, or live execution.
- Final gate is full Rust/Python/metadata/repository-safety CI.

---

### Task 1: Immutable feature domain models and time integrity

**Files:**
- `python/src/shreks_brain/features/models.py`
- `python/tests/test_feature_models.py`

- [x] **Step 1: Write failing model tests** — schema constants, frozen types, value/count validation, anchor bands, pair-creation ordering, extrema validation, exact safety timestamp equality, and look-ahead field absence.
- [x] **Step 2: Verify RED** — commit `6b599fbd7c26c82820419e6e35a538e11075418f`, CI `32658129422`; Python failed because `shreks_brain.features` did not exist.
- [x] **Step 3: Implement validated models** — commit `31748fb03aa2dd6fd39edb35b2597f94ecc4605d`.
- [x] **Step 4: Run full CI and verify GREEN** — initial run `32658188675` exposed a test-fixture clock bug at the 15m maximum boundary; only the fixture was corrected. Final Task 1 GREEN: commit `f00468e5af86b0fecf3b83192dff0d9f8b96a4ab`, CI `32658260537`.

---

### Task 2: Deterministic feature calculations

**Files:**
- `python/src/shreks_brain/features/engine.py`
- `python/tests/test_feature_engine.py`

**Public function:**

```python
def build_feature_vector(inputs: FeatureInputs) -> FeatureVector:
    ...
```

- [x] **Step 1: Write failing engine tests** — exact hand-checkable calculations for source/token age, liquidity change, returns, volume velocity, transaction totals, buy fractions/ratios, flow acceleration, momentum acceleration, local-range structure, safety flags, missing-data ordering, and repeatability.
- [x] **Step 2: Verify RED** — commit `e3e2d75bb12cd8db355453ba332b8b63c5279fc6`, CI `32658351686`; Python failed because `features.engine` did not exist.
- [x] **Step 3: Implement pure feature engine** — commit `9ad137dd9551a34736757c9f9d59c18a1bc0a87b`.
- [x] **Step 4: Run full CI and verify GREEN** — CI `32658410797`; Rust, Python, metadata validation, and repository safety all passed.

---

### Task 3: Stable public API, documentation, and final gate

**Files:**
- `python/src/shreks_brain/features/__init__.py`
- `python/tests/test_feature_public_api.py`
- `README.md`
- this plan

**Public API:**

```python
from shreks_brain.features import (
    ANCHOR_1M_MAX_AGE_MS,
    ANCHOR_1M_MIN_AGE_MS,
    ANCHOR_5M_MAX_AGE_MS,
    ANCHOR_5M_MIN_AGE_MS,
    ANCHOR_15M_MAX_AGE_MS,
    ANCHOR_15M_MIN_AGE_MS,
    FEATURE_SCHEMA_VERSION,
    FeatureInputs,
    FeatureVector,
    MarketFeaturePoint,
    build_feature_vector,
)
```

- [x] **Step 1: Write failing public-API tests** — all public imports use only `shreks_brain.features`; vector construction and look-ahead boundary are rechecked.
- [x] **Step 2: Verify RED** — commit `1fb1b8aba7010af694500ba0b763b379d8343a3e`, CI `32658480317`; package-level imports failed exactly as intended.
- [x] **Step 3: Export stable API and update README** — API commit `a70482e3a54427b13e9c417ccbd8dfe666ecaf5f`; documentation-complete head `ebb8ecf0feb85b0d6ff530483340851f9f1e4782`.
- [x] **Step 4: Run final full CI** — CI `32658547307`; full Rust/Python/metadata/repository-safety gate passed on `ebb8ecf0feb85b0d6ff530483340851f9f1e4782`.
- [x] **Step 5: Record exact RED/GREEN commits and run IDs** — recorded in this plan. One final exact-head CI run is required after this verification-record-only commit before B2 is declared complete.

---

## Verification Summary

- Task 1 RED: `6b599fb…` / CI `32658129422`
- Task 1 GREEN: `f00468e…` / CI `32658260537`
- Task 2 RED: `e3e2d75…` / CI `32658351686`
- Task 2 GREEN: `9ad137d…` / CI `32658410797`
- Task 3 RED: `1fb1b8a…` / CI `32658480317`
- Code/docs GREEN: `ebb8ecf…` / CI `32658547307`

## Self-review

- **Spec coverage:** model fields, anchor timing, all deterministic calculations, safety projection, missing-data semantics, look-ahead protections, public API, and non-trading scope are covered.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** engine/public API consume the exact model names defined in Task 1.
- **Scope:** no storage adapter, setup detector, score, wallet intelligence, regime model, paper execution, or live execution was introduced.
