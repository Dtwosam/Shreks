# Fast PAPER Shadow Coordinator Pending BUY Retry Source — Design

**Date:** 2026-09-26  
**Base main SHA:** `b800034f8b13872d253098b30c7a15a61ec19c4c`

## Purpose

Bind the supervised Fast PAPER shadow coordinator directly to the canonical
write-once pending-BUY retry source directory.

The retry source, retry service transaction, and coordinator retry precedence
already exist separately. This slice composes them so an unattended process can
retry a durable deferred learned BUY without an in-process callback.

## Contract

Extend:

`run_fast_paper_shadow_service_coordinated_cycle(...)`

with optional:

`pending_buy_retry_source_directory: Path | None`

Rules:

1. callers may supply either `pending_buy_retry_resolver` or
   `pending_buy_retry_source_directory`, never both;
2. retry-source handling is considered only when decision and execution cursors
   are equal and the exact authenticated execution bootstrap contains a durable
   pending BUY;
3. when pending BUY exists, a supplied source directory must be an existing
   regular non-symlink directory;
4. the coordinator locates only the source record for the exact current runtime
   state fingerprint and pending source-event identity;
5. if that exact current record is absent, return backpressure: zero decisions,
   zero execution commits, bootstraps unchanged;
6. if the exact record exists, read it only through
   `read_fast_paper_shadow_pending_buy_retry_source_record(...)` using the exact
   manifest/binding/execution-policy/checkpoint/runtime-state tuple;
7. pass only the authenticated record's `retry_input` unchanged into the sealed
   service retry transaction;
8. malformed, stale, tampered, symlinked, or state-mismatched records fail
   closed;
9. retry still requires exactly one checkpoint advance and no learned execution
   cursor change;
10. when no pending BUY exists, retry source authority is irrelevant and must
    not be read or validated;
11. reduction source/resolver authority remains irrelevant during pending BUY
    retry.

The coordinator must not build or write retry-source records, construct retry
inputs, derive risk facts, fetch provider/network data, or execute the retry
executor directly.

## Missing source vs invalid source

The previous in-process retry resolver already defines `None` as backpressure.
The durable equivalent is absence of the exact current-state source record.

An existing exact-current record is authoritative input and must be read
strictly. Reader failure is not backpressure and must propagate fail-closed.

## Authority boundary

```text
PENDING_BUY_RETRY_SOURCE=AUTHENTICATED_READ_ONLY
MISSING_CURRENT_RETRY_SOURCE=BACKPRESSURE
INVALID_CURRENT_RETRY_SOURCE=FAIL_CLOSED
RETRY_FACT_DERIVATION=FORBIDDEN
SOURCE_RECORD_MUTATION=NOT_GRANTED
NEW_DECISION_DURING_RETRY=FORBIDDEN
REDUCTION_AUTHORITY_DURING_RETRY=NOT_USED
SHADOW_EXECUTION=ISOLATED_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- coordinator retry-source-directory keyword;
- mutual exclusion with the existing retry resolver;
- exact current-state source read composition;
- exact retry-input forwarding;
- missing exact source backpressure;
- no source access when no pending BUY exists;
- no reduction-source access during retry;
- strict durable progress checks preserved;
- no source mutation, retry-input construction, provider/network, scoring,
  signing/submission, or LIVE authority.

Current main is expected to fail because the coordinator does not accept the
pending-BUY retry source directory.
