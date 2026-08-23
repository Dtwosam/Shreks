# Phase B9 Risk Engine Design

## Status

Approved for autonomous implementation under the standing Shreks project instruction.

## Goal

Add the source build-order B7 Risk Engine capability as repository Phase B9: a pure, versioned, fail-closed Python layer that accepts only a B8 `ENTER` decision, evaluates point-in-time portfolio/health/executability guardrails, deterministically sizes an entry, and either rejects it or returns the stable `TradeIntent` interface that Phase C paper trading and future live execution will share.

B9 completes the Phase-B requirement that Shreks can create or reject a trade intent without touching money.

## Base and scope

Base: verified B8 head `38f1d1b1f7de80a7504d92904c0314df22ce94f7`.

Create `shreks_brain.risk`. Existing runtime, safety, feature, setup, regime, scoring, decision, Rust, storage, and provider behavior stays unchanged.

B9 performs no I/O. It never reads SQLite, providers, balances, or wall clock directly. The caller supplies one immutable point-in-time `RiskContext` so historical replay and live evaluation use the same deterministic risk function.

B9 creates no paper fill, position ledger, exit engine, signer, route request, transaction, transaction submission, or live-money path.

## Required guardrails

B9 supports all source requirements:

- maximum notional per position;
- maximum percentage of trading capital per position;
- maximum simultaneous positions;
- maximum aggregate open risk;
- maximum daily realized loss;
- maximum rolling drawdown;
- cooldown after consecutive losses;
- minimum liquidity;
- maximum expected price impact;
- maximum slippage;
- duplicate-intent protection;
- health-based new-entry pause;
- global kill switch.

Uncertainty about a critical guardrail means no new entry.

## Public boundary

```python
def assess_entry_risk(
    decision: TradeDecision,
    context: RiskContext,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
) -> RiskAssessment:
    ...
```

Equal inputs return equal outputs.

A successful assessment returns the stable `TradeIntent` domain object that Phase C paper execution and future live execution will consume.

B9 may create intents only for `RuntimeMode.PAPER` or `RuntimeMode.SHADOW`.

- `OBSERVE`: no intent.
- `HALTED`: no intent.
- `LIVE`: hard-disabled in B9 even if every other guardrail passes.

No policy can enable live intent creation in Phase B.

## Domain enums

### `TradeSide`

Exact order:

```text
BUY
SELL
```

B9 entry assessment emits only `BUY`. `SELL` exists so later exits can reuse the same intent type.

### `RiskState`

Exact order:

```text
REJECTED
APPROVED
```

### `RiskReasonCode`

Exact order:

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
KILL_SWITCH_ACTIVE
DATA_HEALTH_UNKNOWN
DATA_HEALTH_DEGRADED
EXECUTION_HEALTH_UNKNOWN
EXECUTION_HEALTH_DEGRADED
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
LIQUIDITY_UNKNOWN
LIQUIDITY_BELOW_MINIMUM
PRICE_IMPACT_UNKNOWN
PRICE_IMPACT_NOTIONAL_UNKNOWN
PRICE_IMPACT_NOTIONAL_TOO_SMALL
PRICE_IMPACT_TOO_HIGH
MARKET_DATA_AGE_UNKNOWN
MARKET_DATA_TOO_OLD
DUPLICATE_ACTIVE_INTENT
RISK_APPROVED
```

A rejected assessment has exactly one terminal reason. An approved assessment has exactly `RISK_APPROVED`.

## Immutable models

All dataclasses are frozen and slotted.

### `RiskFinding`

```python
code: RiskReasonCode
message: str
```

Message is non-empty.

### `RiskPolicy`

Exact fields:

```python
version: str
required_decision_policy_version: str
required_feature_schema_version: str
target_position_notional_usd: float
max_notional_per_position_usd: float
max_capital_fraction_per_position: float
max_simultaneous_positions: int
max_aggregate_open_risk_usd: float
max_daily_realized_loss_usd: float
max_rolling_drawdown_pct: float
cooldown_after_consecutive_losses: int
cooldown_seconds: int
min_liquidity_usd: float
max_expected_price_impact_pct: float
max_slippage_bps: int
max_market_data_age_ms: int
```

Validation:

- version/schema-policy strings non-empty;
- target and maximum notionals finite and strictly positive;
- capital fraction finite in `(0, 1]`;
- max simultaneous positions >= 1;
- aggregate-risk and daily-loss limits finite and strictly positive;
- max rolling drawdown finite in `(0, 100]`;
- consecutive-loss threshold >= 1;
- cooldown seconds >= 0;
- minimum liquidity finite and non-negative;
- max expected price impact finite and non-negative;
- max slippage bps integer in `[0, 10_000]`;
- max market-data age >= 0.

There is no production default policy.

### `RiskContext`

Exact fields:

```python
as_of_unix_ms: int
trading_capital_usd: float | None
open_position_count: int | None
aggregate_open_risk_usd: float | None
daily_realized_pnl_usd: float | None
rolling_drawdown_pct: float | None
consecutive_losses: int | None
last_loss_at_unix_ms: int | None
liquidity_usd: float | None
expected_price_impact_pct: float | None
price_impact_notional_usd: float | None
market_data_age_ms: int | None
data_healthy: bool | None
execution_healthy: bool | None
kill_switch_active: bool
active_intent_keys: frozenset[str]
```

Validation:

- timestamps non-negative;
- present capital/liquidity/open-risk/impact-notional/impact values finite and non-negative;
- present daily realized PnL finite and may be negative or positive;
- present rolling drawdown finite in `[0, 100]`;
- present counts non-negative integers;
- present market-data age non-negative;
- health values bool or `None`;
- kill switch bool;
- active keys a frozenset of non-empty strings.

Missing critical evidence remains `None`; it is never zero-filled or guessed.

`price_impact_notional_usd` explicitly states the entry notional covered by `expected_price_impact_pct`. This prevents using an impact estimate calculated for a smaller trade to approve a larger trade.

### `TradeIntent`

Exact fields:

```python
mint: str
side: TradeSide
requested_notional_usd: float
max_slippage_bps: int
strategy_name: str
strategy_version: str
score_policy_version: str
decision_policy_version: str
risk_policy_version: str
reason: str
idempotency_key: str
execution_mode: RuntimeMode
as_of_unix_ms: int
```

Validation:

- names/versions/reason/key non-empty;
- requested notional finite and > 0;
- max slippage bps in `[0, 10_000]`;
- execution mode is a `RuntimeMode`;
- timestamp non-negative.

`strategy_name` is the setup name; `strategy_version` is the setup policy version. Score, decision, and risk policy versions are carried separately for full auditability.

The intent contains no route, quote, fill, transaction, signature, private key, wallet secret, or realized outcome field.

### `RiskAssessment`

Exact fields:

```python
policy_version: str
mint: str
as_of_unix_ms: int
state: RiskState
decision_action: DecisionAction
execution_mode: RuntimeMode
requested_notional_usd: float | None
idempotency_key: str | None
findings: tuple[RiskFinding, ...]
intent: TradeIntent | None
```

Invariants:

- `REJECTED`: requested notional, idempotency key, and intent are all `None`;
- `APPROVED`: requested notional is positive, key is non-empty, intent is present;
- approved intent mint/as-of/mode/notional/key exactly match assessment.

## Defensive upstream rechecks

Risk independently requires, in order:

1. decision policy version matches `required_decision_policy_version`;
2. feature schema matches `required_feature_schema_version`;
3. decision action is `ENTER`;
4. safety decision is `PASS`;
5. setup state is `READY`;
6. regime is not `DEAD`;
7. total score is not `None`;
8. context as-of equals decision as-of.

B8 normally guarantees these, but risk fails closed on manually constructed or stale inconsistent inputs.

## Runtime gate

After compatibility:

1. `OBSERVE` -> `OBSERVE_MODE_NO_INTENTS`;
2. `HALTED` -> `HALTED_MODE`;
3. `LIVE` -> `LIVE_MODE_DISABLED`;
4. `PAPER` or `SHADOW` continue.

## Global and health gates

Order:

1. kill switch;
2. data health;
3. execution health.

Unknown health rejects. False health rejects.

## Portfolio/loss gates

Order and boundary semantics:

1. trading capital required and > 0;
2. position count required; `>= max_simultaneous_positions` rejects;
3. aggregate open risk required; `>= max_aggregate_open_risk_usd` rejects;
4. daily realized PnL required; `<= -max_daily_realized_loss_usd` rejects;
5. rolling drawdown required; `>= max_rolling_drawdown_pct` rejects;
6. consecutive-loss count required;
7. cooldown logic.

### Cooldown

If `cooldown_seconds == 0`, count is still validated but no time gate is applied.

Otherwise, if consecutive losses reach the configured threshold:

- last-loss timestamp is required;
- future last-loss timestamp rejects;
- elapsed time `< cooldown_seconds` rejects;
- equality at the cooldown boundary passes.

## Deterministic sizing

After portfolio/loss gates, calculate:

```python
capital_fraction_cap = (
    context.trading_capital_usd * policy.max_capital_fraction_per_position
)
remaining_aggregate_risk = (
    policy.max_aggregate_open_risk_usd - context.aggregate_open_risk_usd
)
requested_notional_usd = min(
    policy.target_position_notional_usd,
    policy.max_notional_per_position_usd,
    capital_fraction_cap,
    remaining_aggregate_risk,
)
```

Every term is strictly positive after the preceding validated gates, so the result is strictly positive. There is no unreachable synthetic "no capacity" state.

No score/confidence multiplier is applied. Risk sizing is independent of strategy confidence.

### Conservative aggregate-risk interpretation

Until Phase C has authoritative stop/position/exit state, the full requested entry notional is treated as the incremental open-risk amount. This is deliberately conservative. A later version may replace it with a proven loss-at-risk model only after position/exit state exists.

## Market/executability gates

After sizing, require in order:

1. liquidity present and `>= min_liquidity_usd`;
2. expected price impact present;
3. price-impact notional present;
4. `price_impact_notional_usd >= requested_notional_usd`;
5. expected price impact `<= max_expected_price_impact_pct`;
6. market-data age present and `<= max_market_data_age_ms`.

Equality at each allowed boundary passes.

Accepting an impact estimate for a larger notional is conservative; an estimate for a smaller notional is insufficient evidence and rejects.

B9 does not obtain a route or quote. Phase C/F execution adapters later recheck contemporaneous conditions and enforce the intent's slippage ceiling.

## Idempotency

After all risk/executability gates, derive one SHA-256 key from canonical UTF-8 fields:

```text
entry-v1
execution_mode
mint
decision.as_of_unix_ms
setup_name
setup_policy_version
score_policy_version
decision_policy_version
```

Risk policy version is deliberately excluded. Re-evaluating the same entry idea under a changed risk policy must not create another active intent.

If the key already exists in `active_intent_keys`, reject `DUPLICATE_ACTIVE_INTENT`.

Equal inputs derive equal keys.

## Approval

On approval:

- state `APPROVED`;
- finding `RISK_APPROVED`;
- side `BUY`;
- requested notional from deterministic sizing;
- max slippage from `RiskPolicy.max_slippage_bps`;
- strategy name/version from B8 setup name/setup policy version;
- score/decision/risk policy versions copied into intent;
- reason = `ENTRY_APPROVED`;
- mode = PAPER or SHADOW;
- deterministic idempotency key copied into assessment and intent.

The risk layer never calls an execution adapter.

## Fixed precedence

```text
decision policy compatibility
feature schema compatibility
ENTER action
safety PASS
setup READY
regime not DEAD
total score available
context timestamp match
runtime mode
kill switch
data health
execution health
trading capital
position count
aggregate open risk
daily realized loss
rolling drawdown
consecutive losses / cooldown
deterministic sizing
liquidity
expected price impact
price-impact notional coverage
market-data age
idempotency duplicate check
approval
```

Every rejection is an immediate terminal return. Tests pin this ordering.

## Missing-data semantics

Critical uncertainty always rejects. `None` never becomes zero, healthy, or permissive. Rejected assessments never fabricate size, key, or intent.

## No production defaults

B9 exports no default `RiskPolicy`. Numeric values in tests are fixtures only and make no profitability claim.

## TDD plan

### Task 1 — models

Write RED tests for enum/reason order, policy/context validation, stable `TradeIntent`, `RiskAssessment` invariants, frozen dataclasses, and absence of execution/secret/outcome authority. Expected RED: `shreks_brain.risk` missing.

### Task 2 — evaluator

Write RED tests for every precedence gate, equality boundaries, hard live disable, deterministic sizing, impact-notional coverage, deterministic idempotency, duplicate rejection, and repeated-input equality. Expected RED: `shreks_brain.risk.engine` missing.

### Task 3 — public API and seal

Write package RED tests, then export:

```text
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

Prove existing runtime/safety/features/setups/regime/scoring/decision APIs remain importable. Update README, record RED/GREEN evidence, run exact-head full CI, audit the B8->B9 diff, and leave the stacked PR draft/unmerged.

## Completion criteria

B9 is complete only when:

- every required risk guardrail is represented and test-pinned;
- an eligible PAPER/SHADOW B8 `ENTER` deterministically produces one risk-sized `TradeIntent`;
- critical uncertainty, duplicate state, kill switch, health failure, portfolio/loss limits, liquidity/impact failures, and stale market evidence reject;
- price-impact evidence cannot approve a larger notional than it covers;
- LIVE cannot create an intent;
- no money is touched;
- final exact branch head has fresh green Rust, Python, workspace metadata, and repository-safety CI;
- final diff contains only intended B9 files;
- draft PR remains unmerged.
