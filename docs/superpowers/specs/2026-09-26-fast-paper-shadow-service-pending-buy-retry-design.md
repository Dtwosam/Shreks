# Fast PAPER Shadow Service Pending BUY Retry — Design

**Date:** 2026-09-26  
**Base main SHA:** `9a30bc037ab0c6a840cdae4b7669e62b8101d437`

## Purpose

Add the smallest service-level transaction for retrying one already-durable
deferred learned BUY.

The restart-safe executor already preserves the original BUY approval and learned
target exposure in the isolated checkpoint/runtime pair. It also exposes
`retry_fast_paper_shadow_pending_buy(...)`, which consumes only fresh
point-in-time retry facts.

What is missing is the supervised service transaction that loads the exact
latest durable pair, delegates the retry to that sealed executor, and persists
the resulting transition atomically.

This slice does not source or derive retry market facts. It does not wire the
coordinator. It does not add provider access.

## Contract

Add public:

`run_fast_paper_shadow_service_pending_buy_retry(...)`

Inputs:

- exact runtime manifest;
- exact isolated shadow-ledger binding;
- exact execution policy;
- exact `FastPaperShadowPendingBuyRetryInput`;
- durable commit timestamp.

The service transaction must:

1. load the exact latest isolated PAPER checkpoint and learned runtime state;
2. require both durable objects to exist;
3. call only `retry_fast_paper_shadow_pending_buy(...)` for economic retry;
4. pass the exact latest checkpoint/runtime pair and caller-supplied retry facts;
5. persist only through
   `commit_fast_paper_shadow_transition_atomically(...)`;
6. use exactly `checkpoint.sequence + 1`;
7. return the atomic commit result;
8. propagate fail-closed retry validation without attempting a commit.

The transaction must not:

- create or mutate a learned decision;
- produce or read a normal execution-input source record;
- derive quote, USD, risk, sizing, regime, or entry economics;
- access observer/provider/network state;
- initialize the ledger;
- mutate authoritative PAPER state;
- sign/submit transactions;
- enable LIVE.

## Why this is separate from normal decision execution

A deferred BUY has already consumed its learned decision and already advanced
the learned execution cursor. The original approval, source event, market,
sizing/economic boundary, and selected target exposure are durable.

A retry therefore must not create a second learned decision or replay the normal
execution-source path. Only fresh retry facts are permitted.

## Authority boundary

```text
PENDING_BUY_RETRY=EXPLICIT_INPUT_ONLY
RETRY_FACT_DERIVATION=FORBIDDEN
NEW_DECISION=FORBIDDEN
NORMAL_EXECUTION_SOURCE=NOT_USED
SHADOW_EXECUTION=ISOLATED_ONLY
SHADOW_TRANSITION_PERSISTENCE=ATOMIC_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public service pending-BUY retry API;
- exact latest checkpoint/runtime loading;
- retry executor delegation with exact supplied retry input;
- atomic next-sequence commit only;
- retry failure before commit;
- no normal execution-source, scoring, provider/network, signing/submission, or
  LIVE authority.

Current main is expected to fail during Python collection because the public
service retry API does not exist.
