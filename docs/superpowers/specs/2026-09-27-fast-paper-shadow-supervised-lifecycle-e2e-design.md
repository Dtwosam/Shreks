# Fast PAPER Shadow Supervised Lifecycle E2E — Design

**Date:** 2026-09-27  
**Base main SHA:** `1fb3db52b159f51028c401511f895782b586d45e`

## Purpose

Prove the already-wired learned Fast PAPER shadow runtime can carry one market
through the complete supervised lifecycle:

`BUY -> HOLD -> REDUCE -> SELL`

using the real supervisor/coordinator/source-publisher path and the isolated
shadow PAPER ledger.

The proof must include a process-style restart after REDUCE and must prove the
later SELL uses the exact reduced raw inventory recovered from durable state,
not the deployment-static exit amount and not the original BUY inventory.

This is a proof slice. It grants no new trading authority and does not change
action selection.

## Test boundary

Add one integration test that:

1. provisions the existing isolated shadow runtime;
2. supplies four ordered Fast Lane feature rows for one market;
3. drives learned decisions `BUY`, `HOLD`, `REDUCE`, then `SELL`;
4. runs every action through `run_fast_paper_shadow_supervisor_cycle(...)`;
5. lets the supervisor create/consume the existing BUY and OPEN source records;
6. persists realistic point-in-time quote rows for the exact raw amounts;
7. writes only the already-required quote/USD source evidence between decision
   production and execution;
8. re-bootstraps the supervisor from disk immediately after REDUCE;
9. verifies restart restores exposure `0.25` and raw inventory `2_500_000`;
10. verifies the SELL decision seals `2_500_000` as its full-exit raw input;
11. executes SELL and verifies the isolated position closes;
12. verifies the authoritative PAPER evidence file remains byte-for-byte
    unchanged.

Each action is exercised with the coordinator's real two-step cadence:
decision production first, then execution on the following supervisor cycle.

## Quote/raw inventory proof

The BUY fixture opens:

- target exposure: `0.5`;
- exact base raw inventory: `5_000_000`.

The REDUCE decision targets exposure `0.25` and must consume exact persisted
raw input:

- reduction input: `2_500_000`;
- remaining raw inventory: `2_500_000`.

After restart, the next OPEN quote source must be built from that restored raw
inventory. The SELL evidence must therefore carry:

`exit_quote.input_amount_raw == 2_500_000`

A SELL using `5_000_000`, the static service-policy value after reduction, or
a float-derived raw quantity fails the proof.

## Authority boundary

```text
ACTION_SELECTION=EXISTING_LEARNED_TEST_DOUBLE_ONLY
SUPERVISOR_PATH=REAL
COORDINATOR_PATH=REAL
SOURCE_PUBLISHERS=REAL
OPEN_QUOTE_WRITER=REAL
SHADOW_EXECUTOR=REAL
SHADOW_LEDGER=REAL_ISOLATED_ONLY
RESTART=REAL_DURABLE_REBOOTSTRAP
RAW_INVENTORY=EXACT_PERSISTED_ONLY
FLOAT_TO_RAW_DERIVATION=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```

## Acceptance

The integration proof passes only when:

- BUY executes once and opens one isolated position;
- HOLD executes once without changing raw inventory;
- REDUCE executes once and leaves exact raw inventory `2_500_000`;
- a fresh supervisor bootstrap restores that exact state;
- SELL decision evidence uses `2_500_000` full-exit raw authority;
- SELL executes once and leaves no OPEN learned market mapping;
- the isolated ledger position is CLOSED;
- the authoritative PAPER evidence bytes are unchanged;
- no production runtime implementation change is required unless this proof
  exposes a real contract gap.

## Following slice

If this proof passes on current main, use the now-proven supervised lifecycle as
the basis for production-host shadow commissioning/evidence collection without
granting LIVE authority.
