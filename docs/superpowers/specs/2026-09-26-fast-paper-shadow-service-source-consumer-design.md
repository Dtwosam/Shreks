# Fast PAPER Shadow Service Source Consumer — Design

**Date:** 2026-09-26  
**Base main SHA:** `92fa696fce511eb311d899c8faf412a03ce40987`

## Purpose

Add the consumer-only supervised shadow execution boundary for an already
published, state-bound `FastPaperShadowExecutionInputSourceRecord`.

The prior service transaction can state-bind an in-memory execution input,
publish the canonical source record, read it back, execute, and atomically
commit. A continuously supervised service should not require that raw execution
authority to exist only in memory. A separately authenticated upstream must be
able to publish the canonical source record first, while the service consumes
that record later and still fails closed if isolated durable state has changed.

## Contract

Add:

`consume_fast_paper_shadow_service_execution_source_record(...)`

Inputs:

- exact runtime manifest;
- exact isolated shadow-ledger binding;
- exact shadow execution policy;
- exact learned decision evidence whose fingerprint names the source record;
- private source-record directory;
- durable commit timestamp.

The consumer must:

1. load the exact latest isolated PAPER checkpoint and learned runtime state;
2. require both durable objects to exist;
3. read the already-published source record using the exact current checkpoint
   sequence/payload SHA-256 and runtime-state fingerprint;
4. pass only the authenticated record's `execution_input` to the restart-safe
   shadow executor;
5. reject an unexpected replay transition;
6. persist only via `commit_fast_paper_shadow_transition_atomically(...)` at
   exactly the next checkpoint sequence;
7. return the atomic commit result.

The consumer must not produce, rewrite, repair, or overwrite the source record.
Missing, stale, tampered, policy-drifted, decision-drifted, or state-drifted
source authority must fail closed before economic execution.

The existing
`run_fast_paper_shadow_service_execution(...)` producer+consumer transaction
may delegate its post-publication half to this consumer, so both paths share one
execution/commit boundary.

## Restart semantics

A source record published against checkpoint N may be consumed while N is still
the exact latest durable pair. After N+1 commits, the same record must fail
against the advanced state fingerprints and may not create another economic
action.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
EXECUTION_SOURCE_CONSUMPTION=AUTHENTICATED_EXISTING_ONLY
SOURCE_RECORD_MUTATION=NOT_GRANTED
SHADOW_EXECUTION=ISOLATED_ONLY
SHADOW_TRANSITION_PERSISTENCE=ATOMIC_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
OBSERVER_DATABASE_ACCESS=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public `consume_fast_paper_shadow_service_execution_source_record`;
- exact latest durable-pair loading;
- strict existing-record read before execution;
- authenticated record input only;
- replay refusal before commit;
- atomic next-sequence persistence only;
- no producer/write call in the consumer;
- no scoring, observer DB, provider/network, signing/submission, authoritative
  PAPER mutation, or LIVE authority.

Current main is expected to fail during Python collection because the new
public consumer API does not exist.
