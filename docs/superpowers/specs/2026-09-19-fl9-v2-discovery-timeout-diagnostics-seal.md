# FL9 V2 Discovery Timeout Diagnostics — Release Seal

**Date:** 2026-09-19  
**Implementation main SHA:** `22fc2f4e7e7b1f5281a5dc12dc00cf7193ad3ce1`  
**Status:** SEALED FOR IMMUTABLE RELEASE + PROTECTED PAPER DEPLOY/VERIFY DIAGNOSTICS ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified fail-closed production-verifier diagnostics added after the first fully automatic sealed PAPER delivery reached the production verifier but timed out waiting for a telemetry-mediated FL9 V2 discovery result.

The preceding automatic delivery proved:

- sealed-main CI succeeded;
- immutable release creation succeeded automatically;
- protected PAPER deployment succeeded automatically;
- the active release and release manifest matched the sealed SHA;
- all three core PAPER services were active/running with zero restarts;
- recent core-runtime journals had no failure signature;
- the FL9 discovery bridge was importable;
- protected discovery timed out after 180 seconds on two verifier attempts.

This seal exists only to make that timeout self-diagnosing.

## Implemented diagnostics

Merged PR #316, `fix: expose FL9 discovery timeout diagnostics`, adds read-only evidence before the existing timeout failure:

1. `shreks-telemetry.timer` ActiveState and SubState;
2. timer LastTriggerUSec;
3. timer NextElapseUSecRealtime;
4. `shreks-telemetry.service` ActiveState and SubState;
5. service Result;
6. service ExecMainCode and ExecMainStatus;
7. service ExecMainStartTimestamp and ExecMainExitTimestamp;
8. whether the exact discovery marker still exists;
9. marker path/mode/owner UID/GID/size/mtime metadata without reading marker contents;
10. recent `shreks-telemetry.service` journal output;
11. an explicit begin/end diagnostic boundary.

The verifier still exits nonzero after a discovery timeout.

## Production failure evidence motivating this seal

Automatic delivery run:

`35439069481`

First verifier attempt:

- exact active release: `65338db83263a4970fdad65f23387b60ff685a77`;
- release manifest source SHA matched;
- `shreks-observe.service`: active/running, NRestarts=0;
- `shreks-paper-evidence.service`: active/running, NRestarts=0;
- `shreks-paper-campaign.service`: active/running, NRestarts=0;
- recent failure signatures: none;
- historical evidence read access from deploy identity: denied as designed;
- FL9 discovery bridge: available;
- result: timeout after 180 seconds.

The failed verifier job was retried once. GitHub re-ran the same exact immutable release deployment successfully, then the second verifier attempt reproduced the same discovery timeout.

Therefore this is not being treated as a release-identity or one-off deployment failure.

## Verification evidence

Intentional RED head:

`4e7548e5cfc7bdcb9df05eecda523e60f44ea91c`

RED CI run:

`35439546185`

RED result:

- Repository safety: green;
- Rust tests: green;
- ARM64 release build: green;
- Python: exactly one expected failure;
- Python total: 1 failed, 3441 passed.

The failure was exactly:

`test_production_verifier_reports_read_only_telemetry_diagnostics_on_discovery_timeout`

GREEN feature head:

`9724593400cbe68b5997fe655083ac01e001e2ce`

GREEN PR CI run:

`35447457884`

All four canonical gates completed successfully.

Squash-merged implementation main:

`22fc2f4e7e7b1f5281a5dc12dc00cf7193ad3ce1`

Exact merged-main CI run:

`35447608306`

All four canonical gates completed successfully.

## Authority boundary

After this seal lands and exact sealed-main CI succeeds, it authorizes only:

1. immutable release creation for the exact seal SHA;
2. automatic protected PAPER deployment of that release;
3. automatic reusable production verification;
4. read-only protected FL9 discovery;
5. collection of the newly bounded telemetry timeout diagnostics if discovery again times out.

This seal does not authorize modifying telemetry state in response to diagnostics.

It does not authorize:

- `systemctl start`, restart, reset-failed, enable, or disable operations for diagnosis;
- permission or ownership changes;
- new sudo authority;
- protected-state mutation outside existing telemetry receipt behavior;
- V2 scoring;
- a fresh scoring request;
- model fitting;
- champion publication;
- PAPER promotion;
- risk-intent creation;
- signing;
- transaction submission;
- LIVE trading.

## Required continuation

If the verifier returns a canonical trusted discovery HOLD or FOUND result, preserve that exact evidence and follow the already-sealed downstream authority boundaries.

If the verifier times out again, use the new diagnostics to distinguish at minimum:

- timer not triggering;
- telemetry service failing;
- telemetry service still active/busy;
- discovery marker absent;
- discovery marker still pending;
- journal-visible bridge failure.

Any corrective runtime or systemd change after that evidence is a separate reviewed implementation slice and requires its own tests and seal before production use.

## Promotion boundary

`AUTO_PAPER_DELIVERY=PROVEN_THROUGH_DEPLOY`

`DISCOVERY_TIMEOUT=REPRODUCIBLE`

`TIMEOUT_DIAGNOSTICS_IMPLEMENTATION=MAIN_GREEN`

`TIMEOUT_DIAGNOSTICS_SEAL=PENDING_MERGE`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
