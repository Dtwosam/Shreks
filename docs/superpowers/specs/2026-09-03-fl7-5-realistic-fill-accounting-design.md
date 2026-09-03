# FL7.5 Realistic Fill and Accounting — Design

## Status

Design for build-order phase **FL7.5 Realistic fill and accounting**.

Base: FL7.4 is SEALED at merged-main commit `168bcabc2faf8093870c9f788b7e0fb1794e3239` with fresh push-triggered merged-main CI run `33760235149` four-gate green.

LIVE remains disabled.

## Build-order requirement

FL7.5 requires event-resolution PAPER actions to continue reconciling after partial fills, multiple reductions, failures, restarts, fees, and slippage.

The existing preserved authorities remain canonical:

- C1 `execute_paper_intent` owns PAPER latency, quote windows, capacity, partial fills, slippage, swap/network costs, and failed-after-submission costs.
- C3 `apply_paper_execution` owns quantity, basis release, cash, realized/unrealized PnL, costs, journal sequence/idempotency, and lifecycle state.
- C6 `paper_validation` owns independent accounting reconciliation and safe SQLite checkpoint semantics.
- FL7.1 owns the replayable event/action record.
- FL7.2 owns BUY compatibility into C1/C3.
- FL7.4 owns HOLD/REDUCE/SELL quantity authority and pending-exit latency preservation.

FL7.5 must connect these pieces for durable restart/reconciliation. It must not create a second fill engine, accounting ledger, or risk authority.

## Architectural gap

Legacy C6 checkpoints only `PaperLoopState`. Fast Lane PAPER state is split across:

1. FL7.1 `FastPaperLoopState`, which records material event/action identity and replay cursors;
2. the authoritative C3 `PaperLedger`;
3. optional deferred FL7.2 `FastPaperBuyApproval`, whose original action timestamp must survive a restart;
4. one FL7.4 `FastPaperPositionActionState` for each OPEN ledger lifecycle, including any pending REDUCE/SELL authority.

Checkpointing only the ledger would lose pending action authority. Checkpointing only the event loop would lose accounting. Reconstructing either from guesses would break auditability.

## Runtime bundle

Add immutable `FastPaperRuntimeState` under `shreks_brain.paper_validation`:

```text
version = "fl7.5-v1"
as_of_unix_ms
event_loop_state: FastPaperLoopState
ledger: PaperLedger
fill_policy: PaperFillPolicy
position_action_policy: FastPaperPositionActionPolicy
pending_buy: FastPaperBuyApproval | None
position_action_states: tuple[FastPaperPositionActionState, ...]
```

No quote, risk snapshot, transient SELL intent, provider object, wall clock, signer, or transaction object is persisted.

### Runtime invariants

- version must be exact;
- `as_of_unix_ms` is non-negative and must not precede the ledger, event cursors, pending BUY decision, or any position-action state clock;
- position-action state IDs are unique;
- position-action states exactly cover C3 OPEN positions and no CLOSED lifecycle;
- a pending position exit must name the same mint as its authoritative C3 position;
- a pending BUY cannot target a mint that is already OPEN;
- every persisted pending BUY/exit assessment must be byte-for-value equal to the matching FL7.1 recorded assessment for its `source_event_id`;
- missing or conflicting recorded action authority fails closed.

This keeps restart state causally linked to the action record that authorized it.

## Shared ledger reconciliation

C6 currently contains the correct independent ledger reconciliation math but exposes it only through `validate_paper_accounting(PaperLoopState)`.

Refactor without changing semantics:

```python
validate_paper_ledger(ledger: PaperLedger) -> AccountingValidationReport
validate_paper_accounting(state: PaperLoopState) -> AccountingValidationReport
```

The legacy function becomes a thin wrapper around the shared ledger validator. No accounting formulas or finding codes change.

FL7.5 adds:

```python
validate_fast_paper_accounting(state: FastPaperRuntimeState)
```

which delegates to `validate_paper_ledger(state.ledger)` after runtime-state constructor invariants have passed.

## Checkpoint storage

Reuse the already-migrated append-only C6 `paper_loop_checkpoints` table. No new SQLite migration is needed because the table already stores generic canonical payload text plus schema version/checksum.

Fast checkpoint schema:

```text
fl7.5-fast-paper-state-v1
```

A `run_id` becomes an exclusive checkpoint-schema namespace. Before any Fast PAPER insert/load:

- inspect all existing checkpoint schema versions for that `run_id`;
- if any row uses a different schema version, fail closed;
- never mix legacy C6 and Fast PAPER payloads under one run ID.

This prevents legacy loaders and Fast Lane loaders from silently interpreting each other's payloads while reusing the proven append-only table and transaction semantics.

## Safe canonical codec

Fast PAPER checkpoint serialization is allow-listed and non-executable, matching C6 principles:

- `None`, bool, int, str;
- finite floats encoded by `float.hex()`;
- tuples and canonical frozensets;
- explicit Fast PAPER/C3 enums;
- explicit frozen dataclasses reachable from `FastPaperRuntimeState`.

Unknown tags, raw JSON floats/arrays, non-finite values, extra/missing fields, unsupported types, checksum mismatch, or constructor invariant failure reject.

No pickle, eval, dynamic imports, arbitrary class paths, or executable deserialization.

Canonical JSON uses sorted keys, compact separators, UTF-8, and `allow_nan=False`.

## Fast checkpoint API

Add to `shreks_brain.paper_validation`:

```text
FAST_PAPER_RUNTIME_STATE_VERSION
FAST_PAPER_CHECKPOINT_SCHEMA_VERSION
FastPaperCheckpointError
FastPaperCheckpointRecord
FastPaperRestartValidationReport
FastPaperRuntimeState
encode_fast_paper_checkpoint
decode_fast_paper_checkpoint
save_fast_paper_checkpoint
load_latest_fast_paper_checkpoint
validate_fast_paper_accounting
validate_fast_paper_restart_equivalence
validate_paper_ledger
```

No raw SQLite connection or codec registry is public.

## Save/load semantics

Save mirrors proven C6 behavior:

1. validate run ID, sequence, state, creation time;
2. reject creation time before runtime state;
3. require the existing C6 checkpoint table;
4. require schema-exclusive run ID;
5. canonical encode and SHA-256 before transaction;
6. `BEGIN IMMEDIATE`;
7. exact repeated `(run_id, sequence)` payload is idempotent;
8. conflicting sequence rejects;
9. sequence below existing maximum rejects;
10. append only; never mutate/delete older checkpoints.

Load selects latest sequence for the run, requires schema exclusivity, verifies row/envelope metadata and checksum, decodes only allow-listed types, reruns all constructors, and returns exact immutable state.

## Restart equivalence

`validate_fast_paper_restart_equivalence(expected, restored)` compares:

- exact runtime-state equality;
- canonical state fingerprint;
- shared C3 accounting report;
- event-loop records/cursors;
- processed intent keys and journal order through exact state equality;
- pending BUY authority;
- all per-position pending exit authority;
- pinned fill/action policy values.

Accounting `INVALID` makes restart equivalence fail.

## Required integration proof

FL7.5 tests use real FL7.1/FL7.2/FL7.4/C1/C3 functions and must demonstrate:

1. one exact Fast PAPER BUY opens a C3 lifecycle with realistic entry fee/slippage evidence;
2. first REDUCE is capacity-limited and books a real C1 partial fill/C3 quantity reduction;
3. a fresh later REDUCE books another independent reduction without reusing the prior intent key;
4. a failed-after-submission SELL attempt books the configured network cost but no fake fill;
5. accounting remains reconciled after those events;
6. the full Fast PAPER runtime state checkpoints to file-backed SQLite;
7. all live objects/connections are discarded and the checkpoint is reopened/restored;
8. restart equivalence is exact and processed terminal intents cannot be duplicated;
9. a post-restart fresh SELL closes the remaining lifecycle with current slippage/fees;
10. final accounting is reconciled and reports the expected partial-reduction/failure evidence counters.

A second test preserves a pending FL7.4 exit across checkpoint/restart and proves its original assessment timestamp/idempotency authority survives unchanged.

## Failure behavior

Fail closed on:

- runtime state/ledger/open-position mismatch;
- duplicate/missing position action states;
- pending authority not backed by the FL7.1 action record;
- mixed checkpoint schema under one run ID;
- sequence collision/regression;
- checksum or canonical-payload mismatch;
- malformed/unknown codec tags;
- any constructor invariant failure;
- invalid accounting after restore.

No repair or inferred state is allowed.

## Non-goals

FL7.5 does not:

- change C1 fill math;
- change C3 accounting math;
- change FL6 strategy decisions;
- choose REDUCE size;
- add protective risk exits (FL7.6);
- add production Fast Lane runtime integration (FL10);
- reconcile onchain/live balances;
- enable LIVE.

## Exit criterion

FL7.5 is complete when the event-resolution Fast PAPER state can be durably restored and continued through realistic partial fills, repeated reductions, failures, fees/slippage, and final lifecycle closure while the shared independent ledger validator remains reconciled and no action/accounting authority is fabricated.
