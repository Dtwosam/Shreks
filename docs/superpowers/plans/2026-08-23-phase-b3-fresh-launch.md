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

- [x] **Step 1: Write failing tests**
- [x] **Step 2: Verify RED in CI** — `00384f2995d1bb907dcd75f1e3bd1376e7790eb3`, CI `32658868362`.
- [x] **Step 3: Implement immutable models and validation**
- [x] **Step 4: Run full CI and verify GREEN** — `fd870d72c1e6ce277c12e2eb2e48202e9c7358b4`, CI `32658923308`.

---

### Task 2: Fresh Launch Continuation evaluator

**Files:**
- Create: `python/src/shreks_brain/setups/fresh_launch.py`
- Create: `python/tests/test_fresh_launch_setup.py`

**Produces:** `assess_fresh_launch(features: FeatureVector, policy: FreshLaunchPolicy) -> FreshLaunchAssessment`.

- [x] **Step 1: Write failing evaluator tests**
- [x] **Step 2: Verify RED in CI** — `bd95bb412fdb0b2ff6652fbdd8825822be3f9782`, CI `32659018401`.
- [x] **Step 3: Implement ordered evaluator**
- [x] **Step 4: Run full CI and verify GREEN** — `ad0230f1a7d5047afffdce5203cd3fbcb2b44e5d`, CI `32659077747`.

---

### Task 3: Stable public API, README, and final verification record

**Files:**
- Create: `python/src/shreks_brain/setups/__init__.py`
- Create: `python/tests/test_setup_public_api.py`
- Modify: `README.md`
- Modify: this plan

**Public API:** `FRESH_LAUNCH_CONFIRMATIONS_REQUIRED`, `FRESH_LAUNCH_SETUP_NAME`, `FreshLaunchAssessment`, `FreshLaunchPolicy`, `FreshLaunchReasonCode`, `SetupFinding`, `SetupState`, and `assess_fresh_launch`.

- [x] **Step 1: Write failing public-API tests**
- [x] **Step 2: Verify RED** — `9fb9cdc83ba74e80c79cde403e3e931035d3395a`, CI `32659150856`.
- [x] **Step 3: Export API and document operator semantics** — exports `142d2b56c9847d5679b74c9fcb948147d25085ba`; README `78a2e5188e096e1fc25d80cede20de2ef4eac186`.
- [x] **Step 4: Run final full CI** — code/docs head `78a2e5188e096e1fc25d80cede20de2ef4eac186`, CI `32659708880`.
- [x] **Step 5: Record exact RED/GREEN commits and CI run IDs** — verification record commit `085cd579cfe0d1ec3031d68dfe17a116c927eb52`.

---

## Self-review

- **Spec coverage:** all setup states, reason codes, policy validations, hard gates, missing-evidence semantics, nine confirmations, anti-chase rule, safety precedence, research scoring, public API, and non-trading boundary are implemented and tested.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** evaluator/public API consume exact Task 1 type names.
- **Scope:** no storage, setup calibration, final trade score, position sizing, paper execution, or live execution was introduced.

## Verification record

TDD sequence:

- Task 1 RED — `00384f2995d1bb907dcd75f1e3bd1376e7790eb3`, CI `32658868362`
- Task 1 GREEN — `fd870d72c1e6ce277c12e2eb2e48202e9c7358b4`, CI `32658923308`
- Task 2 RED — `bd95bb412fdb0b2ff6652fbdd8825822be3f9782`, CI `32659018401`
- Task 2 GREEN — `ad0230f1a7d5047afffdce5203cd3fbcb2b44e5d`, CI `32659077747`
- Task 3 RED — `9fb9cdc83ba74e80c79cde403e3e931035d3395a`, CI `32659150856`
- Task 3 code/docs GREEN — `78a2e5188e096e1fc25d80cede20de2ef4eac186`, CI `32659708880`
- Exact final head GREEN — `085cd579cfe0d1ec3031d68dfe17a116c927eb52`, CI `32659792356`

B3 is sealed on the exact final head. The branch remains isolated in its draft PR and is not merged automatically.
