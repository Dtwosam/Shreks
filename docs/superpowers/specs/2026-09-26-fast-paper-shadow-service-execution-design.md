# Fast PAPER Shadow Service Execution Transaction — Design

**Date:** 2026-09-26  
**Base main SHA:** `8b7d73126cac6e065d02523a5a69c41469c55d80`  
**Parent plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Purpose

Add the narrow supervised-service transaction boundary that turns one already
sealed learned shadow decision plus one separately supplied point-in-time
`FastPaperShadowExecutionInput` into an isolated durable Fast PAPER shadow
transition.

The service must not derive missing execution authority. It only authenticates
and consumes authority supplied by an upstream boundary.

## Contract

Add:

`run_fast_paper_shadow_service_execution(...)`

Inputs:

- exact Fast PAPER runtime manifest;
- exact isolated shadow-ledger binding;
- exact shadow execution policy;
- one separately supplied `FastPaperShadowExecutionInput`;
- private execution-input source-record directory;
- source observation timestamp;
- BUY-only risk day-start timestamp;
- durable commit timestamp.

For one supplied decision the transaction must:

1. load the exact latest isolated PAPER checkpoint and learned shadow runtime
   state and require both to exist;
2. call
   `produce_fast_paper_shadow_execution_input_source_record(...)` against that
   exact pair;
3. publish the resulting source record through the existing write-once source
   codec;
4. if the same record already exists, treat that only as a retry-before-commit
   path and continue by authenticating the existing record;
5. read the source record back against the exact current checkpoint/runtime
   fingerprints and require byte-level semantic equality with the freshly
   produced record;
6. pass only the authenticated read-back `execution_input` into
   `execute_fast_paper_shadow_decision(...)`;
7. reject an unexpected replay transition rather than manufacturing a second
   durable checkpoint;
8. persist the fresh transition only through
   `commit_fast_paper_shadow_transition_atomically(...)` at exactly the next
   checkpoint sequence;
9. return the atomic commit result.

The transaction must not mutate the feature-feed checkpoint, authoritative
PAPER evidence, or authoritative PAPER ledger.

## Restart behavior

A crash after publishing the source record but before the atomic transition
commit is recoverable: the same latest durable pair produces the same record,
the write-once collision is accepted only after strict read-back
authentication, and execution can proceed once.

A retry after the transition has already committed does not relabel the old
source record with new durable-state fingerprints. The source reader therefore
fails closed against the advanced checkpoint/runtime pair.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
EXTERNAL_EXECUTION_FACTS=EXPLICIT_ONLY
LATEST_SHADOW_PAIR=REQUIRED
EXECUTION_INPUT_SOURCE=WRITE_ONCE_AUTHENTICATED
SHADOW_EXECUTION=ISOLATED_ONLY
SHADOW_TRANSITION_PERSISTENCE=ATOMIC_ONLY
FEATURE_FEED_CURSOR_MUTATION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- a public `run_fast_paper_shadow_service_execution` API;
- exact latest checkpoint/runtime loading;
- producer -> write/read -> executor -> atomic-commit composition;
- retry-before-commit handling for an already published identical source
  record;
- read-back mismatch refusal before execution;
- missing durable-pair refusal before source production;
- unexpected replay refusal before atomic commit;
- no scoring, observer/provider-network, signing/submission, authoritative
  PAPER mutation, or LIVE authority.

Current main is expected to fail during Python test collection because the new
public service-execution API does not exist.
