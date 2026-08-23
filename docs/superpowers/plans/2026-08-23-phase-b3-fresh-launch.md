# Phase B3 Fresh Launch Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first explicit Shreks setup evaluator, Fresh Launch Continuation, as a pure deterministic layer over B2 `FeatureVector` data with configurable hard gates, nine auditable continuation confirmations, and `BLOCKED / WATCH / READY` output.

**Architecture:** `setups/models.py` owns stable setup enums, reason codes, findings, the validated `FreshLaunchPolicy`, and result type. `setups/fresh_launch.py` performs ordered hard-gate/watch/confirmation evaluation. `setups/__init__.py` exposes the stable public API. No storage/provider/execution dependency is introduced.

**Tech Stack:** Python 3.12+, standard library only, existing B1/B2 public APIs, pytest 8.x.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b3-fresh-launch-design.md`

## Global Constraints

- `READY` is not `ENTER` and cannot execute a trade.
- B1 safety must be `PASS`; safety cannot be overridden by setup evidence.
- All numerical setup thresholds live in explicit `FreshLaunchPolicy`; evaluator code contains no trading-number defaults.
- The setup uses exactly nine confirmations and confirmation score is only checklist completeness.
- Missing required evidence never passes a condition.
- Excessive 5m extension is a hard anti-chase blocker.
- B3 accepts only B2 point-in-time features and has no future-outcome input.
- Full repository CI is the final gate.

---

### Task 1: Setup domain models and policy validation

**Files:**
- Create: `python/src/shreks_brain/setups/models.py`
- Create: `python/tests/test_setup_models.py`

**Produces:** `SetupState`, `FreshLaunchReasonCode`, `SetupFinding`, `FreshLaunchPolicy`, `FreshLaunchAssessment`, and constants `FRESH_LAUNCH_SETUP_NAME = "fresh_launch_continuation"`, `FRESH_LAUNCH_CONFIRMATIONS_REQUIRED = 9`.

- [ ] **Step 1: Write failing tests**

Test exact enum/reason strings, constants, frozen dataclasses, policy validation, and absence of future/trading fields. Validation tests must cover empty version; NaN/inf; negative ages/source age/liquidity/exit impact/max return/tx count/volume velocity; `max_age_seconds <= min_age_seconds`; buy fraction outside `[0,1]`; range position outside `[0,100]`; positive `min_distance_from_local_high_pct`; and `max_return_5m_pct < min_return_5m_pct`.

Representative assertions:

```python
assert SetupState.BLOCKED.value == "BLOCKED"
assert FreshLaunchReasonCode.MOVE_TOO_EXTENDED.value == "MOVE_TOO_EXTENDED"
assert FRESH_LAUNCH_CONFIRMATIONS_REQUIRED == 9
```

- [ ] **Step 2: Verify RED in CI**

Expected: Python fails because `shreks_brain.setups` does not exist.

- [ ] **Step 3: Implement immutable models and validation**

Use `StrEnum`, frozen/slotted dataclasses, and small finite/int/range helpers. Do not provide a production default policy.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: model tests plus all existing checks pass.

---

### Task 2: Fresh Launch Continuation evaluator

**Files:**
- Create: `python/src/shreks_brain/setups/fresh_launch.py`
- Create: `python/tests/test_fresh_launch_setup.py`

**Produces:**

```python
def assess_fresh_launch(
    features: FeatureVector,
    policy: FreshLaunchPolicy,
) -> FreshLaunchAssessment:
    ...
```

- [ ] **Step 1: Write failing evaluator tests**

Use one explicit policy fixture and one hand-built B2 vector that passes all gates/confirmations.

Tests must prove:

- all confirmations pass -> `READY`, 9/9, score `100.0`, final `ALL_CONFIRMATIONS_PASSED` marker;
- each hard blocker independently yields `BLOCKED`: safety, expired age, stale source, low liquidity, high exit impact, excessive 5m return;
- safety `REJECT` and `INCOMPLETE` remain blocked even with 9/9 confirmations;
- unknown/too-young age yields `WATCH`;
- missing liquidity or exit impact yields `WATCH`;
- each of the nine confirmation conditions independently failing yields `WATCH`, 8/9, and the exact reason code;
- each missing confirmation produces its exact `_UNKNOWN` reason and does not pass;
- equality at every threshold passes;
- hard-blocked candidates still calculate confirmation count/score for research;
- multiple findings are in fixed spec order;
- repeated calls return equal assessments.

- [ ] **Step 2: Verify RED in CI**

Expected: Python fails because `setups.fresh_launch` / `assess_fresh_launch` is absent; Task 1 remains green.

- [ ] **Step 3: Implement ordered evaluator**

Perform evaluation in four visible stages:

1. hard gates;
2. age/executability watch evidence;
3. nine confirmation checks;
4. state resolution and optional ready marker.

Use one helper per generic comparison shape, but keep the reason-code order explicit. Score is always:

```python
confirmations_passed / FRESH_LAUNCH_CONFIRMATIONS_REQUIRED * 100.0
```

Do not short-circuit after a hard blocker; confirmations must still be evaluated for research.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: evaluator tests and complete repository gate pass.

---

### Task 3: Stable public API, README, and final verification record

**Files:**
- Create: `python/src/shreks_brain/setups/__init__.py`
- Create: `python/tests/test_setup_public_api.py`
- Modify: `README.md`
- Modify: this plan

**Public API:**

```python
from shreks_brain.setups import (
    FRESH_LAUNCH_CONFIRMATIONS_REQUIRED,
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchAssessment,
    FreshLaunchPolicy,
    FreshLaunchReasonCode,
    SetupFinding,
    SetupState,
    assess_fresh_launch,
)
```

- [ ] **Step 1: Write failing public-API tests**

Import only from `shreks_brain.setups`, construct one explicit policy/vector, and prove a ready assessment. Recheck that `READY` is a setup state only and no trade-intent/execution field exists in `FreshLaunchAssessment`.

- [ ] **Step 2: Verify RED**

Expected: package-level imports fail before `__init__.py` exists.

- [ ] **Step 3: Export API and document operator semantics**

README must state:

- Fresh Launch Continuation avoids first-second blind sniping;
- setup policy thresholds are hypotheses, not profitability claims;
- `BLOCKED / WATCH / READY` meaning;
- safety `PASS` is mandatory;
- 5m chase ceiling exists;
- score is confirmation completeness, not expected return;
- no production default thresholds exist until calibration;
- no paper/live trade execution is enabled.

- [ ] **Step 4: Run final full CI**

Expected: Rust, Python, metadata, repository safety all pass.

- [ ] **Step 5: Record exact RED/GREEN commits and CI run IDs**

Only close B3 after a fresh exact-head verification following the documentation-only record commit.

---

## Self-review

- **Spec coverage:** all setup states, reason codes, policy validations, hard gates, missing-evidence semantics, nine confirmations, anti-chase rule, safety precedence, research scoring, public API, and non-trading boundary are mapped to Tasks 1–3.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** evaluator/public API consume exact Task 1 type names.
- **Scope:** no storage, setup calibration, final trade score, position sizing, paper execution, or live execution is introduced.
