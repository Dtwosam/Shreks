# Fast Lane Protected Physical PAPER Cutover — Design

**Date:** 2026-09-28  
**Base main SHA:** `6affa055e7e504f010d5e96446157264d086e13e`

## Purpose

Perform the first protected production PAPER authority switch from the legacy
observer campaign runtime to the learned Fast Lane authoritative PAPER runtime.

This slice creates the cutover mechanism. It does not execute the ceremony on a
host from repository CI.

LIVE remains disabled.

## App-level cutover authorization

The authoritative runtime now has a second gate in addition to systemd.

`--preflight` remains usable before cutover, but an ordinary runtime start
requires:

```text
/etc/shreks/fast-paper-cutover-authorization.json
```

The root-issued canonical authorization binds:

- exact release source SHA;
- exact Fast manifest/champion/action policy;
- exact Fast authoritative run ID;
- exact authoritative binding fingerprint;
- exact execution-policy fingerprint;
- exact final cutover-preflight report fingerprint;
- exact decision-baseline receipt fingerprint.

A mismatched, missing, malformed, stale, or symlinked authorization fails
normal authoritative runtime startup closed.

The authorization retains:

```text
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Protected cutover sequence

The ceremony requires root and the exact active release virtualenv.

Before mutation it proves:

1. protected authoritative host readiness is
   `READY_FOR_PROTECTED_PAPER_CUTOVER_REVIEW`;
2. the installed active unit is the exact release-local legacy
   `shreks-paper-campaign.service`;
3. the legacy PAPER process is active and comes from the exact release;
4. detached Fast PAPER shadow remains inactive/dead;
5. no cutover authorization exists;
6. the authoritative decision checkpoint is the only member of its decision
   root;
7. all execution/source-authority directories are empty;
8. authoritative PAPER checkpoint sequence is still zero with no processed
   learned execution, pending BUY, or mapped position;
9. the Fast replacement unit is extracted only from the verified sealed wheel.

Mutation order is:

```text
stop legacy shreks-paper-campaign.service
-> require inactive/dead
-> re-run final CUTOVER_PREFLIGHT_READY against stopped legacy state
-> create exact cutover authorization
-> atomically replace shreks-paper-campaign.service bytes with sealed Fast unit
-> systemctl daemon-reload
-> start shreks-paper-campaign.service
-> verify exact Fast process provenance
-> bounded runtime observation
-> persist root-private success receipt
```

No target membership change is required: `shreks.target` already names
`shreks-paper-campaign.service`.

## Bounded production verification

After start, the process must remain stable for an explicit 5–900 second
observation window.

Verification requires:

- active/running systemd state;
- stable MainPID and InvocationID;
- no automatic restart-counter change;
- exact unit FragmentPath;
- exact active-release cwd;
- `User=shreks` and `Group=shreks`;
- `PrivateNetwork=true`;
- exact module
  `shreks_brain.fast_paper_runtime.authoritative_runtime`;
- at least two advancing authoritative runtime status rows;
- `mode=PAPER_AUTHORITATIVE_FAST`;
- `production_paper_cutover=GRANTED_AND_ACTIVE`;
- exact manifest and champion fingerprints;
- `signing_submission_authority=NOT_GRANTED`;
- `live=DISABLED`;
- non-regressing durable decision/execution/checkpoint state.

Successful receipt state:

```text
PRODUCTION_PAPER_CUTOVER_ACTIVE
authoritative_paper_runtime=FAST_LANE_LEARNED_ACTIVE
legacy_paper_runtime=STOPPED
production_paper_cutover=ACTIVE
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Rollback boundary

The ceremony snapshots all authoritative durable state before stopping legacy.

If any failure occurs after legacy stop, the Fast service is stopped and the
authorization is revoked.

Automatic legacy restart is permitted only when the authoritative snapshot is
**exactly unchanged** from the pre-cutover snapshot.

That means no change to:

- learned decision state/cursor;
- decision-directory members;
- authoritative PAPER checkpoint;
- authoritative runtime-state fingerprint/cursor;
- pending BUY/open-position identity;
- source-authority directory members.

When unchanged, the legacy unit is restored if necessary, daemon-reloaded if
necessary, and the exact release-local legacy runtime is restarted.

If any authoritative durable state changed, the legacy unit bytes are restored
but the legacy service is **not** restarted. PAPER authority remains stopped and
a root-private receipt records:

```text
state=MANUAL_RECOVERY_REQUIRED
production_paper_cutover=STOPPED_MANUAL_RECOVERY
legacy_service_restarted=false
```

This prevents duplicate or divergent economic PAPER actions across namespaces.

## Command allowlist

The physical cutover runner may invoke only:

- `systemctl show shreks-paper-campaign.service ...`;
- `systemctl show shreks-fast-paper-shadow.service ...`;
- `systemctl stop shreks-paper-campaign.service`;
- `systemctl daemon-reload`;
- `systemctl start shreks-paper-campaign.service`;
- bounded `journalctl -u shreks-paper-campaign.service ... -o cat`.

It may not use:

- `systemctl restart`;
- `enable`/`disable`;
- shadow service stop/start;
- any other unit;
- signing/submission;
- LIVE.

## CLI

```text
shreks-fast-paper-physical-cutover preflight <release-sha> ...
shreks-fast-paper-physical-cutover activate <release-sha> ... --observe-seconds <5..900>
```

The activate command intentionally requires the same final evidence inputs as
the read-only cutover preflight so it can re-run that proof after legacy PAPER
has stopped.

## Acceptance proof

Tests must prove:

1. runtime preflight does not require cutover authorization;
2. ordinary authoritative runtime start rejects missing/invalid authorization;
3. authorization binds exact release/run/binding/policy identity;
4. physical preflight requires exact legacy process and quiesced shadow;
5. final cutover preflight executes only after legacy stop;
6. sealed Fast unit replaces the active unit atomically;
7. runtime starts with `GRANTED_AND_ACTIVE` status and LIVE disabled;
8. unchanged-state failure restores legacy automatically;
9. changed-state failure never restarts legacy and emits manual-recovery proof;
10. unreviewed systemd operations are rejected by the command allowlist;
11. Python, Rust, ARM64, and repository-safety CI remain green.

## After this slice

Once this code is merged and an immutable release containing it is deployed,
the protected administrator may run the host preparation, final baseline, and
physical cutover ceremony.

That host execution—not this repository merge—is the point at which production
PAPER trading actually starts on Fast Lane.

LIVE remains disabled.
