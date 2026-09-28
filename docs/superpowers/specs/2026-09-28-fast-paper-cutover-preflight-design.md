# Fast Lane Production PAPER Cutover Preflight — Design

**Date:** 2026-09-28
**Base main SHA:** `e5c117e04a138e4756ef263142387d308c985fb4`
**Migration:** controlled Fast Lane learned PAPER runtime cutover

## Purpose

Add the read-only state gate immediately before a future production Fast Lane
PAPER runner/cutover slice.

The repository now has:

- a proven learned Fast Lane shadow runtime;
- FL11.1/2a/2b/3 proof;
- FL11.4 promotion readiness;
- an explicit Fast Lane PAPER champion registry.

What it does **not** yet have is a production Fast Lane service entrypoint using
the authoritative legacy `PaperLedger`. Therefore this slice must not perform
or imply the service cutover.

Instead, it proves that the data and operational state required by the migration
plan are safe enough to hand off:

- the promoted Fast Lane champion is exact and still bound to the learned runtime;
- the detached shadow runtime has a sealed physical restart proof;
- the isolated learned PAPER ledger currently reconciles;
- the legacy authoritative PAPER ledger currently reconciles;
- the legacy ledger is flat;
- there is no pending entry;
- there is no deferred entry/exit execution;
- there is no active legacy intent.

A passing result means only `CUTOVER_PREFLIGHT_READY`. It is **not** cutover
authority.

## CLI

Add:

```text
shreks-fast-paper-cutover-preflight
```

Required arguments:

- `--fast-manifest-path`
- `--champion-registry-path`
- `--shadow-restart-receipt-path`
- `--shadow-ledger-database-path`
- `--legacy-runtime-manifest-path`
- `--legacy-observer-database-path`
- `--expected-release-sha`

The command is read-only and emits one canonical self-fingerprinted JSON report.

## Fast Lane champion authentication

1. read and authenticate the current Fast PAPER runtime manifest;
2. require `release_source_sha == expected_release_sha`;
3. verify the manifest's immutable champion/binary bindings;
4. read the canonical Fast PAPER champion registry;
5. require the registry's current champion version/fingerprint to equal the
   manifest's champion version/fingerprint.

No generic E6/E8 registry identity is accepted.

## Physical restart proof authentication

Read the existing physical shadow restart receipt and require:

```text
schema_name=shreks.fast_paper_shadow_physical_restart
schema_version=1
state=RESTART_RECONSTRUCTION_PROVEN
release_source_sha=<expected release>
manifest_fingerprint_sha256=<current Fast manifest>
champion_version=<current Fast champion>
champion_fingerprint_sha256=<current Fast champion fingerprint>
action_policy_version=<current Fast action policy>
shadow_runtime=ACTIVE_DETACHED
shadow_enable_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
authoritative_paper_runtime=LEGACY_UNCHANGED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The receipt must be canonical and its `receipt_fingerprint_sha256` must
recompute exactly.

## Current isolated Fast PAPER accounting

Build the current shadow-ledger binding from:

- current Fast runtime manifest;
- the restart receipt's exact `run_id`;
- the supplied isolated shadow ledger database path.

Require the computed binding fingerprint to equal the physical restart receipt.

Load the latest Fast shadow checkpoint and run the existing
`validate_fast_paper_accounting(...)` reconciliation.

Gate:

```text
SHADOW_PAPER_ACCOUNTING_RECONCILED
```

passes only when the accounting status is `RECONCILED`.

The shadow ledger is not required to be flat; it remains isolated evidence only.

## Legacy authoritative PAPER state

Decode the existing legacy observer PAPER runtime manifest with its sealed
canonical decoder.

Use its exact `paper_run_id` to load the latest checkpoint from the supplied
observer database. A missing final checkpoint is insufficient cutover evidence.

Run the existing `validate_paper_accounting(...)` reconciliation.

Observed legacy handoff facts are:

- accounting status;
- latest checkpoint sequence/payload SHA;
- open position count;
- pending entry count;
- deferred execution count;
- active intent count.

Definitions:

- open positions are positions whose ledger state is `OPEN`;
- pending entry count is 1 when `state.pending_entry` exists, otherwise 0;
- deferred execution count is pending entry count plus the number of managed
  positions whose `pending_exit` exists;
- active intent count equals the legacy runtime's existing risk-context
  semantics: one active intent exactly when a pending entry exists.

The gate must require:

```text
LEGACY_PAPER_ACCOUNTING_RECONCILED
LEGACY_OPEN_POSITIONS_ZERO
LEGACY_PENDING_ENTRIES_ZERO
LEGACY_DEFERRED_EXECUTIONS_ZERO
LEGACY_ACTIVE_INTENTS_ZERO
```

A valid but non-flat/non-reconciled state produces `CUTOVER_PREFLIGHT_NOT_READY`.
Malformed/corrupt/fingerprint-drifted identity evidence is a hard error.

## Report

Schema:

`shreks.fast_paper_cutover_preflight` version `1`.

Decision:

- `CUTOVER_PREFLIGHT_READY`;
- `CUTOVER_PREFLIGHT_NOT_READY`.

The report binds:

- expected release SHA;
- Fast runtime manifest fingerprint;
- approved champion registry fingerprint/revision;
- Fast champion version/fingerprint;
- action-policy version;
- physical restart receipt fingerprint;
- shadow ledger binding/checkpoint/accounting status;
- legacy runtime-manifest fingerprint;
- legacy run id/checkpoint fingerprint;
- all observed handoff counts;
- individual gate results.

Every report always states:

```text
production_fast_paper_runner=NOT_PRESENT_IN_THIS_SLICE
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
authoritative_paper_mutation=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Authority firewall

This module must not:

- import or invoke scoring/decision selection;
- execute BUY/SKIP/HOLD/REDUCE/SELL;
- save/modify either PAPER ledger;
- write checkpoints;
- mutate the champion registry;
- invoke systemctl/subprocess;
- stop/start/restart services;
- alter systemd units/targets;
- sign or submit transactions;
- enable LIVE.

Legacy runtime manifest decoding is allowed only to authenticate the existing
historical/production state being retired.

## RED acceptance

Tests must prove:

1. exact promoted champion + restart proof + reconciled shadow ledger + flat,
   reconciled legacy checkpoint => `CUTOVER_PREFLIGHT_READY`;
2. legacy OPEN position => `CUTOVER_PREFLIGHT_NOT_READY`;
3. legacy pending entry => not ready;
4. legacy pending exit/deferred execution => not ready;
5. invalid/incomplete legacy accounting => not ready;
6. invalid shadow accounting => not ready;
7. missing legacy checkpoint => not ready;
8. promoted champion/runtime identity drift is rejected;
9. restart receipt fingerprint drift is rejected;
10. restart receipt release/champion/manifest drift is rejected;
11. shadow binding fingerprint drift is rejected;
12. report fingerprint is deterministic;
13. CLI is packaged;
14. source contains no scoring/execution/checkpoint-write/systemd/signing/LIVE authority.

## Following slice

Implement the production Fast Lane PAPER runner that starts from the unchanged
authoritative `PaperLedger` at a freshly revalidated flat checkpoint, then add
the protected service cutover ceremony. The actual ceremony must re-run this
preflight after the legacy service is stopped and before switching authority.

Rollback after cutover remains either a known-good Fast Lane PAPER release or a
halt/observe-only state; legacy score-gated trading authority must not be
restored.
