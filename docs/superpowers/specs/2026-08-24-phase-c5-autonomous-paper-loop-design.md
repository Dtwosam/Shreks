# Phase C5 Autonomous Paper Loop Design

## Goal

Implement source build-order C5 as a deterministic in-memory Python orchestration layer for repeated PAPER cycles:

`observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record`

C5 coordinates already-sealed B2/B6/B7/B8/B9/C1/C3/C4 contracts. It does not create new strategy, risk, fill, accounting, or exit math and does not enable live money.

## Architectural boundary

C5 lives in:

```text
python/src/shreks_brain/paper_loop/
  __init__.py
  models.py
  engine.py
```

It may call only the existing pure domain functions needed for orchestration:

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

No provider/RPC/storage/wall-clock/RNG/signer/transaction reads or writes occur in C5.

## Supported setup families

C5-v1 supports exactly:

1. Fresh Launch Continuation,
2. Graduation/Breakout,
3. First Pullback.

Smart Wallet Cluster remains absent until Phase D has real wallet history/confidence/independence evidence.

## Entry candidate contract

`PaperEntryCandidate` carries:

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

The setup is one of three immutable wrappers:

```python
FreshLaunchSetupInput(policy)
GraduationBreakoutSetupInput(context, policy)
FirstPullbackSetupInput(context, policy)
```

Candidate feature/regime/risk timestamps equal the cycle timestamp. Existing domain engines remain authoritative for deeper compatibility and point-in-time checks.

## Candidate ordering and one-entry invariant

`PaperCycleInput.entry_candidates` is an ordered tuple and therefore the deterministic candidate priority for that cycle. Candidate mints are unique within a cycle.

C5-v1 permits at most one approved BUY execution attempt per cycle. B9 risk contexts are point-in-time snapshots; allowing several approvals from contexts captured before the first fill could reuse stale capital/risk capacity. A pending BUY retry also consumes the cycle entry slot even if it terminates failed.

No new BUY is submitted for a mint already OPEN in C3. C3 can technically increase a lifecycle, but no approved rule yet defines how pyramiding should alter C4 high-water/trailing/take-profit semantics.

## Pinned policies

One `PaperLoopState` pins:

- one explicit `PaperLoopPolicy(version, exit_max_slippage_bps)`,
- one explicit C1 `PaperFillPolicy`.

Every OPEN lifecycle separately pins its C4 `ExitPolicy` in `ManagedPaperPosition`.

There are no production defaults for capital, setup thresholds, score thresholds, risk thresholds, exit thresholds, paper-fill assumptions, or exit slippage.

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

Every C3 OPEN position has exactly one `ManagedPaperPosition`:

```text
position_id
exit_policy
exit_state
pending_exit
```

`pending_exit` is `ExitAssessment | None`.

The C3 position ID/mint, C4 state ID/mint, and exit-policy version must agree. `managed_positions` must exactly cover the ledger's OPEN position IDs.

### Why a pending exit assessment is required

C1 latency is measured from `TradeIntent.as_of_unix_ms`. A C4 exit decision produced at time `T` cannot execute before `T + assumed_latency_ms`.

If C5 discarded an unexecuted exit decision and generated a fresh decision every cycle, non-zero latency could reset forever. Persisting a SELL intent instead would be unsafe because its USD notional would be frozen even if the eventual execution price changed, potentially making C1 derive more token quantity than C4 authorized.

C5 therefore persists the immutable **C4 exit assessment/quantity identity**, never a SELL intent and never a USD notional.

A pending exit must:

- belong to the managed position and mint,
- use the managed exit-policy version,
- have action `REDUCE` or `EXIT`,
- have positive target quantity,
- have `as_of_unix_ms <= exit_state.last_evaluated_at_unix_ms`.

## Pending BUY

C1 may return `DEFERRED`. C5 retains exactly one `PendingPaperEntry(intent, exit_policy)`. The intent must be a PAPER BUY. No second BUY intent is created while one is pending.

## State creation

`create_paper_loop_state(...)` accepts an existing C3 ledger, explicit loop/fill policies, optional managed positions, and optional pending BUY. It validates exact OPEN-position coverage. Initial `last_cycle_at_unix_ms` is the maximum of ledger time and managed C4 `last_evaluated_at_unix_ms` values.

## Cycle input

`PaperCycleInput` contains:

```text
as_of_unix_ms
entry_candidates
exit_observations
quotes
```

Candidate mints, quote mints, and exit-observation position IDs are each unique within their tuples.

`PaperExitObservation(position_id, features, execution_context)` supplies current C4 evidence. C4 policy/state come from the managed position, preventing silent policy switching.

A cycle earlier than `state.last_cycle_at_unix_ms` returns `CYCLE_BEFORE_STATE` with the exact previous state object unchanged and processes nothing.

## Deterministic cycle order

C5-v1 executes:

1. snapshot positions OPEN at cycle start,
2. retry one pending BUY,
3. if the entry slot remains unused, evaluate new candidates and permit at most one approved BUY attempt,
4. monitor only cycle-start OPEN positions,
5. for each managed position, reconcile fresh C4 evidence with any pending exit, then attempt safe exit execution if eligible,
6. mark still-open positions only from usable C4 current-price evidence,
7. return immutable next state plus audit results.

A position opened during the cycle starts C4 monitoring next cycle. Same-cycle pre-entry evidence is never reused as post-fill monitoring evidence.

## BUY path

For each candidate while the entry slot is free:

1. call the matching existing setup evaluator,
2. call B7 `score_candidate`,
3. call B8 `decide_entry`,
4. if mint already OPEN, skip B9,
5. require `risk_context.active_intent_keys == frozenset()` because C5 owns no active BUY when it may call B9,
6. call B9 `assess_entry_risk(..., RuntimeMode.PAPER)`,
7. continue after risk rejection,
8. first approval consumes the entry slot,
9. pass the exact B9 BUY `TradeIntent` unchanged to C1,
10. book terminal C1 outcomes through C3,
11. persist `DEFERRED` as `PendingPaperEntry`,
12. initialize C4 only after C3 actually opens a lifecycle.

C5 never resizes or rewrites a B9 BUY intent.

## Pending BUY retry

A pending BUY is sent to C1 with current cycle evaluation time, current C3 terminal keys, and that mint's cycle quote if any.

- `DEFERRED`: preserve the exact pending intent,
- terminal `FAILED`: book through C3 and clear pending,
- terminal `PARTIAL/FILLED`: book through C3, clear pending, initialize C4 if a new lifecycle opened.

## Position monitoring and pending-exit reconciliation

Every cycle-start OPEN position should have one exit observation. Missing observation does not manufacture a C4 HOLD.

If an observation exists, C5 calls C4 `assess_exit(...)` unchanged and adopts `assessment.next_state`.

Pending-exit precedence is intentionally narrow:

- no pending exit + fresh `REDUCE`/`EXIT` -> persist fresh assessment,
- existing pending `REDUCE` + fresh `EXIT` -> fresh EXIT supersedes pending REDUCE,
- existing pending `EXIT` -> HOLD or REDUCE cannot weaken/cancel it,
- existing pending `REDUCE` + fresh HOLD/REDUCE -> retain original pending REDUCE so its latency clock is not reset,
- a superseding fresh EXIT uses its own later timestamp; C5 never backdates stronger future evidence.

A terminal C1 SELL attempt clears the pending exit. If the position remains OPEN, the next cycle must obtain a fresh C4 decision before a new attempt is created. This makes every retry after a terminal failure/partial fill a new point-in-time decision and idempotency identity.

A pending exit may still be attempted when the current cycle lacks a C4 observation, because the older C4 decision is already-authorized state. The missing observation is not converted into a new decision; only current quote evidence is used for execution economics.

## Safe token quantity -> SELL TradeIntent translation

C4 outputs token quantity while stable `TradeIntent` requests USD notional. C5 must not convert with C4 market price, reference price, weighted entry, or any stale quote.

For pending/fresh authorized target quantity `Q` and the **same quote execution price `P` that C1 will consume**:

```text
requested_notional_usd = Q * P
```

C1 then computes:

```text
filled_notional = min(requested_notional, quoted_notional, available_notional)
filled_quantity = filled_notional / P
```

Therefore:

```text
filled_quantity <= Q
```

by construction.

The SELL `TradeIntent.as_of_unix_ms` remains the persisted C4 decision timestamp. This preserves the original latency clock even though notional is recomputed from a later eligible quote.

## Exit quote eligibility

Let pending C4 decision time be `T`, C1 latency be `L`, quote observation time be `Q`, and cycle time be `C`.

- no quote -> keep pending exit; `EXIT_QUOTE_MISSING`,
- `Q > C` -> keep pending exit; `EXIT_QUOTE_AFTER_CYCLE`, and consume no future quote fields,
- `Q < T + L` -> keep pending exit; `EXIT_QUOTE_BEFORE_LATENCY`,
- missing execution price -> keep pending exit; `EXIT_EXECUTION_PRICE_UNAVAILABLE`,
- otherwise construct a transient SELL intent and pass it with that exact quote to C1.

A quote after C1's maximum quote window is intentionally passed to C1 so C1 remains authoritative and records `QUOTE_TOO_LATE`.

## SELL metadata and idempotency

C5 finds the lifecycle's earliest linked BUY `PaperLedgerEntry` and reuses:

```text
strategy_name
strategy_version
score_policy_version
decision_policy_version
risk_policy_version
```

The transient SELL intent has:

```text
mint = position mint
side = SELL
requested_notional_usd = pending_exit.target_quantity * current quote execution price
max_slippage_bps = loop_policy.exit_max_slippage_bps
reason = pending_exit.primary_reason.value
execution_mode = PAPER
as_of_unix_ms = pending_exit.as_of_unix_ms
```

Idempotency is SHA-256 of:

```text
c5-exit-v1
position_id
exit_policy_version
exit_decision_as_of
primary_exit_reason
target_quantity.float.hex()
```

Changing the quote price changes transient notional but **does not** change the exit decision identity/idempotency key. A later new C4 decision changes the key through its timestamp and/or target/reason.

## SELL execution and accounting

Every SELL uses exactly:

`TradeIntent -> C1 execute_paper_intent -> C3 apply_paper_execution`

C1 remains authoritative for latency, quote window, route availability, executable size, partial fills, slippage, swap/network costs, and simulated submission failure. C3 remains authoritative for quantity reduction, cost-basis release, cash, realized PnL, journal/idempotency, and close state.

No parallel fill or accounting calculation exists in C5.

## Fill-confirmed take-profit advancement

After an APPLIED terminal SELL booking, C5 calls C4 `acknowledge_exit_fill` with authoritative before/after C3 position snapshots and the latest managed `ExitState`.

- no fill / failed SELL -> TP incomplete,
- undersized partial -> TP incomplete,
- target reached -> TP complete,
- full close -> TP complete when take-profit driven.

C5 never advances TP from a decision, pending state, or requested intent alone.

## Marks

After exit processing, if the position remains OPEN and the current cycle's C4 assessment exposed usable `current_price_usd`, C5 applies `PaperPositionMark` at cycle time. It does not mark from missing/stale/future/unusable C4 evidence.

`PaperExitResult` keeps separate `execution_ledger_update` and `mark_ledger_update` fields so booking and mark evidence are never overwritten.

## Managed exit lifecycle

After fresh assessment, managed `exit_state` adopts `assessment.next_state`. After an APPLIED SELL, acknowledgement may additionally advance completed TP levels.

- non-terminal/no execution: retain pending exit as described above,
- terminal SELL attempt: clear pending exit,
- still OPEN: keep one managed record,
- CLOSED: remove managed record and skip mark.

## Cycle result contracts

`PaperPendingEntryResult` preserves pending BUY execution/booking evidence.

`PaperEntryResult` preserves setup, score, decision, optional risk, selection, optional execution/booking, and one orchestration reason.

`PaperExitResult` preserves:

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

`exit_assessment` may be `None` when current monitoring evidence is absent; execution may still refer to a previously persisted pending exit.

`PaperCycleResult` contains policy version, cycle timestamp, immutable next state, optional pending BUY result, entry results, exit results, and exactly one cycle finding.

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
EXIT_POSITION_MARKED
EXIT_POSITION_CLOSED
```

These describe orchestration only; B/C-domain findings remain attached separately.

## Point-in-time and safety rules

C5 must never:

- process a cycle earlier than prior loop state,
- use future quote fields to construct a SELL,
- reset an authorized exit's latency clock merely because a later cycle occurred,
- backdate a newer stronger exit to an older decision time,
- freeze a stale USD SELL notional across cycles,
- allow C1 fill quantity to exceed C4-authorized token quantity,
- use same-cycle pre-entry evidence to monitor a newly opened lifecycle,
- mark from evidence C4 rejected as unusable,
- create a new BUY while one is pending,
- create more than one approved BUY attempt per cycle,
- fabricate wallet-distribution evidence,
- create LIVE intent/execution/signer/transaction authority.

## Error handling

Ordinary trading outcomes remain domain results rather than exceptions: setup WATCH/BLOCKED, decision REJECT/WATCH, risk rejection, execution failure, exit HOLD, and unavailable quote are expected data.

Constructors raise `ValueError` for malformed immutable shapes such as duplicate cycle identities, unsupported setup wrappers, non-PAPER pending BUYs, managed/open-position mismatches, pending exit identity/policy mismatch, or pending HOLD assessments.

## Public C5 API

The stable package is intended to expose:

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

No provider/RPC/storage/signer/transaction/live-execution type is public from C5.

## Explicit non-goals

C5 does not add provider/RPC calls, raw observation ingestion, B1/B2 changes, new setup families, wallet intelligence, scoring/decision/risk changes, C1 fill changes, C3 accounting changes, C4 exit-rule changes, durable restart persistence, Parquet export, transaction construction/submission, or live mode.

C6 remains responsible for persistence/restart/accounting validation across partial exits, multiple positions, wins/losses, failed fills, and restarts.

## Success criterion

C5 is complete when repeated immutable PAPER cycles can evaluate existing setups; score/decide/risk-size through the existing path; carry a deferred BUY; book realistic BUYs; initialize C4 only after lifecycle open; monitor every cycle-start OPEN position; preserve and safely retry latency-delayed C4 exits without stale notional; route all SELLs through C1/C3; fill-confirm TP progress; maintain C3 marks from usable evidence; return auditable cycle results; and keep live execution structurally impossible.
