# Fast Lane Post-Cutover Release Manager — Design

**Date:** 2026-09-29  
**Base main SHA:** `7bcf146a27d79d09bfa6194bc74fda0885731745`

## Purpose

Allow immutable Shreks releases to continue after production PAPER authority has
moved to the learned Fast Lane runtime.

The legacy G2 release manager intentionally refuses ordinary activation whenever
the Fast PAPER production-authorization marker exists. That protects Fast PAPER
from being silently replaced by the legacy score-gated campaign runtime.

This slice adds a separate Fast-aware activation path while keeping that legacy
guard intact.

LIVE remains disabled.

## Delivery routing

The existing root release manager keeps the same externally authorized
`install` command.

After staging and re-verifying the immutable release:

- no Fast production-authorization marker -> existing legacy activation path;
- existing regular Fast production-authorization marker -> Fast-aware release
  upgrade path.

No new SSH command or sudoers permission is required.

Explicit administrator commands are also available:

```text
install-fast
activate-fast-existing
```

The target Fast run ID is deterministic and release-specific:

```text
fast-paper-release-<40-char-target-source-sha>
```

That makes a pre-start retry reuse the same append-only successor namespace.

## Production authorization

The authoritative runtime now accepts either:

1. the original physical-cutover authorization; or
2. a Fast-to-Fast release authorization.

The release authorization binds:

- source release SHA;
- source production-authorization fingerprint;
- append-only Fast release-handoff fingerprint;
- target release SHA;
- target manifest fingerprint;
- champion/action-policy identity;
- target Fast run ID;
- target binding fingerprint;
- target execution-policy fingerprint;
- authorization timestamp.

It retains:

```text
production_paper_cutover=GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

Malformed, stale, mismatched or revoked authorization fails runtime startup
closed.

## Routine-release compatibility boundary

The target manifest is rebuilt from the stopped source runtime and the staged
immutable target release.

Routine Fast-aware activation requires exact trading semantics:

- same champion bytes/identity;
- same Fast decision binary SHA;
- same Fast feature-feed binary SHA;
- same continuous action policy;
- same state/event-loop versions;
- same risk/fill/position-action policy versions;
- same strategy/assessment identity;
- same quote provider/mint/decimals and route-evidence version;
- same authoritative observer database;
- same PAPER evidence and learned-decision checkpoint paths.

Release-local executable paths are retargeted from the current immutable release
to the staged target release and must contain the exact same reviewed bytes.

The execution policy is rebuilt against the target manifest using the exact
source risk/fill/position policy objects.

The BUY-writer policy is rebuilt with the target release-local entry-authority
binary while preserving every market/regime/safety/economics/risk-control value.

Any semantic change is not a routine deploy and requires a separate reviewed
migration.

## Clean handoff boundary

Before switching releases the active Fast PAPER service must be healthy and
authenticated by its current production authorization.

The manager stops only PAPER authority first, then reloads the exact stopped
source bootstrap.

Handoff fails closed unless:

- pending BUY is absent;
- learned decision cursor equals authoritative execution cursor;
- source binding/checkpoint/runtime state remain authentic;
- target run namespace is fresh or an exact deterministic replay.

Open PAPER positions are allowed and carry forward unchanged through the
append-only Fast release handoff.

The successor handoff timestamp is derived deterministically from the stopped
source checkpoint, so exact retry after pre-start rollback is storage
idempotent.

## Release-bound evidence archive

Learned decision evidence and execution-authority source records are
release/manifest bound.

After the append-only successor namespace is created, all active release-bound
files are moved to:

```text
/var/lib/shreks/fast-paper-authoritative/release-history/<source-fast-run-id>/
```

The active decision checkpoint is not archived; it is atomically replaced by
the target-manifest decision state with the exact carried cursor.

The active execution/BUY/USD/reduction/retry roots therefore begin empty for the
target release.

Before target start, rollback restores every archived file exactly.

## Atomic authority rotation

After PAPER is stopped and successor state exists, the manager stops the
supporting observer/evidence services and target, then atomically rotates:

- runtime manifest;
- manifest-bound execution policy;
- BUY-writer policy;
- learned decision checkpoint;
- authoritative environment Fast run ID;
- production authorization;
- active systemd units;
- `/opt/shreks/current`.

The paper-campaign unit always comes from the target release's sealed
authoritative Fast commissioning asset, never the legacy campaign unit in
`deploy/systemd/shreks-paper-campaign.service`.

Observer, evidence and target units come from the verified staged release.

## Verification

After `shreks.target` starts, the manager requires:

- all four runtime units active;
- PAPER process provenance from the exact target release;
- observer and evidence executables/cwd from the exact target release;
- target authoritative bootstrap exactly equals the append-only handoff result;
- at least two advancing Fast runtime status rows;
- exact target manifest/champion identity;
- `production_paper_cutover=GRANTED_AND_ACTIVE`;
- signing/submission not granted;
- LIVE disabled;
- stable PAPER PID/invocation/restart count through the bounded observation.

Success receipt:

```text
state=FAST_PAPER_RELEASE_UPGRADE_ACTIVE
production_paper_runtime=FAST_LANE_LEARNED
production_paper_cutover=ACTIVE
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Rollback boundary

Before the first target `shreks.target` start attempt, any failure restores:

- source protected authority bytes and metadata;
- source learned decision checkpoint;
- source production authorization;
- archived evidence/source records;
- source systemd unit bytes;
- source current-release symlink;

then restarts and health-checks the source release.

The append-only unused successor database namespace is retained. Deterministic
handoff time/run ID makes an exact retry idempotent.

At or after the first target start attempt, automatic rollback is forbidden.

The manager:

- stops target runtime authority;
- replaces production authorization with a revoked manual-recovery marker;
- does not restart the source Fast runtime;
- never restores the legacy score-gated PAPER runtime;
- writes a root-private `MANUAL_RECOVERY_REQUIRED` receipt.

## Command firewall

The package upgrade manager may invoke only bounded operations required for the
Fast release transition:

- stop the Fast PAPER service;
- stop observer/evidence/target after PAPER is quiescent;
- daemon-reload;
- start `shreks.target`;
- read exact systemd state/health;
- bounded PAPER journal read.

It may not:

- invoke `systemctl restart`;
- enable/disable units;
- start the legacy score runtime;
- stop/start the detached shadow service;
- sign/submit transactions;
- enable LIVE.

## Acceptance proof

Tests must prove:

1. both initial cutover and release authorizations authenticate runtime startup;
2. release authorization rejects identity/fingerprint drift;
3. root release-manager `install` routes legacy before cutover and Fast-aware
   after cutover;
4. Fast-aware delegation uses the current Fast release CLI and deterministic
   target run ID;
5. pending BUY or cursor gap blocks handoff;
6. release-local authority paths retarget only inside the immutable release;
7. release-bound evidence is archived while the decision checkpoint remains
   active;
8. unreviewed systemd actions fail the command allowlist;
9. pre-start rollback restores source authority only;
10. post-start failure leaves authority stopped with revoked authorization;
11. no legacy scoring, signing/submission or LIVE authority is introduced;
12. Python, Rust, ARM64 and repository-safety CI remain green.

## Following slice

After merge and a release seal, deploy this capability while the current PAPER
authority remains unchanged.

Once production PAPER has actually cut over to Fast Lane, subsequent immutable
releases may use this Fast-aware path. Strategy/model/policy promotion remains a
separate authority from routine code deployment.
