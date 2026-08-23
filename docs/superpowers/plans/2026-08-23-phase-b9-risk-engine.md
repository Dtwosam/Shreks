# Phase B9 Risk Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure fail-closed Risk Engine that risk-sizes B8 `ENTER` decisions and either rejects them or returns the stable `TradeIntent` interface for Phase C paper execution.

**Architecture:** Create `shreks_brain.risk` beside unchanged runtime/safety/features/setups/regime/scoring/decision code. Task 1 establishes frozen policy/context/intent/assessment models. Task 2 adds the pure evaluator with defensive upstream rechecks, portfolio/loss/health/executability gates, deterministic sizing, and deterministic idempotency. Task 3 seals public exports, README documentation, and exact-head verification.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, hashlib SHA-256, pytest, existing GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b9-risk-engine-design.md`

## Global Constraints

- Base is verified B8 head `38f1d1b1f7de80a7504d92904c0314df22ce94f7`.
- No SQLite/provider/balance/wall-clock read inside risk code.
- Only B8 `ENTER` can reach sizing.
- Safety must remain `PASS`; setup must remain `READY`; DEAD cannot enter.
- PAPER and SHADOW may produce intents; OBSERVE/HALTED/LIVE cannot.
- Critical missing guardrail evidence rejects.
- Risk sizing is independent of strategy score/confidence.
- Full requested entry notional is the B9 incremental aggregate-risk amount.
- Price-impact evidence must cover at least the final risk-sized notional.
- No production `RiskPolicy` defaults.
- No paper fill, position ledger, exit engine, signer, route/quote request, transaction, submission, or live-money path.

---

### Task 1: Immutable risk domain and stable TradeIntent

**Files:**
- Create: `python/src/shreks_brain/risk/models.py`
- Create: `python/tests/test_risk_models.py`

**Interfaces:**
- Consumes: `RuntimeMode`, B8 `DecisionAction`.
- Produces: `TradeSide`, `RiskState`, `RiskReasonCode`, `RiskFinding`, `RiskPolicy`, `RiskContext`, `TradeIntent`, `RiskAssessment`.

- [ ] **Step 1: Write the failing model-contract test**

Create `python/tests/test_risk_models.py` and import all Task-1 symbols from `shreks_brain.risk.models`.

Pin exact enum orders:

```python
assert tuple(item.value for item in TradeSide) == ("BUY", "SELL")
assert tuple(item.value for item in RiskState) == ("REJECTED", "APPROVED")
assert tuple(item.value for item in RiskReasonCode) == (
    "DECISION_POLICY_MISMATCH",
    "FEATURE_SCHEMA_UNSUPPORTED",
    "DECISION_NOT_ENTER",
    "SAFETY_NOT_PASS",
    "SETUP_NOT_READY",
    "REGIME_DEAD",
    "TOTAL_SCORE_UNAVAILABLE",
    "CONTEXT_AS_OF_MISMATCH",
    "OBSERVE_MODE_NO_INTENTS",
    "HALTED_MODE",
    "LIVE_MODE_DISABLED",
    "KILL_SWITCH_ACTIVE",
    "DATA_HEALTH_UNKNOWN",
    "DATA_HEALTH_DEGRADED",
    "EXECUTION_HEALTH_UNKNOWN",
    "EXECUTION_HEALTH_DEGRADED",
    "TRADING_CAPITAL_UNKNOWN",
    "TRADING_CAPITAL_NON_POSITIVE",
    "OPEN_POSITION_COUNT_UNKNOWN",
    "MAX_POSITIONS_REACHED",
    "AGGREGATE_OPEN_RISK_UNKNOWN",
    "AGGREGATE_RISK_LIMIT_REACHED",
    "DAILY_REALIZED_PNL_UNKNOWN",
    "DAILY_LOSS_LIMIT_REACHED",
    "ROLLING_DRAWDOWN_UNKNOWN",
    "ROLLING_DRAWDOWN_LIMIT_REACHED",
    "CONSECUTIVE_LOSSES_UNKNOWN",
    "LOSS_COOLDOWN_TIME_UNKNOWN",
    "LOSS_COOLDOWN_TIME_AFTER_AS_OF",
    "LOSS_COOLDOWN_ACTIVE",
    "LIQUIDITY_UNKNOWN",
    "LIQUIDITY_BELOW_MINIMUM",
    "PRICE_IMPACT_UNKNOWN",
    "PRICE_IMPACT_NOTIONAL_UNKNOWN",
    "PRICE_IMPACT_NOTIONAL_TOO_SMALL",
    "PRICE_IMPACT_TOO_HIGH",
    "MARKET_DATA_AGE_UNKNOWN",
    "MARKET_DATA_TOO_OLD",
    "DUPLICATE_ACTIVE_INTENT",
    "RISK_APPROVED",
)
```

Use this explicit test policy:

```python
RiskPolicy(
    version="risk-v1-test",
    required_decision_policy_version="decision-v1-test",
    required_feature_schema_version="b2-v1",
    target_position_notional_usd=500.0,
    max_notional_per_position_usd=1_000.0,
    max_capital_fraction_per_position=0.10,
    max_simultaneous_positions=5,
    max_aggregate_open_risk_usd=3_000.0,
    max_daily_realized_loss_usd=500.0,
    max_rolling_drawdown_pct=20.0,
    cooldown_after_consecutive_losses=3,
    cooldown_seconds=300,
    min_liquidity_usd=50_000.0,
    max_expected_price_impact_pct=5.0,
    max_slippage_bps=300,
    max_market_data_age_ms=30_000,
)
```

Prove all spec validation boundaries, including non-empty versions, finite/positive notionals/loss/risk values, fraction `(0,1]`, integer count limits, drawdown `(0,100]`, non-negative cooldown/liquidity/impact/age, and slippage `[0,10000]`. Prove dataclasses are frozen.

Use canonical context:

```python
RiskContext(
    as_of_unix_ms=1_000_000,
    trading_capital_usd=10_000.0,
    open_position_count=1,
    aggregate_open_risk_usd=1_000.0,
    daily_realized_pnl_usd=-100.0,
    rolling_drawdown_pct=5.0,
    consecutive_losses=1,
    last_loss_at_unix_ms=900_000,
    liquidity_usd=100_000.0,
    expected_price_impact_pct=2.0,
    price_impact_notional_usd=5_000.0,
    market_data_age_ms=5_000,
    data_healthy=True,
    execution_healthy=True,
    kill_switch_active=False,
    active_intent_keys=frozenset(),
)
```

Prove each critical optional field accepts `None` but rejects invalid present values. Prove active intent keys must be a frozenset of non-empty strings.

Construct canonical intent:

```python
TradeIntent(
    mint="Mint111",
    side=TradeSide.BUY,
    requested_notional_usd=500.0,
    max_slippage_bps=300,
    strategy_name="fresh_launch_continuation",
    strategy_version="fresh-test",
    score_policy_version="score-v1-test",
    decision_policy_version="decision-v1-test",
    risk_policy_version="risk-v1-test",
    reason="ENTRY_APPROVED",
    idempotency_key="abc123",
    execution_mode=RuntimeMode.PAPER,
    as_of_unix_ms=1_000_000,
)
```

Prove `TradeIntent` has none of:

```text
route
quote
fill
transaction
signature
private_key
secret
wallet_secret
realized_pnl
unrealized_pnl
```

Construct canonical approved/rejected `RiskAssessment` and prove state/intent/notional/key invariants.

- [ ] **Step 2: Verify RED**

Commit only the Task-1 test, open stacked draft PR, run full CI.

Expected Python failure:

```text
ModuleNotFoundError: No module named 'shreks_brain.risk'
```

Rust/workspace/repository-safety regressions remain green.

- [ ] **Step 3: Implement minimal immutable models**

Create `python/src/shreks_brain/risk/models.py` exactly from the spec. Use focused validation helpers and `math.isfinite`.

Do not add evaluator code or default policy constants.

- [ ] **Step 4: Verify GREEN**

Run full repository CI and require all jobs green.

- [ ] **Step 5: Record Task-1 evidence**

Record RED/GREEN SHA and CI IDs in the later verification record/PR metadata.

---

### Task 2: Pure fail-closed entry risk evaluator

**Files:**
- Create: `python/src/shreks_brain/risk/engine.py`
- Create: `python/tests/test_risk_engine.py`

**Interfaces:**
- Consumes:

```python
TradeDecision
RiskContext
RiskPolicy
RuntimeMode
```

- Produces:

```python
def assess_entry_risk(
    decision: TradeDecision,
    context: RiskContext,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
) -> RiskAssessment:
    ...
```

- [ ] **Step 1: Write canonical fixtures and expected approval**

Canonical decision:

```python
TradeDecision(
    policy_version="decision-v1-test",
    mint="Mint111",
    as_of_unix_ms=1_000_000,
    action=DecisionAction.ENTER,
    score_policy_version="score-v1-test",
    feature_schema_version="b2-v1",
    safety_decision=SafetyDecision.PASS,
    setup_name="fresh_launch_continuation",
    setup_policy_version="fresh-test",
    setup_state=SetupState.READY,
    market_regime=MarketRegime.NORMAL,
    total_score=80.0,
    required_score_threshold=75.0,
    findings=(
        DecisionFinding(
            code=DecisionReasonCode.ENTRY_APPROVED,
            message="entry threshold passed",
        ),
    ),
)
```

Use the Task-1 policy/context fixtures. Canonical `RuntimeMode.PAPER` must approve exactly $500 notional with one `RISK_APPROVED` finding and a BUY intent.

- [ ] **Step 2: Write failing upstream/runtime precedence tests**

Parameterize exact terminal reasons for:

```text
DECISION_POLICY_MISMATCH
FEATURE_SCHEMA_UNSUPPORTED
DECISION_NOT_ENTER
SAFETY_NOT_PASS
SETUP_NOT_READY
REGIME_DEAD
TOTAL_SCORE_UNAVAILABLE
CONTEXT_AS_OF_MISMATCH
OBSERVE_MODE_NO_INTENTS
HALTED_MODE
LIVE_MODE_DISABLED
```

Assert every rejection has `state=REJECTED`, `requested_notional_usd is None`, `idempotency_key is None`, and `intent is None`.

- [ ] **Step 3: Write failing kill-switch/health tests**

Pin:

```text
KILL_SWITCH_ACTIVE
DATA_HEALTH_UNKNOWN
DATA_HEALTH_DEGRADED
EXECUTION_HEALTH_UNKNOWN
EXECUTION_HEALTH_DEGRADED
```

Prove kill switch wins before health findings.

- [ ] **Step 4: Write failing portfolio/loss/cooldown tests**

Pin missing and breached cases for:

```text
TRADING_CAPITAL_UNKNOWN
TRADING_CAPITAL_NON_POSITIVE
OPEN_POSITION_COUNT_UNKNOWN
MAX_POSITIONS_REACHED
AGGREGATE_OPEN_RISK_UNKNOWN
AGGREGATE_RISK_LIMIT_REACHED
DAILY_REALIZED_PNL_UNKNOWN
DAILY_LOSS_LIMIT_REACHED
ROLLING_DRAWDOWN_UNKNOWN
ROLLING_DRAWDOWN_LIMIT_REACHED
CONSECUTIVE_LOSSES_UNKNOWN
LOSS_COOLDOWN_TIME_UNKNOWN
LOSS_COOLDOWN_TIME_AFTER_AS_OF
LOSS_COOLDOWN_ACTIVE
```

Boundary tests:

- position count one below max passes; equality rejects;
- open risk one unit below max continues; equality rejects;
- daily PnL just above negative loss limit passes; equality rejects;
- drawdown just below max passes; equality rejects;
- cooldown elapsed one millisecond short rejects; equality passes;
- cooldown seconds zero skips last-loss timestamp requirement after count validation.

- [ ] **Step 5: Write failing deterministic sizing tests**

Canonical size = 500.

Independently prove each cap binds:

```text
target position notional
max notional per position
capital fraction cap
remaining aggregate-risk capacity
```

Examples:

- target 2,000 / max notional 1,000 / other caps larger -> 1,000;
- capital 4,000 at 10% / other caps larger -> 400;
- max aggregate risk 3,000 with 2,900 already open -> 100.

Prove changing `decision.total_score` while it stays eligible does not change requested notional.

- [ ] **Step 6: Write failing executability tests**

Pin:

```text
LIQUIDITY_UNKNOWN
LIQUIDITY_BELOW_MINIMUM
PRICE_IMPACT_UNKNOWN
PRICE_IMPACT_NOTIONAL_UNKNOWN
PRICE_IMPACT_NOTIONAL_TOO_SMALL
PRICE_IMPACT_TOO_HIGH
MARKET_DATA_AGE_UNKNOWN
MARKET_DATA_TOO_OLD
```

Boundary semantics:

- liquidity equality passes;
- impact-notional equality with requested size passes;
- impact equality passes;
- data-age equality passes.

Prove an impact estimate covering $499.99 cannot approve a $500 intent.

- [ ] **Step 7: Write failing idempotency tests**

For an approved input, capture the generated key. Re-run with that key in `active_intent_keys` and assert `DUPLICATE_ACTIVE_INTENT`.

Prove:

- equal inputs derive equal keys;
- changing risk-policy version alone does not change the key;
- changing mint/as-of/setup policy/decision policy/mode does change the key.

- [ ] **Step 8: Write failing stable-intent tests**

On PAPER and SHADOW approval assert:

```text
side = BUY
reason = ENTRY_APPROVED
strategy_name = setup_name
strategy_version = setup_policy_version
score/decision/risk policy versions copied exactly
slippage ceiling = policy.max_slippage_bps
mode copied exactly
```

Assert `assess_entry_risk()` never creates LIVE/OBSERVE/HALTED intent.

- [ ] **Step 9: Write failing determinism/terminal-finding test**

Call twice with equal inputs and assert equal assessments. Construct a case violating multiple downstream guards and prove only the earliest fixed-precedence terminal finding appears.

- [ ] **Step 10: Verify RED**

Commit Task-2 tests. Full PR CI must fail Python only because `shreks_brain.risk.engine` / `assess_entry_risk` is missing.

- [ ] **Step 11: Implement minimal evaluator**

Create `python/src/shreks_brain/risk/engine.py`.

Use immediate terminal-return helpers and this exact stage order:

```text
upstream compatibility
runtime mode
global/health
portfolio/loss/cooldown
size
liquidity/impact/age
idempotency
approval
```

Private helpers may include:

```python
def _reject(... ) -> RiskAssessment: ...
def _entry_idempotency_key(... ) -> str: ...
def _requested_notional(... ) -> float: ...
```

Use `hashlib.sha256` over a newline-separated canonical payload. Do not use Python's randomized `hash()`.

- [ ] **Step 12: Verify GREEN**

Run full repository CI and require all jobs green.

- [ ] **Step 13: Record Task-2 evidence**

Record exact RED/GREEN SHAs and CI IDs.

---

### Task 3: Stable package API, README, and immutable Phase-B seal

**Files:**
- Create: `python/src/shreks_brain/risk/__init__.py`
- Create: `python/tests/test_risk_public_api.py`
- Modify: `README.md`
- Modify: this plan only for the final non-self-referential verification record

**Stable exports:**

```python
RiskAssessment
RiskContext
RiskFinding
RiskPolicy
RiskReasonCode
RiskState
TradeIntent
TradeSide
assess_entry_risk
```

- [ ] **Step 1: Write failing public API regression test**

Import all stable risk symbols from `shreks_brain.risk`. Prove `assess_entry_risk` is callable and canonical PAPER input returns `RiskAssessment` with `TradeIntent`.

Also prove existing imports remain available from:

```text
shreks_brain.runtime
shreks_brain.safety
shreks_brain.features
shreks_brain.setups
shreks_brain.regime
shreks_brain.scoring
shreks_brain.decision
```

Inspect `dataclasses.fields(TradeIntent)` and assert no signer/transaction/fill/private-key/wallet-secret/outcome fields.

- [ ] **Step 2: Verify RED**

Full CI must fail Python only because package-level risk exports are absent.

- [ ] **Step 3: Export stable API**

Create `risk/__init__.py` exporting exactly the nine public symbols above. Export no default policy or live executor.

- [ ] **Step 4: Verify package GREEN**

Run full repository CI.

- [ ] **Step 5: Document Phase-B risk semantics**

README section must state:

- B9 = source B7 Risk Engine capability;
- exact guardrail categories;
- critical uncertainty fails closed;
- deterministic sizing formula and full-notional aggregate-risk assumption;
- price-impact estimate must cover risk-sized notional;
- idempotency is deterministic and duplicate-active keys reject;
- PAPER/SHADOW only, LIVE hard-disabled;
- stable `TradeIntent` is now the Phase-C execution boundary;
- no production risk defaults and no money is touched.

- [ ] **Step 6: Replace this plan with completed verification record**

Record Task-1/2/3 RED/GREEN SHAs and CI IDs plus the README predecessor. Do not write the final branch SHA into a tracked file.

- [ ] **Step 7: Immutable final seal**

After the last tracked commit, run fresh exact-head full CI. Audit verified B8 -> B9 diff. Record final SHA/run only in draft PR metadata. Leave PR draft/unmerged.

## Self-Review

- Spec coverage: all source risk controls, sizing, stable intent, idempotency, live disable, missing-data semantics, and final Phase-B interface are assigned to explicit tasks.
- Placeholder scan: no `TBD`, `TODO`, “similar to”, unspecified validation, or implicit default remains.
- Type consistency: Task-2 and Task-3 signatures exactly consume Task-1 models and existing B8/runtime types.
- Scope remains one subsystem: no paper-fill, position-ledger, exit, provider, storage, signing, transaction, or live-execution implementation is hidden in B9.
