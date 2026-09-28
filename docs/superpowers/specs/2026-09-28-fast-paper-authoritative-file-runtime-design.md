# Fast Lane Authoritative PAPER File Runtime — Design

**Date:** 2026-09-28  
**Base main SHA:** `2fda5573ce65dfa31639937ab8559d53b89730e5`

## Purpose

Complete the pre-cutover Fast Lane PAPER runtime process boundary without
granting service-control authority.

The runtime path becomes:

```text
canonical learned decision producer
-> prepublished file-backed economic authority
-> sealed execution-source record
-> authoritative Fast PAPER coordinator
-> authoritative runner
-> atomic PaperLedger/checkpoint/runtime-state commit
```

No systemd unit is installed, enabled, started, stopped, or replaced by this
slice.

## File-backed authority model

The production-facing runtime does not fetch provider/network facts and does not
manufacture execution authority.

Three authoritative file formats are added.

### BUY authority source

A BUY authority record binds:

- runtime manifest fingerprint;
- authoritative binding fingerprint;
- execution-policy fingerprint;
- exact PAPER checkpoint sequence/fingerprint;
- exact authoritative runtime-state fingerprint;
- exact learned decision fingerprint/event/market;
- deterministic entry authority;
- risk context derived for the authoritative PaperLedger;
- market regime;
- risk-day timestamp;
- source observation timestamp;
- external source version/fingerprint.

The record is valid only while its exact checkpoint/runtime pair remains latest.

A separate already-sealed quote/USD source record is required for the same
decision before BUY execution authority can be materialized.

### OPEN reduction source

An OPEN reduction record binds the exact authoritative position mapping and
contains:

- position ID and mint;
- current exposure;
- current raw inventory;
- full-exit raw input equal to current raw inventory;
- the complete eligible REDUCE target/input set for the current action policy.

The file name is scoped by authoritative runtime-state fingerprint and market
key. A record therefore cannot silently survive a position-state change.

### Pending BUY retry source

A retry record binds:

- exact pending checkpoint/runtime pair;
- exact original learned BUY fingerprint/event/market;
- retry quote;
- retry risk context;
- retry quote/USD evidence;
- risk-day/source-observation timestamps.

It is scoped by authoritative runtime-state fingerprint and pending event ID.
After the pending BUY resolves and the checkpoint advances, the old file no
longer authenticates.

## Resolver behavior

The runtime supplies the existing authoritative coordinator with file-backed
resolvers.

- `SKIP` remains source-free.
- `BUY` requires BUY authority + quote/USD files.
- `HOLD/REDUCE/SELL` require quote/USD evidence for the exact decision.
- OPEN decision production requires the exact current reduction-source file.
- pending BUY retry requires the exact retry-source file.

Missing BUY/OPEN execution or retry files create backpressure and no economic
commit. Missing OPEN reduction authority prevents decision production for that
OPEN posture.

Malformed, stale, torn, symlinked, conflicting, or fingerprint-mismatched files
fail closed.

## Runtime entrypoint

Add:

`python -m shreks_brain.fast_paper_runtime.authoritative_runtime`

The entrypoint:

1. loads the existing canonical Fast runtime manifest;
2. loads the learned decision service policy using the already-proven decision
   producer contract;
3. loads the authoritative execution policy/binding/checkpoint/runtime pair;
4. validates distinct non-overlapping source roots;
5. obtains one wall-clock timestamp per cycle;
6. invokes the authoritative coordinator with file-backed resolvers;
7. emits canonical runtime status;
8. sleeps only between completed cycles.

`--preflight` authenticates the full runtime configuration and authoritative
pair without running a cycle.

The active package `__all__` remains sealed; this migration entrypoint is
addressed by explicit module path.

## Environment contract

Decision/runtime:

- `SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH`
- `SHREKS_FAST_PAPER_SERVICE_POLICY_PATH`
- `SHREKS_FAST_PAPER_DECISION_EVIDENCE_DIRECTORY`
- `SHREKS_FAST_PAPER_INTERVAL_SECONDS` (optional, default 2 seconds)

Authoritative execution:

- `SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_POLICY_PATH`
- `SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_SOURCE_DIRECTORY`
- `SHREKS_FAST_PAPER_AUTHORITATIVE_DATABASE_PATH`
- `SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID`

Prepublished authorities:

- `SHREKS_FAST_PAPER_BUY_AUTHORITY_SOURCE_DIRECTORY`
- `SHREKS_FAST_PAPER_QUOTE_USD_SOURCE_DIRECTORY`
- `SHREKS_FAST_PAPER_REDUCTION_SOURCE_DIRECTORY`
- `SHREKS_FAST_PAPER_PENDING_BUY_RETRY_SOURCE_DIRECTORY`

The decision batch is hard-bounded to one row by this runtime.

## Status contract

Runtime status explicitly reports:

```text
mode=PAPER_AUTHORITATIVE_FAST
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live=DISABLED
```

It also exposes exact champion/action-policy identity, decision/execution
cursors, authoritative checkpoint sequence, pending BUY state, and open market
position count.

## Authority firewall

This slice may:

- read the observer database through the already-sealed learned decision feed;
- read/write learned decision evidence;
- read prepublished file-backed execution authority;
- publish sealed execution-source records;
- mutate the authoritative PAPER checkpoint/runtime pair through the already
  proven authoritative runner.

It must not:

- derive provider/network authority inside this runtime;
- initialize or mutate an isolated shadow ledger;
- invoke legacy scoring or score thresholds;
- invoke systemd/service control;
- sign or submit transactions;
- expose LIVE mode.

## Acceptance proof

Tests must prove:

1. authoritative BUY authority round-trips canonically and combines only with
   matching quote/USD evidence;
2. a BUY authority record becomes stale after authoritative checkpoint advance;
3. pending BUY retry authority survives process restart for the exact pending
   state;
4. missing OPEN reduction authority backpressures without producing a learned
   decision;
5. source files are write-once, state-bound, and symlink-resistant;
6. runtime source contains no shadow-ledger mutation, scoring, provider network,
   service-control, signing/submission, or LIVE authority;
7. existing Python, Rust, ARM64, and repository-safety suites remain green.

## Following slice

The next protected slice is commissioning/cutover preparation:

- package and seal this authoritative runtime entrypoint;
- bind immutable deployment configuration/source roots;
- extend cutover preflight to authenticate the exact entrypoint and authority
  files;
- prove legacy authoritative ledger flatness and no pending/deferred ambiguity.

The actual systemd authority switch remains a separate explicit cutover
ceremony.
