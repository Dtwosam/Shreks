# Fast PAPER Shadow Service Execution Bootstrap — Design

**Date:** 2026-09-26  
**Base main SHA:** `809139b2611fda0f231a6d929022f90ce466b2a2`

## Purpose

Add the read/verify-only service bootstrap required before the supervised
Fast PAPER shadow daemon may consume pre-published execution authority.

The daemon already has a decision-only bootstrap. The merged execution path can
consume an authenticated state-bound execution source record, but startup does
not yet prove which isolated ledger run, execution policy, or source directory
the daemon is attached to.

This slice adds that attachment boundary only. It does not initialize ledger
state, consume a source record, execute an action, or mutate any checkpoint.

## Configuration

Add `FastPaperShadowServiceExecutionConfig` with exactly:

- `execution_policy_path`;
- `source_directory`;
- `ledger_database_path`;
- `run_id`.

Add
`load_fast_paper_shadow_service_execution_config(environment=None)` reading:

- `SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID`.

All four settings are explicit and required by this execution bootstrap. The
existing decision-only service configuration remains unchanged.

## Bootstrap contract

Add `bootstrap_fast_paper_shadow_service_execution(manifest, config)`.

It must:

1. require the exact runtime manifest and exact execution config;
2. read/authenticate the existing execution policy against the manifest;
3. build the exact manifest-bound isolated ledger binding from the configured
   run id and database path;
4. require the source directory to be an existing regular non-symlink
   directory;
5. require the execution policy source to stay outside the source directory;
6. require the isolated ledger database to be an existing regular
   non-symlink file;
7. load the latest isolated PAPER checkpoint;
8. load the latest learned shadow runtime state;
9. require both durable objects to exist;
10. require the runtime state's execution-policy fingerprint to equal the
    authenticated execution policy fingerprint;
11. return one immutable bootstrap containing the binding, execution policy,
    exact latest checkpoint, and exact latest learned runtime state.

The bootstrap must not call:

- ledger initialization;
- checkpoint/runtime-state writers;
- source-record producer/writer/consumer;
- shadow executor;
- atomic commit.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
SERVICE_EXECUTION_ATTACHMENT=READ_VERIFY_ONLY
SHADOW_LEDGER_INITIALIZATION=NOT_GRANTED
SHADOW_SOURCE_CONSUMPTION=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
SHADOW_TRANSITION_PERSISTENCE=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public execution-config and bootstrap types;
- explicit four-setting loader;
- execution-policy authentication;
- manifest-bound ledger binding;
- exact latest checkpoint/runtime-state loading;
- missing durable-pair refusal;
- execution-policy fingerprint continuity;
- no state/source mutation or execution authority.

Current main is expected to fail during Python collection because this service
execution bootstrap API does not exist.
