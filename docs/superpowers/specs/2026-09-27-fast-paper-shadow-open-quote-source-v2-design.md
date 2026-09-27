# Fast PAPER Shadow OPEN Quote Source v2 — Design

**Date:** 2026-09-27  
**Base main SHA:** `8924f8996e900a7b995caf353bd594e3a1f26ae4`

## Purpose

Evolve the existing write-once shadow reduction source into complete durable
OPEN quote-read authority.

Runtime-state schema v3 now seals exact current raw base inventory for every
OPEN learned mapping. The existing reduction source still carries only
target-specific reduction raw inputs, while the supervised service continues to
hold a deployment-static full-exit input amount. That becomes stale after the
first successful REDUCE.

This slice changes only the durable source record contract. It does not discover
observer quotes, change the supervised service, or execute PAPER.

## Schema

Keep the stable schema name:

`shreks.fast_paper_shadow_reduction_source`

and advance its schema version from `1` to `2`.

Add exact fields:

- `current_base_quantity_raw`;
- `exit_input_amount_raw`.

Both are positive u64 integers encoded canonically as decimal JSON strings.

## State binding

`build_fast_paper_shadow_reduction_source_record(...)` keeps its existing
public call shape.

The builder derives both new fields only from the exact authenticated
`FastPaperShadowMarketPosition.current_base_quantity_raw` bound to the latest
checkpoint/runtime-state pair:

```text
current_base_quantity_raw = mapping.current_base_quantity_raw
exit_input_amount_raw     = mapping.current_base_quantity_raw
```

The caller cannot override full-exit size.

The existing complete eligible reduction-target-set rule remains unchanged.
Reduction raw inputs remain explicit caller-supplied authority for now.

## Persistence

The two new raw fields participate in the record fingerprint and canonical
write-once payload.

Strict read-back must reject:

- version-1 payloads;
- missing/unknown fields;
- malformed/non-canonical decimal-u64 text;
- zero or overflow;
- current raw inventory inconsistent with the exact latest learned state;
- full-exit raw input not equal to exact current raw inventory;
- state/checkpoint drift;
- payload/fingerprint tamper;
- symlinks/non-regular files.

Existing deterministic filename and private `0600` write-once publication
remain unchanged.

## Authority boundary

```text
CURRENT_RAW_INVENTORY=EXACT_DURABLE_SHADOW_STATE
FULL_EXIT_RAW_INPUT=EXACT_CURRENT_RAW_INVENTORY
REDUCTION_RAW_INPUTS=EXPLICIT_EXISTING_AUTHORITY
OBSERVER_QUOTE_DISCOVERY=NOT_GRANTED
SERVICE_DYNAMIC_EXIT_CONSUMPTION=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- schema version `2`;
- source record exposes exact durable raw inventory;
- source record exposes exact full-exit raw input equal to that inventory;
- canonical write/read round trip preserves both values;
- tampering either raw field fails closed;
- raw fields participate in the fingerprint;
- no float-to-raw conversion or new observer/execution authority.

Current main is expected to fail only these additive v2 contract checks.

## Following slice

Add a read-only persisted-observer OPEN quote authority resolver/writer that:

1. uses exact durable `current_base_quantity_raw` for full EXIT;
2. selects target-specific reduction raw inputs only from matching persisted
   EXIT quote rows;
3. never reconstructs raw amounts from PAPER ledger floats;
4. writes this v2 source record restart-safely before the supervised OPEN
   decision cycle.
