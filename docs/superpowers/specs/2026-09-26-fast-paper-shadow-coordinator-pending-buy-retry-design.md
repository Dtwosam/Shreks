# Fast PAPER Shadow Coordinator Pending BUY Retry — Design

**Date:** 2026-09-26  
**Base main SHA:** `576070c2fc286675ddabfdf6347557843e5c8d5f`

## Purpose

Allow the supervised decision/execution coordinator to service one already-durable
deferred learned BUY before any new learned decision is produced.

The service-level pending BUY retry transaction is already sealed. This slice only
adds coordinator precedence and orchestration around that transaction.

Retry facts remain explicit caller-supplied authority. The coordinator must not
derive, fetch, or persist them itself.

## Contract

Extend:

`run_fast_paper_shadow_service_coordinated_cycle(...)`

with optional:

`pending_buy_retry_resolver`

The resolver receives the exact freshly authenticated
`FastPaperShadowServiceExecutionBootstrap` and returns either:

- one exact `FastPaperShadowPendingBuyRetryInput`; or
- `None` when fresh retry authority is not yet available.

Rules when decision and execution cursors are equal:

1. if no durable pending BUY exists, existing decision production behavior is
   unchanged;
2. if a durable pending BUY exists:
   - no learned decision may be produced;
   - OPEN reduction source/resolver authority is irrelevant and must not be
     touched;
   - without a retry resolver, fail closed;
   - resolver returning `None` is backpressure: return zero decisions and zero
     commits with the current bootstraps unchanged;
   - exact retry input must be passed unchanged to
     `run_fast_paper_shadow_service_pending_buy_retry(...)`;
   - reload execution bootstrap after the transaction;
   - require the isolated checkpoint sequence to advance exactly once;
   - require the learned execution cursor to remain unchanged, because retry
     does not create or consume another learned decision;
   - return one committed execution transition and no produced decision.

The refreshed durable state may either retain pending BUY (retry deferred again)
or clear it (terminal retry). A later coordinator invocation decides what to do
next.

## Precedence

Pending BUY retry occurs before:

- reduction-source directory validation;
- OPEN reduction resolver access;
- feature fetch;
- decision inference;
- decision evidence persistence.

This ensures a deferred entry cannot be starved or invalidated by unrelated
OPEN-position authority configuration.

## Authority boundary

```text
PENDING_BUY_RETRY_PRECEDENCE=REQUIRED
RETRY_FACTS=EXPLICIT_CALLER_AUTHORITY_ONLY
MISSING_RETRY_FACTS=BACKPRESSURE
NEW_DECISION_DURING_RETRY=FORBIDDEN
REDUCTION_AUTHORITY_DURING_RETRY=NOT_USED
EXECUTION_CURSOR_CHANGE_DURING_RETRY=FORBIDDEN
SHADOW_EXECUTION=ISOLATED_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- coordinator retry-resolver keyword;
- pending BUY precedence before decision production;
- resolver `None` backpressure;
- exact service retry transaction delegation;
- exactly-one checkpoint advance verification;
- unchanged learned execution cursor verification;
- no reduction source access during pending BUY retry;
- no direct retry executor, scoring, provider/network, authoritative PAPER,
  signing/submission, or LIVE authority.

Current main is expected to fail because the coordinator does not accept the
pending-BUY retry resolver.
