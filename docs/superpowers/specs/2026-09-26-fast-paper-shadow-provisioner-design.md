# Fast PAPER Shadow Provisioner — Design

**Date:** 2026-09-26  
**Base main SHA:** `a1ed90d276cecd347559785d5b5ea1027f9cba6c`

## Purpose

Add an explicit one-time provisioning command for the coordinated Fast PAPER
shadow supervisor.

The supervisor bootstrap intentionally remains read/verify-only. A clean host
therefore needs a separate mutation boundary that creates the private shadow
directories and the initial isolated ledger/checkpoint/runtime pair before the
supervisor can pass preflight.

Provisioning must never run implicitly from the service or from systemd
preflight.

## Configuration

Add `FastPaperShadowProvisionConfig` containing:

- exact `FastPaperShadowSupervisorConfig`;
- explicit positive finite `starting_cash_usd`.

Load all existing supervisor settings unchanged plus:

- `SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD`.

## Mutation boundary

`provision_fast_paper_shadow(...)` may:

1. authenticate the runtime manifest and execution policy before any ledger
   state is created;
2. create the four private shadow roots when their common host-owned parent
   already exists:
   - decision evidence/checkpoint root;
   - execution-source root;
   - reduction-source root;
   - pending-BUY-retry-source root;
3. create the isolated ledger database and persisted binding;
4. create sequence-0 PAPER state using only:
   - explicit starting cash;
   - exact execution-policy fill policy;
   - exact execution-policy position-action policy;
   - one supplied provisioning clock value;
5. create the matching learned runtime state with:
   - no pending BUY;
   - no market positions;
   - no processed learned decision identity;
   - the exact execution-policy fingerprint;
6. verify the completed state through the existing execution bootstrap and
   decision bootstrap.

It may not create manifest/policy authority files, fetch provider data, run
inference, consume source records, execute trades, or touch authoritative PAPER
state.

## Existing database rule

If the configured isolated ledger database already exists, provisioning must
not attempt initialization or repair.

It must instead authenticate the existing run through the normal execution
bootstrap and require:

- the configured starting cash equals the durable ledger starting cash;
- the exact run/policy/checkpoint/runtime bindings are valid.

A complete existing run is an idempotent success.

A partial/torn/incompatible existing database fails closed. This provisioner
does not guess whether an existing database is safe to repair or delete.

## Directory safety

Provisioning may create only a missing leaf directory whose parent already
exists as a regular non-symlink directory.

It must never recursively create arbitrary parents or follow a symlinked target.

All created shadow directories use mode 0700.

Decision, execution, reduction, and retry roots remain distinct and
non-overlapping.

## CLI

Add:

`python -m shreks_brain.fast_paper_runtime.shadow_provision --initialize`

No default mutating action is permitted.

The command emits one canonical result document and returns nonzero on any
fail-closed validation error.

The packaged env example gains
`SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD`.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
PROVISIONING=EXPLICIT_ONLY
SUPERVISOR_PREFLIGHT=READ_VERIFY_ONLY
INITIAL_SHADOW_LEDGER_MUTATION=GRANTED
INITIAL_SHADOW_RUNTIME_STATE_MUTATION=GRANTED
EXISTING_RUN_REPAIR=NOT_GRANTED
SOURCE_RECORD_PRODUCTION=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- new provisioner module/config/result/main API;
- exact supervisor-config reuse;
- explicit starting cash;
- authority-file authentication before initialization;
- private leaf-directory creation;
- exact sequence-0 ledger/runtime construction;
- existing complete-run idempotent verification;
- partial existing-run fail-closed behavior;
- supervisor preflight source contains no provisioner call;
- env example includes starting cash;
- no scoring, source production/consumption, execution, provider/network,
  signing/submission, authoritative PAPER, or LIVE authority.
