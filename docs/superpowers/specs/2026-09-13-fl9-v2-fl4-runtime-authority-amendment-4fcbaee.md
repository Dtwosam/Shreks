# FL9 V2 FL4 Physical Runbook — Runtime Authority Amendment for 4fcbaee

## Status

**AUTHORIZED RUNBOOK AMENDMENT.**

This document supersedes only the runtime-release binding established by `docs/superpowers/specs/2026-09-13-fl9-v2-fl4-runtime-authority-amendment.md` for the physical FL4 procedure in `docs/superpowers/specs/2026-09-12-fl9-v2-fl4-physical-execution-runbook.md`.

It does not supersede `docs/superpowers/specs/2026-09-13-fl9-v2-fl4-explicit-quiesce-amendment.md`; that explicit quiesce order remains mandatory.

The prior authorized runtime was:

`9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73`

Physical production quiesce later proved that runtime unsuitable because the observer could remain alive through the full 30-second stop deadline. Intermediate sealed runtimes fixed portions of that shutdown path but still failed the direct restart acceptance proof.

For every runtime-identity requirement in the FL4 physical runbook after this amendment, the authorized runtime SHA is:

`4fcbaee62ab33431875109edf98d9b0d5c01cbae`

Immutable release tag:

`shreks-4fcbaee62ab33431875109edf98d9b0d5c01cbae`

## Evidence for the replacement binding

- sealed runtime `dc6861d25ab2ed3426a172a0385a5c027064743e` bounded realtime shutdown cleanup, but its direct production observer restart still reached approximately the full 30-second stop deadline;
- PR #293 bounded the normalizer's fresh Pump selector to the newest 2,048 raw rows and produced sealed runtime `6034c37f7d6021ba2664418f72d5a8790d7202c7`;
- the direct production restart on `6034c37f7d6021ba2664418f72d5a8790d7202c7` still took `30278 ms`, so that runtime was not accepted;
- production then proved the analogous PumpSwap fresh selector exceeded 20 seconds while a 2,048-row bounded-frontier form completed in approximately `124 ms`;
- PR #294 added the symmetric PumpSwap frontier plus a RED/GREEN regression;
- exact PR head `a7ca34f4de57d9c00a14799e7ec18449ddb77b4c` passed all four canonical CI lanes on both branch and pull-request runs;
- PR #294 was squash-merged with seal commit `4fcbaee62ab33431875109edf98d9b0d5c01cbae`;
- main CI run `34778967647` passed all four canonical lanes on that exact SHA;
- immutable release run `34779106639` succeeded and published `shreks-4fcbaee62ab33431875109edf98d9b0d5c01cbae`;
- protected deployment run `34780516014` installed that exact release successfully;
- production verifier run `34781006506` proved exact release and manifest identity, all three PAPER services active/running with `NRestarts=0` and `ExecMainStatus=0`, zero observer invalid-response lines, and no recent SQLite-contention or runtime-restart signatures;
- the final direct physical observer restart completed in `36 ms`;
- that restart emitted the normal realtime-writer stop marker and `Shreks observe stopped:`, contained no timeout or SIGKILL signature, changed only the observer PID, and left both sibling PAPER PIDs and the target activation timestamp unchanged.

This closes only the runtime graceful-shutdown condition. It does not close the privileged frozen-cohort or FL4 prestate gates.

## Unchanged authority

All other runbook authority remains unchanged, including:

- frozen cohort path and fingerprints;
- accepted decision count `274334`;
- horizon `30000 ms`;
- source sessions `115` through `122`;
- expected complete/incomplete counts `272391` / `1943`;
- root-only cohort authentication;
- SQLite mutation only under the `shreks` service identity;
- authenticated request handoff through `/run/shreks-fl4-backfill/request.json`;
- pre-mutation out-of-cohort fingerprint capture;
- explicit quiesce order from the existing amendment;
- inactive-service and database-holder gates;
- one first invocation plus one controlled idempotence invocation;
- exact postcondition and restoration proofs.

No FL4 mutation is authorized merely by this amendment. Before mutation, the trusted administrator must re-prove campaign advancement, reauthenticate the frozen cohort, refresh the privileged read-only FL4 prestate and out-of-cohort fingerprint, verify source-session authority, quiesce with the explicit stop order, prove no unexpected database holders remain, and satisfy every remaining runbook precondition.

Any runtime, cohort, count, fingerprint, source-session, holder, service-health, or restart drift is a HOLD.

## Safety boundary

This amendment does not authorize PAPER promotion or LIVE operation. LIVE remains disabled.
