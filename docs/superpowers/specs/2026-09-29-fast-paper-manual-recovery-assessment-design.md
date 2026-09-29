# Fast PAPER Manual-Recovery Assessment — Design

**Date:** 2026-09-29  
**Base main SHA:** `0b360b8b9455cba504f3b2161da13418dd7c2fef`

## Purpose

Add the first dedicated recovery-proof layer for Fast PAPER fail-closed states.

Both the initial physical cutover and later Fast-to-Fast release upgrades
intentionally stop PAPER authority and replace production authorization with a
`REVOKED_MANUAL_RECOVERY` marker if failure occurs after a Fast start attempt.

That boundary is correct, but the repository previously had no dedicated tool
for authenticating the retained state before an operator decides what recovery
action is permissible.

This slice is **read-only**. It does not restart PAPER.

## Supported failure families

The verifier recognizes exactly two recovery families.

### Physical cutover failure

Required evidence:

- canonical
  `shreks.fast_paper_cutover_authorization_revocation`;
- canonical
  `shreks.fast_paper_physical_cutover_failure`;
- the retained authoritative Fast environment/runtime namespace;
- current immutable release identity.

It requires:

- the PAPER campaign unit inactive/dead with MainPID 0;
- detached shadow inactive/dead with MainPID 0;
- failure receipt proving legacy was not restored/restarted;
- Fast unit retained;
- final Fast environment retained;
- authorization revoked;
- release identity matching the retained Fast manifest.

### Fast release-upgrade failure

Required evidence:

- canonical
  `shreks.fast_paper_release_authorization_revocation`;
- canonical
  `shreks.fast_paper_release_upgrade_failure`;
- exact append-only Fast-to-Fast release handoff row;
- retained target authoritative Fast environment/runtime namespace;
- current immutable target release identity.

It requires all runtime units stopped:

- `shreks-paper-campaign.service`;
- `shreks-paper-evidence.service`;
- `shreks-observe.service`;
- `shreks.target`.

The release revocation must bind the same target release/run and exact handoff
fingerprint recorded in the authoritative database.

## Evidence authentication

Every recovery marker/receipt must be:

- existing regular non-symlink file;
- UTF-8 canonical JSON;
- exact schema/field set;
- no duplicate keys;
- no non-finite values;
- exact fail-closed state;
- exact SHA/fingerprint format;
- internally fingerprint-valid.

A malformed, stale, mismatched or cross-family evidence pair fails closed.

## Authoritative runtime proof

After proving runtime authority is stopped, the verifier:

1. reads the canonical authoritative environment;
2. loads the production runtime config;
3. bootstraps the retained authoritative Fast namespace without requiring a
   valid production authorization;
4. authenticates current release identity;
5. validates the exact checkpoint/runtime pair;
6. independently reconciles the authoritative Fast PAPER ledger;
7. requires the authoritative open-position mapping to exactly match the set of
   OPEN ledger positions;
8. verifies the release-handoff audit row when the failure came from a
   Fast-to-Fast upgrade.

Open PAPER positions are allowed and reported. They are never flattened or
modified by this tool.

## Recovery classification

A successful assessment emits one of two states.

### `READY_FOR_FAST_RECOVERY_PLANNING`

The retained Fast state is internally reconciled and there is no unresolved
durable learned work at the assessed boundary.

This is **not restart authority**. It means only that a later reviewed recovery
action can be planned from an authenticated state.

For a source with an authoritative execution cursor, the learned decision cursor
must equal it.

For an initial sequence-0 Fast namespace with no production execution cursor,
the learned shadow baseline cursor may be nonzero, but the decision evidence
directory must contain no post-baseline evidence.

### `RECOVERY_RECONCILIATION_REQUIRED`

The retained namespace is authentic and reconciled but has durable work that
must be understood before any restart, for example:

- pending BUY;
- learned decision one step ahead of authoritative execution;
- sequence-0 initial namespace with newly persisted decision evidence.

Unexpected cursor relationships fail closed rather than being classified.

## Receipt

The canonical assessment reports:

- failure family;
- release/run identity;
- manifest/binding/execution-policy fingerprints;
- decision/runtime-state fingerprints;
- PAPER checkpoint sequence/fingerprint;
- learned decision/execution cursors;
- pending BUY state;
- decision-evidence count;
- open/mapped position counts;
- accounting status;
- release-handoff fingerprint where applicable;
- revocation/failure-receipt fingerprints;
- exact stopped unit set.

Every successful assessment states:

```text
recovery_restart_authority=NOT_GRANTED
service_control_authority=READ_ONLY
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## CLI

```text
sudo /opt/shreks/current/.venv/bin/shreks-fast-paper-manual-recovery \
  assess \
  --failure-receipt-path <exact-root-private-failure-receipt>
```

Production paths are fixed to:

```text
/etc/shreks/fast-paper-authoritative.env
/etc/shreks/fast-paper-cutover-authorization.json
/opt/shreks/current
```

The command requires root because it reads protected production evidence.

## Host-command firewall

The verifier may issue only exact read-only `systemctl show` calls for:

- PAPER campaign;
- PAPER evidence;
- observer;
- Shreks target;
- detached Fast PAPER shadow.

It must never invoke:

- start;
- stop;
- restart;
- daemon-reload;
- enable/disable;
- journal mutation;
- file replacement;
- authorization rewrite;
- ledger/checkpoint commit;
- BUY/HOLD/REDUCE/SELL execution;
- signing/submission;
- LIVE.

## Acceptance proof

Tests must prove:

1. a clean failed physical-cutover baseline authenticates as
   `READY_FOR_FAST_RECOVERY_PLANNING`;
2. durable post-baseline decision evidence is classified
   `RECOVERY_RECONCILIATION_REQUIRED`;
3. release-upgrade recovery authenticates the append-only handoff and carries
   open-position mapping safely;
4. an active PAPER writer fails before authoritative bootstrap;
5. tampered revocation fingerprints fail closed;
6. ledger/runtime open-position mapping mismatch fails closed;
7. the command runner rejects every service-control action;
8. the source contains no mutation, trade-execution, signing/submission or LIVE
   authority;
9. Python, Rust, ARM64 and repository-safety CI remain green.

## Following slice

A later separately reviewed recovery-action layer may consume a successful
assessment.

That layer must preserve the same non-legacy boundary:

- never restore the legacy score-gated PAPER runtime after a Fast start attempt;
- choose only an authenticated known-good Fast namespace/release;
- explicitly reconcile any pending BUY or learned decision gap;
- issue a fresh exact production authorization only after recovery proof;
- start Fast PAPER under bounded observation;
- keep signing/submission not granted;
- keep LIVE disabled.

This assessment slice grants none of that mutation authority.
