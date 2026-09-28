# Fast Lane Authoritative PAPER Runner — Design

**Date:** 2026-09-28  
**Base main SHA:** `fe625326f7eef4c1a43d403f8595c6bb2e289d54`  
**Migration:** PR 4 durable Fast Lane PAPER runner on the existing `PaperLedger`

## Purpose

Add the first production-facing Fast Lane PAPER execution runner that mutates the
authoritative Fast PAPER checkpoint/runtime-state pair created by the handoff
and durability slices.

This slice changes execution topology, not service authority. The runner can
apply learned `BUY/SKIP/HOLD/REDUCE/SELL` decisions to the authoritative
`PaperLedger`, but no systemd target, service, deployment, signing, submission,
or LIVE authority is granted.

## Reuse instead of reimplementation

The already-proven shadow executor owns the sealed Fast PAPER economic
semantics:

- learned-result -> `FastPaperActionAssessment`;
- material event/idempotency handling;
- score-free BUY risk;
- `execute_fast_paper_buy(...)`;
- `apply_fast_paper_position_action(...)`;
- deferred BUY semantics;
- REDUCE/SELL raw-inventory checks;
- position-action state evolution.

Its reconstruction entrypoints execute those semantics without mutating shadow
storage. The authoritative runner therefore adapts the current authoritative
checkpoint/runtime state into the reconstruction contract, obtains one
checkpoint-ready transition, converts only the companion market-position type,
and commits through
`commit_fast_paper_authoritative_transition_atomically(...)`.

No second PAPER accounting or execution engine is added.

## Authoritative decision execution

`run_fast_paper_authoritative_execution(...)`:

1. loads and authenticates the exact latest authoritative binding;
2. loads the exact latest Fast checkpoint + authoritative runtime state;
3. requires the exact binding-pinned execution policy;
4. rejects a new learned decision while a deferred BUY is pending;
5. validates/materializes the supplied execution evidence against the manifest;
6. reconstructs the transition using the sealed Fast PAPER executor;
7. treats exact event replay as a storage no-op;
8. otherwise commits checkpoint + authoritative runtime state atomically at
   exactly `current_sequence + 1`.

Exact replay must not create another checkpoint or invoke another economic
action.

## Deferred BUY retry

The canonical `FastPaperRuntimeState.pending_buy` contains the durable BUY
approval, but the companion learned target exposure is intentionally not
duplicated into the authoritative runtime-state schema.

A retry therefore requires the exact original durable decision evidence. The
runner authenticates that evidence against:

- release SHA;
- manifest fingerprint;
- champion fingerprint;
- durable last-processed source sequence;
- durable source event ID;
- durable decision-evidence fingerprint;
- pending BUY approval market/mint/quote identity.

Only then is the learned target exposure reconstructed for the sealed retry
semantics. The resulting checkpoint/runtime transition is committed atomically.
A completed retry clears the canonical pending BUY; another retry then fails
closed.

## State adapter boundary

The reconstruction functions require the old isolated-shadow companion types.
The runner builds an in-memory compatibility adapter:

- same Fast run ID;
- same checkpoint;
- same execution-policy fingerprint;
- authoritative market mappings converted one-for-one;
- authoritative learned cursor copied exactly;
- pending target supplied only from authenticated original decision evidence.

The adapter path is a deterministic non-authoritative placeholder. No shadow
database is initialized, read, or written. The reconstruction entrypoints do
not perform storage mutation.

## Replay and restart guarantees

Required behavior:

- fresh SKIP/BUY/HOLD/REDUCE/SELL transition -> one authoritative sequence
  advance;
- exact replay -> zero sequence advance;
- conflicting replay -> fail closed;
- restart between deferred BUY and retry -> retry reconstructs from durable
  checkpoint/runtime pair plus exact original evidence;
- completed BUY retry cannot execute twice;
- open-position mapping remains exactly aligned with OPEN `PaperLedger`
  positions;
- authoritative atomic commit retains accounting validation: INVALID is rejected, while an open position may remain INCOMPLETE until mark evidence exists.

## Authority firewall

This runner may:

- consume already-authenticated learned decision/execution evidence;
- call existing Fast PAPER economic primitives through the sealed
  reconstruction boundary;
- mutate the authoritative PAPER checkpoint/runtime pair through the atomic
  commit primitive.

It must not:

- import or invoke legacy scoring or `decide_entry`;
- fetch providers or manufacture quote/risk authority;
- write or initialize shadow-ledger state;
- control systemd/services/targets;
- sign or submit transactions;
- enable LIVE.

Canonical status remains:

```text
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

## Acceptance tests

1. fresh learned SKIP commits authoritative sequence exactly once;
2. exact replay is a no-op and does not append another checkpoint/runtime row;
3. a learned BUY may durably defer in the authoritative checkpoint;
4. restart-safe retry with exact original decision evidence fills once;
5. completed retry cannot run again;
6. tampered original decision evidence is rejected;
7. authoritative market mapping and OPEN ledger position remain coherent;
8. open-position accounting is never INVALID (INCOMPLETE remains valid when mark evidence is absent);
9. source contains no scoring, shadow-storage mutation, service-control,
   signing/submission, or LIVE authority.

## Public API boundary

The existing `shreks_brain.fast_paper_runtime.__all__` contract remains sealed. The authoritative runner is imported explicitly from `fast_paper_runtime.authoritative_runner`, matching the existing authoritative handoff/commit modules and avoiding an unrelated package-surface expansion.

## Following slice

Wire the decision/evidence producer and explicit execution-source publication
around this runner into the production Fast PAPER coordinator/runtime entrypoint,
then prove restart/accounting/no-score behavior end to end.

The protected physical service cutover ceremony remains a separate slice.
