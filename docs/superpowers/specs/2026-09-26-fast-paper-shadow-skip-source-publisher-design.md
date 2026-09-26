# Fast PAPER Shadow SKIP Source Publisher — Design

**Date:** 2026-09-26  
**Base main SHA:** `ac1b26d068034a1b7a0f1bc1ecbf764066e55563`

## Purpose

Add the smallest safe supervised source publisher for learned Fast PAPER
execution.

A learned `SKIP` decision requires no entry sizing authority, no RiskContext,
no MarketRegime, and no quote/USD evidence. The exact decision evidence itself
is therefore sufficient to construct the already-sealed
`FastPaperShadowExecutionInput` for SKIP without inventing an external fact.

This slice automatically prepublishes only those SKIP source records. All other
actions continue to backpressure until separately authenticated execution
authority exists.

## Contract

Add:

`run_fast_paper_shadow_skip_source_publisher_cycle(...)`

Inputs:

- exact runtime manifest;
- exact authenticated execution bootstrap;
- decision-evidence directory.

For one invocation the publisher must:

1. validate the decision-evidence directory as an existing regular non-symlink
   directory;
2. enumerate canonical `shadow-*.json` decision evidence deterministically;
3. ignore decisions already processed by the durable execution cursor;
4. select only the oldest unexecuted decision;
5. authenticate release/manifest/champion identity against the runtime manifest;
6. if no pending decision exists, return zero;
7. if the oldest pending decision is not `SKIP`, return zero without touching
   its expected execution-source path;
8. if it is `SKIP`, construct exactly:
   - that decision evidence;
   - `entry_authority=None`;
   - `risk_context=None`;
   - `market_regime=None`;
   - `quote_usd_evidence=None`;
9. delegate state/checkpoint/policy validation and source-record construction to
   `produce_fast_paper_shadow_execution_input_source_record(...)` against the
   exact bootstrap pair;
10. use the decision's own evaluation timestamp as source-observation timestamp,
    because SKIP carries no later external facts;
11. write only through
    `write_fast_paper_shadow_execution_input_source_record(...)`;
12. publish at most one source record per invocation;
13. on a write collision, strictly read the existing exact source record and
    require byte-semantic equality with the record this invocation would have
    published.

The publisher must not execute the decision, commit ledger/runtime state, derive
market/risk/sizing/regime/USD facts, read provider/network state, or skip ahead
past an older non-SKIP decision.

## Supervisor composition

Before each coordinator invocation, the coordinated supervisor may invoke this
publisher against its current authenticated execution bootstrap.

This preserves the existing coordinator rule:

`SOURCE_AUTHORITY=PREPUBLISHED_ONLY`

because the coordinator still only consumes a source record. The publisher is a
separate bounded authority that can create a source only for the action whose
execution-input contract explicitly contains no external authority.

A newly published SKIP record may then be consumed by the coordinator in the
same supervisor loop iteration.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
AUTO_SOURCE_ACTION=SKIP_ONLY
EXTERNAL_FACT_DERIVATION=FORBIDDEN
BUY_SOURCE_PUBLICATION=NOT_GRANTED
HOLD_SOURCE_PUBLICATION=NOT_GRANTED
REDUCE_SOURCE_PUBLICATION=NOT_GRANTED
SELL_SOURCE_PUBLICATION=NOT_GRANTED
SOURCE_RECORD_MUTATION=WRITE_ONCE_ONLY
SHADOW_EXECUTION=NOT_GRANTED
SHADOW_TRANSITION_PERSISTENCE=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public SKIP-source publisher cycle API;
- deterministic oldest-unexecuted selection;
- no leapfrog past oldest non-SKIP decision;
- exact all-None SKIP execution input;
- exact authenticated producer composition;
- source-observation timestamp pinned to decision evaluation;
- write-once publication and strict collision readback;
- no execution/commit/risk/regime/USD/provider/network/scoring/LIVE authority;
- supervisor invocation before the coordinator.
