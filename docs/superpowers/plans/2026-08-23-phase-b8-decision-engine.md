# Phase B8 Deterministic Decision Engine Implementation Plan

**Goal:** Add a pure, versioned entry Decision Engine that converts one B7 score into `REJECT`, `WATCH`, or `ENTER` using hard safety/setup precedence plus explicit setup-specific and regime-specific score thresholds.

**Architecture:** Create `shreks_brain.decision` beside unchanged safety/features/setups/regime/scoring packages. Define the full six-action decision vocabulary now for forward compatibility, while `decide_entry()` emits only pre-entry actions because position/exit evidence does not exist yet. B8 creates no `TradeIntent`; the following risk phase owns sizing, portfolio constraints, slippage, idempotency, and intent construction.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b8-decision-engine-design.md`

**Base:** verified B7 head `26367ddf64aab9aae724afce4843219770b9feae`.

## Global constraints

- B7 score semantics remain unchanged.
- Full action vocabulary is exactly `REJECT / WATCH / ENTER / HOLD / REDUCE / EXIT`.
- B8-v1 `decide_entry()` may emit only `REJECT / WATCH / ENTER`.
- Safety veto and incomplete-critical-evidence behavior precede all score thresholds.
- Setup state precedes score thresholds.
- Setup-specific regime thresholds are explicit configuration; there is no fallback/default setup rule.
- DEAD never permits a new entry.
- A `None` HOT/NORMAL/WEAK threshold disables entry for that setup/regime.
- Threshold equality passes.
- No default production policy.
- No position sizing, portfolio accounting, slippage policy, idempotency key, `TradeIntent`, paper fill, signing, or live execution.

---

## Task 1 — Immutable decision domain and policy contract

**Files:**
- Create `python/src/shreks_brain/decision/models.py`
- Create `python/tests/test_decision_models.py`

### RED contract

Pin exact `DecisionAction` order:

```text
REJECT
WATCH
ENTER
HOLD
REDUCE
EXIT
```

Pin exact `DecisionReasonCode` order:

```text
SCORE_POLICY_MISMATCH
SAFETY_REJECTED
SAFETY_INCOMPLETE
SETUP_BLOCKED
SETUP_WATCH
SETUP_RULE_MISSING
SETUP_DISABLED
REGIME_DEAD
REGIME_DISABLED
TOTAL_SCORE_UNAVAILABLE
TOTAL_SCORE_BELOW_THRESHOLD
ENTRY_APPROVED
```

Pin frozen/validated models:

```python
DecisionFinding
SetupDecisionRule
DecisionPolicy
TradeDecision
```

`SetupDecisionRule` validation:
- non-empty setup name;
- boolean enabled;
- each optional threshold finite in `[0, 100]`;
- `None` threshold allowed;
- no threshold-order assumption across regimes.

`DecisionPolicy` validation:
- non-empty version and required score-policy version;
- non-empty tuple of rules;
- unique setup names;
- every item a `SetupDecisionRule`;
- frozen;
- no default construction.

`TradeDecision` exact fields:

```python
policy_version: str
mint: str
as_of_unix_ms: int
action: DecisionAction
score_policy_version: str
feature_schema_version: str
safety_decision: SafetyDecision
setup_name: str
setup_policy_version: str
setup_state: SetupState
market_regime: MarketRegime
total_score: float | None
required_score_threshold: float | None
findings: tuple[DecisionFinding, ...]
```

Prove no fields for side, requested size/notional, capital %, slippage, idempotency, execution mode, wallet, signer, order, fill, transaction, realized PnL, or position quantity.

### RED verification

Open stacked draft PR after the RED test commit. Expected Python failure: `shreks_brain.decision` missing; Rust/workspace/repository safety remain green.

### GREEN implementation

Implement `decision/models.py` only. Do not add evaluator logic.

Run full CI and require all jobs green before Task 2 production code.

---

## Task 2 — Pure pre-entry decision evaluator

**Files:**
- Create `python/src/shreks_brain/decision/engine.py`
- Create `python/tests/test_decision_engine.py`

### Canonical score fixture

Use a B7 `ScoreAssessment` with:

```text
policy_version = score-v1-test
feature_schema_version = b2-v1
as_of = 1_000_000
safety = PASS
setup = fresh_launch_continuation / READY
regime = NORMAL
total_score = 80.0
```

### Canonical policy fixture

Use three independent setup rules, e.g.:

```text
Fresh Launch: HOT 70 / NORMAL 75 / WEAK 85
Graduation:  HOT 65 / NORMAL 75 / WEAK 90
Pullback:    HOT 72 / NORMAL 78 / WEAK 88
```

All values are test fixtures only, not production defaults.

### RED behavior tests

Pin precedence independently:

1. score-policy mismatch -> `REJECT / SCORE_POLICY_MISMATCH`
2. safety REJECT -> `REJECT / SAFETY_REJECTED`
3. safety INCOMPLETE -> `WATCH / SAFETY_INCOMPLETE`
4. setup BLOCKED -> `REJECT / SETUP_BLOCKED`
5. setup WATCH -> `WATCH / SETUP_WATCH`
6. missing setup rule -> `REJECT / SETUP_RULE_MISSING`
7. disabled setup -> `REJECT / SETUP_DISABLED`
8. DEAD -> `REJECT / REGIME_DEAD`
9. HOT/NORMAL/WEAK selected threshold `None` -> `WATCH / REGIME_DISABLED`
10. `total_score=None` -> `WATCH / TOTAL_SCORE_UNAVAILABLE`
11. score below selected threshold -> `WATCH / TOTAL_SCORE_BELOW_THRESHOLD`
12. score exactly at threshold -> `ENTER / ENTRY_APPROVED`
13. score above threshold -> `ENTER / ENTRY_APPROVED`

Also prove:
- HOT/NORMAL/WEAK select the correct threshold;
- every current setup family uses its own rule;
- a missing rule never falls back to another setup's rule;
- mint and score context are copied exactly;
- one terminal finding only;
- repeated equal inputs return equal outputs;
- across all tested entry scenarios, `decide_entry()` never emits HOLD/REDUCE/EXIT.

### GREEN implementation

Implement:

```python
def decide_entry(mint: str, score: ScoreAssessment, policy: DecisionPolicy) -> TradeDecision:
    ...
```

Use fixed precedence from the spec and return immediately at each terminal gate.

No provider/SQLite/wall-clock/portfolio/risk/execution reads.

Run full CI and require all jobs green.

---

## Task 3 — Stable public API, README, immutable seal

**Files:**
- Create `python/src/shreks_brain/decision/__init__.py`
- Create `python/tests/test_decision_public_api.py`
- Modify `README.md`
- Modify this plan only for non-self-referential verification evidence

Stable public imports:

```python
DecisionAction
DecisionFinding
DecisionPolicy
DecisionReasonCode
SetupDecisionRule
TradeDecision
decide_entry
```

Public API regression test must prove existing safety/features/setups/regime/scoring entry points remain importable.

README must document:
- repo B8 = source build-order decision capability;
- safety/setup precedence;
- setup-specific regime thresholds;
- DEAD never enters;
- missing/disabled regime and unavailable score WATCH;
- `ENTER` only forwards to risk;
- full six-action vocabulary exists, while HOLD/REDUCE/EXIT await real position/exit evidence;
- no production threshold defaults;
- no `TradeIntent` or execution authority.

After the final tracked-file commit, run one fresh exact-head full CI. Audit the diff against verified B7. Record final SHA/run only in draft-PR metadata and leave the PR draft/unmerged.

## Self-review

- The plan covers every spec reason code and precedence gate.
- It does not hide risk/position/execution work inside B8.
- It keeps action vocabulary compatible with the source while refusing to fabricate open-position decisions prematurely.
- No placeholders or unspecified production defaults remain.