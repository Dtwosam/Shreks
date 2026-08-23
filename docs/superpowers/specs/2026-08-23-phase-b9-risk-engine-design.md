# Phase B9 Risk Engine Design

## Status

Approved for autonomous implementation under the standing Shreks project instruction.

## Goal

Add the source build-order B7 Risk Engine capability as repository Phase B9: a pure, versioned, fail-closed Python risk layer that accepts only a B8 `ENTER` decision, evaluates point-in-time portfolio/health/executability guardrails, deterministically sizes an entry, and either rejects it or returns the stable `TradeIntent` interface that Phase C paper trading and future live execution will share.

B9 completes the Phase-B requirement that Shreks can create or reject a trade intent without touching money.

## Base and scope

Base: verified B8 head `38f1d1b1f7de80a7504d92904c0314df22ce94f7`.

Create a new `shreks_brain.risk` package. Existing safety, feature, setup, regime, scoring, decision, Rust, storage, and provider behavior stays unchanged.

B9 does not read SQLite, providers, balances, or wall clock directly. The caller supplies one immutable point-in-time `RiskContext`; this keeps the function replayable and prevents hidden future/state leakage.

B9 creates no paper fill, position ledger, exit engine, signer, route request, transaction, transaction submission, or live-money path.

## Source requirements implemented

The risk layer must support:

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
- health-based entry pause;
- global kill switch.

Uncertainty about a critical guardrail means no new entry.

## Architecture

### Pure boundary

Public function:

```python
def assess_entry_risk(
    decision: TradeDecision,
    context: RiskContext,
    policy: RiskPolicy,
    execution_mode: RuntimeMode,
) -> RiskAssessment:
    ...
```

The function is deterministic for equal inputs and performs no I/O.

### Stable intent boundary

A successful risk assessment returns a `TradeIntent`. Paper and future live execution consume this exact domain type; only execution adapters differ.

B9 may construct intents only for `RuntimeMode.PAPER` or `RuntimeMode.SHADOW`.

- `OBSERVE` never creates an intent.
- `HALTED` never creates an intent.
- `LIVE` is hard-disabled in B9 even if all other risk controls pass. Live authorization remains a future proof-gated phase.

This prevents the Phase-B risk engine from accidentally creating a live-money path while still establishing the stable future execution interface.

## Domain models

All models are `@dataclass(frozen=True, slots=True)` unless an enum.

### `TradeSide`

Exact public vocabulary:

```text
BUY
SELL
```

B9 entry risk emits only `BUY`. `SELL` exists so the same `TradeIntent` type can later represent reductions/exits without interface replacement.

### `RiskState`

```text
REJECTED
APPROVED
```

### `RiskReasonCode`

Exact deterministic order:

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
PRICE_IMPACT_TOO_HIGH
MARKET_DATA_AGE_UNKNOWN
MARKET_DATA_TOO_OLD
DUPLICATE_ACTIVE_INTENT
NO_ENTRY_CAPACITY
RISK_APPROVED
```

One terminal reason is returned for a rejected assessment. An approved assessment has exactly `RISK_APPROVED`.

### `RiskFinding`

```python
code: RiskReasonCode
message: str
```

Message must be non-empty.

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
- target and maximum per-position notionals finite and strictly positive;
- capital fraction finite in `(0, 1]`;
- max simultaneous positions >= 1;
- aggregate risk limit finite and strictly positive;
- daily loss limit finite and strictly positive;
- max rolling drawdown finite in `(0, 100]`;
- consecutive-loss threshold >= 1;
- cooldown seconds >= 0;
- minimum liquidity finite and non-negative;
- max expected price impact finite and non-negative;
- max slippage bps integer in `[0, 10_000]`;
- max market-data age >= 0.

There is no production default policy instance.

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
market_data_age_ms: int | None
data_healthy: bool | None
execution_healthy: bool | None
kill_switch_active: bool
active_intent_keys: frozenset[str]
```

Validation:

- timestamps non-negative;
- present capital/liquidity/open-risk/impact values finite and non-negative;
- present daily realized PnL finite and may be negative or positive;
- present rolling drawdown finite in `[0, 100]`;
- present counts non-negative integers;
- market data age non-negative;
- health fields are bool or `None`;
- kill-switch field is bool;
- active intent keys are a frozenset of non-empty strings.

Missing critical values remain `None`; they are never guessed or zero-filled.

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

- all names/versions/reason/idempotency key non-empty;
- requested notional finite and strictly positive;
- max slippage bps in `[0, 10_000]`;
- execution mode must be a `RuntimeMode`;
- timestamp non-negative.

The type contains no route, quote, fill, transaction, signature, private key, wallet secret, or realized outcome field.

`strategy_name` is the B8 setup name. `strategy_version` is the setup policy version. Score, decision, and risk policy versions are carried separately so one paper/live intent can be audited back through the exact decision path.

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

- `REJECTED` => no intent and no requested notional;
- `APPROVED` => positive requested notional, non-empty idempotency key, and non-None intent;
- approved assessment intent mint/as-of/mode/notional/key match the assessment.

## Defensive upstream rechecks

Risk does not trust `DecisionAction.ENTER` as sufficient proof by itself. Before portfolio sizing it independently requires:

- decision policy version matches `RiskPolicy.required_decision_policy_version`;
- feature schema matches `RiskPolicy.required_feature_schema_version`;
- decision action is `ENTER`;
- safety is `PASS`;
- setup state is `READY`;
- market regime is not `DEAD`;
- total score is available;
- risk context timestamp equals decision timestamp.

This is defense in depth; B8 normally guarantees these conditions, but manually constructed or stale objects must fail closed.

## Runtime-mode gate

After upstream compatibility:

1. `OBSERVE` -> reject `OBSERVE_MODE_NO_INTENTS`.
2. `HALTED` -> reject `HALTED_MODE`.
3. `LIVE` -> reject `LIVE_MODE_DISABLED`.
4. `PAPER` and `SHADOW` continue.

No policy can override the B9 live-mode prohibition.

## Global and health gates

Order:

1. kill switch;
2. data health;
3. execution health.

`None` health is uncertainty and rejects. False health rejects.

This intentionally happens before capital sizing.

## Portfolio and loss gates

Order:

1. trading capital required and > 0;
2. open-position count required and below maximum;
3. aggregate open risk required and below maximum;
4. daily realized PnL required and above the negative daily-loss boundary;
5. rolling drawdown required and strictly below the maximum;
6. consecutive-loss count required;
7. loss cooldown if threshold reached.

Boundary semantics:

- `open_position_count >= max_simultaneous_positions` rejects;
- `aggregate_open_risk_usd >= max_aggregate_open_risk_usd` rejects;
- `daily_realized_pnl_usd <= -max_daily_realized_loss_usd` rejects;
- `rolling_drawdown_pct >= max_rolling_drawdown_pct` rejects.

### Consecutive-loss cooldown

If `cooldown_seconds == 0`, the cooldown is effectively disabled after count validation.

Otherwise, when `consecutive_losses >= cooldown_after_consecutive_losses`:

- `last_loss_at_unix_ms` is required;
- future last-loss timestamps reject as contradictory;
- elapsed time `< cooldown_seconds` rejects;
- equality at the cooldown boundary passes.

## Market/executability gates

Order:

1. liquidity required and `>= min_liquidity_usd`;
2. expected price impact required and `<= max_expected_price_impact_pct`;
3. market-data age required and `<= max_market_data_age_ms`.

Equality at each allowed boundary passes.

B9 does not fetch a route or quote. Phase C/F execution adapters later use the intent's `max_slippage_bps` and contemporaneous execution evidence to recheck market conditions.

## Idempotency

B9 derives one deterministic entry idempotency key using SHA-256 over canonical UTF-8 fields:

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

The risk-policy version is deliberately excluded. Re-evaluating the same entry decision under a changed risk policy must not create a second active intent for the same idea.

If the derived key is already present in `RiskContext.active_intent_keys`, reject with `DUPLICATE_ACTIVE_INTENT`.

Equal inputs always derive equal keys.

## Deterministic sizing

For an otherwise eligible entry, calculate:

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

If the result is not strictly positive, reject `NO_ENTRY_CAPACITY`.

No score/confidence multiplier is applied. Risk sizing is independent of strategy confidence.

### Conservative aggregate-risk interpretation

B9 has no authoritative stop/position/exit state yet. Therefore the full requested entry notional is treated as the incremental open-risk amount for aggregate-risk capacity.

This is intentionally conservative and point-in-time safe. A future version may use stop-distance or other loss-at-risk estimates only after Phase C has authoritative position/exit state and tests proving that model.

## Approval and intent construction

On approval:

- state = `APPROVED`;
- one finding = `RISK_APPROVED`;
- side = `BUY`;
- requested notional is the deterministic risk-sized amount;
- intent slippage ceiling equals policy `max_slippage_bps`;
- strategy name/version come from B8 setup name/setup policy version;
- reason is `ENTRY_APPROVED` from the upstream decision path;
- execution mode is PAPER or SHADOW;
- the deterministic idempotency key is copied into both assessment and intent.

The risk layer never calls an execution adapter.

## Fixed evaluation precedence

`assess_entry_risk()` uses immediate terminal returns in this order:

```text
decision-policy compatibility
feature-schema compatibility
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
liquidity
expected price impact
market data age
derive idempotency key / duplicate check
deterministic sizing
approval
```

This ordering is test-pinned.

## Missing-data semantics

Every critical portfolio, health, and market guardrail is fail-closed. `None` never becomes zero, healthy, or permissive.

A rejection does not fabricate a requested size or intent.

## No production defaults

B9 exports no production `RiskPolicy` instance. Test fixtures may use numeric examples, but repository behavior remains disabled until a caller explicitly supplies a versioned policy.

## Testing strategy

Strict TDD in three tasks.

### Task 1 — domain/policy models

Write tests first for:

- enum/reason-code order;
- policy validation and frozen dataclasses;
- context validation and missing critical evidence representation;
- `TradeIntent` stable interface;
- `RiskAssessment` approved/rejected invariants;
- absence of signer/transaction/fill/wallet-secret/outcome authority fields.

Expected RED: `shreks_brain.risk` missing.

### Task 2 — pure risk evaluator

Write tests first for every precedence gate, every equality boundary, live-mode hard disable, deterministic idempotency, duplicate protection, conservative sizing arithmetic, aggregate-risk capping, and repeated-input determinism.

Expected RED: `shreks_brain.risk.engine` missing.

### Task 3 — stable package API and Phase-B seal

Write package-level import tests first, then export:

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

Also prove existing runtime/safety/features/setups/regime/scoring/decision APIs remain importable.

Update README with the risk and stable-intent semantics, record RED/GREEN evidence, run fresh exact-head CI, audit B8->B9 diff, and leave the stacked PR draft/unmerged.

## Completion criteria

B9 is complete only when:

- all required risk guardrails above are represented and test-pinned;
- a valid PAPER or SHADOW B8 `ENTER` can deterministically produce one risk-sized `TradeIntent`;
- critical uncertainty, duplicate state, kill switch, health failure, portfolio/loss limit, liquidity/impact failure, and stale market evidence all reject;
- LIVE cannot produce an intent;
- no money is touched;
- exact final branch head has fresh green Rust, Python, workspace metadata, and repository-safety CI;
- final diff contains only intended B9 files;
- draft PR remains unmerged.
