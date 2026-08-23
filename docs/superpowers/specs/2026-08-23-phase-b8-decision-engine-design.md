# Phase B8 Deterministic Decision Engine Design

**Project:** Shreks  
**Repository:** `Dtwosam/Shreks`  
**Branch:** `feat/phase-b8-decision-engine`  
**Base:** verified B7 head `26367ddf64aab9aae724afce4843219770b9feae`

## Purpose

B8 adds the source build-order Decision Engine after deterministic scoring and before risk sizing. It converts one immutable B7 `ScoreAssessment` plus explicit policy into an auditable pre-entry `TradeDecision`.

B8 does not size positions and does not create `TradeIntent`. The next risk phase owns capital, portfolio, slippage, and intent construction.

## Dependency refinement

The source decision vocabulary is exactly:

```text
REJECT
WATCH
ENTER
HOLD
REDUCE
EXIT
```

The repository does not yet have the Phase C position ledger or exit-signal engine required to produce evidence-based `HOLD`, `REDUCE`, or `EXIT` actions. B8 therefore defines the complete six-action vocabulary and a general `TradeDecision` model now, but B8-v1's entry evaluator emits only `REJECT`, `WATCH`, or `ENTER`.

This avoids inventing fake open-position evidence or forcing entry-style setup rules to masquerade as exit logic. Phase C position/exit work will reuse the same `TradeDecision` type for `HOLD`, `REDUCE`, and `EXIT`.

## Package

Create:

```text
python/src/shreks_brain/decision/
    __init__.py
    models.py
    engine.py
```

The package is pure Python with no SQLite, provider, wall-clock, portfolio, execution, or future-outcome reads.

## Decision identity

B7 scores are candidate-level but intentionally do not carry mint identity. B8 accepts the candidate mint explicitly so the decision becomes a durable candidate-bound domain object:

```python
def decide_entry(
    mint: str,
    score: ScoreAssessment,
    policy: DecisionPolicy,
) -> TradeDecision:
    ...
```

The function has no hidden lookup. The caller is responsible for binding the score to the same candidate mint during orchestration.

## DecisionAction

```python
class DecisionAction(StrEnum):
    REJECT = "REJECT"
    WATCH = "WATCH"
    ENTER = "ENTER"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
```

## Setup-specific regime rules

One global entry score threshold would make independent setup calibration harder and would violate the project's goal that losing setups be independently disableable.

Each setup receives an explicit immutable rule:

```python
@dataclass(frozen=True, slots=True)
class SetupDecisionRule:
    setup_name: str
    enabled: bool
    hot_min_score: float | None
    normal_min_score: float | None
    weak_min_score: float | None
```

A `None` threshold disables new entries for that setup in that regime. `DEAD` has no configurable threshold because new entries are always rejected in a DEAD regime.

Thresholds are hypotheses. B8 does not enforce a monotonic HOT <= NORMAL <= WEAK ordering because only later point-in-time evaluation can justify how score cutoffs should differ by regime.

## DecisionPolicy

```python
@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    version: str
    required_score_policy_version: str
    setup_rules: tuple[SetupDecisionRule, ...]
```

Validation:

- version strings are non-empty;
- rules are a non-empty tuple;
- setup names are unique;
- every rule is a `SetupDecisionRule`;
- thresholds, when present, are finite within `[0, 100]`;
- `enabled` is boolean;
- no default production policy exists.

`required_score_policy_version` prevents a decision threshold calibrated for one scoring policy from silently being applied to another score definition.

## Reason codes

Stable order:

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

## TradeDecision

```python
@dataclass(frozen=True, slots=True)
class TradeDecision:
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

This object deliberately has no requested size, capital percentage, slippage ceiling, idempotency key, execution mode, wallet, signer, order, fill, or transaction fields. Those belong to later risk/execution layers.

The general model permits all six `DecisionAction` enum values so the later exit system can reuse it, but `decide_entry()` is tested never to emit `HOLD`, `REDUCE`, or `EXIT`.

## Entry decision precedence

`decide_entry()` evaluates in this exact order:

1. score-policy compatibility;
2. B1 safety decision;
3. setup state;
4. setup-rule existence/enabled state;
5. market regime permission;
6. total-score availability;
7. configured score threshold;
8. entry approval.

### 1. Score-policy compatibility

If `score.policy_version != policy.required_score_policy_version`:

```text
REJECT / SCORE_POLICY_MISMATCH
```

This is a configuration/schema incompatibility, not a low-quality candidate.

### 2. Safety precedence

- `SafetyDecision.REJECT` -> `REJECT / SAFETY_REJECTED`
- `SafetyDecision.INCOMPLETE` -> `WATCH / SAFETY_INCOMPLETE`
- only `PASS` continues.

This preserves the project's hard safety veto while distinguishing proven hard rejection from unresolved critical evidence.

### 3. Setup state

- `BLOCKED` -> `REJECT / SETUP_BLOCKED`
- `WATCH` -> `WATCH / SETUP_WATCH`
- only `READY` continues.

### 4. Setup rule

- no matching policy rule -> `REJECT / SETUP_RULE_MISSING`
- matching rule with `enabled=False` -> `REJECT / SETUP_DISABLED`

There is no fallback/default rule.

### 5. Regime

- `DEAD` -> `REJECT / REGIME_DEAD`
- HOT/NORMAL/WEAK with threshold `None` -> `WATCH / REGIME_DISABLED`

A disabled live entry regime is WATCH rather than candidate rejection because the same setup may become eligible when the global environment changes.

### 6. Score availability

If `score.total_score is None`:

```text
WATCH / TOTAL_SCORE_UNAVAILABLE
```

This covers missing positive-weight score evidence and B7 point-in-time compatibility failures. Critical uncertainty cannot create an entry.

### 7. Threshold

If score is strictly below the selected setup/regime threshold:

```text
WATCH / TOTAL_SCORE_BELOW_THRESHOLD
```

Threshold equality passes.

### 8. Entry

If every prior gate passes and score is at or above threshold:

```text
ENTER / ENTRY_APPROVED
```

`ENTER` means only that the candidate may proceed to the Risk Engine. It is not an order, size, fill, or transaction request.

## Deterministic findings

B8-v1 returns one terminal decision reason rather than accumulating lower-precedence reasons after a terminal gate. This keeps the primary decision reason unambiguous and avoids claiming that downstream thresholds were evaluated when an upstream veto already stopped eligibility.

`DecisionFinding` still supports observed/threshold values for auditability.

## Research and calibration semantics

The Decision Engine is the first place where setup-specific/regime-specific entry thresholds are applied. These remain configuration hypotheses and must later be evaluated by setup, regime, costs, expectancy, and drawdown.

The scorer remains useful on rejected candidates, but the Decision Engine never lets a high research score override:

- B1 safety rejection;
- B1 incomplete critical evidence;
- setup BLOCKED/WATCH state;
- missing/disabled setup policy;
- DEAD/disabled market regime;
- missing total score.

## Public API

Stable imports:

```python
DecisionAction
DecisionFinding
DecisionPolicy
DecisionReasonCode
SetupDecisionRule
TradeDecision
decide_entry
```

## TDD requirements

Tests must pin:

- exact six-action enum order;
- exact reason-code order;
- frozen models and validation;
- no default policy;
- duplicate setup-rule rejection;
- score-policy mismatch;
- safety REJECT vs INCOMPLETE semantics;
- setup BLOCKED/WATCH semantics;
- missing/disabled setup rules;
- DEAD regime hard rejection;
- HOT/NORMAL/WEAK threshold selection;
- `None` threshold regime disabling;
- missing score behavior;
- threshold equality passes;
- below threshold WATCH;
- above threshold ENTER;
- each current setup family can use its own rule;
- no fallback from one setup rule to another;
- `decide_entry()` never emits HOLD/REDUCE/EXIT;
- deterministic repeated results;
- public API regression for safety/features/setups/regime/scoring;
- no TradeIntent/risk/size/execution fields.

## Out of scope

B8 does not implement:

- position sizing;
- portfolio limits;
- aggregate exposure;
- loss/drawdown/cooldown limits;
- slippage ceilings;
- idempotency keys;
- TradeIntent construction;
- position ledger;
- HOLD/REDUCE/EXIT logic;
- paper fills;
- exit signals;
- wallet intelligence;
- transaction signing/submission;
- live trading.

## Completion criteria

B8 is complete when the pure decision domain, setup/regime policy rules, and deterministic pre-entry evaluator are TDD-verified; all prior public APIs remain green; README documents the dependency refinement; full exact-head CI passes; and the final diff contains only the intended decision subsystem/docs/tests.