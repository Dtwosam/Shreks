# Phase C3 Authoritative Paper Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an immutable, self-reconciling paper accounting ledger that books terminal C1 execution evidence into authoritative position lifecycles, cash, costs, realized PnL, and point-in-time unrealized PnL.

**Architecture:** Extend `shreks_brain.paper` with `ledger_models.py` for frozen accounting state and `ledger.py` for pure reducers. The ledger stores an append-only terminal execution journal plus derived immutable position snapshots; journal equations must reconcile cash, realized PnL, accumulated costs, processed intent keys, and per-position totals on every construction. Persistence, exit decisions, and autonomous looping remain later phases.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, SHA-256, `math.isclose`, pytest, existing GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-c3-paper-ledger-design.md`

## Global Constraints

- Base is verified C1+C2 head `bf613e727240a6eecccefe851b155029cac2398f`.
- Consume exact B9 `TradeIntent` plus exact C1 `PaperExecutionResult`; do not invent a second execution interface.
- C3 performs no provider/storage/balance/wall-clock/RNG reads.
- No leverage: applying any terminal cash flow that would make simulated cash negative is rejected.
- DEFERRED execution is a NOOP: no journal entry, no processed key, no timestamp advance.
- FAILED/PARTIAL/FILLED are terminal and may be booked exactly once.
- Weighted entry excludes explicit fees; all-in open cost basis includes incurred BUY explicit costs.
- SELL realized PnL uses net sale cash flow minus proportional all-in open cost basis.
- Explicit costs are audit totals and must never be subtracted a second time from realized PnL.
- Unrealized PnL is mark-to-market after incurred entry costs but before hypothetical future exit costs; it is not executable-exit PnL.
- At most one OPEN position lifecycle per mint; later BUY after close creates a new lifecycle.
- No production capital default, exit policy, persistence/restart wiring, signer, transaction, or live-money path.

---

### Task 1: Immutable self-reconciling ledger domain

**Files:**
- Create: `python/src/shreks_brain/paper/ledger_models.py`
- Test: `python/tests/test_paper_ledger_models.py`

**Interfaces:**
- Consumes: `TradeSide`, C1 `PaperExecutionState`, C1 `PaperExecutionReasonCode`.
- Produces: `PaperPositionState`, `PaperLedgerUpdateState`, `PaperLedgerReasonCode`, `PaperPositionMark`, `PaperPosition`, `PaperLedgerEntry`, `PaperLedger`, `PaperLedgerFinding`, `PaperLedgerUpdate`.

- [ ] **Step 1: Write the failing exact enum/model test**

Pin enum orders from the spec exactly:

```python
assert tuple(item.value for item in PaperPositionState) == ("OPEN", "CLOSED")
assert tuple(item.value for item in PaperLedgerUpdateState) == (
    "NOOP", "REJECTED", "APPLIED"
)
assert tuple(item.value for item in PaperLedgerReasonCode) == (
    "INTENT_MODE_NOT_PAPER",
    "INTENT_RESULT_KEY_MISMATCH",
    "INTENT_RESULT_MINT_MISMATCH",
    "INTENT_RESULT_SIDE_MISMATCH",
    "INTENT_RESULT_NOTIONAL_MISMATCH",
    "EXECUTION_REASON_STATE_MISMATCH",
    "DUPLICATE_TERMINAL_INTENT",
    "EXECUTION_TIME_BEFORE_LEDGER",
    "EXECUTION_DEFERRED_NOOP",
    "INSUFFICIENT_CASH",
    "SELL_WITHOUT_OPEN_POSITION",
    "SELL_QUANTITY_EXCEEDS_POSITION",
    "FAILED_EXECUTION_BOOKED",
    "POSITION_OPENED",
    "POSITION_INCREASED",
    "POSITION_REDUCED",
    "POSITION_CLOSED",
    "MARK_TIME_BEFORE_LEDGER",
    "MARK_POSITION_NOT_FOUND",
    "MARK_MINT_MISMATCH",
    "MARK_POSITION_CLOSED",
    "POSITION_MARKED",
)
```

Prove all dataclasses are frozen and validate non-empty identities, finite numeric values, non-negative timestamps/counts, and exact OPEN/CLOSED lifecycle invariants.

- [ ] **Step 2: Pin one internally reconciled BUY snapshot**

Use a canonical execution-price `$1.01` BUY of `$500` with `$1.51` explicit cost:

```python
quantity = 500.0 / 1.01
position = PaperPosition(
    position_id="position-1",
    mint="Mint111",
    state=PaperPositionState.OPEN,
    quantity=quantity,
    weighted_entry_price_usd=1.01,
    open_cost_basis_usd=501.51,
    realized_pnl_usd=0.0,
    unrealized_pnl_usd=None,
    accumulated_costs_usd=1.51,
    opened_at_unix_ms=1_000_500,
    updated_at_unix_ms=1_000_500,
    closed_at_unix_ms=None,
    last_mark_price_usd=None,
    last_mark_at_unix_ms=None,
    buy_fill_count=1,
    sell_fill_count=0,
)
entry = PaperLedgerEntry(
    sequence=1,
    intent_idempotency_key="intent-1",
    position_id="position-1",
    mint="Mint111",
    side=TradeSide.BUY,
    execution_state=PaperExecutionState.FILLED,
    paper_execution_reason_code=PaperExecutionReasonCode.FILL_COMPLETE,
    ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
    strategy_name="fresh_launch_continuation",
    strategy_version="fresh-test",
    score_policy_version="score-test",
    decision_policy_version="decision-test",
    risk_policy_version="risk-test",
    paper_policy_version="paper-test",
    booked_at_unix_ms=1_000_500,
    filled_quantity=quantity,
    filled_notional_usd=500.0,
    cash_flow_usd=-501.51,
    explicit_cost_usd=1.51,
    realized_pnl_delta_usd=0.0,
)
ledger = PaperLedger(
    starting_cash_usd=1_000.0,
    cash_balance_usd=498.49,
    realized_pnl_usd=0.0,
    unrealized_pnl_usd=None,
    accumulated_costs_usd=1.51,
    as_of_unix_ms=1_000_500,
    positions=(position,),
    entries=(entry,),
    processed_intent_keys=frozenset({"intent-1"}),
)
```

Prove construction succeeds.

- [ ] **Step 3: Pin reconciliation failures**

Independently corrupt and reject:

- cash balance equation;
- aggregate realized PnL equation;
- accumulated cost equation;
- duplicate position ID;
- two OPEN positions for one mint;
- non-contiguous journal sequence;
- duplicate journal intent key;
- processed-key set mismatch;
- position realized PnL not equal linked entry realized deltas;
- position accumulated costs not equal linked entry explicit costs;
- ledger timestamp earlier than entry/position;
- aggregate unrealized incorrectly set to zero while an OPEN position is unmarked.

Also prove an empty ledger snapshot with no open positions may have unrealized PnL exactly zero.

- [ ] **Step 4: Pin mark and update model invariants**

`PaperPositionMark` requires positive finite price and valid identity/time.

`PaperLedgerUpdate` requires exactly one `PaperLedgerFinding`.

For NOOP/REJECTED prove all deltas are zero. For APPLIED allow economic deltas or zero-delta mark application.

- [ ] **Step 5: Verify RED**

Commit only `test_paper_ledger_models.py`, open stacked draft PR, and require Python CI to fail only because `shreks_brain.paper.ledger_models` is absent. Existing Rust/workspace/repository-safety checks remain green.

- [ ] **Step 6: Implement minimal models**

Create `ledger_models.py` exactly from the design. Use accounting tolerance:

```python
rel_tol = 1e-12
abs_tol = 1e-9
```

Do not add reducers or persistence.

- [ ] **Step 7: Verify GREEN**

Run full CI and require Rust, Python, workspace metadata, and repository safety all green.

- [ ] **Step 8: Record evidence**

Record Task-1 RED/GREEN SHA and CI IDs in the later verification record/PR metadata.

---

### Task 2: Terminal execution booking and position cost basis

**Files:**
- Create: `python/src/shreks_brain/paper/ledger.py`
- Test: `python/tests/test_paper_ledger.py`

**Interfaces:**
- Produces:

```python
def create_paper_ledger(starting_cash_usd: float, as_of_unix_ms: int) -> PaperLedger:
    ...


def apply_paper_execution(
    ledger: PaperLedger,
    intent: TradeIntent,
    execution: PaperExecutionResult,
) -> PaperLedgerUpdate:
    ...
```

- [ ] **Step 1: Write canonical helpers using the real C1 simulator**

Tests must create C1 `TradeIntent`, `PaperFillPolicy`, `PaperQuote`, `PaperExecutionContext`, then call real `execute_paper_intent()` to generate execution evidence. Do not mock fill economics.

Use simple exact-price cases where helpful (`reference_price == execution_price == 1.0`) so flat-price PnL isolates fees.

- [ ] **Step 2: Pin empty ledger creation**

```python
ledger = create_paper_ledger(1_000.0, 1_000_000)
```

Assert:

```text
starting cash = cash = 1000
realized = 0
unrealized = 0
costs = 0
positions/entries/processed = empty
```

Reject negative/non-finite starting cash and invalid timestamp. No package default capital exists.

- [ ] **Step 3: Pin intent/result linkage and reason-state precedence**

Pass alternate intents against a real execution result and pin first reasons for:

```text
INTENT_MODE_NOT_PAPER
INTENT_RESULT_KEY_MISMATCH
INTENT_RESULT_MINT_MISMATCH
INTENT_RESULT_SIDE_MISMATCH
INTENT_RESULT_NOTIONAL_MISMATCH
EXECUTION_REASON_STATE_MISMATCH
```

Construct one contradictory C1 FILLED result carrying a non-fill finding to prove authoritative accounting rejects it instead of repairing it.

Every rejection returns the exact input ledger and zero deltas.

- [ ] **Step 4: Pin duplicate/time/deferred behavior**

- applying the same terminal key twice -> `DUPLICATE_TERMINAL_INTENT`;
- terminal execution evaluated before ledger `as_of` -> `EXECUTION_TIME_BEFORE_LEDGER`;
- C1 DEFERRED -> `NOOP / EXECUTION_DEFERRED_NOOP`;
- DEFERRED does not advance time, append journal, or consume idempotency;
- duplicate terminal key wins before time reversal on a replayed old result.

- [ ] **Step 5: Pin terminal FAILED accounting**

Route-unavailable zero-cost FAILED:

- appends one FAILED journal entry;
- consumes key;
- cash/realized/cost unchanged;
- reason `FAILED_EXECUTION_BOOKED`.

Failed-after-submission with `$0.02` network fee:

```text
cash delta = -0.02
realized PnL delta = -0.02
cost delta = +0.02
```

No position exists for a failed opening attempt.

With an existing open position for the mint, the failed-attempt entry links to that position and updates its realized PnL and accumulated costs without changing quantity/open cost basis.

- [ ] **Step 6: Pin general nonnegative-cash guard**

Prove any terminal result whose `cash_balance + execution.net_cash_flow_usd < 0` rejects `INSUFFICIENT_CASH`, including:

- a BUY fill larger than available cash;
- a failed-after-submission fee larger than cash;
- a pathological tiny SELL whose explicit costs make net sale cash flow negative beyond available cash.

Equality at zero remaining cash passes.

- [ ] **Step 7: Pin first BUY lifecycle**

For a flat-price `$500` BUY with 30bps swap fee and `$0.01` network fee:

- deterministic position ID is equal across equal inputs;
- quantity equals C1 fill quantity;
- weighted entry equals execution price and excludes fees;
- open cost basis equals filled notional + `$1.51` explicit cost;
- position realized PnL remains zero;
- ledger cash decreases by C1 net cash flow;
- accumulated cost increases by `$1.51`;
- ledger aggregate unrealized becomes `None` until mark;
- journal preserves strategy/score/decision/risk/paper policy versions;
- reason `POSITION_OPENED`.

- [ ] **Step 8: Pin multiple BUY weighted entry**

Apply a second BUY on the same OPEN mint with a different intent key and execution price. Assert:

```python
new_weighted = (
    old_quantity * old_weighted_entry
    + second_fill.filled_notional_usd
) / (old_quantity + second_fill.quantity)
```

Open cost basis adds second filled notional + second explicit cost. Costs accumulate. Realized PnL remains unchanged. Previous mark fields/unrealized are cleared. Position ID is unchanged. Reason `POSITION_INCREASED`.

- [ ] **Step 9: Pin SELL guards**

- valid SELL with no open position -> `SELL_WITHOUT_OPEN_POSITION`;
- SELL fill quantity exceeding holdings beyond tolerance -> `SELL_QUANTITY_EXCEEDS_POSITION`;
- both reject with unchanged ledger and unconsumed key.

- [ ] **Step 10: Pin partial SELL all-in basis release**

At flat price, buy `$500`, then sell `$250`.

Compute:

```python
sell_fraction = sold_quantity / old_quantity
released_basis = old_open_cost_basis * sell_fraction
realized_delta = sell_result.net_cash_flow_usd - released_basis
```

Assert remaining quantity/basis, unchanged weighted entry, realized delta, accumulated SELL cost, cleared mark, sell-fill count, cash delta, and `POSITION_REDUCED`.

At a flat market price, realized loss must equal the proportionally allocated entry cost plus current exit explicit cost; costs must not be subtracted again.

- [ ] **Step 11: Pin full close**

Sell all remaining quantity within tolerance. Assert:

```text
quantity = 0
open cost basis = 0
state = CLOSED
closed_at set
unrealized = 0
weighted entry preserved
```

At a flat price after two half exits, cumulative realized loss equals total incurred explicit costs exactly once. Reason `POSITION_CLOSED`.

- [ ] **Step 12: Pin later re-entry creates a new lifecycle**

After close, apply a new BUY with new intent key. Closed history remains unchanged and a second OPEN `PaperPosition` is appended with a different deterministic position ID.

- [ ] **Step 13: Pin journal/ledger reconciliation after mixed outcomes**

Run a sequence containing:

```text
failed entry fee
successful buy
failed exit fee
partial sell
final sell
new position buy
```

Assert:

```python
ledger.cash_balance_usd == ledger.starting_cash_usd + sum(e.cash_flow_usd for e in ledger.entries)
ledger.realized_pnl_usd == sum(e.realized_pnl_delta_usd for e in ledger.entries)
ledger.accumulated_costs_usd == sum(e.explicit_cost_usd for e in ledger.entries)
ledger.processed_intent_keys == frozenset(e.intent_idempotency_key for e in ledger.entries)
```

- [ ] **Step 14: Verify RED**

Commit only `test_paper_ledger.py`; full CI must fail Python only because `shreks_brain.paper.ledger` / reducer functions are absent.

- [ ] **Step 15: Implement minimal reducer**

Create `ledger.py` with pure helpers for:

```text
position lookup/replacement
position-id SHA-256
state/finding consistency
ledger entry append
aggregate unrealized recomputation
NOOP/REJECTED/APPLIED update construction
```

Fixed execution precedence follows the design. Use no hidden policy or I/O.

- [ ] **Step 16: Verify GREEN**

Run full repository CI and require all jobs green.

- [ ] **Step 17: Record evidence**

Record exact Task-2 RED/GREEN SHA and CI IDs.

---

### Task 3: Mark-to-market PnL, stable API, docs, and immutable seal

**Files:**
- Modify: `python/src/shreks_brain/paper/ledger.py`
- Modify: `python/src/shreks_brain/paper/__init__.py`
- Test: `python/tests/test_paper_ledger_marks.py`
- Test: `python/tests/test_paper_ledger_public_api.py`
- Modify: `README.md`
- Modify: this plan only for the final non-self-referential verification record

**Interfaces:**

```python
def mark_paper_position(
    ledger: PaperLedger,
    mark: PaperPositionMark,
) -> PaperLedgerUpdate:
    ...
```

`shreks_brain.paper` keeps every C1 export and adds exactly:

```text
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

- [ ] **Step 1: Write failing mark behavior tests**

Open one flat-price position and mark it above/below entry. Assert:

```python
unrealized_pnl_usd == quantity * mark_price_usd - open_cost_basis_usd
```

This must include already-incurred BUY costs through cost basis.

Pin first reasons for:

```text
MARK_TIME_BEFORE_LEDGER
MARK_POSITION_NOT_FOUND
MARK_MINT_MISMATCH
MARK_POSITION_CLOSED
POSITION_MARKED
```

Mark equality with ledger `as_of` passes. Rejected marks return exact input ledger and zero deltas.

- [ ] **Step 2: Pin aggregate unrealized semantics**

With two OPEN positions:

- before marks -> ledger unrealized `None`;
- after marking only one -> still `None`;
- after marking both -> exact sum;
- after a fill changes one position -> that position mark is cleared and aggregate returns to `None`;
- after all positions close -> aggregate unrealized exactly zero.

Marking changes no cash, realized PnL, explicit costs, execution journal, or processed keys.

- [ ] **Step 3: Verify mark RED**

Commit mark tests. Full CI must fail Python because `mark_paper_position` is absent.

- [ ] **Step 4: Implement mark reducer**

Add only `mark_paper_position()` plus focused helper reuse. Do not add executable-exit estimates, hypothetical future fees, or C4 rules.

- [ ] **Step 5: Verify mark GREEN**

Run full CI and require all jobs green.

- [ ] **Step 6: Write failing public API regression test**

Import all twelve C3 additions from `shreks_brain.paper`, plus representative pre-C3 C1 exports and earlier runtime/risk interfaces. Prove reducer functions are callable and a canonical entry+mark produces typed ledger/update objects.

Inspect public ledger/position models and assert no signer, transaction, wallet secret, exit-rule, or live-execution authority exists.

- [ ] **Step 7: Verify public API RED**

Full CI must fail Python only because C3 package-level exports are absent.

- [ ] **Step 8: Export stable API**

Modify `paper/__init__.py` to retain all C1 exports and add exactly the twelve C3 symbols. Do not export private accounting helpers.

- [ ] **Step 9: Verify package GREEN**

Run full CI and require all jobs green.

- [ ] **Step 10: Document C3 accounting semantics**

README must document:

- append-only terminal journal + immutable position snapshots;
- weighted entry excludes fees;
- open cost basis includes incurred BUY fees;
- realized PnL is net of allocated entry basis and exit costs exactly once;
- failed post-submission network fees remain realized expenses;
- mark-to-market unrealized includes incurred entry costs but excludes hypothetical future exit costs/liquidity and therefore is not guaranteed realizable PnL;
- closed position history remains immutable and re-entry creates a new lifecycle;
- C3 remains pure/replayable with persistence, exits, and live trading still absent.

- [ ] **Step 11: Replace this plan with final verification record**

Before final CI, replace the tracked checklist with a concise completed record containing predecessor TDD SHAs/runs and architectural facts. Do not write the final branch SHA/run into a tracked file.

- [ ] **Step 12: Freeze and verify final head**

After the verification-record commit, make no further branch writes. Run fresh full CI and require Rust, Python, workspace metadata, and repository safety all green on that exact head.

- [ ] **Step 13: Audit C1 -> C3 diff**

Expected intended files only:

```text
README.md
docs/superpowers/plans/2026-08-23-phase-c3-paper-ledger.md
docs/superpowers/specs/2026-08-23-phase-c3-paper-ledger-design.md
python/src/shreks_brain/paper/__init__.py
python/src/shreks_brain/paper/ledger.py
python/src/shreks_brain/paper/ledger_models.py
python/tests/test_paper_ledger.py
python/tests/test_paper_ledger_marks.py
python/tests/test_paper_ledger_models.py
python/tests/test_paper_ledger_public_api.py
```

No C1 execution math, prior brain layer, Rust/storage/provider, C4 exit, signer, or live-execution file may change.

- [ ] **Step 14: Seal PR metadata only**

Update the draft PR with immutable final C3 head/run, full TDD evidence, and exact diff audit. Preserve draft/unmerged state and do not mutate the branch afterward.
