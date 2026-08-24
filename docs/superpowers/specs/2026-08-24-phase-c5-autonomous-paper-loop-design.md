# Phase C5 Autonomous Paper Loop Design

## Goal

Implement the source build-order C5 Autonomous Loop as a deterministic, in-memory Python orchestration layer that repeatedly reuses the already-sealed Shreks decision path:

`observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record`

C5 makes paper mode operationally autonomous without creating a second strategy, risk, execution, accounting, or exit path. It coordinates the existing B2/B3-B5/B6/B7/B8/B9/C1/C3/C4 contracts and preserves enough cycle output for later C6 persistence/restart/accounting validation.

C5 does **not** enable live money.

## Source requirements

The build order requires C5 to operate unattended using:

```text
observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record
```

The master source of truth additionally requires:

- one decision path for paper and future live modes,
- paper mode to be fully autonomous,
- realistic slippage, costs, latency, partial/failed fills, and limited exit liquidity,
- complete position lifecycle support,
- every important decision to remain auditable,
- no live execution before proof,
- fail-closed handling of stale, missing, contradictory, or unreliable critical evidence.

## Architectural boundary

C5 lives in a new package:

```text
python/src/shreks_brain/paper_loop/
  __init__.py
  models.py
  engine.py
```

The package is orchestration only. It may call stable earlier-domain functions but must not reimplement their calculations.

### Existing functions reused unchanged

C5 calls:

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

C5 does not change the semantics of any of them.

## What "observe" means in C5

Rust/A-phase ingestion and B1/B2 feature construction already exist. C5 therefore does not duplicate provider access, raw normalization, token safety calculation, or feature engineering.

For C5, an observed candidate is a caller-supplied, point-in-time B2 `FeatureVector` plus the structural context required by one already-implemented setup family and the contemporaneous B6 regime assessment. C5 begins orchestration from that normalized evidence boundary.

This preserves the Rust-eyes/Python-brain architecture and avoids a second observer implementation inside the paper loop.

## Supported setup families

C5-v1 supports exactly the setup families that exist before Phase D:

1. Fresh Launch Continuation,
2. Graduation/Breakout,
3. First Pullback.

Smart Wallet Cluster remains absent because Phase D wallet intelligence does not yet exist.

C5 never fabricates wallet quality, wallet history, or wallet-cluster evidence.

## Immutable setup input wrappers

To avoid a loosely validated bag of optional fields, C5 uses one of three immutable setup-input wrappers:

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

`PaperEntryCandidate.setup` is the union of those three wrappers. C5 dispatches only to the matching existing setup evaluator.

## Entry candidate contract

One candidate contains all explicit policy/evidence required to run the existing entry path:

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

`exit_policy` is supplied at entry time because C4 requires one exit-policy version to be pinned for the resulting position lifecycle. C5 must initialize C4 state immediately after an actual C3 BUY opens a new lifecycle; initializing it much later would lose historical high-water evidence.

Candidate timestamps must be point-in-time coherent with the cycle. Engines remain authoritative for their own detailed compatibility checks.

## Deterministic candidate ordering

`PaperCycleInput.entry_candidates` is an ordered tuple. That order is the deterministic priority order supplied to C5.

C5-v1 requires candidate mints to be unique inside one cycle. The repository has no approved policy for choosing between multiple simultaneous setup families for the same mint. C5 therefore does not invent cross-setup arbitration, cross-setup score comparison, or pyramiding behavior.

A caller that wants to compare multiple setup hypotheses for the same mint can still do so in research outside the autonomous execution batch.

## One new entry attempt per cycle

C5-v1 allows at most one new BUY intent/execution attempt per cycle.

This is a correctness invariant, not a profitability threshold.

Reason: B9 `RiskContext` contains point-in-time portfolio evidence such as capital, aggregate open risk, loss state, and active intents. If C5 approved and executed several new entries from contexts all captured before the first fill, later candidates could reuse stale risk capacity and violate limits.

C5 therefore:

1. computes setup/score/decision in deterministic candidate order,
2. calls B9 risk only while the entry slot is still unused,
3. selects the first B9 `APPROVED` intent,
4. creates no later BUY intent in that cycle.

A future version may widen this only when it can refresh authoritative portfolio risk context after each terminal booking.

## No same-mint pyramiding in C5-v1

C3 can technically increase an existing position, but C4 trailing/take-profit state is defined around one position lifecycle and one execution-weighted entry basis. The repository has no approved policy for how a later add changes high-water/trailing/take-profit treatment.

C5-v1 therefore does not submit a new BUY for a mint that already has an OPEN C3 position. This prevents silent strategy semantics from changing under an existing exit state.

## Pinned experiment policies

The autonomous loop state pins:

- one `PaperLoopPolicy`,
- one C1 `PaperFillPolicy`.

They remain unchanged for that in-memory run.

`PaperLoopPolicy` contains only orchestration configuration:

```text
version
exit_max_slippage_bps
```

There is no production default.

The paper fill policy remains the existing C1 contract and continues to own latency, quote lag, swap fee, network fee, and partial-fill assumptions.

Each position separately pins its own C4 `ExitPolicy`.

## Autonomous loop state

`PaperLoopState` is immutable and contains:

```text
ledger
loop_policy
paper_fill_policy
managed_positions
pending_entry
last_cycle_at_unix_ms
```

### `ManagedPaperPosition`

For every OPEN C3 position the loop owns exactly one managed exit record:

```text
position_id
exit_policy
exit_state
```

Invariants:

- managed position ID must refer to an OPEN C3 position,
- `exit_state.position_id` and mint must match that C3 position,
- exit state policy version must match `exit_policy.version`,
- there is exactly one managed record per OPEN position.

This makes position monitoring explicit and prevents an open position from silently existing without C4 state.

### `PendingPaperEntry`

C1 may return `DEFERRED` while entry latency or quote evidence is still pending. C5 therefore persists exactly one pending BUY intent in memory:

```text
intent
exit_policy
```

The exit policy travels with the pending intent so an eventual actual fill can initialize the correct C4 lifecycle state.

C5 never creates a second BUY intent while a pending entry exists.

## Cycle input

`PaperCycleInput` contains:

```text
as_of_unix_ms
entry_candidates
exit_observations
quotes
```

### Quotes

Quotes are C1 `PaperQuote` values. A cycle may carry at most one quote per mint. Missing quote evidence remains missing; C5 does not synthesize a price or route.

### Exit observations

Each `PaperExitObservation` contains:

```text
position_id
features
execution_context
```

C4 `ExitPolicy` and `ExitState` come from the managed-position state, not from the caller each cycle. This prevents silent policy switching.

A cycle may carry at most one exit observation per position.

## Cycle chronology

`PaperCycleInput.as_of_unix_ms` must not precede `PaperLoopState.last_cycle_at_unix_ms`.

A chronology violation fails the whole cycle closed with no state change.

Entry candidate B2 features and risk context must refer to the cycle timestamp. Exit feature/context coherence is still enforced by C4.

## Cycle order

C5-v1 uses this deterministic order:

1. retry an existing pending BUY intent,
2. if no pending BUY remains and the entry slot is still unused, evaluate new entry candidates and allow at most one approved BUY attempt,
3. monitor positions that were OPEN at the beginning of the cycle,
4. return the immutable next state plus auditable entry/exit results.

Positions newly opened during this cycle begin C4 monitoring on the next cycle. This avoids using same-cycle market evidence as both pre-entry decision evidence and post-fill position-monitoring evidence.

The cycle order matches the source flow (`... size -> paper buy -> monitor -> paper sell -> record`) while keeping risk context temporally coherent.

## Pending BUY retry

For a pending entry C5 constructs the existing C1 `PaperExecutionContext` using:

```text
evaluated_at_unix_ms = cycle.as_of_unix_ms
processed_intent_keys = current C3 ledger terminal keys
quote = current cycle quote for the pending mint, if any
```

Then it calls `execute_paper_intent` unchanged.

- `DEFERRED`: keep the exact pending intent.
- terminal `FAILED`: book it through C3 and clear pending.
- terminal `PARTIAL/FILLED`: book through C3, clear pending, and if a new lifecycle opened, initialize C4 state immediately.

Retrying a pending BUY consumes the cycle's one entry-attempt slot even when it terminates. C5 does not immediately fire a different candidate after a failed retry using the same pre-cycle risk snapshot.

## New BUY path

For each candidate while the slot is available:

1. run the matching setup evaluator,
2. run B7 `score_candidate`,
3. run B8 `decide_entry`,
4. if the mint is already OPEN, do not call B9 and record an orchestration rejection,
5. otherwise call B9 `assess_entry_risk(..., RuntimeMode.PAPER)`,
6. if B9 rejects, continue to the next candidate,
7. if B9 approves, its exact BUY `TradeIntent` is the only new entry intent eligible this cycle,
8. send that intent to C1 with the same cycle quote evidence,
9. book terminal results through C3,
10. persist `DEFERRED` as `PendingPaperEntry`,
11. initialize C4 state only after a booked BUY actually opens a new lifecycle.

C5 does not resize, rewrite, or bypass a B9 BUY intent.

## Risk active-intent coherence

When no pending entry exists, the autonomous C5 loop owns no active BUY intent. Therefore a candidate `RiskContext.active_intent_keys` must be empty when B9 is called.

When a pending entry exists, C5 does not call B9 for new candidates at all.

This keeps B9 duplicate-intent semantics consistent with C5's actual in-memory active-intent state instead of trusting a contradictory caller claim.

## Position monitoring

Every position that was OPEN at cycle start should have one exit observation for full monitoring coverage.

If an observation is absent, C5 does **not** invent a C4 `HOLD`. It records an orchestration-level `EXIT_OBSERVATION_MISSING` result and leaves C4 state unchanged.

When evidence exists, C5 calls C4 `assess_exit` unchanged.

- C4 `HOLD`: no SELL intent is created.
- C4 `REDUCE`/`EXIT`: C5 attempts safe quote-aware translation described below.

C4 remains the only source of exit reason, target reduction fraction, and target token quantity.

## Marking open positions

When C4 returns usable `current_price_usd`, C5 keeps C3 unrealized accounting current by applying a C3 `PaperPositionMark` at the cycle timestamp after any exit execution attempt is processed.

C5 never marks from stale/future/unusable evidence that C4 did not expose as usable current price.

If a position fully closes during the cycle, no mark is applied afterward.

## Safe quote-aware C4 quantity -> SELL TradeIntent translation

This is the critical C5 bridge.

C4 intentionally outputs token quantity, while the stable B9 `TradeIntent` requests USD notional. Converting quantity with decision-time market price is unsafe: if actual SELL execution price is lower, C1 derives a larger token quantity and may oversell.

C5 therefore waits for the **same contemporaneous quote that C1 will execute**.

For a C4 target quantity `Q` and that quote's execution price `P`:

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

C5 does not use reference price, B2 market price, weighted entry, or a stale earlier quote for this conversion.

## Exit quote eligibility

C5 does not construct a SELL intent from future quote evidence.

For C1 latency `L`, an exit decision at `T`, and quote observed at `Q`:

- if `Q > cycle.as_of`: no intent; future evidence is not consumed,
- if `Q < T + L`: no intent yet; quote is before the C1 execution-eligibility boundary,
- otherwise, if the quote has a positive execution price, C5 may construct the quantity-safe SELL intent and then lets C1 apply its existing quote-window, route, missing-field, slippage, partial-fill, and failure rules.

A quote later than C1's maximum quote window is still passed to C1 once it is otherwise eligible; C1 remains authoritative for the terminal `QUOTE_TOO_LATE` result.

If quote execution price is unavailable, C5 does not fabricate a requested notional. The exit remains requested by C4, but no executable SELL intent can yet be formed.

## SELL intent metadata

A C5 SELL intent reuses the original position lifecycle's earliest linked BUY ledger entry for:

```text
strategy_name
strategy_version
score_policy_version
decision_policy_version
risk_policy_version
```

This avoids fake placeholder versions and preserves which entry strategy created the lifecycle.

Other fields:

```text
mint = position mint
side = SELL
max_slippage_bps = pinned PaperLoopPolicy.exit_max_slippage_bps
reason = C4 primary_reason value
execution_mode = PAPER
as_of_unix_ms = C4 decision as_of
```

The SELL idempotency key is deterministic SHA-256 over a versioned identity containing:

```text
position_id
exit_policy_version
exit_decision_as_of
primary_exit_reason
target_quantity (stable float hex encoding)
```

Replaying the same C4 exit decision produces the same key. A later retry from a new C4 timestamp produces a new key only after the earlier terminal attempt is no longer active.

## Exit execution and accounting

Once a SELL intent exists, C5 uses exactly:

```text
SELL TradeIntent -> C1 execute_paper_intent -> C3 apply_paper_execution
```

No alternate fill calculation or accounting path is allowed.

C1 remains authoritative for:

- route availability,
- latency/quote window,
- executable notional,
- partial fills,
- slippage,
- swap/network costs,
- failed-after-submission costs.

C3 remains authoritative for:

- token quantity reduction,
- cost-basis release,
- realized PnL,
- cash,
- journal/idempotency,
- full lifecycle close.

## Fill-confirmed take-profit advancement

After an APPLIED terminal SELL booking, C5 retrieves the C3 before/after position snapshots and calls C4 `acknowledge_exit_fill`.

A take-profit level advances only when booked C3 quantity reduction reaches the C4 target quantity or the position fully closes.

Consequences:

- no-fill -> level remains incomplete,
- failed SELL -> level remains incomplete,
- undersized partial fill -> level remains incomplete,
- exact target -> level completes,
- larger-than-target booked reduction -> level completes,
- full close -> level completes when take-profit driven.

C5 never marks a take-profit level complete from a requested intent or simulated decision alone.

## Stronger exit evidence on later cycles

C5 does not persist a separate pending C4 exit decision. It persists only the evolving C4 `ExitState`.

If one cycle requests REDUCE but no eligible quote exists, the next cycle reassesses the position from fresh point-in-time evidence. A later emergency/full-exit signal can therefore supersede an earlier take-profit request naturally through C4 precedence.

This avoids stale pending-exit orders blocking stronger new exit evidence.

## Exit state lifecycle

After each C4 assessment, the managed record adopts `assessment.next_state`.

After an APPLIED SELL, fill acknowledgement may further advance `completed_take_profit_levels`.

- position remains OPEN -> keep one managed record,
- position becomes CLOSED -> remove its managed record,
- no C3 quantity mutation -> retain state without falsely completing TP levels.

## Cycle output and auditability

C5 does not add persistence yet; C6 owns restart/accounting validation. Each `run_paper_cycle` returns a complete immutable `PaperCycleResult` containing:

```text
policy_version
as_of_unix_ms
next_state
pending_entry_result
entry_results
exit_results
findings
```

### Entry result

Each candidate result preserves as applicable:

```text
mint
setup assessment
score assessment
decision
risk assessment
selected_for_entry
execution result
ledger update
orchestration reason
```

### Exit result

Each monitored position result preserves as applicable:

```text
position_id
mint
exit assessment
constructed SELL intent
execution result
ledger update
orchestration reason
```

This makes the cycle reconstructable by the caller without adding a second durable database before C6.

## Orchestration reason codes

C5 reason codes describe only coordination state; they do not replace B/C-domain reasons.

Stable initial codes:

```text
CYCLE_APPLIED
CYCLE_BEFORE_STATE
PENDING_ENTRY_DEFERRED
PENDING_ENTRY_TERMINAL
ENTRY_NOT_SELECTED
ENTRY_OPEN_POSITION_EXISTS
ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH
ENTRY_SELECTED
ENTRY_EXECUTION_DEFERRED
ENTRY_EXECUTION_TERMINAL
EXIT_OBSERVATION_MISSING
EXIT_HOLD
EXIT_QUOTE_MISSING
EXIT_QUOTE_AFTER_CYCLE
EXIT_QUOTE_BEFORE_LATENCY
EXIT_EXECUTION_PRICE_UNAVAILABLE
EXIT_INTENT_CREATED
EXIT_EXECUTION_TERMINAL
EXIT_POSITION_MARKED
EXIT_POSITION_CLOSED
```

Each entry/exit result carries exactly one orchestration reason. The underlying setup/score/decision/risk/C1/C3/C4 reason objects remain available separately.

## No production defaults

C5 ships no:

- starting capital,
- entry threshold,
- risk threshold,
- exit threshold,
- paper-fill assumptions,
- exit slippage limit,
- setup ordering recommendation.

All such values are explicit caller-supplied research configuration.

The one-new-entry-attempt-per-cycle restriction is a temporal/risk-context correctness invariant, not a claimed optimal trading cadence.

## Point-in-time rules

C5 must never:

- consume a cycle earlier than prior loop state,
- use future quote evidence to construct a SELL intent,
- initialize exit state from market evidence observed after the actual position lifecycle existed,
- mark positions from evidence C4 rejected as unusable,
- reuse a pending BUY's slot to create another simultaneous BUY,
- use decision-time price to convert C4 token quantity into a SELL notional.

## Error handling

Domain contradictions that existing engines model as assessments/results remain results; C5 does not raise merely because a candidate is rejected, watched, risk-rejected, execution-failed, or exit-held.

C5 model constructors raise `ValueError` for malformed immutable input shapes such as:

- duplicate candidate mint within one cycle,
- duplicate quote mint within one cycle,
- duplicate exit observation position ID,
- malformed managed-position identity,
- inconsistent pending-entry mode/exit policy.

A cycle chronology violation returns a fail-closed `PaperCycleResult` with the exact previous state unchanged.

## Public C5 API

The stable public package API is intended to expose:

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
PendingPaperEntry
create_paper_loop_state
run_paper_cycle
```

No provider/RPC/storage/signer/transaction/live-execution object is public from C5.

## Explicit non-goals

C5 does not add:

- provider or RPC calls,
- raw observation ingestion,
- B1 safety calculation changes,
- B2 feature-schema changes,
- new setup families,
- Smart Wallet Cluster,
- scoring/decision/risk changes,
- C1 fill-model changes,
- C3 accounting formula changes,
- C4 exit-rule changes,
- durable restart persistence,
- Parquet export,
- wallet reconstruction,
- signer/wallet secrets,
- Solana transaction construction,
- transaction submission,
- live mode.

C6 is the next phase and will validate/persist/recover autonomous accounting across partial exits, multiple positions, wins/losses, failed fills, and restarts.

## Success criterion

C5 is complete when one immutable state machine can, across repeated point-in-time cycles:

- evaluate existing candidate setups,
- score/decide/risk-size through the existing path,
- carry a deferred BUY until terminal,
- book actual paper BUYs,
- initialize C4 state at lifecycle open,
- monitor every pre-existing OPEN position,
- construct quantity-safe quote-aware SELL intents only when possible,
- route every SELL through C1 and C3,
- fill-confirm take-profit advancement,
- keep marks/accounting current from usable evidence,
- preserve auditable per-cycle results,
- and do all of the above with live execution still impossible.