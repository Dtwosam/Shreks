# Phase B2 Deterministic Feature Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, dependency-light Python feature engine that converts point-in-time normalized market evidence plus a same-timestamp B1 safety assessment into a versioned, auditable `FeatureVector` without strategy scoring or look-ahead leakage.

**Architecture:** `features/models.py` owns immutable input/output types, schema constants, and timing/value validation. `features/engine.py` owns pure deterministic calculations. `features/__init__.py` exports the stable package contract. B2 depends only on the Python standard library and `shreks_brain.safety`; it performs no SQLite/provider/network work.

**Tech Stack:** Python 3.12+, standard library (`dataclasses`, `math`), existing `shreks_brain.safety`, pytest 8.x already present.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b2-feature-engine-design.md`

## Global Constraints

- Feature schema version is exactly `b2-v1`.
- Named 1m/5m/15m anchors must satisfy the exact versioned timing bands in the spec.
- Safety assessment timestamp must equal feature `as_of_unix_ms` exactly.
- Missing values remain `None`; numeric missing values are never zero-filled.
- Zero/invalid denominators produce `None`, never infinity or optimistic substitutes.
- B2 computes raw/derived features only; no setup eligibility, score weights, `TradeDecision`, position sizing, paper execution, or live execution.
- B2 has no SQLite/provider/network dependency and no future-outcome inputs.
- Full repository CI remains the final gate: Rust workspace tests, Python tests, workspace metadata validation, and repository secret-safety.

---

### Task 1: Immutable feature domain models and time-integrity validation

**Files:**
- Create: `python/src/shreks_brain/features/models.py`
- Create: `python/tests/test_feature_models.py`

**Interfaces:**
- Consumes: `SafetyAssessment` and `SafetyDecision` from `shreks_brain.safety`.
- Produces: `FEATURE_SCHEMA_VERSION`, anchor timing constants, `MarketFeaturePoint`, `FeatureInputs`, and `FeatureVector`.

- [ ] **Step 1: Write failing model tests**

Create table-driven tests covering exact schema/timing constants, frozen dataclasses, market-value/count validation, anchor timing bands, pair-creation ordering, local-extrema validation, exact safety timestamp equality, and absence of future-outcome fields.

Representative test shape:

```python
from dataclasses import FrozenInstanceError, fields

import pytest

from shreks_brain.safety import SafetyAssessment, SafetyDecision
from shreks_brain.features.models import (
    ANCHOR_1M_MAX_AGE_MS,
    ANCHOR_1M_MIN_AGE_MS,
    FEATURE_SCHEMA_VERSION,
    FeatureInputs,
    MarketFeaturePoint,
)


def test_schema_and_anchor_contract_is_stable():
    assert FEATURE_SCHEMA_VERSION == "b2-v1"
    assert ANCHOR_1M_MIN_AGE_MS == 60_000
    assert ANCHOR_1M_MAX_AGE_MS == 90_000


def test_future_outcome_fields_are_absent():
    names = {field.name for field in fields(FeatureInputs)}
    assert "future_return_pct" not in names
    assert "mfe_pct" not in names
    assert "mae_pct" not in names
```

Also prove:

- negative/NaN/inf market values fail;
- negative/non-int counts fail;
- current/future observations fail;
- 1m anchor ages of 59,999 ms and 90,001 ms fail while 60,000 and 90,000 pass;
- equivalent exact boundary tests for 5m and 15m;
- `pair_created_at_unix_ms > current.observed_at_unix_ms` fails;
- local high below local low fails;
- non-positive known extrema fail;
- safety `as_of_unix_ms` mismatch fails;
- dataclasses cannot be mutated.

- [ ] **Step 2: Run CI and verify RED**

Expected: Python fails importing `shreks_brain.features.models`; Rust and repository-safety remain unchanged.

- [ ] **Step 3: Implement minimal validated models**

Use `@dataclass(frozen=True, slots=True)` and focused private validators:

```python
def _require_non_negative_int(name: str, value: int | None) -> None: ...
def _require_non_negative_finite(name: str, value: float | None) -> None: ...
def _require_positive_finite(name: str, value: float | None) -> None: ...
def _validate_anchor(name: str, point: MarketFeaturePoint | None, *, as_of_unix_ms: int, min_age_ms: int, max_age_ms: int) -> None: ...
```

`FeatureVector` contains exactly the fields defined by the spec, including `source_age_ms` and deterministic `missing_features`.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: Task 1 model tests and all existing repository checks pass.

---

### Task 2: Deterministic feature calculations

**Files:**
- Create: `python/src/shreks_brain/features/engine.py`
- Create: `python/tests/test_feature_engine.py`

**Interfaces:**
- Consumes: `FeatureInputs`, `FeatureVector`, `FEATURE_SCHEMA_VERSION`, B1 safety reason/severity enums.
- Produces:

```python
def build_feature_vector(inputs: FeatureInputs) -> FeatureVector:
    ...
```

- [ ] **Step 1: Write failing engine tests**

Use exact numeric fixtures whose outputs can be calculated by hand.

A representative clean fixture should include:

```python
as_of = 1_000_000
current = MarketFeaturePoint(
    observed_at_unix_ms=990_000,
    price_usd=1.20,
    liquidity_usd=120_000.0,
    volume_m5_usd=24_000.0,
    volume_h1_usd=120_000.0,
    buys_m5=80,
    sells_m5=20,
    buys_h1=600,
    sells_h1=400,
)
```

Historical points must sit inside their timing bands and use simple prices/liquidity that produce exact expected returns.

Tests must assert exact behavior for:

- `source_age_ms`;
- token age;
- 5m liquidity percentage change;
- 1m/5m/15m returns;
- volume velocity `(m5 * 12) / h1`;
- m5/h1 transaction totals;
- buy fractions;
- buy/sell ratios;
- buy-pressure acceleration;
- momentum acceleration `return_1m - return_5m / 5`;
- distance from local high;
- range position;
- B1 safety policy/decision copy;
- soft finding count and four reason flags;
- rejected and incomplete safety still produce a vector;
- deterministic equality across repeated calls.

Add edge-case tests proving:

```python
assert vector.return_5m_pct is None          # baseline price is 0
assert vector.buy_sell_ratio_m5 is None      # sells_m5 is 0
assert vector.volume_velocity_ratio is None  # volume_h1_usd is 0
assert vector.range_position_pct is None     # local high == local low
```

Also assert that missing numeric features appear once in canonical `missing_features` order and no missing value is replaced by `0`.

- [ ] **Step 2: Run CI and verify RED**

Expected: Python fails importing `shreks_brain.features.engine` or `build_feature_vector`; Task 1 tests remain green.

- [ ] **Step 3: Implement pure feature engine**

Implement small helpers with no side effects:

```python
def _pct_change(current: float | None, baseline: float | None) -> float | None: ...
def _tx_count(buys: int | None, sells: int | None) -> int | None: ...
def _buy_fraction(buys: int | None, sells: int | None) -> float | None: ...
def _buy_sell_ratio(buys: int | None, sells: int | None) -> float | None: ...
```

Build all feature values first, then construct `missing_features` from one explicit canonical tuple of numeric feature names. Do not introspect arbitrary dataclass fields or depend on dictionary iteration order.

Safety flags are derived only from `SafetyReasonCode` membership in `inputs.safety.findings`.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: engine tests and all existing checks pass.

---

### Task 3: Stable public API, operator documentation, and final regression gate

**Files:**
- Create: `python/src/shreks_brain/features/__init__.py`
- Create: `python/tests/test_feature_public_api.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-b2-feature-engine.md`

**Interfaces:**
- Public package imports:

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

- [ ] **Step 1: Write failing public-API test**

Import every symbol only from `shreks_brain.features`, build one vector through that API, and assert:

```python
assert vector.schema_version == "b2-v1"
assert vector.safety_decision is SafetyDecision.PASS
assert "future_return_pct" not in FeatureInputs.__dataclass_fields__
```

- [ ] **Step 2: Run CI and verify RED**

Expected: package-level imports fail until `features/__init__.py` exists.

- [ ] **Step 3: Export public API and update README**

README must document:

- B2 is raw/derived point-in-time feature computation, not a score;
- missing data stays unknown;
- return horizons are enforced by versioned timing bands;
- B1 safety remains the hard gate and B2 cannot override it;
- rejected/incomplete candidates still get features for unbiased research;
- no trading behavior is enabled.

- [ ] **Step 4: Run final full CI**

Expected: Rust workspace tests, Python tests, workspace metadata validation, and repository secret-safety all pass.

- [ ] **Step 5: Record exact RED/GREEN commits and CI run IDs in this plan**

Only mark this task complete after a fresh CI run on the documentation-complete exact branch head.

---

## Self-review

- **Spec coverage:** all B2 model fields, anchor timing semantics, raw feature calculations, B1 safety integration, missing-data behavior, look-ahead protections, public API, and non-trading scope are mapped to Tasks 1–3.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** Task 2 consumes the exact types produced by Task 1; Task 3 exports those exact names.
- **Scope:** no storage adapter, setup detector, score, wallet intelligence, market regime, paper execution, or live execution is introduced.
