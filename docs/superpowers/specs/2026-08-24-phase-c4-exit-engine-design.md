# Phase C4 Deterministic Exit Engine Design

## Goal

Implement the source build-order C4 Exit Engine as a pure, point-in-time Python decision layer that turns one authoritative C3 OPEN paper position plus contemporaneous market/execution evidence into exactly one `HOLD`, `REDUCE`, or `EXIT` decision with one primary reason, auditable supporting signals, and an exact target quantity.

C4 does **not** execute a SELL. C5 will translate an approved exit quantity into the existing `TradeIntent` -> C1 realistic execution -> C3 accounting path once quote-aware quantity safety is designed. C4 must not create a second execution channel or pretend a USD-notional SELL is quantity-safe when execution price can move.

## Source requirements

The source build order requires configurable:

- hard stop,
- take profit,
- partial take profit,
- trailing stop,
- maximum hold time,
- flow deterioration,
- momentum deterioration,
- wallet-distribution exit,
- liquidity emergency exit,
- global halt exit.

The master design requires:

- exits as first-class decisions,
- `HOLD / REDUCE / EXIT` vocabulary,
- every exit to record one primary reason plus supporting signals,
- exit-policy variants to be evaluated by realized expectancy rather than assumed optimal,
- realistic limited exit liquidity,
- no invented numeric thresholds.

## Architectural boundaries

C4 lives in a new dependency-light package:

```text
python/src/shreks_brain/exits/
  __init__.py
  models.py
  engine.py
```

It may import only stable earlier-domain contracts:

- `DecisionAction` from B8 for `HOLD / REDUCE / EXIT`,
- B2 `FeatureVector`,
- C3 `PaperPosition` / `PaperPositionState`.

It performs no SQLite reads, provider/RPC calls, balance reads, wall-clock reads, random sampling, quote generation, paper fills, or transaction work.

### Why C4 does not build a SELL TradeIntent yet

The current stable `TradeIntent` requests USD notional, while C4 must control **position quantity**. A naive conversion such as `target_quantity * current_price` can oversell if actual SELL execution price is lower than the decision price because C1 derives filled quantity from filled notional / execution price.

C4 therefore outputs the exact target quantity and reduction fraction but stops before intent construction. C5 must solve quote-aware intent translation without weakening C1/C3 quantity integrity. This is a deliberate correctness boundary, not deferred hand-waving.

## Inputs

### C3 authoritative position

C4 consumes one `PaperPosition` and requires it to be `OPEN` for normal exit evaluation.

Authoritative fields used:

- `position_id`,
- `mint`,
- `quantity`,
- `weighted_entry_price_usd`,
- `open_cost_basis_usd`,
- `opened_at_unix_ms`,
- `updated_at_unix_ms`.

C4 never reconstructs quantity or entry price from market data.

### B2 point-in-time features

C4 consumes the unchanged `b2-v1` `FeatureVector` for:

- current price,
- source timestamp / age,
- liquidity,
- five-minute buy fraction,
- buy-pressure acceleration,
- one-minute return,
- five-minute return.

C4 does not use B2 `exit_price_impact_pct` as authoritative full-position exitability because B2 does not carry the notional size covered by that estimate.

### `ExitExecutionContext`

C4 adds only the execution evidence B2 cannot safely express:

```text
as_of_unix_ms
observed_at_unix_ms
route_state
available_exit_notional_usd
expected_exit_price_impact_pct
price_impact_notional_usd
wallet_distribution_detected
global_halt_active
```

`route_state` is one of:

- `AVAILABLE`,
- `UNAVAILABLE`,
- `UNKNOWN`.

Impact percentage and impact notional must be paired. Unknown capacity/impact remains `None`; it is never converted to zero or healthy evidence.

Wallet distribution is optional evidence (`True / False / None`). `None` means no statistically defensible wallet-distribution signal is available. C4 does not fabricate Smart Wallet or holder-identity evidence before Phase D.

## Versioned exit policy

C4 has no production default policy.

`ExitPolicy` contains:

```text
version
required_feature_schema_version
max_market_data_age_ms
max_execution_evidence_age_ms
hard_stop_loss_pct | None
take_profit_levels
trailing_activation_return_pct | None
trailing_stop_drawdown_pct | None
max_hold_seconds | None
flow_exit_max_buy_fraction_m5 | None
flow_exit_max_buy_pressure_acceleration | None
momentum_exit_max_return_1m_pct | None
momentum_exit_max_return_5m_pct | None
min_liquidity_usd | None
max_exit_price_impact_pct | None
min_exit_capacity_fraction | None
wallet_distribution_enabled
```

Optional thresholds disable that rule when `None`. Paired rules must be both present or both absent:

- trailing activation + trailing drawdown,
- flow buy fraction + buy-pressure acceleration,
- momentum 1m + 5m returns.

`wallet_distribution_enabled=False` explicitly disables that signal even if context provides it.

### Take-profit levels

Each `TakeProfitLevel` contains:

```text
name
trigger_return_pct
reduce_fraction_of_current_quantity
```

Rules:

- names unique and non-empty,
- trigger return strictly positive,
- triggers strictly increasing,
- reduction fraction in `(0, 1]`,
- no implicit/default ladder.

A fraction below 1 emits `REDUCE`; a fraction equal to 1 emits `EXIT`.

If price gaps through multiple incomplete levels, only the earliest incomplete triggered level is selected per decision. This preserves an auditable staged ladder and lets C1/C3 confirm actual fills before a later level becomes eligible.

## Stateful trailing / take-profit evidence

Trailing stops require historical high-water state. C4 therefore owns immutable `ExitState`:

```text
policy_version
position_id
mint
initialized_at_unix_ms
last_evaluated_at_unix_ms
high_water_price_usd
high_water_at_unix_ms
completed_take_profit_levels
```

`create_exit_state(position, policy)` initializes high water from the best price evidence already carried by the position (`max(weighted_entry_price, last_mark_price when present)`) without looking into future data.

C5 must initialize this state when a new C3 lifecycle is opened. Initializing later cannot reconstruct a missed historical peak and must not be treated as equivalent research evidence.

Every fresh evaluation returns `next_state`, updating high water only from the current point-in-time price. Policy version is pinned for the lifecycle; silent mid-position exit-policy switching is rejected rather than mixing research treatments.

### Take-profit completion is fill-confirmed

C4 must not mark a take-profit level complete merely because it emitted a `REDUCE` decision. The paper SELL may fail or partially fill.

`acknowledge_exit_fill(state, decision, before_position, after_position)` marks a take-profit level completed only when C3 shows that actual quantity reduction reached the decision's target quantity (within deterministic arithmetic tolerance) or the position fully closed. A partial fill below the target leaves the level incomplete so C5 can continue trying it.

This helper remains pure and consumes only authoritative before/after C3 position snapshots.

## Derived evidence

When fresh price evidence exists:

```text
position_age_seconds = (as_of - opened_at) / 1000
price_return_pct = (current_price / weighted_entry_price - 1) * 100
current_market_value_usd = quantity * current_price
high_water = max(previous_high_water, current_price)
drawdown_from_high_water_pct = (current_price / high_water - 1) * 100
```

A mark or market price is **decision evidence**, not an executable exit quote. Actual proceeds remain unknown until C1 receives a contemporaneous quote.

### Exit capacity

When `available_exit_notional_usd` and current market value are known:

```text
exit_capacity_fraction = min(1, available_exit_notional_usd / current_market_value_usd)
```

Missing capacity remains `None`.

## Deterministic decision precedence

C4 evaluates one primary reason in this fixed order.

### Structural / compatibility gates

1. feature schema mismatch -> `HOLD`
2. position is not OPEN -> `HOLD`
3. state position/mint mismatch -> `HOLD`
4. exit-state policy mismatch -> `HOLD`
5. context/feature `as_of` mismatch -> `HOLD`
6. evaluation before position/state chronology -> `HOLD`

These are explicit non-action decisions, not affirmative claims that holding is economically desirable.

### Price-independent forced exits

7. global halt active -> full `EXIT`
8. configured max hold reached -> full `EXIT`

These may fire even if current market data is stale because they do not require current price. C1 still decides whether a contemporaneous executable SELL route exists.

### Market/execution evidence quality

9. market source after `as_of` -> `HOLD`
10. market source too old -> `HOLD`
11. execution evidence after `as_of` -> `HOLD`
12. execution evidence too old -> `HOLD`
13. current price unavailable/non-positive -> `HOLD`

High-water state is not advanced by unusable market evidence.

### Market-dependent exits

14. route explicitly unavailable -> full `EXIT` (`LIQUIDITY_ROUTE_UNAVAILABLE`)
15. known liquidity at/below configured minimum -> full `EXIT`
16. known size-aware exit impact at/above configured maximum -> full `EXIT`
17. known exit capacity fraction at/below configured minimum -> full `EXIT`
18. hard-stop return at/below `-hard_stop_loss_pct` -> full `EXIT`
19. activated trailing drawdown at/below `-trailing_stop_drawdown_pct` -> full `EXIT`
20. enabled wallet distribution explicitly detected -> full `EXIT`
21. both configured flow-deterioration conditions met -> full `EXIT`
22. both configured momentum-deterioration conditions met -> full `EXIT`
23. earliest incomplete take-profit level reached -> `REDUCE` or `EXIT`
24. otherwise -> `HOLD`

Threshold equality triggers the corresponding exit/reduction.

This order deliberately makes emergency/risk exits outrank profit-taking. A candidate cannot choose a partial take profit while a full-exit emergency is simultaneously proven.

## Supporting signals

Every `ExitAssessment` has:

- exactly one `primary_reason`,
- a non-empty tuple of `ExitFinding`,
- exactly one finding marked `primary=True`, whose code equals `primary_reason`.

After the primary reason is selected, C4 includes other simultaneously proven trigger findings as supporting (`primary=False`) when their evidence is usable. This lets later research ask whether a hard stop also coincided with flow collapse, bad liquidity, or wallet distribution without changing deterministic action precedence.

Data-quality HOLD decisions carry their primary contradiction and do not manufacture supporting triggers from unusable data.

## Output contract

`ExitAssessment` contains:

```text
policy_version
feature_schema_version
position_id
mint
as_of_unix_ms
action
primary_reason
target_reduction_fraction
target_quantity
position_age_seconds
current_price_usd
current_market_value_usd
price_return_pct
drawdown_from_high_water_pct
exit_capacity_fraction
triggered_take_profit_level
next_state
findings
```

Action invariants:

- `HOLD`: target fraction = 0 and target quantity = 0.
- `REDUCE`: target fraction in `(0,1)` and target quantity in `(0, position.quantity)`.
- `EXIT`: target fraction = 1 and target quantity equals current position quantity.

`ExitAssessment` is not a fill, PnL result, or promise that the desired quantity is executable.

## Trigger semantics

### Hard stop

Uses price return versus execution-weighted entry. Entry fees remain in C3 accounting and are not embedded into the hard-stop price metric.

### Take profit / partial take profit

Uses the same price-return metric. Actual after-cost profitability is measured later from C3 realized PnL; a positive price return is not assumed to be profitable after costs.

### Trailing stop

Trailing is active only after the high-water return reaches the configured activation return. Once active, current drawdown from high water at or below the configured negative drawdown triggers full `EXIT`.

### Max hold

Uses local position lifecycle timestamps only. No wall-clock call occurs inside C4.

### Flow deterioration

Triggers only when both configured conditions are known and met:

```text
buy_fraction_m5 <= configured maximum
buy_pressure_acceleration <= configured maximum
```

Missing either value cannot trigger flow deterioration.

### Momentum deterioration

Triggers only when both configured conditions are known and met:

```text
return_1m_pct <= configured maximum
return_5m_pct <= configured maximum
```

Missing either value cannot trigger momentum deterioration.

### Wallet distribution

Triggers only from explicit `wallet_distribution_detected=True` and only when policy enables it. `None` never becomes `False`, `True`, a score, or a fabricated wallet-quality inference.

### Liquidity emergency

Can be proven by any of:

- explicit route unavailable,
- known liquidity below/equal threshold,
- known size-aware impact above/equal threshold,
- known available exit capacity fraction below/equal threshold.

A low impact estimate at an undersized notional is never used as proof that full liquidation is safe. C4 does not require impact-notional coverage to treat **high** impact as bad evidence, because poor impact at even a smaller notional is already adverse. Actual quantity remains governed by C1 evidence.

### Global halt

Always requests full `EXIT`; it is not softened by score, profit, or setup state.

## No production defaults / no profitability claims

C4 ships no threshold values, take-profit ladder, or exit policy instance. All numeric choices remain hypotheses for later point-in-time paper comparison after realistic C1 execution costs and C3 realized accounting.

No C4 threshold is described as profitable, optimal, or calibrated.

## Explicit non-goals

C4 does not add:

- SELL `TradeIntent` construction,
- quote retrieval,
- swap routing,
- fill simulation changes,
- position accounting changes,
- autonomous loop/orchestration,
- persistence/restart state wiring,
- Phase D wallet reconstruction,
- signer/wallet secrets,
- transaction construction/submission,
- live execution.

Those boundaries keep C4 independently testable and prevent exit research from silently changing execution/accounting assumptions.
