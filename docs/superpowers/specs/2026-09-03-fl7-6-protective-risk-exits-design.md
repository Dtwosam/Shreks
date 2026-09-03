# FL7.6 Fast PAPER Protective Risk Exits — Design

## Status

Design for build-order phase **FL7.6 Protective risk exits**.

Base: FL7.5 is SEALED at merged-main commit `092c3026b59a4e0f3464f115c571407c78052076` with fresh push-triggered merged-main CI run `33762471582` four-gate green.

LIVE remains disabled.

## Build-order requirement

The canonical build order says:

> **FL7.6 Protective risk exits** — Existing hard stops, trailing stops, max hold, liquidity emergency, and global halt remain available as independent protective backstops.

The FL7 exit criterion is:

> Shreks can PAPER trade event-driven strategies with realistic costs/latency/capacity and reconciled accounting.

FL7.6 must therefore connect the already-sealed C4 protective exit authority to the already-sealed FL7.1/FL7.4/FL7.5 Fast PAPER path without inventing another stop formula, another exit executor, another ledger, or another persisted execution intent.

## Goal

Add one deterministic protective arbitration layer that:

- keeps C4 `assess_exit(...)` authoritative for protective trigger semantics and precedence;
- permits only the C4 rules named by FL7.6: hard stop, trailing stop, max hold, liquidity/executability emergency, and global halt;
- excludes C4 take-profit, wallet-distribution, flow-deterioration, and momentum-deterioration rules from the protective lane because those are strategy-like exits rather than FL7.6 backstops;
- evaluates protection before the final FL7.1 assessment is recorded;
- lets a protective C4 `EXIT` override any strategy `HOLD`, `REDUCE`, or `SELL` with a full-quantity Fast PAPER `SELL`;
- leaves the strategy FL7.4 approval byte-for-byte unchanged when C4 does not require a protective exit;
- never emits `BUY` or `SKIP` for an open position;
- preserves C4 high-water state across restart so trailing-stop authority cannot disappear after a crash;
- routes any resulting SELL through the existing FL7.4 adapter, which remains the only Fast PAPER open-position execution boundary;
- keeps C1/C3/FL7.5 fill, cost, accounting, idempotency, and reconciliation authority unchanged.

No production numeric defaults are introduced.

## Authority boundaries

### C4 remains the protective trigger authority

FL7.6 does not recalculate price return, high-water drawdown, position age, liquidity thresholds, impact thresholds, capacity fractions, or C4 trigger precedence.

It calls the sealed C4 public API:

```python
create_exit_state(position, exit_policy)
assess_exit(position, features, context, exit_state, exit_policy)
```

and consumes the returned `ExitAssessment`.

The existing C4 precedence remains unchanged:

1. global halt;
2. maximum hold;
3. route unavailable;
4. liquidity below minimum;
5. exit impact too high;
6. exit capacity too low;
7. hard stop;
8. trailing stop.

The later C4 strategy-style triggers are impossible in FL7.6 because the protective policy rejects them at construction time.

C4 evidence-quality and structural semantics also remain unchanged. FL7.6 does not reinterpret stale/missing evidence as a fabricated stop signal.

### FL7.4 remains the execution authority

FL7.6 does not create a `TradeIntent`, consume a quote, simulate latency, calculate USD notional, or mutate the ledger.

It returns a normal `FastPaperPositionActionApproval`. The caller passes that approval to the sealed:

```python
apply_fast_paper_position_action(...)
```

FL7.4 then remains authoritative for:

- preserved action timestamp;
- pending SELL precedence;
- quote identity/time validation;
- base-quantity to current USD-notional conversion;
- C1 execution;
- C3 ledger application;
- partial-fill behavior;
- failed-after-submission cost booking;
- idempotency.

### FL7.5 remains the accounting/restart base authority

FL7.6 does not replace `FastPaperRuntimeState`. Instead it wraps the sealed FL7.5 runtime state with the additional C4 policy/state required by trailing-stop restart safety.

This additive wrapper preserves the FL7.5 `fl7.5-v1` checkpoint contract unchanged and introduces a new schema namespace for FL7.6 protected runtime checkpoints.

## Why arbitration must happen before FL7.1 records the event

FL7.5 restart validation requires every pending FL7.4 exit approval to be backed by the exact `FastPaperActionAssessment` stored in the corresponding FL7.1 `FastPaperEventRecord`.

Therefore FL7.6 cannot:

1. record a strategy `HOLD`, then
2. separately invent a protective `SELL` approval for the same event.

That would create two action authorities for one event and make the pending SELL impossible to validate after restart.

Instead FL7.6 wraps the FL7.1 evaluator boundary. On a genuinely new material event:

1. invoke the caller's strategy approval evaluator exactly once;
2. validate that its assessment belongs to the triggering update and authoritative position;
3. call C4 protection exactly once;
4. resolve the final approval;
5. return the final assessment to `run_fast_paper_event(...)` so FL7.1 records exactly the authority that FL7.4 may execute.

On `REPLAYED` or `IGNORED_NON_MATERIAL`, FL7.1 does not call its evaluator. Therefore FL7.6 also must not call strategy logic, C4 protection, or advance protective high-water state.

## Protective policy

New immutable policy:

```python
FAST_PAPER_PROTECTIVE_EXIT_VERSION = "fl7.6-v1"
FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY = "protective-risk"

@dataclass(frozen=True, slots=True)
class FastPaperProtectiveExitPolicy:
    version: str
    exit_policy: ExitPolicy
```

`version` is an explicit caller-supplied FL7.6 policy/configuration version. It has no production default.

`exit_policy` remains the sealed C4 `ExitPolicy` and therefore carries all numeric thresholds and C4 evidence-age requirements.

To be accepted for the FL7.6 protective lane, the C4 policy must have all strategy-style exits disabled:

```text
take_profit_levels == ()
flow_exit_max_buy_fraction_m5 is None
flow_exit_max_buy_pressure_acceleration is None
momentum_exit_max_return_1m_pct is None
momentum_exit_max_return_5m_pct is None
wallet_distribution_enabled is False
```

The allowed protective inputs remain:

- `hard_stop_loss_pct`;
- `trailing_activation_return_pct` + `trailing_stop_drawdown_pct`;
- `max_hold_seconds`;
- `min_liquidity_usd`;
- `max_exit_price_impact_pct`;
- `min_exit_capacity_fraction`;
- C4 route availability;
- `global_halt_active`.

A policy may leave individual numeric rules disabled. Global halt and explicit route-unavailable protection remain available through C4 even when every optional numeric threshold is `None`.

## Strategy approval evaluator

The protected event wrapper consumes a callback:

```python
FastPaperPositionApprovalEvaluator = Callable[
    [FastPaperMaterialUpdate],
    FastPaperPositionActionApproval,
]
```

The callback must return a normal FL7.4 approval for the current authoritative OPEN position.

The returned approval must match the triggering update on:

- `source_event_id`;
- `market_key`;
- `source_sequence`;
- `as_of_unix_ms`;
- `state_version`.

Its action must already be one of `HOLD / REDUCE / SELL` by FL7.4 model validation.

Its position ID and mint must match the supplied authoritative C3 `PaperPosition`.

The strategy evaluator remains responsible for explicit REDUCE/SELL base-quantity authority. FL7.6 never invents a reduction fraction.

## Protective resolution

C4 protective evaluation uses the same decision timestamp as the material update:

```text
features.as_of_unix_ms == update.as_of_unix_ms
context.as_of_unix_ms == update.as_of_unix_ms
```

C4 receives the authoritative OPEN position, caller-supplied `FeatureVector`, caller-supplied `ExitExecutionContext`, persisted `ExitState`, and the validated protective `ExitPolicy`.

### C4 HOLD

If C4 returns `DecisionAction.HOLD`:

- the applied approval is exactly the strategy approval object;
- strategy action, family, version, reasons, and target quantity remain unchanged;
- the returned next protective state is C4's `next_state`, including any new high-water price/time;
- FL7.6 does not add a reason or rewrite strategy attribution.

### C4 EXIT

If C4 returns `DecisionAction.EXIT`:

- FL7.6 produces a new Fast PAPER assessment bound to the same event identity/time/version as the strategy assessment;
- `action = FastPaperAction.SELL`;
- `strategy_family = "protective-risk"`;
- `strategy_version = FastPaperProtectiveExitPolicy.version`;
- target base quantity equals the authoritative current full OPEN position quantity;
- position/mint/quote/state identifiers are copied from the validated strategy approval;
- C4 ordered findings become ordered `protective:<REASON_CODE>` reasons;
- the original strategy action is preserved as `strategy_action:<ACTION>`;
- the original ordered strategy reasons are appended as `strategy:<reason>` values for auditability.

The first reason is always the C4 primary protective reason.

Example:

```text
protective:HARD_STOP_TRIGGERED
strategy_action:HOLD
strategy:continuation_conditions_met
```

This records that the final executable authority came from the protective lane while still preserving what the deterministic strategy wanted at the same event.

### Unexpected C4 REDUCE

A protective-only C4 policy cannot legitimately produce `DecisionAction.REDUCE`; C4 uses REDUCE only for take-profit behavior, which FL7.6 forbids.

If a REDUCE nevertheless appears, FL7.6 raises a typed error rather than silently converting it.

## Public protected-event contract

New package files:

- `python/src/shreks_brain/fast_paper/protective_models.py`
- `python/src/shreks_brain/fast_paper/protective.py`

Stable public names:

```python
FAST_PAPER_PROTECTIVE_EXIT_VERSION = "fl7.6-v1"
FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY = "protective-risk"

class FastPaperProtectiveExitError(ValueError): ...

FastPaperPositionApprovalEvaluator = Callable[
    [FastPaperMaterialUpdate],
    FastPaperPositionActionApproval,
]

@dataclass(frozen=True, slots=True)
class FastPaperProtectiveExitPolicy:
    version: str
    exit_policy: ExitPolicy

@dataclass(frozen=True, slots=True)
class FastPaperProtectiveEventResult:
    version: str
    event_result: FastPaperEventResult
    strategy_approval: FastPaperPositionActionApproval | None
    applied_approval: FastPaperPositionActionApproval | None
    protective_assessment: ExitAssessment | None
    next_protective_state: ExitState
    protective_triggered: bool

create_fast_paper_protective_exit_state(...)
run_fast_paper_protective_event(...)
```

`run_fast_paper_protective_event(...)` accepts:

- current `FastPaperLoopState`;
- one `FastPaperMaterialUpdate`;
- authoritative current OPEN `PaperPosition`;
- C4 `FeatureVector`;
- C4 `ExitExecutionContext`;
- current C4 `ExitState`;
- `FastPaperProtectiveExitPolicy`;
- `FastPaperPositionApprovalEvaluator`.

It does not accept a quote, fill policy, ledger, provider, signer, or runtime mode because it has no execution authority.

## Replay and non-material behavior

The wrapper delegates replay/order/materiality to sealed FL7.1.

For `REPLAYED` and `IGNORED_NON_MATERIAL`:

- strategy evaluator invocation count remains zero;
- C4 is not evaluated;
- `strategy_approval is None`;
- `applied_approval is None`;
- `protective_assessment is None`;
- `next_protective_state` is exactly the input state;
- `protective_triggered is False`.

This prevents replay from moving high-water state or creating duplicate action authority.

## Restart-safe protected runtime

Trailing stops require durable high-water state. The sealed C3 ledger only persists the latest mark, not the historical maximum, so a restart cannot safely reconstruct C4 `ExitState.high_water_price_usd` from the ledger alone.

FL7.6 therefore adds an additive wrapper rather than modifying the sealed FL7.5 runtime contract.

New model file:

- `python/src/shreks_brain/paper_validation/protected_models.py`

Stable names:

```python
FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION = "fl7.6-v1"
FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION = "fl7.6-fast-paper-protected-state-v1"

@dataclass(frozen=True, slots=True)
class FastPaperProtectedRuntimeState:
    version: str
    base_runtime_state: FastPaperRuntimeState
    protective_policy: FastPaperProtectiveExitPolicy
    protective_states: tuple[ExitState, ...]

@dataclass(frozen=True, slots=True)
class FastPaperProtectedCheckpointRecord:
    run_id: str
    sequence: int
    checkpoint_schema_version: str
    state_as_of_unix_ms: int
    created_at_unix_ms: int
    payload_sha256: str
    state: FastPaperProtectedRuntimeState
```

`FastPaperProtectedRuntimeState` invariants:

- version exactly `fl7.6-v1`;
- `base_runtime_state` is a valid sealed FL7.5 `FastPaperRuntimeState`;
- protective policy is valid and its embedded C4 policy is protective-only;
- protective states use unique position IDs;
- protective states exactly cover authoritative OPEN positions in the base runtime ledger;
- each state position ID and mint matches its C3 position;
- each state policy version equals `protective_policy.exit_policy.version`;
- each state initialized time equals the C3 position open time;
- each state last-evaluated/high-water time does not exceed base runtime time;
- each high-water price is at least the C3 weighted entry price within the preserved strict tolerance.

Closed positions carry no protective state.

## Protected checkpoint contract

FL7.6 extends the existing safe Fast PAPER codec additively. It does not change FL7.5's constants or old encode/decode functions.

New public functions:

```python
encode_fast_paper_protected_checkpoint(...)
decode_fast_paper_protected_checkpoint(...)
save_fast_paper_protected_checkpoint(...)
load_latest_fast_paper_protected_checkpoint(...)
validate_fast_paper_protected_restart_equivalence(...)
```

The codec continues to use only:

- allow-listed dataclasses/enums;
- finite float hex encoding;
- tuples/frozensets;
- canonical JSON;
- SHA-256;
- the existing append-only `paper_loop_checkpoints` SQLite table.

No pickle, eval, dynamic import, provider object, quote object, transaction object, or secret is persisted.

The new protected schema namespace is exclusive per run ID. A run ID containing:

- legacy C6 checkpoint rows;
- FL7.5 `fl7.5-fast-paper-state-v1` rows; or
- any other schema

must be rejected by protected save/load, and vice versa.

No SQLite migration is required.

The protected restart-equivalence report reuses `FastPaperRestartValidationReport` and reconciles the authoritative C3 ledger through the existing `validate_paper_ledger` body.

## Trailing-stop restart proof

The decisive FL7.6 restart test must prove behavior, not only serialization.

Test sequence:

1. create an OPEN position;
2. initialize C4 protective state;
3. evaluate a higher price that activates/raises the trailing high-water state without exiting;
4. wrap the FL7.5 runtime and save a protected checkpoint;
5. reopen the file-backed SQLite database and restore the protected state;
6. verify exact restart equivalence;
7. evaluate a lower current price that breaches the configured trailing drawdown;
8. require FL7.6 to produce a protective full-quantity SELL approval using the restored high-water state.

If the high-water state is lost or reconstructed only from the latest mark, this test must fail.

## Test matrix

FL7.6 tests must prove:

1. public versions/family are stable;
2. protective policy rejects take-profit configuration;
3. protective policy rejects wallet/flow/momentum exit configuration;
4. no protective trigger leaves strategy HOLD unchanged;
5. no protective trigger leaves explicit strategy REDUCE quantity unchanged;
6. hard stop overrides strategy HOLD with full SELL;
7. trailing stop overrides strategy REDUCE with full SELL;
8. max hold overrides strategy HOLD even when ordinary market evidence is stale, matching C4 semantics;
9. global halt overrides strategy HOLD even when ordinary market evidence is stale, matching C4 semantics;
10. route unavailable triggers full protective SELL;
11. liquidity below minimum triggers full protective SELL;
12. exit impact above maximum triggers full protective SELL;
13. exit capacity below minimum triggers full protective SELL;
14. C4 precedence/reason ordering remains stable when multiple protective triggers coexist;
15. protective reasons preserve original strategy action/reasons for audit;
16. strategy approval/update identity mismatch fails closed;
17. protected result never emits BUY/SKIP;
18. non-material event does not invoke strategy or move protective state;
19. exact replay does not invoke strategy or move protective state;
20. a protective approval can be passed directly to FL7.4 and close the authoritative PAPER position through C1/C3;
21. protected runtime requires exact OPEN-position state coverage;
22. protected runtime rejects policy/state/position identity contradictions;
23. protected checkpoint is byte-stable and round-trips exactly;
24. protected/FL7.5/legacy schema namespaces cannot mix under one run ID;
25. file-backed protected restart preserves trailing high-water state and still triggers the expected SELL;
26. existing FL7.5 checkpoint functions remain green and unchanged in behavior;
27. existing C4, FL7.1, FL7.4, FL7.5 and accounting suites remain green.

## Scope exclusions

FL7.6 does **not**:

- calibrate stop thresholds;
- add production default thresholds;
- alter C4 trigger equations or precedence;
- use C4 take-profit/wallet/flow/momentum exits in the protective lane;
- choose Fast Lane strategy REDUCE quantity;
- request quotes or provider/RPC data;
- construct or sign Solana transactions;
- change C1 fill/slippage/fee behavior;
- change C3 position/PnL/accounting math;
- alter FL7.4 pending-exit/idempotency semantics;
- alter the sealed FL7.5 checkpoint schema or constants;
- add a SQLite migration;
- enable LIVE;
- claim profitability.

## Completion boundary

FL7.6 is complete only when:

1. intentional RED proves the new public FL7.6 API is absent while repository safety, Rust, and ARM64 remain green;
2. candidate CI passes all four canonical gates;
3. exact scope and compatibility audits pass;
4. clean exact-head CI passes all four canonical gates;
5. guarded merge accepts only that exact head;
6. fresh merged-main CI passes all four canonical gates.

At that point the **FL7 software exit criterion** is satisfied for the implemented/tested event-driven PAPER action path.

That still does **not** prove profitable edge, shadow acceptance, learned-model superiority, production runtime acceptance, or LIVE readiness. Those require later FL8+ and PAPER/shadow evidence.
