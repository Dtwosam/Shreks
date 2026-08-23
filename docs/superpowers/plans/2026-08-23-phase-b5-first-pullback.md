# Phase B5 First Pullback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic First Pullback setup evaluator that requires explicit point-in-time impulse/peak/trough structure and current evidence of controlled recovery, seller absorption, and renewed demand.

**Architecture:** Keep B2 exactly `b2-v1`. Extend the existing setup model module with immutable First Pullback context/policy/finding/assessment types, then add a pure `first_pullback.py` evaluator that derives structure metrics itself from raw context prices/timestamps plus the current `FeatureVector`. Stable exports remain in `shreks_brain.setups`; no Rust, storage, provider, paper, or live execution code changes are allowed.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, pytest, existing `FeatureVector`, existing shared `SetupState`, GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b5-first-pullback-design.md`

## Global Constraints

- Base is verified B4b head `58c4cb660c10fd73b97fc2fa2ab892c5e9b0ab9f`.
- B2 remains exactly `b2-v1`.
- Context chronology is strict: impulse start < peak < trough.
- The evaluator may use no structural evidence later than the current B2 market source observation.
- Missing values remain unknown; they are never zero-filled.
- A current price below the recorded trough invalidates the context.
- B1 safety PASS is mandatory.
- B5-v1 uses exactly 9 equal-weight confirmations.
- No production policy defaults.
- Confirmation score is evidence completeness, never probability/expected return/size.
- No SQLite/provider reads from setup code.
- No `TradeIntent`, position sizing, paper fills, wallet/signing, swap submission, or live-money path.
- B3 and B4b public behavior must remain unchanged.

---

### Task 1: First Pullback immutable model contract

**Files:**
- Create: `python/tests/test_first_pullback_models.py`
- Modify: `python/src/shreks_brain/setups/models.py`

**Produces:**

```python
FIRST_PULLBACK_SETUP_NAME = "first_pullback"
FIRST_PULLBACK_CONFIRMATIONS_REQUIRED = 9

class FirstPullbackReasonCode(StrEnum): ...

@dataclass(frozen=True, slots=True)
class PullbackContext:
    impulse_started_at_unix_ms: int
    peak_at_unix_ms: int
    trough_at_unix_ms: int
    impulse_start_price_usd: float
    peak_price_usd: float
    trough_price_usd: float
    peak_liquidity_usd: float | None
    trough_liquidity_usd: float | None
    trough_buy_fraction_m5: float | None
    sample_count: int

@dataclass(frozen=True, slots=True)
class FirstPullbackPolicy: ...

@dataclass(frozen=True, slots=True)
class FirstPullbackFinding: ...

@dataclass(frozen=True, slots=True)
class FirstPullbackAssessment: ...
```

- [ ] **RED:** Prove exact setup/confirmation constants and exact reason-code order; strict timestamp chronology; positive finite prices; peak >= start and peak > trough; optional non-negative finite liquidity; trough buy fraction in `[0,1]`; sample count integer >=3; policy finiteness/range/order validation; frozen dataclasses; assessment derived-metric validation; and absence of execution/future-outcome fields.
- [ ] **Verify RED:** Full PR CI must fail in Python only because B5 model symbols do not exist.
- [ ] **GREEN:** Add only the B5 model contract and small reusable validation helpers if required. Preserve B3/B4b semantics.
- [ ] **Verify GREEN:** Full repository CI.
- [ ] **Commit:** coherent model GREEN.

---

### Task 2: Pure First Pullback evaluator

**Files:**
- Create: `python/tests/test_first_pullback_setup.py`
- Create: `python/src/shreks_brain/setups/first_pullback.py`

**Produces:**

```python
def assess_first_pullback(
    features: FeatureVector,
    pullback: PullbackContext | None,
    policy: FirstPullbackPolicy,
) -> FirstPullbackAssessment:
    ...
```

- [ ] **RED:** Build explicit fixtures and prove:
  - canonical structure + 9 confirmations => READY / 100;
  - no context => WATCH with structural metrics `None`;
  - safety REJECT/INCOMPLETE => BLOCKED;
  - future trough => BLOCKED;
  - trough later than current market source => BLOCKED and no future-derived recovery metrics;
  - insufficient sample count => WATCH;
  - min/max trough-age equality passes; too recent => WATCH; expired => BLOCKED;
  - weak impulse => BLOCKED;
  - shallow pullback => WATCH;
  - max pullback-depth equality passes; deeper => BLOCKED;
  - current price below trough => BLOCKED;
  - excessive current-vs-peak breakout => BLOCKED;
  - stale source, low liquidity, excessive exit impact, excessive 1m move => BLOCKED;
  - missing current price/liquidity/exit impact => WATCH;
  - missing peak/trough liquidity or zero peak liquidity => retention unknown, never infinity;
  - missing trough buy fraction => absorption unknown;
  - each of the 9 confirmations independently below threshold => WATCH, 8/9;
  - each missing confirmation => corresponding UNKNOWN reason;
  - equality at every confirmation threshold passes;
  - seller-absorption improvement is current buy fraction minus trough buy fraction;
  - blocked candidates retain computable confirmation counts;
  - deterministic multi-finding order and repeatability.
- [ ] **Verify RED:** Full PR CI must fail only on missing `first_pullback` evaluator.
- [ ] **GREEN:** Implement exact staged evaluation from the spec with no wall clock/storage/provider dependency and no short-circuiting of computable research evidence.
- [ ] **Verify GREEN:** Full repository CI, including unchanged B3/B4b tests.
- [ ] **Commit:** coherent evaluator GREEN.

---

### Task 3: Public API, documentation, exact-head seal

**Files:**
- Create: `python/tests/test_first_pullback_public_api.py`
- Modify: `python/src/shreks_brain/setups/__init__.py`
- Modify: `README.md`
- Modify: this plan with verification evidence

- [ ] **RED:** Public API test imports all stable B5 symbols from `shreks_brain.setups`, constructs a READY assessment, verifies B3/B4b entry points remain importable, and proves the assessment has no execution authority.
- [ ] **Verify RED:** Full CI fails only because B5 package exports are absent.
- [ ] **GREEN:** Export B5 constants/types/evaluator without removing or renaming B3/B4b exports.
- [ ] **Verify package GREEN:** Full repository CI.
- [ ] **Document:** README explains explicit chronology, broken-trough invalidation, 9-confirmation contract, no production defaults, evidence-score semantics, and no execution.
- [ ] **Verification record:** Record task RED/GREEN evidence and run a fresh full CI on a documentation head.
- [ ] **Final seal:** Make metadata-only completion commit, run fresh exact-head CI, update stacked draft PR against B4b with immutable final head/run, and keep it unmerged.

## Self-Review

- Spec coverage: all B5 model, derivation, gate, confirmation, missing-data, and audit requirements map to Tasks 1–3.
- No placeholder/TODO implementation steps remain.
- Types/signatures are consistent across tasks.
- No B2/Rust/storage/execution change is planned.
- The design measures a pullback chronology rather than relabeling a current momentum snapshot.
- The setup cannot call a broken trough “recovery.”
