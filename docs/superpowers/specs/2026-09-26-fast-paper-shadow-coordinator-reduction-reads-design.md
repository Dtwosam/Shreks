# Fast PAPER Shadow Coordinator OPEN Reduction Reads — Design

**Date:** 2026-09-26  
**Base main SHA:** `4f2a2eecf8b1670a91c10de03dddd51935e58e76`

## Purpose

Remove the coordinator's temporary FLAT-only restriction now that the decision
service has an explicit caller-supplied target-specific reduction-read hook.

The coordinator must still never derive raw token units from normalized PAPER
holdings. OPEN decision production is allowed only when explicit reduction-read
authority is supplied by the caller.

## Contract

Extend:

`run_fast_paper_shadow_service_coordinated_cycle(...)`

with optional:

`reduction_read_resolver(record, position) -> tuple[FastPaperShadowReductionRead, ...]`

Rules:

1. pending BUY still blocks new decision production;
2. when durable learned OPEN mappings exist, a reduction-read resolver is
   required;
3. the durable posture resolver remains
   `fast_paper_shadow_decision_position(...)`;
4. OPEN posture is no longer rejected by the coordinator;
5. the exact caller resolver is forwarded unchanged to
   `run_fast_paper_shadow_service_cycle(...)`;
6. FLAT compatibility remains unchanged when no resolver is supplied;
7. execution catch-up behavior remains unchanged and never invokes the
   reduction-read resolver.

The coordinator must not construct `FastPaperShadowReductionRead` values,
convert floats to raw units, read provider data, or mutate either durable state
directly.

## Authority boundary

```text
RAW_REDUCTION_AMOUNT_DERIVATION=FORBIDDEN
REDUCTION_READ_AUTHORITY=EXPLICIT_CALLER_ONLY
DURABLE_OPEN_POSTURE=ALLOWED_WITH_REDUCTION_AUTHORITY
PENDING_BUY_PRECEDENCE=PRESERVED
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

- coordinator reduction-read resolver keyword;
- OPEN durable posture permitted only with explicit resolver;
- exact resolver forwarding into the decision service cycle;
- OPEN without resolver refusal before decision production;
- unchanged pending-execution catch-up behavior;
- no raw-unit derivation or reduction-read construction inside the coordinator.

Current main is expected to fail because the coordinator does not accept the
new resolver keyword and still rejects every OPEN durable posture.
