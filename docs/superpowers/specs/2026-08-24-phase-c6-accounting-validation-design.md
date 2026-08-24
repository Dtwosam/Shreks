# Phase C6 Accounting Validation and Restart Recovery Design

## Goal

Complete source-order Phase C by proving that autonomous PAPER state remains economically reconcilable across partial exits, multiple positions, wins, losses, failed fills, and real process restarts.

C6 does not add strategy logic, alter fill/accounting math, or enable live money. It validates and durably checkpoints the already-sealed C3/C5 state.

## Source requirements

The build order requires C6 to ensure portfolio values reconcile after:

- partial exits,
- multiple positions,
- losses,
- wins,
- failed fills,
- restarts.

The Phase C exit criterion is autonomous realistic paper trading for extended periods with a complete and reconcilable trade history.

The master source additionally requires:

- SQLite in WAL mode as V1 shared operational state,
- state recovery after process restart from the operational database,
- restart/recovery and idempotency tests,
- no unresolved accounting defects before live promotion,
- no live execution before proof.

## Architectural boundary

C6 uses the existing architecture rather than inventing a new persistence service:

- Rust `shreks-storage` remains the owner of SQLite schema migrations.
- Python `shreks_brain.paper_validation` owns paper accounting validation, canonical state encoding/decoding, and reads/writes the C6 checkpoint table through Python's stdlib `sqlite3`.
- C3 remains the sole authority for fill booking, cost basis, realized/unrealized PnL, cash, costs, journal sequence, and position lifecycle.
- C5 remains the sole authority for autonomous orchestration state.
- C6 never reimplements a trade fill, risk decision, exit decision, or PnL mutation.

No Redis, hosted database, pickle, arbitrary object deserialization, provider read, RPC call, wall-clock read, signer, transaction construction, or live execution is introduced.

## Operational database migration

Rust migration `0006_paper_loop_checkpoints.sql` adds one append-only table:

```sql
CREATE TABLE paper_loop_checkpoints (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    checkpoint_schema_version TEXT NOT NULL,
    state_as_of_unix_ms INTEGER NOT NULL CHECK (state_as_of_unix_ms >= 0),
    created_at_unix_ms INTEGER NOT NULL CHECK (created_at_unix_ms >= 0),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);

CREATE INDEX idx_paper_loop_checkpoints_run_latest
    ON paper_loop_checkpoints (run_id, sequence DESC);
```

The table stores immutable checkpoints rather than mutating one current-state row. This preserves recovery history and makes rollback/collision detection explicit.

Python does not create or migrate this table. If the operational database has not been migrated by `shreks-storage`, C6 fails closed with a schema error.

## Accounting validation

Public function:

```python
validate_paper_accounting(state: PaperLoopState) -> AccountingValidationReport
```

It independently recomputes accounting identities from C3 journal/position evidence without mutating state.

### Required portfolio identities

Cash:

```text
expected_cash = starting_cash + sum(entry.cash_flow_usd)
```

Realized PnL:

```text
expected_realized = sum(entry.realized_pnl_delta_usd)
```

Accumulated costs:

```text
expected_costs = sum(entry.explicit_cost_usd)
```

For each lifecycle:

```text
position.realized_pnl = sum(linked entry realized deltas)
position.accumulated_costs = sum(linked entry explicit costs)
```

Running journal quantity for a lifecycle is:

```text
BUY filled quantity - SELL filled quantity
```

and must match the final C3 position quantity within the same fixed arithmetic tolerance used for accounting validation.

### Equity/PnL identity

When every OPEN position has a current C3 mark:

```text
open_market_value = sum(open quantity * mark price)
equity = cash_balance + open_market_value
net_pnl = equity - starting_cash
expected_net_pnl = realized_pnl + unrealized_pnl
```

`net_pnl` and `expected_net_pnl` must reconcile.

Already-incurred costs are embedded in C3 realized/open-basis accounting and are **not** subtracted again.

If any OPEN position is unmarked, structural accounting can still reconcile but total marked portfolio equity is unknown. The report is `INCOMPLETE`, not falsely zero-filled or declared invalid.

### Scenario evidence counters

The report records deterministic counts needed by the C6 source criterion:

- journal entry count,
- terminal failure count,
- lifecycle count,
- OPEN/CLOSED lifecycle count,
- partial lifecycle reduction count,
- winning closed lifecycle count,
- losing closed lifecycle count,
- flat closed lifecycle count.

A lifecycle partial reduction is a SELL that leaves positive running quantity after the booked reduction, independent of whether C1 labeled the requested SELL itself `PARTIAL` or `FILLED`.

## Validation status and findings

```text
RECONCILED
INCOMPLETE
INVALID
```

- `INVALID`: any structural/accounting identity fails.
- `INCOMPLETE`: identities known from booked evidence pass, but marked equity cannot be computed because at least one OPEN lifecycle lacks a mark.
- `RECONCILED`: all booked identities pass and marked equity/PnL reconcile.

Findings are deterministic, ordered, and explicit. C6 never repairs an invalid ledger.

## Canonical checkpoint format

Checkpoint schema version:

```text
c6-paper-state-v1
```

A checkpoint envelope contains:

```text
checkpoint_schema_version
run_id
sequence
created_at_unix_ms
state_as_of_unix_ms
state
```

`state` is the exact immutable `PaperLoopState` encoded through a safe allow-listed codec.

### Safe typed encoding

The codec supports only:

- `None`, bool, int, str,
- finite Python floats encoded by `float.hex()` for exact round-trip,
- tuples,
- frozensets sorted by canonical encoded representation,
- explicitly allow-listed enums,
- explicitly allow-listed frozen dataclasses reachable from `PaperLoopState`.

Every enum/dataclass contains an explicit type tag. Decode resolves tags only through a fixed registry of Shreks domain classes. Unknown tags, unsupported values, non-finite floats, malformed envelopes, missing/extra dataclass fields, or constructor invariant failures reject.

`pickle`, `eval`, dynamic import, arbitrary class paths, and executable deserialization are forbidden.

Canonical JSON uses sorted keys, compact separators, UTF-8, and `allow_nan=False`.

`payload_sha256` is SHA-256 of the exact canonical UTF-8 payload bytes.

## Durable checkpoint record

Public record:

```text
run_id
sequence
checkpoint_schema_version
state_as_of_unix_ms
created_at_unix_ms
payload_sha256
state
```

The decoded state must equal the state encoded in the payload and must pass all existing C3/C5 constructor invariants.

## Save semantics

```python
save_paper_checkpoint(
    database_path,
    run_id,
    sequence,
    state,
    created_at_unix_ms,
) -> PaperCheckpointRecord
```

Rules:

1. `run_id` non-empty; sequence/timestamp non-negative.
2. checkpoint time cannot precede `state.last_cycle_at_unix_ms`.
3. the migrated `paper_loop_checkpoints` table must already exist.
4. encode canonical payload + checksum before opening the transaction.
5. use SQLite `BEGIN IMMEDIATE` for one atomic append.
6. if `(run_id, sequence)` does not exist, insert it.
7. if it exists with byte-identical payload/checksum, return the existing record idempotently.
8. if it exists with different payload, fail with sequence collision.
9. a new sequence below the current maximum for that run is rejected as non-monotonic.
10. no older row is modified or deleted.

The function never invents a timestamp; `created_at_unix_ms` is explicit evidence supplied by the caller.

## Load/restart semantics

```python
load_latest_paper_checkpoint(database_path, run_id) -> PaperCheckpointRecord | None
```

Loading:

1. reads the highest sequence for `run_id`,
2. verifies table-row metadata against the envelope,
3. recomputes SHA-256 before decode,
4. decodes only allow-listed types,
5. reconstructs C3/C5 immutable state so existing invariants run again,
6. returns the exact restart state.

No checkpoint returns `None`; corruption or incompatibility raises `PaperCheckpointError` and fails closed.

## Restart equivalence

```python
validate_restart_equivalence(
    expected: PaperLoopState,
    restored: PaperLoopState,
) -> RestartValidationReport
```

The report compares:

- exact immutable state equality,
- canonical state SHA-256,
- C6 accounting status/metrics before and after,
- ledger journal keys/order,
- cash/PnL/cost values,
- positions and lifecycle state,
- C4 managed/pending exit state,
- pending BUY state,
- pinned C1/C5 policies,
- loop timestamp.

Restart validation does not weaken equality to a small subset of fields.

## Process-restart proof

C6 tests must persist a non-trivial C5 state to a file-backed SQLite database, close every connection/object reference representing the running process, reopen the database, load the latest checkpoint, and continue a later paper cycle from the restored state.

This is stronger than encode/decode in one process and directly tests the source restart requirement.

## Required scenario tests

C6 integration coverage must use real C1/C3/C5 domain functions and include:

1. a winning lifecycle,
2. a losing lifecycle,
3. multiple positions in the same ledger,
4. at least one lifecycle partial reduction,
5. at least one failed-after-submission cost,
6. marked open-position equity where applicable,
7. durable checkpoint/reopen/restore,
8. post-restart continuation without duplicate terminal booking,
9. final C3/C6 reconciliation after continuation.

No test may directly inject impossible economics merely to make totals balance.

## Public package boundary

C6 package:

```text
shreks_brain.paper_validation
```

Expected stable public API:

```text
AccountingFinding
AccountingFindingCode
AccountingValidationReport
AccountingValidationStatus
PaperCheckpointError
PaperCheckpointRecord
RestartValidationReport
decode_paper_checkpoint
encode_paper_checkpoint
load_latest_paper_checkpoint
save_paper_checkpoint
validate_paper_accounting
validate_restart_equivalence
```

No raw SQLite connection, dynamic type registry, migration helper, signer, transaction, provider, or live-execution function is public.

## Scope exclusions

C6 does not:

- change C1 fill math,
- change C3 accounting math,
- change C4 exits,
- change C5 strategy/orchestration behavior,
- add backtesting/ML/wallet intelligence,
- reconcile live/onchain balances,
- introduce continuous deployment or monitoring,
- choose promotion thresholds,
- enable live execution.

Onchain balance/fill reconciliation remains a future live-execution concern because C6 is PAPER-only.
