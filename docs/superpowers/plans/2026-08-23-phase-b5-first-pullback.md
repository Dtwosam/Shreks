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

- [x] **RED:** Prove exact setup/confirmation constants and exact reason-code order; strict timestamp chronology; positive finite prices; peak >= start and peak > trough; optional non-negative finite liquidity; trough buy fraction in `[0,1]`; sample count integer >=3; policy finiteness/range/order validation; frozen dataclasses; assessment derived-metric validation; and absence of execution/future-outcome fields.
- [x] **Verify RED:** Full PR CI failed in Python only because B5 model symbols did not exist.
- [x] **GREEN:** Added only the B5 model contract and reusable validation required by that contract. B3/B4b semantics preserved.
- [x] **Verify GREEN:** Full repository CI passed.
- [x] **Commit:** coherent model GREEN.

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

- [x] **RED:** Built explicit fixtures covering READY, missing context, safety veto, decision-time contradictions, sample count, trough-age boundaries, impulse strength, pullback depth, broken trough, anti-chase gates, missing evidence, all nine confirmation failures/unknowns, threshold equality, seller-absorption calculation, blocked-candidate research evidence, finding order, and repeatability.
- [x] **Verify RED:** Full PR CI failed only on missing `first_pullback` evaluator.
- [x] **GREEN:** Implemented exact staged evaluation with no wall clock/storage/provider dependency and no short-circuiting of computable research evidence.
- [x] **Verify GREEN:** Full repository CI passed, including unchanged B3/B4b tests.
- [x] **Commit:** coherent evaluator GREEN.

---

### Task 3: Public API, documentation, exact-head seal

**Files:**
- Create: `python/tests/test_first_pullback_public_api.py`
- Modify: `python/src/shreks_brain/setups/__init__.py`
- Modify: `README.md`
- Modify: this plan with verification evidence

- [x] **RED:** Public API test imports all stable B5 symbols from `shreks_brain.setups`, constructs a READY assessment, verifies B3/B4b entry points remain importable, and proves the assessment has no execution authority.
- [x] **Verify RED:** Full CI failed only because B5 package exports were absent.
- [x] **GREEN:** Exported B5 constants/types/evaluator without removing or renaming B3/B4b exports.
- [x] **Verify package GREEN:** Full repository CI passed.
- [x] **Document:** README explains explicit chronology, broken-trough invalidation, 9-confirmation contract, no production defaults, evidence-score semantics, and no execution.
- [x] **Verification record:** Fresh documentation-head CI passed and is recorded below.
- [x] **Final seal procedure:** Tracked documentation records predecessor verification only. The immutable final branch head and its fresh CI run are recorded in PR metadata after CI, preventing a self-referential commit loop.

## Verification Evidence

- Task 1 RED: `53dffdc85f6e4f6cd6dc1e15f2272f7d00a3ba1c` / CI `32665629841` — Python failed only on missing B5 model symbols; repository safety passed.
- Task 1 GREEN: `5a7abfb76168acab8cf86913a2a667a623c08b07` / CI `32665715647` — Rust, Python, workspace metadata, and repository safety all GREEN.
- Task 2 RED: `6dd4e32a1c22bd4ad57d8e7916d015ff5e2cb923` / CI `32665844442` — Rust and repository safety GREEN; Python failed only on missing `shreks_brain.setups.first_pullback`.
- Task 2 GREEN: `2b34ab3ae6720d4509c93a1f68896eec3a7574c0` / CI `32666274853` — full GREEN.
- Task 3 RED: `eb561f497b93d44b2ba23c78926c573a6b8f1b77` / CI `32666353695` — Python failed only because B5 package exports were absent; repository safety GREEN.
- Task 3 package GREEN: `69b13218d6f9252fe85c5d848151346f7fc8783d` / CI `32666385342` — full GREEN.
- README documentation commit: `f3b57fe9d4616b983e16bedc23b06107c1532423`.
- Documentation/verification head: `902386846ce74a42944e899cf417ae9825da3656` / CI `32666494775` — full GREEN.
- Verified predecessor head: `b910bb5359592c4fa5e406a176cd519237105d92` / CI `32666669620` — Rust, Python, workspace metadata, and repository safety all GREEN.
- The final immutable head/run are stored in draft PR #8 metadata after this plan is no longer modified.

## Self-Review

- Spec coverage: all B5 model, derivation, gate, confirmation, missing-data, and audit requirements map to Tasks 1–3.
- No placeholder/TODO implementation steps remain.
- Types/signatures are consistent across tasks.
- No B2/Rust/storage/execution change is planned.
- The design measures a pullback chronology rather than relabeling a current momentum snapshot.
- The setup cannot call a broken trough “recovery.”
