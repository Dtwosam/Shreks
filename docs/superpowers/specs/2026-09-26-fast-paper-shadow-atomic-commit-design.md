# Fast PAPER Shadow Atomic Commit — Design

**Date:** 2026-09-26  
**Base main SHA:** `3bfe3a6bfe321102d29d3ed829bc2a47ce35e39f`

## Purpose

Close the remaining crash-consistency gap in the isolated learned Fast PAPER
shadow path before the supervised service is allowed to execute it.

The restart-safe executor returns one checkpoint-ready transition containing the
next canonical Fast PAPER runtime state plus the next learned posture companion
state. Today those states can only be persisted through two independent
transactions. A process failure after the PAPER checkpoint write and before the
companion write intentionally makes restart fail closed, but it also strands the
shadow run.

This slice adds one atomic SQLite commit boundary for the pair.

It does not wire the shadow service, resolve new execution-input authority,
mutate authoritative PAPER state, fetch providers, sign, submit, or enable LIVE.

## Atomic commit contract

Add:

`commit_fast_paper_shadow_transition_atomically(...)`

Inputs:

- exact authenticated runtime manifest;
- exact isolated shadow-ledger binding;
- exact latest durable Fast PAPER checkpoint;
- exact latest durable learned posture state;
- one exact `FastPaperShadowExecutionTransition`;
- the next checkpoint sequence;
- commit timestamp.

The commit must:

1. authenticate the binding against the manifest;
2. require the supplied checkpoint/posture pair to be the exact latest durable
   pair before opening the write transaction;
3. require the target sequence to equal current sequence + 1;
4. require the transition execution-policy fingerprint to equal the durable
   learned posture fingerprint;
5. canonical-encode the Fast PAPER checkpoint using the existing checkpoint
   codec;
6. build and canonical-encode the learned posture companion against that exact
   new checkpoint;
7. open the already isolated shadow SQLite database;
8. enter one `BEGIN IMMEDIATE` transaction;
9. re-check the current durable pair inside that transaction to close the
   check/write race;
10. insert both rows;
11. commit only after both inserts succeed;
12. rollback both inserts on any exception;
13. read back and validate the exact committed pair before returning.

No second connection may commit one half of the pair.

## Idempotency / stale-writer rule

This API is a transition commit, not an upsert.

- a stale caller whose supplied current pair is no longer latest fails closed;
- target sequence collision fails closed;
- sequence gaps fail closed;
- callers recover after an uncertain process outcome by reopening the database
  and loading the latest durable pair, not by blind re-insertion.

## Existing standalone persistence APIs

The existing standalone checkpoint/posture save functions remain available for
fixtures, migrations, and earlier state-construction tests. The learned service
execution path must use the atomic transition commit once service integration is
added.

## Service boundary

The current daemon still lacks authenticated runtime sources for BUY sizing,
risk context, regime, and quote/USD conversion. Those values must not be
invented from environment variables or normalized exposure.

Therefore this slice deliberately stops at durable transition commit. A later
service integration slice must first bind a point-in-time execution-input source
and then use this atomic commit API.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
SHADOW_LEDGER_EXECUTION=UNCHANGED
SHADOW_TRANSITION_PERSISTENCE=ATOMIC
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
SHADOW_SERVICE_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```
