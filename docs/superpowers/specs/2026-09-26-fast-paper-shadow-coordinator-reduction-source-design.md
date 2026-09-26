# Fast PAPER Shadow Coordinator Reduction Source — Design

**Date:** 2026-09-26  
**Base main SHA:** `65c6fa224620d2930dcfe661bf8d58e5477e9264`

## Purpose

Bind the supervised coordinator directly to the canonical write-once reduction
source directory so OPEN decision production no longer requires an in-process
caller to manufacture a reduction-read callback.

The coordinator still does not derive raw token quantities. It only reads the
already-authenticated source record against the exact execution bootstrap state.

## Contract

Extend:

`run_fast_paper_shadow_service_coordinated_cycle(...)`

with optional:

`reduction_source_directory: Path | None`

Rules:

1. callers may supply either `reduction_read_resolver` or
   `reduction_source_directory`, never both;
2. after the coordinator authenticates the execution bootstrap, a supplied
   source directory must be an existing regular non-symlink directory;
3. for OPEN posture, the coordinator builds a bounded resolver that:
   - derives only the canonical market key from the feature record;
   - requires the supplied decision posture to equal
     `fast_paper_shadow_decision_position(...)` from that exact runtime state;
   - reads
     `read_fast_paper_shadow_reduction_source_record(...)` against the exact
     bootstrap binding/checkpoint/runtime state;
   - returns only the authenticated record's `reduction_reads`;
4. FLAT posture returns an empty tuple and does not require or read a reduction
   source record;
5. missing/stale/tampered source authority fails closed before decision
   persistence;
6. execution catch-up remains unchanged and must not read reduction sources.

The coordinator must not build a reduction source record, write a reduction
source record, construct `FastPaperShadowReductionRead` values, derive raw
units, or read observer/provider data for this authority.

## Authority boundary

```text
REDUCTION_SOURCE=AUTHENTICATED_READ_ONLY
RAW_REDUCTION_AMOUNT_DERIVATION=FORBIDDEN
SOURCE_RECORD_MUTATION=NOT_GRANTED
DURABLE_POSTURE=EXACT_BOOTSTRAP_ONLY
DECISION_BATCH_SIZE=ONE
SHADOW_EXECUTION=ISOLATED_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- coordinator reduction-source-directory keyword;
- mutual exclusion with an explicit callback;
- exact source reader composition;
- FLAT no-read compatibility;
- OPEN exact-posture source consumption;
- stale/missing source failure before decision persistence;
- execution catch-up no-read behavior;
- no source mutation or raw-unit derivation.

Current main is expected to fail because the coordinator does not accept the
new reduction-source-directory keyword.
