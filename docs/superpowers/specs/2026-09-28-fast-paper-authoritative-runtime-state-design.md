# Fast Lane Authoritative PAPER Runtime State + Atomic Commit — Design

**Date:** 2026-09-28
**Base main SHA:** `607a890b7d83033a10360e3cbbbd91309f71dd55`
**Migration:** durable Fast Lane PAPER runner on the existing `PaperLedger`

## Purpose

Extend the merged authoritative handoff so a learned Fast PAPER run remains
restart-safe after sequence `0`.

This slice adds a companion authoritative runtime-state record and one atomic
checkpoint+runtime commit primitive. It still does not run a service or switch
production PAPER authority.

The existing Fast checkpoint already carries:

- exact `PaperLedger`;
- Fast PAPER event-loop state;
- pending BUY approval;
- per-position action/deferred-exit state;
- fill and position-action policies.

The missing durable companion state is:

- exact authoritative binding fingerprint;
- exact execution-policy fingerprint;
- exact PAPER checkpoint sequence/payload fingerprint;
- market-key -> open position mapping needed to recover learned posture;
- last processed learned source sequence/event identity;
- last processed decision-evidence fingerprint.

## New runtime-state schema

Add:

`shreks.fast_paper_authoritative_runtime_state` version `1`.

Each state contains:

- binding fingerprint;
- execution-policy fingerprint;
- exact Fast PAPER checkpoint sequence;
- exact Fast PAPER checkpoint payload SHA-256;
- canonical sorted market-position tuple;
- optional last processed learned source sequence;
- optional last processed source-event ID;
- optional last processed decision-evidence fingerprint;
- state fingerprint.

Each market-position row contains:

- market key;
- position ID;
- mint;
- current exposure fraction;
- current base quantity.

The market-position set must exactly cover OPEN positions in the bound
`FastPaperRuntimeState.ledger`.

For a flat checkpoint the mapping must be empty.

The last-processed learned identity is all-or-none.

## Handoff extension

The existing authoritative handoff must seed one authoritative runtime-state
row for Fast checkpoint sequence `0` in the **same SQLite transaction** as:

1. authoritative binding row;
2. initial Fast checkpoint row.

Initial runtime state:

- exact binding fingerprint;
- execution-policy fingerprint from the binding;
- Fast checkpoint sequence `0`;
- exact checkpoint payload SHA;
- empty market positions;
- no last-processed learned identity.

Exact repeated handoff remains idempotent only when binding, checkpoint, and
runtime-state rows all exactly match.

Any partial/colliding namespace fails closed.

## Atomic subsequent commit

Add:

`commit_fast_paper_authoritative_transition_atomically(...)`.

Inputs:

- exact manifest;
- exact authoritative binding;
- exact current latest Fast checkpoint;
- exact current latest authoritative runtime state;
- one explicit next transition;
- next checkpoint sequence;
- commit timestamp.

Transition contains:

- next `FastPaperRuntimeState`;
- next canonical market-position mapping;
- exact execution-policy fingerprint;
- optional last processed learned source identity.

The commit must:

1. authenticate manifest/binding;
2. require exact latest durable checkpoint+runtime pair;
3. require target sequence = current sequence + 1;
4. validate next ledger/accounting;
5. validate market-position mapping against OPEN positions;
6. encode next Fast checkpoint;
7. build next runtime state bound to that encoded checkpoint;
8. `BEGIN IMMEDIATE`;
9. re-check binding and exact current rows in-transaction;
10. require target checkpoint/runtime sequence unused;
11. insert checkpoint and runtime rows;
12. commit;
13. read back both and require exact equality.

Any exception rolls the transaction back. Torn checkpoint/runtime state is not
allowed.

## Replay/idempotency rule

This commit primitive is a state transition authority, not an execution
authority.

It must reject:

- source sequence regression;
- changing one part of an existing learned source identity without an actual
  source-sequence advance;
- changing execution-policy fingerprint inside a run;
- market mapping that does not exactly match OPEN ledger positions;
- stale current checkpoint/runtime state;
- target sequence collision.

Exact historical rows remain immutable.

## Authority boundary

This slice may:

- write authoritative Fast checkpoint/runtime rows;
- validate accounting and state invariants;
- persist exact learned decision identity.

It must not:

- select BUY/SKIP/HOLD/REDUCE/SELL;
- call scoring or legacy decision code;
- build risk authority;
- fetch quotes/providers;
- control services/systemd;
- change target membership;
- sign or submit transactions;
- enable LIVE.

The actual production Fast PAPER runner will consume this atomic primitive in
the following slice.

## Storage

Use existing authoritative observer SQLite.

New table:

`fast_paper_authoritative_runtime_states`

Primary key:

`(fast_run_id, paper_checkpoint_sequence)`.

Rows store:

- Fast run ID;
- checkpoint sequence;
- checkpoint payload SHA;
- runtime-state schema version;
- created-at timestamp;
- runtime payload SHA;
- canonical runtime payload JSON.

No legacy row may be updated or deleted.

## Acceptance tests

1. authoritative handoff now seeds binding + checkpoint + runtime row atomically;
2. initial runtime row is flat/empty and exactly bound to sequence `0`;
3. runtime-state fingerprint is deterministic;
4. market mapping exactly matching one OPEN position is accepted;
5. missing/extra/wrong-position mapping is rejected;
6. atomic sequence `1` commit writes checkpoint and runtime together;
7. restored checkpoint/runtime pair is exact and restart-equivalent;
8. stale current checkpoint is rejected;
9. stale current runtime state is rejected;
10. target sequence collision is rejected;
11. source decision identity regression/inconsistent mutation is rejected;
12. a deferred-execution checkpoint may preserve the current learned identity;
13. execution-policy fingerprint drift is rejected;
14. injected insert/commit failure leaves neither target row;
15. tampered runtime payload/fingerprint fails closed;
16. source contains no scoring, action-selection, provider, service-control,
    signing, submission or LIVE-enable authority.

## Following slice

Wire the learned decision/evidence producer and proven Fast PAPER execution
semantics into a production Fast PAPER coordinator that uses this authoritative
binding/checkpoint/runtime-state pair.

Service cutover remains a separate protected ceremony after that runner passes
restart/accounting/no-score regression proof.
