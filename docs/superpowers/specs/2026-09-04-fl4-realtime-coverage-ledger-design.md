# FL4 Realtime Coverage Ledger — Design

**Date:** 2026-09-04
**Base:** `3fcae8d476dc32c63582a8dc7699abaa08bfd60e`

## Status

Design slice after physical FL9 proof execution established that the deployed PAPER database contains
11,172,394 canonical FastEvents but zero FL4 future-path labels and zero Fast PAPER decision audit
rows.

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

FL4 correctly distinguishes:

- a complete horizon with no future market event; and
- an incomplete horizon where capture may have been unavailable.

The current production observer database does not durably preserve a canonical realtime continuity
boundary. Therefore a host-side label backfill cannot truthfully set
`FuturePathCoverage.contiguous = true` for historical intervals merely because FastEvents exist
before and after them.

Using event density, service uptime, wall-clock guesses, or a hand-authored flag as a substitute
would create false no-trade labels and contaminate downstream FL8/FL9 training evidence.

## Goal

Add an observe-only durable coverage ledger for the bounded Pump/PumpSwap realtime lane so future
FL4 labeling can prove that a decision horizon remained inside one uninterrupted capture session.

The design is deliberately conservative: coverage is proven only through actual notifications
received on one uninterrupted websocket session. Missing proof means incomplete, never complete.

## Capture-session identity

The live bounded realtime path gains a session envelope used only by the deployed observer path.
Existing parser fixtures and `PumpRealtimeSignalSource` compatibility stay intact.

A session changes when any of the following happens:

- the underlying websocket reconnects;
- the failover lane switches provider;
- the bounded public lane is rebuilt after retry exhaustion;
- the observer process restarts.

The failover wrapper emits a monotonically increasing in-process `session_sequence` for delivered
notifications. The sequence is not treated as globally durable identity. The SQLite writer creates
a durable row on the first notification it sees for a new in-process session.

## Durable schema

Migration 18 adds `fast_realtime_coverage_sessions`.

Each row stores:

- durable integer `session_id` primary key;
- provider;
- first received notification timestamp;
- last received notification timestamp;
- first notification slot;
- last notification slot;
- first notification signature;
- last notification signature;
- notification count;
- observer process-local session sequence.

Rows are append-only except that the current session row may monotonically extend its
`last_*` fields and notification count as more notifications arrive.

A new process never resumes an older session row.

## Coverage semantics

A coverage session proves only:

`[first_notification_observed_at_unix_ms, last_notification_observed_at_unix_ms]`

for that single uninterrupted websocket session.

It does **not** claim:

- that every Solana transaction was observed;
- that an interval before the first notification is covered;
- that an interval after the last notification is covered;
- that two adjacent sessions can be merged;
- that reconnect gaps were backfilled.

A future FL4 population labeler may set `contiguous = true` for a decision/horizon only when both
the decision observation time and the complete horizon end are enclosed by the same single session.

This intentionally discards otherwise plausible labels when continuity is not proven.

## Provider-session bridge

The bounded realtime stream already owns reconnect state. Add a live-only wrapper containing:

- the existing `PumpRealtimeNotification`;
- a monotonic in-process `session_sequence`.

Do not add coverage fields to the historical `PumpRealtimeNotification` parser contract.

The bounded stream increments connection generation after each successful new websocket
connection. The failover wrapper maps provider/index/rebuild-generation/connection-generation
changes onto its monotonic session sequence.

Existing `next_realtime_notification()` and `PumpRealtimeSignalSource` behavior remain unchanged.
The deployed observer uses the new session-aware forwarding path.

## Writer behavior

The realtime writer timestamps each received envelope using the same local observation clock already
used for raw Pump/PumpSwap persistence.

For every notification:

1. validate provider/signature identity as today;
2. open a new coverage row when session sequence differs from the writer's current session;
3. otherwise extend exactly that current row monotonically;
4. persist lifecycle/trade evidence through the existing code path.

Coverage persistence and raw evidence persistence share the same SQLite writer connection. A storage
error fails the supervised observer instead of silently dropping coverage evidence.

## Restart and reconnect behavior

Process restart intentionally begins a new durable coverage session even when the provider and first
slot resemble the previous row.

Internal reconnect/provider failover/rebuild intentionally begins a new session. Sessions are never
merged later.

This means a horizon crossing a reconnect remains incomplete even if post-reconnect events happen to
look continuous.

## Authority boundary

This slice adds no:

- strategy threshold;
- action selection;
- future-path label generation;
- PAPER fill or ledger mutation;
- model training;
- promotion;
- signer;
- transaction submission;
- LIVE authority.

It only records observation continuity evidence required by FL4.

## TDD requirements

Tests must prove:

1. migration 18 creates the exact coverage schema;
2. first notification opens one session;
3. repeated notifications in one session extend only monotonic end/count fields;
4. a new session sequence creates a new row;
5. provider switch creates a new live session;
6. bounded-stream reconnect/rebuild produces a new session sequence;
7. process restart cannot resume an existing coverage row;
8. existing realtime parser/writer behavior remains intact;
9. source/firewall audit confirms no trading, signing, submission, or LIVE authority.

## Following work

After this ledger is sealed and deployed:

1. collect genuine coverage sessions prospectively;
2. add a bounded event-decision FL4 population command;
3. select every canonical FastEvent in an explicit chronological decision window, never by future
   outcome;
4. require each requested horizon to fit inside one durable coverage session before marking it
   complete;
5. persist labels through the existing exact/idempotent FL4 API;
6. rerun the sealed FL8.1 proof workspace once a sufficient mature population exists.

This ordering protects the learning objective: maximize long-run net expectancy after realistic
costs without teaching the model that data outages were losing/no-trade opportunities.

LIVE remains disabled.
