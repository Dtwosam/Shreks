# Phase B4b Graduation/Breakout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, point-in-time Graduation/Breakout setup evaluator that consumes unchanged B2 features plus verified B4a graduation context, with no execution authority or production trading defaults.

**Architecture:** Keep `FeatureVector` at `b2-v1`. Add setup-specific immutable lifecycle/context, policy, finding, and assessment types to the existing setup models module, then add a pure `graduation_breakout.py` evaluator beside unchanged Fresh Launch logic. Stable exports remain under `shreks_brain.setups`; no Rust/storage/provider or execution changes are allowed in this phase.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, pytest, existing `shreks_brain.features` and `shreks_brain.safety` types, repository GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b4b-graduation-breakout-design.md`

## Global Constraints

- Base is verified B4a head `b50f80d82ca25aac2d1da99269c8f9ca54175525`.
- B2 schema remains exactly `b2-v1`; do not modify `python/src/shreks_brain/features/`.
- `detected_at_unix_ms` is the sole graduation decision clock; `occurred_at_unix_ms` is audit metadata only.
- Only `pump_graduation` with exact `pump_fun_bonding_curve -> pump_swap` transition is eligible lifecycle evidence.
- Setup state is shared `SetupState.BLOCKED / WATCH / READY`.
- B4b-v1 uses exactly 8 equal-weight confirmations.
- Missing evidence never becomes zero and never passes a condition.
- B1 safety `PASS` is mandatory; `REJECT` and `INCOMPLETE` cannot be overridden.
- No production default thresholds.
- No SQLite/provider reads from setup code.
- No `TradeDecision`, `TradeIntent`, sizing, paper fills, wallets, signers, Jupiter execution, or live-money path.
- B3 public behavior and imports must remain unchanged.

---

### Task 1: Immutable Graduation/Breakout model contract

**Files:**
- Create: `python/tests/test_graduation_breakout_models.py`
- Modify: `python/src/shreks_brain/setups/models.py`

**Interfaces:**
- Consumes: existing shared `SetupState` and validation helpers in `setups/models.py`.
- Produces:
  - `GRADUATION_BREAKOUT_SETUP_NAME = "graduation_breakout"`
  - `GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED = 8`
  - `GraduationBreakoutReasonCode`
  - `GraduationContext`
  - `GraduationBreakoutFinding`
  - `GraduationBreakoutPolicy`
  - `GraduationBreakoutAssessment`

- [x] **Step 1: Write the failing model tests**

The tests pin the canonical setup name and confirmation count, reason-code order, immutable lifecycle context, full-width Solana slot support, policy validation, assessment validation, and the absence of execution/future-outcome fields.

- [x] **Step 2: Verify RED**

Authoritative PR CI fails in Python only because B4b model symbols do not yet exist; Rust and repository safety remain green.

- [x] **Step 3: Implement minimal immutable models**

Models are added alongside the existing B3 types without changing B3 semantics. Shared numeric validators are reused and a non-empty-string validator is added for lifecycle identity fields.

- [x] **Step 4: Verify GREEN**

Full repository CI passes.

- [x] **Step 5: Commit**

The model contract is committed as a coherent GREEN change.

---

### Task 2: Pure Graduation/Breakout evaluator

**Files:**
- Create: `python/tests/test_graduation_breakout_setup.py`
- Create: `python/src/shreks_brain/setups/graduation_breakout.py`

**Interfaces:**
- Consumes: `FeatureVector`, `SafetyDecision`, Task 1 model types.
- Produces:

```python
def assess_graduation_breakout(
    features: FeatureVector,
    graduation: GraduationContext | None,
    policy: GraduationBreakoutPolicy,
) -> GraduationBreakoutAssessment:
    ...
```

- [x] **Step 1: Write failing evaluator tests**

The evaluator suite proves lifecycle identity, safety precedence, decision-safe graduation timing, post-graduation age boundaries, freshness/executability/anti-chase gates, all eight confirmation boundaries, missing-data behavior, deterministic finding order, blocked-candidate research scoring, repeatability, and explicit exclusion of cross-regime 5-minute momentum from positive evidence.

- [x] **Step 2: Verify RED**

Full CI fails in Python only because the `graduation_breakout` evaluator module does not yet exist.

- [x] **Step 3: Implement minimal evaluator**

Implementation order is exact:

```text
hard lifecycle/safety gates
post-graduation timing
freshness/executability/anti-chase hard gates
missing executability evidence
8 confirmations
state resolution
READY marker
```

The evaluator has no wall-clock, storage, provider, wallet, quote, or execution dependency and does not short-circuit confirmation research for blocked candidates.

- [x] **Step 4: Verify GREEN**

Full repository CI passes with all existing B3 tests unchanged.

- [x] **Step 5: Commit**

The evaluator is committed as a coherent GREEN change.

---

### Task 3: Stable package API, documentation, exact-head seal

**Files:**
- Create: `python/tests/test_graduation_breakout_public_api.py`
- Modify: `python/src/shreks_brain/setups/__init__.py`
- Modify: `README.md`
- Modify: this plan file to record verification evidence

**Interfaces:**
- Produces stable imports from `shreks_brain.setups` for all B4b constants/types and `assess_graduation_breakout`.

- [x] **Step 1: Write failing public API tests**

The public API test constructs a READY Graduation/Breakout assessment entirely from package-level imports, preserves the existing Fresh Launch entry point, and proves the result exposes no execution authority.

- [x] **Step 2: Verify RED**

Full CI fails in Python only because B4b symbols are not exported from the package root.

- [x] **Step 3: Export stable API**

All B4b constants, types, and evaluator are exported without removing or renaming any B3 symbol.

- [x] **Step 4: Verify package GREEN**

Full repository CI passes.

- [x] **Step 5: Document B4b**

README documents the verified-lifecycle requirement, local detection-time decision clock, unchanged B2 schema, eight-confirmation evidence score, no production defaults, cross-regime momentum exclusion, and no-execution guarantee.

- [x] **Step 6: Run documentation-head full CI**

Documentation/verification candidate head `a953656c46fc7f396aa6b267686f5fceb77bc6ce` passed full CI `32665204666`: Rust, Python, workspace metadata, and repository safety are green.

- [x] **Step 7: Keep stacked draft PR sealed and unmerged**

PR #7 remains stacked against `feat/phase-b4a-graduation-lifecycle`, draft, and intentionally unmerged. Its final body is updated after the metadata-only seal CI so it can record the true immutable final branch head without creating another branch commit.

## Verification Record

- Task 1 RED test introduced: `356f70a00ac9f51278b2e9acdb438796397e1a6f`.
- Task 1 authoritative RED CI head: `c9b597dd4b18c1780231a20aa7ac5971c6735cb4`; CI `32664732934` failed in Python on missing B4b model exports while repository safety remained green.
- Task 1 GREEN: `79641dcda9264fa534aaa61413ea9fe52a0ada73`; CI `32664786888` passed Rust, Python, workspace metadata, and repository safety.
- Task 2 RED: `2ce69efd0004e972ce1880cb73e82838633244dd`; CI `32664888831` failed in Python only because `shreks_brain.setups.graduation_breakout` did not yet exist.
- Task 2 GREEN: `6b94a0a2f9177879fb2770134ddf93944e471eab`; CI `32664936611` passed Rust, Python, workspace metadata, and repository safety.
- Task 3 RED: `e45230bfe74d82caeee51a5b53d0457c85c57b48`; CI `32665007991` failed in Python only because B4b package-level exports did not yet exist.
- Task 3 package GREEN: `d92e214cca3a7938ec4109ce18494875281e838e`; CI `32665067816` passed Rust, Python, workspace metadata, and repository safety.
- README documentation: `fc3789503adc2d768142ec5eec725a9ec0f6b43a`.
- Documentation/verification head: `a953656c46fc7f396aa6b267686f5fceb77bc6ce`; CI `32665204666` passed Rust, Python, workspace metadata, and repository safety.
- The final metadata-only branch head and its fresh CI run are recorded in draft PR #7 after this file is committed, avoiding a self-referential documentation commit loop.

## Self-Review

- Every spec requirement maps to Task 1, 2, or 3.
- No placeholder/TODO steps remain.
- Type names and signatures are consistent across all tasks.
- No Rust/B2/storage change was made.
- The implementation does not permit live trading or claim profitability.
- Blocked-candidate confirmation scoring is preserved for later filter-value research.
