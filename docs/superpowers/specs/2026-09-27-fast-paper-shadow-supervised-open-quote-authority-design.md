# Fast PAPER Shadow Supervised OPEN Quote Authority — Design

**Date:** 2026-09-27  
**Base main SHA:** `3785e1b40ed42ca2527e7a3b827938cdf38b0928`

## Purpose

Wire the persisted-observer OPEN quote writer into the supervised learned-shadow
cycle and consume the v2 OPEN quote-source record's exact dynamic full-exit raw
amount during the next OPEN decision.

The durable learned state already seals current raw inventory. The v2 OPEN
source already seals:

- exact current raw inventory;
- exact full-exit raw input equal to current inventory;
- complete reduction raw inputs.

The service must no longer use the deployment-static full-exit input amount for
a supervised OPEN posture after inventory changes.

This slice does not change action selection or execute anything outside the
existing isolated PAPER coordinator.

## Service boundary

Extend `run_fast_paper_shadow_service_cycle(...)` with optional explicit:

`exit_input_amount_resolver(record, position) -> int`

Rules:

- FLAT posture does not call the resolver and keeps the service-policy entry/exit
  defaults used for FLAT quote resolution;
- OPEN posture may use the resolver;
- returned value must be an exact positive u64;
- the resolved value becomes
  `FastPaperShadowQuoteReadPolicy.exit_input_amount_raw`;
- reduction reads remain supplied through the existing explicit reduction-read
  resolver;
- the service must not derive raw values from normalized quantities.

## Coordinator source consumption

When `reduction_source_directory` is supplied, the coordinator must read the
exact current v2 source record for OPEN posture and expose both:

- `record.exit_input_amount_raw`;
- `record.reduction_reads`.

The same authenticated record must back both resolvers for a feature/market
within the invocation. State, market, checkpoint, and source-directory binding
remain unchanged.

FLAT posture reads no OPEN source.

The legacy direct `reduction_read_resolver` call path may continue using the
deployment-static exit amount because it is explicit caller authority and is
not the unattended supervised source path.

## Supervisor ordering

In each supervisor cycle use one exact `now` and order:

1. SKIP source publisher;
2. BUY-authority writer;
3. BUY source publisher;
4. OPEN quote writer;
5. OPEN execution-source publisher;
6. coordinator.

Call the OPEN quote writer with:

- current decision bootstrap;
- current execution bootstrap;
- exact reduction/OPEN source directory;
- `clock_unix_ms=lambda: now`.

The writer publishes authority for the next not-yet-decided OPEN feature. The
coordinator then consumes that source in the same cycle.

## Authority boundary

```text
OPEN_QUOTE_WRITER=SUPERVISED_BEFORE_DECISION
OPEN_FULL_EXIT_RAW=V2_SOURCE_EXACT
OPEN_REDUCTION_RAW=V2_SOURCE_EXACT
FLOAT_TO_RAW_DERIVATION=FORBIDDEN
ACTION_SELECTION=UNCHANGED
DECISION_CURSOR=EXISTING_COORDINATOR_ONLY
EXECUTION_SOURCE_PUBLICATION=EXISTING_ONLY
PAPER_EXECUTION=EXISTING_ISOLATED_ONLY
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- service supports explicit dynamic OPEN full-exit raw resolver;
- OPEN resolver output becomes quote-read policy full-exit input;
- FLAT posture does not call the dynamic resolver;
- coordinator v2 source consumption forwards full-exit raw plus reduction reads
  from the same authenticated record;
- supervisor calls OPEN quote writer before OPEN publisher/coordinator and
  forwards the same cycle timestamp;
- source contains no float-to-raw derivation, scoring, provider-network,
  signing/submission, authoritative PAPER, or LIVE authority.

Current main is expected to fail only these additive supervised OPEN authority
contracts.

## Following slice

Prove BUY -> HOLD -> REDUCE -> SELL end to end through the supervised isolated
PAPER path, including restart after REDUCE and exact dynamic raw inventory/full
exit authority.
