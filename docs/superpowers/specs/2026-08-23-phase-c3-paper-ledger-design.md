# Phase C3 Authoritative Paper Ledger Design

## Status

Approved for autonomous implementation under the standing Shreks project instruction.

## Goal

Implement source build-order C3: an authoritative, deterministic, point-in-time paper position/accounting ledger that consumes the exact C1+C2 `TradeIntent` + `PaperExecutionResult` evidence and maintains:

- open and closed position lifecycles;
- token quantity;
- execution-weighted entry price;
- all-in open cost basis;
- realized PnL after incurred explicit costs;
- mark-to-market unrealized PnL;
- accumulated explicit costs;
- simulated cash balance;
- terminal-intent idempotency;
- an append-only execution journal with strategy/policy provenance.

The ledger is the accounting truth used by later C4 exits and C5 autonomous paper operation. It does not choose exits or execute trades.

## Base and scope

Base: verified C1+C2 head `bf613e727240a6eecccefe851b155029cac2398f`.

Extend `shreks_brain.paper` with focused ledger models and a pure reducer:

```text
python/src/shreks_brain/paper/ledger_models.py
python/src/shreks_brain/paper/ledger.py
```

Existing C1 execution models and `execute_paper_intent()` remain unchanged.

C3 has no provider, storage, balance, wall-clock, RNG, exit-policy, signer, transaction, or live-money I/O. Persistence/restart wiring is intentionally deferred to the later autonomous/reconciliation stages; the C3 state is replayable so those stages can persist the same journal without changing accounting formulas.

## Why journal + snapshots

A mutable position dictionary alone would make duplicate booking, failed-attempt expenses, and provenance difficult to audit. SQLite-first accounting would mix domain math with persistence before restart/reconciliation work is scheduled.

C3 therefore keeps two synchronized views:

1. an append-only tuple of terminal execution journal entries; and
2. immutable derived position snapshots.

`PaperLedger` validates that cash, realized PnL, accumulated costs, journal entries, processed intent keys, and position totals reconcile with one another. This turns accounting drift into an immediate invariant failure instead of a later dashboard surprise.

## Public enums

### `PaperPositionState`

Exact order:

```text
OPEN
CLOSED
```

### `PaperLedgerUpdateState`

Exact order:

```text
NOOP
REJECTED
APPLIED
```

### `PaperLedgerReasonCode`

Exact order:

```text
INTENT_MODE_NOT_PAPER
INTENT_RESULT_KEY_MISMATCH
INTENT_RESULT_MINT_MISMATCH
INTENT_RESULT_SIDE_MISMATCH
INTENT_RESULT_NOTIONAL_MISMATCH
EXECUTION_REASON_STATE_MISMATCH
DUPLICATE_TERMINAL_INTENT
EXECUTION_TIME_BEFORE_LEDGER
EXECUTION_DEFERRED_NOOP
INSUFFICIENT_CASH
SELL_WITHOUT_OPEN_POSITION
SELL_QUANTITY_EXCEEDS_POSITION
FAILED_EXECUTION_BOOKED
POSITION_OPENED
POSITION_INCREASED
POSITION_REDUCED
POSITION_CLOSED
MARK_TIME_BEFORE_LEDGER
MARK_POSITION_NOT_FOUND
MARK_MINT_MISMATCH
MARK_POSITION_CLOSED
POSITION_MARKED
```

These are accounting/reducer reasons, separate from C1 `PaperExecutionReasonCode` market/execution reasons.

## Models

### `PaperPositionMark`

Immutable caller-supplied mark evidence:

```python
position_id: str
mint: str
observed_at_unix_ms: int
mark_price_usd: float
```

The mark is a valuation input only. It is not executable quote evidence and carries no claim about exit liquidity, slippage, or future exit cost.

Validation:

- non-empty `position_id` and `mint`;
- non-negative timestamp;
- finite strictly positive mark price.

### `PaperPosition`

Immutable position-lifecycle snapshot:

```python
position_id: str
mint: str
state: PaperPositionState
quantity: float
weighted_entry_price_usd: float
open_cost_basis_usd: float
realized_pnl_usd: float
unrealized_pnl_usd: float | None
accumulated_costs_usd: float
opened_at_unix_ms: int
updated_at_unix_ms: int
closed_at_unix_ms: int | None
last_mark_price_usd: float | None
last_mark_at_unix_ms: int | None
buy_fill_count: int
sell_fill_count: int
```

Invariants:

- identity fields non-empty;
- weighted entry finite and strictly positive;
- realized PnL finite;
- accumulated costs finite and non-negative;
- timestamps non-negative and ordered;
- fill counts are non-negative integers and at least one BUY fill exists;
- `OPEN` requires strictly positive quantity, strictly positive open cost basis, `closed_at_unix_ms is None`;
- `CLOSED` requires quantity and open cost basis equal zero within accounting tolerance, `closed_at_unix_ms` present, and `unrealized_pnl_usd == 0`;
- last mark price/time are both present or both absent;
- an open position may have `unrealized_pnl_usd=None` when no current mark exists;
- if an open mark exists, unrealized PnL must equal `quantity * last_mark_price_usd - open_cost_basis_usd` within tolerance.

`weighted_entry_price_usd` is the execution-price-weighted entry price and deliberately excludes explicit fees. `open_cost_basis_usd` is the all-in remaining acquisition basis and includes allocated BUY-side explicit costs.

### `PaperLedgerEntry`

One immutable terminal execution booking:

```python
sequence: int
intent_idempotency_key: str
position_id: str | None
mint: str
side: TradeSide
execution_state: PaperExecutionState
paper_execution_reason_code: PaperExecutionReasonCode
ledger_reason_code: PaperLedgerReasonCode
strategy_name: str
strategy_version: str
score_policy_version: str
decision_policy_version: str
risk_policy_version: str
paper_policy_version: str
booked_at_unix_ms: int
filled_quantity: float
filled_notional_usd: float
cash_flow_usd: float
explicit_cost_usd: float
realized_pnl_delta_usd: float
```

Only terminal C1 states are journaled:

```text
FAILED
PARTIAL
FILLED
```

`DEFERRED` never creates an entry and never consumes an idempotency key.

Validation:

- `sequence >= 1`;
- all provenance strings non-empty;
- terminal execution state only;
- filled quantity/notional are non-negative and both zero for FAILED;
- PARTIAL/FILLED require strictly positive fill quantity/notional;
- cash flow and realized delta finite;
- explicit cost finite and non-negative;
- position ID is optional only because failed entry attempts can incur cost before any position exists.

### `PaperLedger`

Immutable authoritative accounting snapshot:

```python
starting_cash_usd: float
cash_balance_usd: float
realized_pnl_usd: float
unrealized_pnl_usd: float | None
accumulated_costs_usd: float
as_of_unix_ms: int
positions: tuple[PaperPosition, ...]
entries: tuple[PaperLedgerEntry, ...]
processed_intent_keys: frozenset[str]
```

Validation is intentionally strong:

- starting cash and current cash are finite and non-negative; C3 does not model leverage;
- realized PnL finite;
- unrealized PnL finite when known;
- accumulated costs finite and non-negative;
- position IDs unique;
- at most one OPEN position exists per mint;
- journal sequences are exactly `1..N`;
- journal intent keys are unique;
- `processed_intent_keys` equals exactly the set of terminal journal intent keys;
- `cash_balance_usd == starting_cash_usd + sum(entry.cash_flow_usd)` within tolerance;
- ledger realized PnL equals `sum(entry.realized_pnl_delta_usd)`;
- accumulated costs equal `sum(entry.explicit_cost_usd)`;
- each position's realized PnL equals the sum of realized deltas for entries linked to that position;
- each position's accumulated costs equal the sum of explicit costs for entries linked to that position;
- `as_of_unix_ms` is not earlier than any journal booking or position update;
- aggregate unrealized PnL is `0` when there are no OPEN positions, `None` when any OPEN position lacks a current mark, otherwise the sum of all OPEN-position unrealized PnL.

### `PaperLedgerFinding`

```python
code: PaperLedgerReasonCode
message: str
```

Both are required and validated.

### `PaperLedgerUpdate`

Immutable reducer result:

```python
state: PaperLedgerUpdateState
ledger: PaperLedger
position_id: str | None
cash_delta_usd: float
realized_pnl_delta_usd: float
cost_delta_usd: float
findings: tuple[PaperLedgerFinding, ...]
```

Exactly one finding is required.

For `NOOP` and `REJECTED`:

- all deltas are zero;
- returned ledger equals the input ledger.

For `APPLIED`:

- deltas must match the state transition;
- a mark-only update has zero economic deltas but still advances/revalues ledger state.

## Public functions

### `create_paper_ledger()`

```python
def create_paper_ledger(
    starting_cash_usd: float,
    as_of_unix_ms: int,
) -> PaperLedger:
    ...
```

Returns an empty self-reconciling ledger:

- cash equals starting cash;
- realized PnL = 0;
- unrealized PnL = 0;
- accumulated costs = 0;
- no positions/journal entries/processed keys.

No production capital amount is supplied by the package.

### `apply_paper_execution()`

```python
def apply_paper_execution(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
) -> PaperLedgerUpdate:
    ...
```

Pure and deterministic.

## Defensive linkage and precedence

Fixed first-reason precedence:

1. intent must be `RuntimeMode.PAPER`;
2. intent/result idempotency keys match;
3. mint matches;
4. side matches;
5. requested notional matches within tolerance;
6. C1 execution state/finding pairing is internally consistent;
7. already-processed terminal key -> `DUPLICATE_TERMINAL_INTENT`;
8. execution evaluation timestamp earlier than ledger `as_of` -> `EXECUTION_TIME_BEFORE_LEDGER`;
9. `DEFERRED` -> `NOOP / EXECUTION_DEFERRED_NOOP`;
10. apply terminal accounting rules.

Valid C1 state/reason pairing for C3:

- DEFERRED: `LATENCY_PENDING`, `QUOTE_PENDING`, or `QUOTE_BEFORE_LATENCY`;
- PARTIAL: exactly `FILL_PARTIAL`;
- FILLED: exactly `FILL_COMPLETE`;
- FAILED: any non-deferred, non-fill C1 reason.

Contradictory pairings reject with `EXECUTION_REASON_STATE_MISMATCH` before accounting mutates.

## Terminal FAILED accounting

FAILED is terminal and consumes the intent idempotency key.

- C1 zero-cost failures append a journal entry with zero cash/cost/PnL delta.
- `SIMULATED_SUBMISSION_FAILED` preserves its negative network-fee cash flow and explicit cost.
- Failed execution with an economic cost reduces ledger realized PnL by the same amount because no asset was acquired or disposed.
- If an OPEN position already exists for the mint, a failed attempt is linked to that position so its realized PnL/accumulated costs preserve the expense. If no OPEN position exists, the expense remains portfolio-level with `position_id=None`.
- If applying the failed-attempt cash delta would make simulated cash negative, reject with `INSUFFICIENT_CASH` rather than create an impossible ledger state.

Successful terminal entries are appended after all validation passes.

## BUY fill accounting

A C1 PARTIAL or FILLED BUY consumes cash exactly from `execution.net_cash_flow_usd`.

If cash would become negative, reject `INSUFFICIENT_CASH`.

### New lifecycle

When no OPEN position exists for the mint:

- create a deterministic `position_id` from a versioned SHA-256 payload containing mint + first BUY intent idempotency key;
- quantity = fill quantity;
- weighted entry = fill execution price;
- open cost basis = filled notional + explicit cost;
- realized PnL = 0;
- unrealized PnL = `None` until marked;
- accumulated costs = BUY explicit cost;
- state = OPEN;
- ledger reason = `POSITION_OPENED`.

A previously CLOSED position for the same mint remains historical. A later BUY creates a new lifecycle with a new position ID rather than mutating closed history.

### Increase existing lifecycle

For an already-OPEN position:

```python
old_gross_entry_notional = old_quantity * old_weighted_entry_price
new_weighted_entry = (
    old_gross_entry_notional + fill.filled_notional_usd
) / (old_quantity + fill.quantity)
```

Then:

- quantity increases by fill quantity;
- open cost basis increases by `filled_notional + BUY explicit cost`;
- accumulated costs increase by explicit cost;
- realized PnL unchanged;
- prior mark/unrealized value is cleared because quantity/cost basis changed;
- BUY fill count increments;
- ledger reason = `POSITION_INCREASED`.

Strategy strength never changes accounting math.

## SELL fill accounting

A terminal SELL requires exactly one OPEN position for the mint.

No OPEN position -> `SELL_WITHOUT_OPEN_POSITION`.

If C1 fill quantity exceeds open quantity beyond accounting tolerance -> `SELL_QUANTITY_EXCEEDS_POSITION` and no accounting mutation occurs.

For valid SELL:

```python
sell_fraction = sold_quantity / old_quantity
released_cost_basis = old_open_cost_basis * sell_fraction
realized_pnl_delta = execution.net_cash_flow_usd - released_cost_basis
```

When sold quantity is within tolerance of the entire position, use an exact fraction of `1.0` and close the position.

### Partial reduction

- quantity decreases;
- weighted entry stays unchanged;
- open cost basis decreases by released cost basis;
- position realized PnL increases by realized delta;
- accumulated costs increase by SELL explicit cost;
- prior mark/unrealized value is cleared because quantity changed;
- SELL fill count increments;
- state stays OPEN;
- ledger reason = `POSITION_REDUCED`.

### Full close

- quantity = 0;
- open cost basis = 0;
- weighted entry is preserved as historical entry evidence;
- realized PnL includes all allocated entry costs plus all exit costs exactly once;
- unrealized PnL = 0;
- state = CLOSED;
- `closed_at_unix_ms` set;
- ledger reason = `POSITION_CLOSED`.

The closed position remains in ledger history and can never be marked or reduced again.

## Explicit-cost treatment

C1 already places adverse/favorable slippage into execution price and signed audit fields. C3 never subtracts slippage a second time.

Position economics therefore use:

```text
BUY open cost basis += filled notional + explicit swap/network cost
SELL realized delta = net sale cash flow - released all-in open cost basis
```

This counts each incurred explicit cost once.

`accumulated_costs_usd` is an audit total; consumers must not subtract it again from `realized_pnl_usd`.

## Failed-attempt costs

A post-submission failed paper attempt can incur network cost without a fill. C3 books that cost as:

```text
cash delta = negative network cost
realized PnL delta = same negative amount
accumulated cost delta = network cost
```

This prevents failed routing/submission activity from disappearing from paper expectancy.

## Mark-to-market unrealized PnL

### `mark_paper_position()`

```python
def mark_paper_position(
    ledger: PaperLedger,
    mark: PaperPositionMark,
) -> PaperLedgerUpdate:
    ...
```

Fixed precedence:

1. mark timestamp earlier than ledger `as_of` -> `MARK_TIME_BEFORE_LEDGER`;
2. position ID missing -> `MARK_POSITION_NOT_FOUND`;
3. mint mismatch -> `MARK_MINT_MISMATCH`;
4. position CLOSED -> `MARK_POSITION_CLOSED`;
5. apply mark -> `POSITION_MARKED`.

Mark equality with ledger `as_of` is valid.

For an OPEN position:

```python
unrealized_pnl_usd = quantity * mark_price_usd - open_cost_basis_usd
```

This includes already-incurred BUY costs through open cost basis. It deliberately does **not** subtract hypothetical future SELL fees, slippage, or liquidity impact because the mark is not executable quote evidence. C4/C1 SELL execution must determine what can actually be realized.

Marking changes no cash, realized PnL, accumulated cost, quantity, or journal entry. It updates the position mark fields, position/ledger timestamp, and aggregate unrealized PnL.

If any OPEN position is unmarked, ledger aggregate unrealized PnL remains `None` instead of pretending an unknown position is worth zero.

## Chronology and point-in-time integrity

The ledger is monotonic by `as_of_unix_ms`.

- terminal execution booking uses `execution.evaluated_at_unix_ms` as the accounting booking timestamp;
- marks use their supplied observation timestamp;
- no reducer action may move the ledger backward in time;
- DEFERRED execution is a NOOP and does not advance ledger time or consume idempotency.

C1 fill/quote timestamps remain preserved inside the C1 execution result; C3 does not rewrite them.

## Journal provenance

Every terminal journal entry preserves the intent/execution versions needed to audit the decision path later:

- strategy name/version;
- score policy version;
- decision policy version;
- risk policy version;
- paper fill policy version;
- C1 execution reason;
- C3 accounting reason.

C3 does not claim this is the final durable trade-history schema. C5/C6 can persist/replay these immutable entries and add exit/reconciliation records without changing C3 math.

## Public API additions

`shreks_brain.paper` keeps all existing C1 exports and adds exactly:

```python
PaperLedger
PaperLedgerEntry
PaperLedgerFinding
PaperLedgerReasonCode
PaperLedgerUpdate
PaperLedgerUpdateState
PaperPosition
PaperPositionMark
PaperPositionState
apply_paper_execution
create_paper_ledger
mark_paper_position
```

No default ledger capital, no default mark source, and no exit/live authority are exported.

## Determinism

Equal ledger + intent + execution inputs produce equal updates.

Equal ledger + mark inputs produce equal updates.

Position IDs use SHA-256 over a canonical versioned payload, never Python `hash()` and never randomness.

Positions and entries preserve deterministic tuple order. New position lifecycles append; existing snapshots are replaced in place.

## Rejection semantics

C3 rejects contradictory accounting evidence rather than repairing it silently.

Examples:

- intent/result identity mismatch;
- terminal duplicate booking;
- time reversal;
- BUY that would create negative simulated cash;
- SELL without an OPEN position;
- SELL quantity beyond authoritative holdings.

A rejected update returns the exact input ledger with zero deltas and one stable finding.

## Non-goals

C3 does not add:

- stop loss;
- take profit;
- trailing stop;
- max hold;
- emergency/liquidity exit decision;
- autonomous paper loop;
- SQLite persistence/restart wiring;
- provider/RPC calls;
- execution quote generation;
- wallet/signing;
- transaction construction/submission;
- live trading.

Those remain C4+ responsibilities.

## Testing strategy

Strict RED -> GREEN TDD.

Tests must prove at minimum:

- exact enums/model invariants and frozen dataclasses;
- self-reconciling empty ledger;
- intent/result linkage failures and deterministic precedence;
- DEFERRED no-op does not consume key or advance time;
- zero-cost and post-submission FAILED booking;
- duplicate terminal protection;
- insufficient cash rejection;
- first BUY opens lifecycle;
- multiple BUYs produce correct weighted entry and all-in open cost basis;
- BUY costs are not immediately realized;
- partial SELL releases proportional all-in basis and realizes net PnL after exit cost;
- final SELL closes lifecycle exactly;
- oversell and sell-without-position reject;
- failed exit network costs remain visible in position/portfolio realized PnL;
- later BUY after close creates a new position ID and preserves closed history;
- marks compute unrealized after incurred entry costs;
- multiple open positions make aggregate unrealized `None` until all are marked;
- stale/wrong/closed marks reject;
- journal cash/cost/realized equations reconcile after wins, losses, partial exits, and failed fills;
- equal inputs are deterministic;
- prior C1/B9 APIs remain unchanged;
- no position model contains signer/transaction/live authority.

## Completion gate

C3 is complete only when:

1. models, reducer, mark logic, and stable exports pass strict TDD;
2. full Rust/Python/workspace/repository-safety CI is green on the exact immutable final head;
3. the final C1->C3 diff contains only intended C3 files;
4. README explicitly distinguishes mark-to-market PnL from realistically realizable exit PnL;
5. PR remains draft/unmerged;
6. no C4 exit policy or live execution has been added.
