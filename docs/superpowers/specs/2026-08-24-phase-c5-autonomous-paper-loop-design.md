# Phase C5 Autonomous Paper Loop Design

## Goal

Implement source build-order C5 as a deterministic in-memory PAPER orchestration layer:

`observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record`

C5 coordinates the already-sealed B2/B6/B7/B8/B9/C1/C3/C4 contracts. It does not invent strategy, risk, fill, accounting, or exit math and does not enable live money.

## Boundary

C5 lives in `shreks_brain.paper_loop` and may call only existing pure domain functions for setup evaluation, scoring, decision, entry risk, C1 paper execution, C3 accounting/marks, and C4 exit decisions/acknowledgement.

It performs no provider, RPC, SQLite, storage, wall-clock, RNG, signer, transaction construction, or transaction submission work.

Supported setup families are exactly Fresh Launch Continuation, Graduation/Breakout, and First Pullback. Smart Wallet Cluster remains absent until Phase D has real wallet-history/confidence/independence evidence.

## Immutable loop state

`PaperLoopState` pins one explicit `PaperLoopPolicy`, one explicit C1 `PaperFillPolicy`, the authoritative C3 `PaperLedger`, optional pending BUY, managed C4 position records, and the last cycle timestamp.

Every C3 OPEN lifecycle has exactly one `ManagedPaperPosition`:

```text
position_id
exit_policy
exit_state
pending_exit
```

`pending_exit` is `ExitAssessment | None`. Position ID, mint, and exit-policy version must remain coherent across C3/C4/C5 state.

No production defaults are supplied for capital, setup thresholds, score thresholds, risk thresholds, exit thresholds, fill assumptions, or exit slippage.

## Cycle order

Each `PaperCycleInput` contains one caller-supplied timestamp plus ordered entry candidates, exit observations, and quotes. Candidate mints, quote mints, and exit-observation position IDs are unique within the cycle.

A cycle earlier than current loop state fails closed and returns the exact previous state unchanged.

A valid cycle executes deterministically:

1. snapshot positions OPEN at cycle start,
2. retry one pending BUY,
3. if the entry slot is still unused, evaluate ordered candidates and permit at most one approved BUY attempt,
4. monitor only positions that were OPEN at cycle start,
5. reconcile fresh C4 evidence with any pending exit decision,
6. when eligible, construct a transient quantity-safe SELL and route it through C1/C3,
7. mark still-open positions only from usable C4 current-price evidence,
8. return immutable next state plus complete audit results.

A lifecycle opened during a cycle begins monitoring next cycle, preventing pre-entry evidence from being reused as post-fill exit evidence.

## BUY path

Each candidate carries `FeatureVector`, regime evidence, one supported setup input, explicit score/decision/risk policies, point-in-time `RiskContext`, and the C4 `ExitPolicy` to pin if a lifecycle opens.

C5 calls the existing setup evaluator, `score_candidate`, `decide_entry`, and `assess_entry_risk` unchanged. It does not call B9 when the mint is already OPEN or when C5 already owns a pending/new BUY slot.

C5-v1 permits at most one approved BUY execution attempt per cycle because multiple B9 approvals from risk snapshots captured before the first fill could reuse stale capital/risk capacity.

A B9-approved BUY `TradeIntent` is passed to C1 unchanged. Terminal results are booked through C3. A C1 `DEFERRED` result becomes the single `PendingPaperEntry`; no second BUY is created while it remains pending. C4 state is initialized only after C3 proves a real OPEN lifecycle exists.

## Why C5 persists C4 exit decisions, not SELL notionals

C4 authorizes token quantity, while stable `TradeIntent` requests USD notional. C1 also models latency from `TradeIntent.as_of_unix_ms`.

Discarding an unexecuted C4 exit every cycle would reset the latency clock indefinitely. Persisting a SELL intent instead would freeze USD notional; if the eventual execution price fell, C1 could derive more token quantity than C4 authorized.

C5 therefore persists the immutable C4 `ExitAssessment`/token target, never a SELL intent and never a USD notional.

A pending exit must belong to the managed lifecycle/policy, be `REDUCE` or `EXIT`, have positive target quantity, and be no later than the current managed C4 state.

## Pending-exit precedence

Fresh C4 assessments always advance `exit_state` to `assessment.next_state`, but they do not arbitrarily reset pending execution authority:

- no pending exit + fresh `REDUCE`/`EXIT` -> persist fresh assessment,
- pending `REDUCE` + fresh `EXIT` -> newer full EXIT supersedes the pending reduction,
- pending `EXIT` + fresh HOLD/REDUCE -> retain the existing full EXIT,
- pending `REDUCE` + fresh HOLD/REDUCE -> retain the original reduction so latency does not reset,
- a superseding newer EXIT keeps its own newer timestamp; C5 never backdates stronger future evidence.

A terminal C1 SELL attempt clears the pending exit. If the position remains OPEN, another attempt requires a fresh C4 decision on a later cycle.

An already-authorized pending exit may be attempted on a cycle without a fresh exit observation; the previous C4 decision supplies authorization while only current quote evidence supplies execution economics.

## Quantity-safe SELL conversion

For C4-authorized target quantity `Q` and the **same quote execution price `P` C1 will consume**:

```text
requested_notional_usd = Q * P
```

C1 then computes:

```text
filled_notional = min(requested_notional, quoted_notional, available_notional)
filled_quantity = filled_notional / P
```

Therefore `filled_quantity <= Q` by construction.

C5 never converts with C4 market price, reference price, weighted entry, or a stale earlier quote.

The transient SELL intent keeps `as_of_unix_ms = pending_exit.as_of_unix_ms`, preserving the original latency clock. Its strategy/score/decision/risk versions come from the lifecycle's earliest linked BUY ledger entry. `max_slippage_bps` comes from explicit `PaperLoopPolicy`; reason comes from C4 primary reason.

SELL idempotency is deterministic SHA-256 over a versioned identity containing position ID, exit-policy version, exit-decision timestamp, primary reason, and stable float-hex target quantity. Quote-price changes alter transient notional but do not alter the same exit decision's idempotency key.

## Quote eligibility

For pending decision time `T`, C1 latency `L`, quote time `Q`, and cycle time `C`:

- no quote -> keep pending,
- `Q > C` -> reject future quote before consuming its price fields,
- `Q < T + L` -> keep pending; latency not yet satisfied,
- missing execution price -> keep pending; no notional is fabricated,
- otherwise build the transient SELL and give that exact quote to C1.

A quote later than C1's maximum quote window is still passed to C1 once otherwise eligible so C1 remains authoritative for `QUOTE_TOO_LATE` terminal evidence.

## SELL execution, accounting, and take profits

Every SELL uses exactly:

`TradeIntent -> C1 execute_paper_intent -> C3 apply_paper_execution`

C1 remains authoritative for latency, quote window, route state, executable size, partial fills, slippage, swap/network costs, and failed-after-submission costs. C3 remains authoritative for quantity reduction, basis release, cash, realized PnL, journal/idempotency, and lifecycle closure.

C5 never implements a parallel fill or accounting formula.

After an APPLIED terminal SELL, C5 calls C4 `acknowledge_exit_fill` with authoritative C3 before/after position snapshots. Failed/no-fill or undersized partial exits cannot complete a take-profit level. The level completes only when booked C3 quantity reduction reaches the target or the take-profit-driven lifecycle fully closes.

## Marks and audit outputs

If a still-open position has a fresh C4 assessment exposing usable `current_price_usd`, C5 applies a C3 `PaperPositionMark` at cycle time. Missing, stale, future, or unusable C4 evidence is never converted into a mark.

`PaperExitResult` keeps separate `execution_ledger_update` and `mark_ledger_update` fields so accounting booking evidence is not overwritten by mark evidence.

`PaperCycleResult` retains immutable next state, optional pending-BUY result, entry results, exit results, and one cycle-level orchestration finding. Underlying setup/score/decision/risk/C1/C3/C4 reason objects remain attached rather than being replaced by C5 reason codes.

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

## Safety invariants

C5 must never:

- consume future quote fields,
- reset authorized-exit latency merely because a new cycle occurred,
- backdate a newer stronger exit,
- freeze stale USD SELL notional across cycles,
- let C1 fill more token quantity than C4 authorized,
- monitor a newly opened lifecycle using the same cycle's pre-entry evidence,
- mark from unusable C4 evidence,
- create a new BUY while one is pending,
- approve more than one new BUY attempt per cycle,
- fabricate wallet-distribution evidence,
- expose provider/RPC/storage/signer/transaction/LIVE execution authority.

## Public API

The stable C5 package exposes exactly:

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

No execution primitive or runtime mode is re-exported.

## Non-goals and next phase

C5 adds no provider/RPC ingestion, B1/B2 changes, new setup families, wallet intelligence, scoring/decision/risk changes, C1 fill changes, C3 accounting changes, C4 exit-rule changes, persistence/restart recovery, signer, transaction submission, or live mode.

C6 is responsible for persistence/restart/accounting validation across partial exits, multiple positions, wins/losses, failed fills, and process restarts.

## Success criterion

C5 is complete when repeated immutable PAPER cycles can evaluate existing setups; score/decide/risk-size through the existing path; carry deferred BUYs; book realistic BUYs; initialize C4 only after lifecycle open; monitor all cycle-start OPEN positions; preserve latency-delayed C4 exits without stale notional; route every SELL through C1/C3; fill-confirm TP progress; maintain marks from usable evidence; return auditable results; and keep live execution structurally impossible.
