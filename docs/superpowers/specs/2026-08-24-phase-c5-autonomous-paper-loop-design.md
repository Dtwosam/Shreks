# Phase C5 Autonomous Paper Loop Design

## Goal

Implement the source build-order C5 Autonomous Loop as a deterministic, in-memory Python orchestration layer that repeatedly reuses the already-sealed Shreks decision path:

`observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record`

C5 makes paper mode operationally autonomous without creating a second strategy, risk, execution, accounting, or exit path. It coordinates the existing B2/B3-B5/B6/B7/B8/B9/C1/C3/C4 contracts and returns complete immutable cycle evidence for later C6 persistence/restart/accounting validation.

C5 does **not** enable live money.

## Source requirements

The build order requires C5 to operate unattended using:

```text
observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record
```

The master source of truth additionally requires one decision path, realistic paper execution, complete position lifecycles, auditability, fail-closed evidence handling, and no live execution before proof.

## Architectural boundary

C5 lives in:

```text
python/src/shreks_brain/paper_loop/
  __init__.py
  models.py
  engine.py
```

It is orchestration only. It calls stable earlier-domain functions unchanged:

```python
assess_fresh_launch(...)
assess_graduation_breakout(...)
assess_first_pullback(...)
score_candidate(...)
decide_entry(...)
assess_entry_risk(...)
execute_paper_intent(...)
apply_paper_execution(...)
mark_paper_position(...)
create_exit_state(...)
assess_exit(...)
acknowledge_exit_fill(...)
```

C5 performs no provider/RPC/storage reads and does not reimplement calculations owned by those layers.

## What "observe" means in C5

Rust/A-phase ingestion and B1/B2 feature construction already exist. C5 therefore starts from caller-supplied, point-in-time B2 `FeatureVector` evidence plus the structural context required by one implemented setup family and a contemporaneous B6 regime assessment.

C5 does not duplicate raw observation ingestion, safety calculation, feature engineering, or provider adapters.

## Supported setup families

C5-v1 supports exactly:

1. Fresh Launch Continuation,
2. Graduation/Breakout,
3. First Pullback.

Smart Wallet Cluster stays absent until Phase D wallet intelligence exists.

## Setup input wrappers

C5 avoids an optional-field bag by using one immutable setup wrapper:

```python
@dataclass(frozen=True, slots=True)
class FreshLaunchSetupInput:
    policy: FreshLaunchPolicy

@dataclass(frozen=True, slots=True)
class GraduationBreakoutSetupInput:
    context: GraduationContext | None
    policy: GraduationBreakoutPolicy

@dataclass(frozen=True, slots=True)
class FirstPullbackSetupInput:
    context: PullbackContext | None
    policy: FirstPullbackPolicy
```

`PaperEntryCandidate.setup` is their union. C5 dispatches only to the matching existing setup evaluator.

## Entry candidate contract

One candidate contains:

```text
mint
features
regime
setup
score_policy
decision_policy
risk_context
risk_policy
exit_policy
```

`exit_policy` is supplied before entry so C5 can initialize C4 state immediately after a real C3 BUY opens a new lifecycle. Delayed initialization would lose high-water evidence.

Candidate feature/regime/risk timestamps must refer to the cycle timestamp. Existing engines remain authoritative for deeper compatibility rules.

## Deterministic candidate ordering and uniqueness

`PaperCycleInput.entry_candidates` is an ordered tuple. Its order is the deterministic execution priority supplied to C5.

Candidate mints must be unique inside a cycle. The repository has no approved cross-setup arbitration rule for one mint satisfying multiple setup families, so C5 does not invent one.

## One new entry attempt per cycle

C5-v1 permits at most one BUY intent/execution attempt per cycle.

This is a correctness invariant, not a trading threshold. B9 `RiskContext` contains point-in-time portfolio capacity. Executing several entries from risk contexts all captured before the first fill could reuse stale capital/risk capacity.

C5 therefore computes setup/score/decision in order, calls risk only while the slot is unused, and the first B9-approved intent consumes the slot. A pending BUY retry also consumes the slot for that cycle even if it terminates failed.

A future version may widen this only when authoritative portfolio risk context can be refreshed after each terminal booking.

## No same-mint pyramiding in C5-v1

C3 can technically increase a position, but no approved rule defines how an add should alter C4 weighted-entry/high-water/trailing/take-profit treatment. C5-v1 therefore does not submit a new BUY for a mint that already has an OPEN C3 position.

## Pinned run policies

One autonomous state pins:

- one `PaperLoopPolicy`,
- one C1 `PaperFillPolicy`.

`PaperLoopPolicy` contains only:

```text
version
exit_max_slippage_bps
```

There is no production default. Each OPEN position separately pins its own C4 `ExitPolicy`.

## Loop state

`PaperLoopState` is immutable:

```text
ledger
loop_policy
paper_fill_policy
managed_positions
pending_entry
last_cycle_at_unix_ms
```

### Managed position

Every OPEN C3 position has exactly one `ManagedPaperPosition`:

```text
position_id
exit_policy
exit_state
```

Its C3 position ID/mint, C4 state ID/mint, and exit-policy version must agree. The managed-position set must exactly equal the ledger's OPEN position IDs.

### Pending BUY

C1 may return `DEFERRED`. C5 therefore retains exactly one `PendingPaperEntry`:

```text
intent
exit_policy
```

The intent must be a PAPER BUY. Its exit policy travels with it so a later actual fill can initialize the lifecycle correctly. No second BUY intent is created while one is pending.

## State creation

`create_paper_loop_state(...)` accepts an existing C3 `PaperLedger`, explicit loop/paper policies, and optional managed/pending state. It validates the exact OPEN-position coverage invariant.

The initial `last_cycle_at_unix_ms` is the maximum of ledger time and managed C4 `last_evaluated_at_unix_ms` values. Empty-ledger runs therefore begin at the C3 ledger timestamp.

## Cycle input

`PaperCycleInput` contains:

```text
as_of_unix_ms
entry_candidates
exit_observations
quotes
```

Entry candidate mints, quote mints, and exit-observation position IDs are each unique within their tuples.

### Exit observation

`PaperExitObservation` contains:

```text
position_id
features
execution_context
```

C4 policy/state come from `ManagedPaperPosition`, preventing silent policy switching.

## Cycle chronology

A cycle timestamp earlier than `state.last_cycle_at_unix_ms` returns a fail-closed `CYCLE_BEFORE_STATE` result with the **exact previous state object** unchanged.

No candidate or quote from that cycle is processed.

## Cycle order

C5-v1 executes deterministically:

1. snapshot the positions OPEN at cycle start,
2. retry an existing pending BUY,
3. if no pending remains and the entry slot is still unused, evaluate new candidates and permit at most one approved BUY attempt,
4. monitor only the positions that were OPEN in the cycle-start snapshot,
5. return the immutable next state and audit results.

A newly opened position begins C4 monitoring next cycle. This avoids using the same evidence as both pre-entry decision evidence and post-fill monitoring evidence.

## Pending BUY retry

C5 calls C1 with:

```text
evaluated_at_unix_ms = cycle.as_of_unix_ms
processed_intent_keys = current C3 terminal keys
quote = cycle quote for pending mint, if any
```

Then:

- `DEFERRED`: preserve exact pending intent,
- terminal `FAILED`: book through C3 and clear pending,
- terminal `PARTIAL/FILLED`: book through C3, clear pending, and initialize C4 state if a new lifecycle opened.

The retry is represented by a dedicated `PaperPendingEntryResult`; it is not forced into a current candidate result that no longer has setup/score/decision objects.

## New BUY path

For each candidate while the entry slot is unused:

1. run its existing setup evaluator,
2. run B7 `score_candidate`,
3. run B8 `decide_entry`,
4. if its mint is already OPEN, skip B9 and record `ENTRY_OPEN_POSITION_EXISTS`,
5. require `risk_context.active_intent_keys == frozenset()` because C5 owns no active BUY when it is allowed to call B9,
6. call B9 `assess_entry_risk(..., RuntimeMode.PAPER)`,
7. if B9 rejects, continue,
8. if B9 approves, its exact BUY `TradeIntent` consumes the cycle entry slot,
9. send it unchanged to C1 with current cycle quote evidence,
10. book terminal C1 outcomes through C3,
11. preserve `DEFERRED` as `PendingPaperEntry`,
12. initialize C4 only after an actual booked BUY opens a lifecycle.

After the entry slot is consumed, later candidates still receive setup/score/decision results for auditability but no new B9 intent is created.

C5 never resizes or rewrites an approved B9 BUY intent.

## Position monitoring coverage

Every position OPEN at cycle start should have one exit observation.

If absent, C5 records `EXIT_OBSERVATION_MISSING`; it does **not** manufacture a C4 HOLD and does not mutate that position's C4 state.

With evidence, C5 calls C4 `assess_exit` unchanged and adopts `assessment.next_state`.

## Position marks

When C4 exposes usable `current_price_usd`, C5 applies a C3 `PaperPositionMark` at the cycle timestamp **after** any SELL execution/accounting attempt.

This preserves current unrealized accounting without marking from stale/future evidence that C4 rejected. A fully closed position is not marked.

Because an exit cycle can both book a terminal SELL attempt and then mark a still-open position, `PaperExitResult` has two distinct audit fields:

```text
execution_ledger_update
mark_ledger_update
```

No evidence is overwritten by forcing both operations into one field.

## Safe C4 quantity -> SELL TradeIntent translation

C4 outputs token quantity while `TradeIntent` requests USD notional. Decision-price conversion is unsafe because a lower actual SELL price can cause C1 to derive more tokens than C4 targeted.

C5 waits for the **same quote C1 will consume**. For target quantity `Q` and that quote's execution price `P`:

```text
requested_notional_usd = Q * P
```

C1 computes:

```text
filled_notional = min(requested_notional, quoted_notional, available_notional)
filled_quantity = filled_notional / P
```

Therefore `filled_quantity <= Q` by construction.

C5 never uses decision price, reference price, weighted entry, or a different quote for this conversion.

## Exit quote eligibility

Let C4 decision time be `T`, C1 assumed latency be `L`, quote time be `Q`, and cycle time be `C`.

- `Q > C`: `EXIT_QUOTE_AFTER_CYCLE`; no future quote fields are consumed.
- no quote: `EXIT_QUOTE_MISSING`.
- `Q < T + L`: `EXIT_QUOTE_BEFORE_LATENCY`; no SELL intent yet.
- quote execution price missing/non-positive: `EXIT_EXECUTION_PRICE_UNAVAILABLE`; no requested notional is fabricated.
- otherwise C5 may construct the SELL intent and lets C1 remain authoritative for quote-window expiry, mint mismatch, route state, partial-fill rules, slippage, and simulated submission failure.

A quote later than C1's maximum quote window is intentionally passed to C1 so C1 produces its existing terminal `QUOTE_TOO_LATE` evidence.

## SELL intent metadata

C5 finds the lifecycle's earliest linked BUY `PaperLedgerEntry` and reuses its:

```text
strategy_name
strategy_version
score_policy_version
decision_policy_version
risk_policy_version
```

No fake exit placeholders are invented.

The SELL intent has:

```text
mint = position mint
side = SELL
requested_notional_usd = C4 target quantity * same quote execution price
max_slippage_bps = pinned PaperLoopPolicy.exit_max_slippage_bps
reason = C4 primary_reason.value
execution_mode = PAPER
as_of_unix_ms = C4 decision as_of
```

Its idempotency key is deterministic SHA-256 over a versioned identity containing:

```text
position_id
exit_policy_version
exit_decision_as_of
primary_exit_reason
target_quantity.float.hex()
```

Replaying the same decision creates the same key.

## SELL execution and accounting

Every SELL uses exactly:

`SELL TradeIntent -> C1 execute_paper_intent -> C3 apply_paper_execution`

C1 stays authoritative for latency, route, quote size, partial/failed fills, slippage, swap/network costs, and submission failure. C3 stays authoritative for quantity, cost-basis release, PnL, cash, journal/idempotency, and close state.

C5 adds no parallel fill or accounting calculation.

## Fill-confirmed take-profit advancement

After an APPLIED terminal SELL booking C5 calls C4 `acknowledge_exit_fill` with authoritative before/after C3 position snapshots.

- no fill -> incomplete TP,
- failed SELL -> incomplete TP,
- undersized partial -> incomplete TP,
- target reached -> complete TP,
- full close -> complete when take-profit driven.

C5 never advances a TP level from a decision or requested intent alone.

## No persistent pending exit order

C5 persists evolving C4 `ExitState`, not a stale exit order.

If a REDUCE lacks an eligible quote, the next cycle reassesses fresh evidence. A later emergency EXIT can therefore supersede the earlier reduction through normal C4 precedence.

## Exit state lifecycle

After assessment, managed state adopts `assessment.next_state`. After an APPLIED SELL, acknowledgement may additionally change completed TP levels.

- still OPEN -> keep exactly one managed record,
- CLOSED -> remove managed record,
- no booked quantity change -> do not invent TP completion.

## Cycle result contracts

### `PaperPendingEntryResult`

Preserves:

```text
intent_idempotency_key
mint
execution
ledger_update
reason
```

### `PaperEntryResult`

Preserves:

```text
mint
setup_assessment
score_assessment
decision
risk_assessment | None
selected_for_entry
execution | None
ledger_update | None
reason
```

Setup/score/decision are always produced for a structurally valid candidate. Risk is `None` only when C5 intentionally skips B9 because the entry slot is unavailable, the mint is already OPEN, or active-intent evidence contradicts C5 state.

### `PaperExitResult`

Preserves:

```text
position_id
mint
exit_assessment | None
intent | None
execution | None
execution_ledger_update | None
mark_ledger_update | None
reason
```

`exit_assessment` is `None` only when monitoring evidence is absent.

### `PaperCycleResult`

Contains:

```text
policy_version
as_of_unix_ms
next_state
pending_entry_result | None
entry_results
exit_results
findings
```

A normal cycle has one `CYCLE_APPLIED` finding. A chronology-rejected cycle has one `CYCLE_BEFORE_STATE` finding and exact previous state.

## Stable orchestration reasons

```text
CYCLE_APPLIED
CYCLE_BEFORE_STATE
PENDING_ENTRY_DEFERRED
PENDING_ENTRY_TERMINAL
ENTRY_NOT_SELECTED
ENTRY_OPEN_POSITION_EXISTS
ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH
ENTRY_RISK_REJECTED
ENTRY_EXECUTION_DEFERRED
ENTRY_EXECUTION_TERMINAL
EXIT_OBSERVATION_MISSING
EXIT_HOLD
EXIT_QUOTE_MISSING
EXIT_QUOTE_AFTER_CYCLE
EXIT_QUOTE_BEFORE_LATENCY
EXIT_EXECUTION_PRICE_UNAVAILABLE
EXIT_EXECUTION_TERMINAL
EXIT_POSITION_CLOSED
```

These describe orchestration only. Underlying setup/score/decision/risk/C1/C3/C4 reasons remain separately attached to results.

## No production defaults

C5 ships no starting capital, setup threshold, score threshold, risk threshold, exit threshold, paper-fill assumptions, or exit slippage default.

The one-entry-attempt rule is a point-in-time risk-context invariant, not a claimed optimal trading cadence.

## Point-in-time rules

C5 must never:

- process a cycle earlier than prior state,
- use future quote evidence to construct a SELL,
- use same-cycle pre-entry evidence as post-fill C4 monitoring for a newly opened lifecycle,
- mark from evidence C4 rejected as unusable,
- create a new BUY while one is pending,
- create more than one BUY attempt in one cycle,
- use decision-time price to convert C4 quantity to SELL notional.

## Error handling

Expected trading outcomes remain domain results rather than exceptions: REJECT/WATCH/risk reject/execution fail/exit HOLD are ordinary data.

Constructors raise `ValueError` for malformed immutable shapes such as duplicate candidate/quote/exit IDs, inconsistent managed-position identity, or a non-PAPER/non-BUY pending entry.

Cycle chronology violation is a fail-closed result with no state mutation.

## Public C5 API

```text
FirstPullbackSetupInput
FreshLaunchSetupInput
GraduationBreakoutSetupInput
ManagedPaperPosition
PaperCycleInput
PaperCycleResult
PaperEntryCandidate
PaperEntryResult
PaperExitObservation
PaperExitResult
PaperLoopFinding
PaperLoopPolicy
PaperLoopReasonCode
PaperLoopState
PaperPendingEntryResult
PendingPaperEntry
create_paper_loop_state
run_paper_cycle
```

No provider/RPC/storage/signer/transaction/live-execution object is public.

## Explicit non-goals

C5 does not add provider/RPC access, raw observation ingestion, B1/B2 changes, new setup families, Smart Wallet Cluster, score/decision/risk changes, C1 fill-model changes, C3 accounting formula changes, C4 exit-rule changes, durable restart persistence, Parquet export, wallet reconstruction, signer secrets, Solana transaction construction/submission, or live mode.

C6 is next and will validate/persist/recover autonomous accounting across partial exits, multiple positions, wins/losses, failed fills, and restarts.

## Success criterion

C5 is complete when repeated immutable cycles can:

- evaluate existing setups,
- score/decide/risk-size through the existing path,
- carry one deferred BUY until terminal,
- book actual paper BUYs,
- initialize C4 state at lifecycle open,
- monitor every pre-existing OPEN position,
- build quantity-safe quote-aware SELL intents,
- route SELLs through C1/C3 only,
- fill-confirm TP advancement,
- keep marks current from usable evidence,
- return reconstructable cycle evidence,
- and keep live execution impossible.