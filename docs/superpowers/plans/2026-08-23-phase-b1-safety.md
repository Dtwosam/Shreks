# Phase B1 Deterministic Safety Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, dependency-free Python safety engine that turns point-in-time candidate facts plus a versioned policy into auditable `PASS`, `REJECT`, or `INCOMPLETE` assessments before any strategy scoring.

**Architecture:** `models.py` owns immutable domain types and validation; `evaluator.py` owns a pure ordered rule evaluator; `safety/__init__.py` exposes the stable public API. The package has no SQLite/provider/network dependency and accepts no future-outcome fields, preserving deterministic point-in-time behavior.

**Tech Stack:** Python 3.12+, standard library only (`dataclasses`, `enum`, `math`), pytest 8.x already present.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b1-safety-design.md`

## Global Constraints

- Safety runs before strategy scoring and has hard veto power.
- Decision precedence is exactly `REJECT > INCOMPLETE > PASS`.
- Thresholds are explicit `SafetyPolicy` configuration, never evaluator magic constants.
- Unknown required critical facts fail closed as `INCOMPLETE`; they are never guessed.
- Freshness is always critical; missing, stale, future-dated, or explicitly contradictory critical evidence cannot produce `PASS`.
- Soft findings remain auditable but never independently produce `REJECT` or `INCOMPLETE`.
- Percentage values use percentage points and must be finite within `[0, 100]`.
- B1 has no SQLite, provider, outcome-checkpoint, wallet, signer, execution, paper-trade, or live-trade dependency.

---

### Task 1: Immutable safety domain models and validation

**Files:**
- Create: `python/src/shreks_brain/safety/models.py`
- Create: `python/tests/test_safety_models.py`

**Interfaces:**
- Produces `SafetyDecision`, `SafetySeverity`, `SafetyReasonCode`, `SafetyFinding`, `SafetyInputs`, `SafetyPolicy`, and `SafetyAssessment`.
- Later tasks import these exact names from `shreks_brain.safety.models`.

- [ ] **Step 1: Write failing model tests**

Tests must assert exact enum values, frozen dataclass behavior, valid construction, rejection of empty policy versions, negative/non-finite numeric values, percentage values outside `[0, 100]`, inconsistent hard/soft thresholds, negative timestamps, and the absence of future-outcome fields such as `return_pct`, `mfe_pct`, and `mae_pct` from `SafetyInputs`.

Representative assertions:

```python
assert SafetyDecision.PASS.value == "PASS"
assert SafetySeverity.HARD.value == "HARD"
assert SafetyReasonCode.GLOBAL_RISK_HALT.value == "GLOBAL_RISK_HALT"
assert "return_pct" not in SafetyInputs.__dataclass_fields__
```

- [ ] **Step 2: Run CI and verify RED**

Expected: Python fails importing `shreks_brain.safety.models`; Rust and repository-safety jobs remain unchanged.

- [ ] **Step 3: Implement minimal validated immutable models**

Use `StrEnum` and `@dataclass(frozen=True, slots=True)`. Put validation in `__post_init__` with small private helpers:

```python
def _require_non_negative_finite(name: str, value: float | None) -> None: ...
def _require_percentage(name: str, value: float | None) -> None: ...
def _require_non_negative_int(name: str, value: int | None) -> None: ...
```

`SafetyAssessment` convenience properties return tuples filtered by severity while preserving canonical finding order.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: model tests pass and existing repository tests remain green.

---

### Task 2: Deterministic hard, data-quality, and soft evaluation

**Files:**
- Create: `python/src/shreks_brain/safety/evaluator.py`
- Create: `python/tests/test_safety_evaluator.py`

**Interfaces:**
- Consumes model types from Task 1.
- Produces:

```python
def assess_safety(inputs: SafetyInputs, policy: SafetyPolicy) -> SafetyAssessment:
    ...
```

- [ ] **Step 1: Write failing evaluator tests**

Use a reusable clean fixture and table-driven cases. Tests must prove:

- clean facts produce `PASS` with no findings;
- each hard reason independently produces `REJECT` and the exact code;
- hard rejection wins when missing/stale facts also exist;
- required unknown authority/liquidity/concentration/exit facts produce `INCOMPLETE`;
- disabled `require_*` flags suppress only their matching unknown-field finding, not global freshness checks;
- missing/stale critical timestamp produces `CRITICAL_DATA_STALE`;
- future timestamp or `critical_data_contradictory=True` produces `CRITICAL_DATA_CONTRADICTORY`;
- soft liquidity/concentration/creator/price-impact findings remain `PASS` when no blocker exists;
- hard/soft threshold boundaries use the exact strict/inclusive semantics from the spec;
- multiple findings appear in the fixed spec order;
- repeated calls return equal assessments.

- [ ] **Step 2: Run CI and verify RED**

Expected: Python fails importing `assess_safety` while model tests remain green.

- [ ] **Step 3: Implement the pure evaluator**

Build findings in exactly three ordered passes: hard, data-quality, soft. Use stable message templates and populate observed/threshold values where meaningful. Compute decision only after all findings are collected:

```python
if any(f.severity is SafetySeverity.HARD for f in findings):
    decision = SafetyDecision.REJECT
elif any(f.severity is SafetySeverity.DATA_QUALITY for f in findings):
    decision = SafetyDecision.INCOMPLETE
else:
    decision = SafetyDecision.PASS
```

Freshness rules:

```python
if observed_at is None:
    CRITICAL_DATA_STALE
elif observed_at > inputs.as_of_unix_ms:
    CRITICAL_DATA_CONTRADICTORY
elif inputs.as_of_unix_ms - observed_at > policy.max_critical_data_age_ms:
    CRITICAL_DATA_STALE
```

Do not create a stale finding for a future timestamp in addition to contradiction; use contradiction only for that case.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: evaluator tests and all existing checks pass.

---

### Task 3: Stable package API, documentation, and final regression gate

**Files:**
- Create: `python/src/shreks_brain/safety/__init__.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-b1-safety.md`
- Create: `python/tests/test_safety_public_api.py`

**Interfaces:**
- Public imports are available from `shreks_brain.safety`:

```python
from shreks_brain.safety import (
    SafetyAssessment,
    SafetyDecision,
    SafetyFinding,
    SafetyInputs,
    SafetyPolicy,
    SafetyReasonCode,
    SafetySeverity,
    assess_safety,
)
```

- [ ] **Step 1: Write failing public-API tests**

Tests import every public symbol from `shreks_brain.safety`, run one clean assessment through only that API, and assert deterministic structured output. Also inspect `SafetyInputs.__dataclass_fields__` to reconfirm there are no future-outcome fields in the public model.

- [ ] **Step 2: Verify RED**

Expected: package-level imports are absent until `__init__.py` is created.

- [ ] **Step 3: Export the stable API and update README**

README operator notes must state that B1 is pure point-in-time analysis, only `PASS` is eligible for later entry consideration, `REJECT` and `INCOMPLETE` fail closed, thresholds are policy configuration, and no trading/execution behavior is enabled.

- [ ] **Step 4: Run final full CI**

Expected: Rust workspace tests, Python tests, workspace metadata validation, and repository secret-safety all pass.

- [ ] **Step 5: Record the final CI commit/run in this plan**

Update this checklist only after fresh final-head verification.

---

## Self-review

- **Spec coverage:** all approved B1 domain types, validation, hard rules, critical-data rules, soft rules, deterministic precedence/order, audit fields, point-in-time boundary, and non-trading guarantee are mapped to Tasks 1–3.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** Task 2 and Task 3 consume the exact model names produced by Task 1.
- **Scope:** no assembler, persistence, strategy score, paper execution, or live execution is introduced.
