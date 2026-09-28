# Fast Lane Authoritative PAPER Coordinator — Design

**Date:** 2026-09-28  
**Base main SHA:** `0ece8d042286404ea4d010720660714b1e1d1a45`

## Purpose

Wire the already-sealed Fast Lane decision producer to the authoritative Fast
PAPER runner without changing service ownership or granting physical production
cutover authority.

This slice completes the in-process production PAPER coordination seam:

```text
canonical Fast feature feed
-> learned BUY/SKIP/HOLD/REDUCE/SELL decision evidence
-> explicit execution-source record
-> authoritative Fast PAPER runner
-> atomic authoritative checkpoint/runtime commit
```

The legacy systemd service remains untouched.

## Reused boundaries

The coordinator deliberately reuses:

- `run_fast_paper_shadow_service_cycle(...)` as the already-proven bounded
  learned decision/evidence producer;
- the sealed execution-source envelope and write-once codec;
- the exact approved execution policy codec;
- the authoritative handoff/binding/checkpoint/runtime-state pair;
- `run_fast_paper_authoritative_execution(...)`;
- `run_fast_paper_authoritative_pending_buy_retry(...)`.

The historical `shadow` names on decision/evidence and execution-source codec
types are compatibility names only. No isolated shadow ledger participates in
this path.

## Authoritative execution bootstrap

Add an authoritative execution bootstrap that loads:

- exact execution policy;
- exact persisted authoritative binding;
- exact latest Fast PAPER checkpoint;
- exact latest authoritative runtime state;
- an existing write-once execution-source directory.

The bootstrap requires checkpoint/runtime/policy fingerprints to agree and
requires the database to be the manifest-bound authoritative observer database.

It never initializes a ledger, creates a new run namespace, or alters service
state.

## Execution-source bridge

Before an economic action can reach the authoritative runner, the source bridge
must validate the supplied execution input against the exact latest
authoritative pair.

Required checks include:

- learned decision posture equals the authoritative market-position mapping;
- decision time does not predate the durable PAPER state;
- source observation is not from the future;
- BUY risk accounting matches the authoritative `PaperLedger`;
- no unresolved pending BUY exists before a fresh BUY;
- execution policy fingerprint matches both authoritative binding and runtime
  state.

The existing sealed execution-source record format is reused. Its legacy field
named `shadow_runtime_state_fingerprint_sha256` carries the exact
**authoritative runtime-state fingerprint** in this path. This avoids a second
execution-input codec during migration.

The source record is written before runner invocation. A crash after source
publication but before commit is therefore restart-safe: the coordinator can
read the exact record and finish the one pending execution.

## Coordinator cursor rule

The coordinator preserves the existing bounded relationship:

```text
execution_sequence <= decision_sequence
decision_sequence - execution_sequence <= 1
```

When cursors are equal:

- at most one new learned decision is produced;
- position posture is resolved from authoritative runtime state;
- OPEN posture requires explicit reduction quote authority.

When the decision cursor is exactly one ahead:

- another decision is forbidden;
- the oldest contiguous decision evidence is selected;
- an existing execution-source record is consumed, or explicit source authority
  is used to publish one;
- exactly one authoritative transition must commit;
- the refreshed execution cursor must catch up exactly.

`SKIP` needs no external economic authority and can publish its empty
execution input directly. BUY/HOLD/REDUCE/SELL require an explicit resolver;
the coordinator does not fetch, infer, or manufacture external execution facts.

## Deferred BUY recovery

A durable pending BUY blocks new learned decisions.

The coordinator locates the exact original decision evidence by the durable
processed decision fingerprint and requires an explicit pending-BUY retry
resolver. The authoritative runner then performs the already-proven retry
semantics.

A retry:

- advances the PAPER checkpoint exactly once;
- does not advance the learned decision cursor;
- cannot run again after the canonical pending BUY is cleared.

A durable file-backed pending-BUY retry publisher may be layered on this
resolver boundary in a later slice; the coordinator itself never manufactures
retry quotes or risk facts.

## Public API boundary

The sealed `shreks_brain.fast_paper_runtime.__all__` surface remains
unchanged. These production migration modules are imported explicitly by module
path, matching the authoritative handoff/commit/runner pattern.

## Authority firewall

This slice may:

- read canonical feature/decision evidence;
- write execution-source evidence;
- mutate the authoritative PAPER checkpoint/runtime pair through the runner.

It must not:

- initialize or write an isolated shadow ledger;
- import legacy scoring/decision authority;
- fetch network/provider facts;
- control systemd or service targets;
- sign or submit transactions;
- enable LIVE.

Canonical authority state remains:

```text
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

## Acceptance proof

Tests must prove:

1. an authenticated SKIP source commits once through the authoritative bridge;
2. an already-published source survives restart and is consumed exactly once;
3. equal decision/execution cursors produce at most one decision;
4. a pending decision blocks another decision until authoritative execution
   catches up;
5. deferred BUY retry survives restart, advances the checkpoint once, and leaves
   the learned cursor unchanged;
6. resolved pending BUY cannot execute again;
7. authoritative source production rejects stale/torn policy/state/risk facts;
8. new coordinator source has no shadow-ledger mutation, scoring, service
   control, signing/submission, or LIVE authority.

## Following slice

Add the file-backed production authority publishers needed by this coordinator
for BUY and OPEN execution inputs, plus a durable pending-BUY retry source
adapter. Then wrap the coordinator in a production Fast PAPER runtime
entrypoint suitable for protected commissioning.

The physical systemd authority switch remains the separately protected PR 5
cutover ceremony.
