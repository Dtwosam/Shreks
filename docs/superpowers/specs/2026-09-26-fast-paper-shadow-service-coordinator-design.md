# Fast PAPER Shadow Service Decision/Execution Coordinator — Design

**Date:** 2026-09-26  
**Base main SHA:** `b9c082105dd838da9df444f0c4d58e063d0c2a67`

## Purpose

Add the first supervisor-level handshake between learned decision production and
isolated Fast PAPER economic execution.

The learned decision cursor and the isolated economic execution cursor are
separate durable authorities. The decision service must not run arbitrarily
ahead of execution, because execution source records are bound to the exact
current isolated checkpoint/runtime pair.

This slice keeps those cursors in lockstep while preserving the currently
sealed execution-authority boundary.

## Contract

Add:

`FastPaperShadowServiceCoordinatorResult`

containing:

- updated decision-service bootstrap;
- latest execution bootstrap;
- number of learned decisions produced in this invocation;
- number of economic executions committed in this invocation.

Add:

`run_fast_paper_shadow_service_coordinated_cycle(...)`

Inputs:

- exact decision-service bootstrap;
- exact decision-service config;
- exact execution config;
- optional decision clock;
- durable execution commit timestamp.

Each invocation must first authenticate a fresh execution bootstrap from the
decision bootstrap's exact manifest.

Define:

- decision sequence = decision runtime cursor sequence, or zero when absent;
- execution sequence = isolated learned runtime state's last processed source
  sequence, or zero when absent.

Required invariants:

1. execution sequence may never exceed decision sequence;
2. decision sequence may be ahead of execution sequence by at most one;
3. if decision is ahead by one:
   - run only the bounded execution cycle against the decision evidence
     directory;
   - do not fetch or produce another learned decision;
   - if source authority is absent, return zero execution and keep the pending
     decision;
   - after a successful execution commit, reload the execution bootstrap and
     require its durable execution cursor to catch up exactly to the decision
     cursor;
4. if the cursors are equal:
   - require no unresolved pending BUY;
   - for this first coordinator slice, require no OPEN learned market mappings;
   - force the decision service batch size to exactly one;
   - supply posture through
     `fast_paper_shadow_decision_position(...)` from the authenticated
     execution runtime state;
   - produce at most one learned decision and do not attempt economic execution
     in the same invocation.

## Why the first coordinator is FLAT-only

The isolated ledger/posture authority now exists, but the supervised decision
service still has no sealed authority for target-specific REDUCE persisted quote
input amounts. Running an OPEN learned decision with an empty reduction quote
population would silently change the action comparison.

Therefore this coordinator fails closed once a learned OPEN mapping exists.
That is an explicit temporary boundary, not a claim of continuous OPEN-position
support.

A following slice must seal target-specific OPEN reduction quote authority
before this restriction can be removed.

## Pending BUY

An unresolved canonical pending BUY also blocks new learned decision production.
The executor already requires retry before another learned decision. The
coordinator must preserve that precedence and fail closed rather than advancing
the feature cursor.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
DECISION_CURSOR_EXECUTION_CURSOR_GAP<=1
MISSING_EXECUTION_AUTHORITY=BACKPRESSURE
PENDING_BUY_PRECEDENCE=PRESERVED
OPEN_POSITION_DECISION_PRODUCTION=BLOCKED_PENDING_REDUCTION_AUTHORITY
DECISION_BATCH_SIZE=ONE
SOURCE_AUTHORITY=PREPUBLISHED_ONLY
SHADOW_EXECUTION=ISOLATED_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public coordinator result/API;
- fresh execution bootstrap every invocation;
- decision/execution cursor ordering checks;
- no decision production while one decision is pending execution;
- missing execution source returns backpressure without producing another
  decision;
- successful execution reloads and verifies the durable execution cursor;
- exactly one decision maximum when cursors are equal;
- durable posture resolver binding;
- pending BUY and OPEN-position refusal before decision production;
- no scoring, source manufacturing, provider/network, authoritative PAPER,
  signing/submission, systemd cutover, or LIVE authority.

Current main is expected to fail during Python collection because the
coordinator module/API does not exist.
