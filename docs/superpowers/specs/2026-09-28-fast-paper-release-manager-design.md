# Fast Lane Post-Cutover PAPER Release Manager — Design

**Date:** 2026-09-28  
**Base main SHA:** `7bcf146a27d79d09bfa6194bc74fda0885731745`

## Purpose

Restore immutable release upgrades after Fast Lane becomes the authoritative
production PAPER runtime without ever falling back to the legacy score-gated
campaign.

The existing G2 release manager intentionally blocks ordinary activation when
`/etc/shreks/fast-paper-cutover-authorization.json` exists. That fail-closed
guard remains correct.

This slice adds a separate release-local Fast-aware manager and teaches the
already-rooted G2 `install` entrypoint to delegate to it after cutover.

LIVE remains disabled.

## Deployment-account boundary

The deploy account keeps the existing exact sudo command shape:

```text
/usr/local/sbin/shreks-release-manager install
  /var/tmp/shreks-release-*.tar.gz
  /var/tmp/shreks-release-*.tar.gz.sha256
  /var/tmp/shreks-release-*.RELEASE_MANIFEST.json
```

No new sudo verb, shell, wildcard authority, protected-state read authority, or
systemd command is granted to the deploy account.

The root release manager still:

1. authenticates and stages the immutable release;
2. detects whether the Fast cutover/recovery guard path exists;
3. before cutover, uses the existing legacy activation path;
4. after cutover, invokes only the current immutable release's installed
   `shreks-fast-paper-release-manager activate-staged <target-release>`.

The legacy `activate_release(...)` function keeps its existing post-cutover
guard. Calling it directly after cutover still fails before service control.

## Root-manager prerequisite

`/usr/local/sbin/shreks-release-manager` is a separately installed root
control-plane helper. Ordinary immutable releases transport a sealed copy in
the wheel but do not replace the installed root helper.

Therefore **before the first physical Fast PAPER cutover**, a trusted
administrator must use a separately reviewed release-bound installation proof
to refresh the root helper to the exact sealed version containing the Fast-aware
dispatch.

This slice does not silently replace `/usr/local/sbin`.

Until that prerequisite is proven, physical cutover may be technically possible
but future automatic deployments would remain intentionally blocked.

## Target release authentication

The Fast-aware manager runs from the current authoritative Fast release.

Before stopping PAPER it authenticates the staged target release:

- canonical G2 release manifest;
- exact release directory/source SHA identity;
- every manifest-listed payload size/SHA;
- one installed Shreks wheel;
- target release virtualenv;
- sealed Fast proof tools;
- sealed Fast runtime feature tool;
- sealed authoritative Fast PAPER candidate unit.

The target native Fast tools are materialized from the authenticated sealed
wheel into the staged target release's private
`.venv/shreks-fast-tools` directory with executable permissions. They remain
release-local and are re-bound by exact SHA-256 in the target runtime manifest
and BUY-writer policy.

This staging may happen during Fast upgrade preflight and is non-economic: it
does not alter the current service, `/etc/shreks`, authoritative PAPER state,
or `/opt/shreks/current`. It also does not depend on any historical operator
choice for the source manifest's binary path layout.

## Routine release compatibility

The target authority is reconstructed from the current authority.

The target runtime manifest changes only release identity and authenticated
release-bound tool paths. The existing Fast-to-Fast handoff remains the final
compatibility gate.

A routine release upgrade requires exact equality of trading semantics,
including:

- champion identity and bytes;
- decision binary bytes;
- runtime feature-feed binary bytes;
- continuous action policy;
- risk policy;
- fill policy;
- position-action policy;
- service/quote identity;
- strategy/assessment/state identities;
- authoritative database identity.

The target execution policy is rebuilt against the target manifest with the
same risk/fill/position policies.

The BUY-writer policy is rebuilt with the same market/regime/safety/economics
and operator-risk policy, but with the target release's authenticated
entry-authority binary path. Its binary digest must equal the current release.

A release that changes trading semantics is not a routine deployment and fails
before service control.

## Fresh successor namespace

Every successful or attempted handoff uses an append-only target run namespace.

The preferred target ID is:

```text
fast-release-<target-release-sha>
```

If that namespace already exists because an earlier pre-start attempt committed
a durable handoff, retry selects:

```text
fast-release-<target-release-sha>.2
fast-release-<target-release-sha>.3
...
```

No prior binding/checkpoint/runtime/handoff rows are deleted or overwritten.

## Protected upgrade sequence

The exact sequence is:

```text
authenticate current Fast release + valid authorization
-> authenticate/stage target release and sealed Fast assets
-> prove current Fast PAPER process is healthy/exact
-> stop shreks-paper-campaign.service
-> prove inactive/dead
-> reload/authenticate exact post-stop source state
-> capture rollback bytes from that post-stop state
-> replace valid authorization with invalid UPGRADE_IN_PROGRESS guard
-> append target Fast-to-Fast release handoff
-> stop observe/evidence/target for immutable release switch
-> atomically rotate target manifest/execution policy/BUY policy/decision state/env
-> install target observe/evidence/target units + sealed Fast PAPER unit
-> atomically switch /opt/shreks/current
-> daemon-reload
-> bootstrap/authenticate complete target Fast authority
-> replace UPGRADE_IN_PROGRESS with valid target authorization
-> START BOUNDARY
-> systemctl start shreks.target
-> verify target Fast process provenance and companion services
-> bounded authoritative runtime-status observation
-> persist root-private success receipt
```

The post-stop source reload is mandatory: the source runtime may commit a final
cycle while systemd is stopping. Rollback bytes must represent the state after
the process is fully inactive, not a pre-stop snapshot.

## Upgrade guard

Immediately after the source Fast writer is stopped, the valid runtime
authorization is replaced atomically with a canonical invalid guard:

```text
state=UPGRADE_IN_PROGRESS
production_paper_cutover=PAUSED_FOR_RELEASE_UPGRADE
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The normal authoritative runtime does not recognize that schema as a valid
cutover authorization. An unexpected PAPER service start during multi-file
rotation therefore fails closed.

A new valid authorization is installed only after:

- successor state exists;
- all target control files are installed;
- the target Fast unit is installed;
- the current release link points to the target;
- target runtime bootstrap exactly matches the handoff.

The target authorization preserves the original physical-cutover
preflight/baseline fingerprints as provenance while rebinding release,
manifest, Fast run, binding and execution-policy identity.

## Rollback boundary

**Before the first target Fast start attempt**, failure may restore:

- exact post-stop source manifest/policies/decision checkpoint/env;
- exact source systemd units;
- exact source release symlink;
- exact source valid authorization;

and restart the source Fast release.

The durable failed target handoff namespace remains append-only history. A
later retry uses a fresh target run ID.

**At or after the first target Fast start attempt**, automatic rollback to the
source Fast run is forbidden.

Failure then:

- stops all runtime services best-effort;
- replaces target authorization with the existing
  `REVOKED_MANUAL_RECOVERY` marker;
- does not restart source Fast;
- does not restore legacy score-gated PAPER;
- records `MANUAL_RECOVERY_REQUIRED`;
- leaves PAPER stopped for explicit reconciliation.

This mirrors the physical-cutover no-return boundary and prevents two Fast run
namespaces from both becoming economic authority.

## Systemd allowlist

The Fast-aware release manager may use only:

- `systemctl show shreks-paper-campaign.service ...`;
- stop:
  - `shreks-paper-campaign.service`;
  - `shreks-paper-evidence.service`;
  - `shreks-observe.service`;
  - `shreks.target`;
- `systemctl daemon-reload`;
- `systemctl start shreks.target`;
- read-only `systemctl is-active --quiet` for observe/evidence/target;
- bounded PAPER `journalctl`.

It may not use restart, enable, disable, arbitrary units, detached-shadow
service control, signing/submission, or LIVE.

## Receipt states

Successful target activation records:

```text
state=FAST_PAPER_RELEASE_UPGRADE_ACTIVE
authoritative_paper_runtime=FAST_LANE_LEARNED_ACTIVE
production_paper_cutover=ACTIVE
service_control_authority=EXERCISED_BY_PROTECTED_RELEASE_UPGRADE
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

Post-start failure records:

```text
state=MANUAL_RECOVERY_REQUIRED
production_paper_cutover=STOPPED_MANUAL_RECOVERY
source_fast_restarted=false
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

Receipts are target-release-specific so later releases are not blocked by an
earlier successful receipt.

## Authority firewall

This slice does not:

- authorize a champion/policy/strategy change;
- execute a direct BUY/SKIP/HOLD/REDUCE/SELL outside normal Fast runtime;
- contact signing or submission APIs;
- use wallet material;
- enable LIVE;
- restore legacy score-gated PAPER after Fast cutover.

## Acceptance proof

Tests must prove:

1. target incompatibility fails before any service-control command;
2. source rollback snapshot is captured only after PAPER is confirmed stopped
   and source authority is reloaded;
3. invalid upgrade guard precedes successor handoff/control rotation;
4. target authorization is installed only after exact target bootstrap proof;
5. target start is the hard no-return boundary;
6. pre-start failure restores source Fast authority;
7. post-start failure never restores source/legacy authority and revokes target
   authorization;
8. failed pre-start handoffs use fresh append-only run IDs on retry;
9. root G2 install delegates to the current release Fast helper after cutover;
10. missing/symlinked Fast helper fails before service control;
11. direct legacy activation remains blocked after cutover;
12. command allowlist rejects restart/enable/disable/arbitrary service control;
13. source contains no scoring, signing/submission, legacy campaign execution or
    LIVE authority;
14. Python, Rust, ARM64 and repository-safety CI remain green.

## Following slice

Before physical Fast cutover can safely be performed on the protected host:

1. seal and deploy this Fast-aware release capability while legacy PAPER is
   still authoritative;
2. add/execute a separately reviewed release-bound installation proof that
   refreshes `/usr/local/sbin/shreks-release-manager` to the exact sealed
   Fast-aware version;
3. prove the existing sudoers command shape is unchanged;
4. re-run physical-cutover readiness.

Only then is the host operationally ready to switch production PAPER authority
without freezing all future deployments.

LIVE remains disabled.
