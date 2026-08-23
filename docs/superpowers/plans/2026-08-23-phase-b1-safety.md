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

**Interfaces:** Produces `SafetyDecision`, `SafetySeverity`, `SafetyReasonCode`, `SafetyFinding`, `SafetyInputs`, `SafetyPolicy`, and `SafetyAssessment`.

- [x] **Step 1: Write failing model tests** — exact enum values, frozen dataclasses, policy/input validation, percentage bounds, threshold consistency, and absence of future-outcome fields.
- [x] **Step 2: Run CI and verify RED** — Python failed on missing `shreks_brain.safety`; Rust and repository safety were unaffected.
- [x] **Step 3: Implement minimal validated immutable models** — `StrEnum`, frozen/slotted dataclasses, and focused validation helpers.
- [x] **Step 4: Run full CI and verify GREEN** — complete repository gate passed.

---

### Task 2: Deterministic hard, data-quality, and soft evaluation

**Files:**
- Create: `python/src/shreks_brain/safety/evaluator.py`
- Create: `python/tests/test_safety_evaluator.py`

**Interface:**

```python
def assess_safety(inputs: SafetyInputs, policy: SafetyPolicy) -> SafetyAssessment:
    ...
```

- [x] **Step 1: Write failing evaluator tests** — clean pass, every hard veto, required/optional unknowns, freshness, future/contradictory data, soft findings, threshold boundaries, ordering, and repeatability.
- [x] **Step 2: Run CI and verify RED** — Python failed only on missing evaluator module.
- [x] **Step 3: Implement the pure evaluator** — findings are built in hard → data-quality → soft passes, then decision precedence is applied as `REJECT > INCOMPLETE > PASS`.
- [x] **Step 4: Run full CI and verify GREEN** — complete repository gate passed.

Freshness semantics implemented:

```text
missing critical timestamp -> CRITICAL_DATA_STALE
future critical timestamp -> CRITICAL_DATA_CONTRADICTORY
age > configured maximum -> CRITICAL_DATA_STALE
explicit contradiction -> CRITICAL_DATA_CONTRADICTORY
```

A future timestamp produces contradiction rather than a duplicate stale finding.

---

### Task 3: Stable package API, documentation, and final regression gate

**Files:**
- Create: `python/src/shreks_brain/safety/__init__.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-b1-safety.md`
- Create: `python/tests/test_safety_public_api.py`

**Public API:**

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

- [x] **Step 1: Write failing public-API tests** — all public symbols import from the package root, a clean case evaluates through only that API, and future-outcome fields remain absent.
- [x] **Step 2: Verify RED** — package-level imports failed exactly as intended before `__init__.py` existed.
- [x] **Step 3: Export the stable API and update README** — operator notes document fail-closed semantics, policy configuration, point-in-time inputs, and the non-trading boundary.
- [x] **Step 4: Run final full CI** — Rust workspace tests, Python tests, workspace metadata validation, and repository secret-safety passed.
- [x] **Step 5: Record the final CI commit/run in this plan** — recorded below after fresh verification.

---

## Verification record

- **Task 1 RED:** commit `d62ba2da8b3a62702d2fda00a14a02ece278074d`, CI `32656608967`; Python failed on missing `shreks_brain.safety`.
- **Task 1 GREEN:** commit `0ac0dc3364fb1932160706ae3cce006170dac3af`, CI `32656677139`; Rust, Python, metadata validation, and repository safety all passed.
- **Task 2 RED:** commit `3a706fdd1a4b6e4785ec8b62d30d84117e879b18`, CI `32656768963`; Python failed on missing `shreks_brain.safety.evaluator`.
- **Task 2 GREEN:** commit `edf8d10de28eda5543d49b1fe421420e37d7dcf1`, CI `32656827013`; complete repository gate passed.
- **Task 3 RED:** commit `247c9614179daad9a63149e5abe95442fce0bb6a`, CI `32656898249`; package-level public imports failed exactly as intended.
- **Code/documentation GREEN:** commit `53895d63ef035b2ed562af18d84ca8fd541a5419`, CI `32656985541`; complete repository gate passed.
- A final exact-head CI run is required after this verification-record-only commit before the branch is declared complete.

## Self-review

- **Spec coverage:** all approved B1 domain types, validation, hard rules, critical-data rules, soft rules, deterministic precedence/order, audit fields, point-in-time boundary, and non-trading guarantee are implemented.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** evaluator and public API consume the exact model names produced by the model layer.
- **Scope:** no assembler, persistence, strategy score, paper execution, or live execution was introduced.
