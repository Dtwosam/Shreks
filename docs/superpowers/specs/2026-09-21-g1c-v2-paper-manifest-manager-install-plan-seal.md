# G1C V2 PAPER Manifest Manager Trusted-Admin Install Plan — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `2e15c7aef2ed5a380fa125b011a43ae490170d8b`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY INSTALL-PLANNING CODE; TRUSTED-ADMINISTRATOR READ-ONLY PLANNER USE AUTHORIZED AFTER PRODUCTION VERIFY; AUTOMATIC PLAN EXECUTION DISABLED; AUTOMATIC HELPER INSTALL DISABLED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the root-only, read-only trusted-administrator first-install planner for the PAPER manifest-manager helper.

The planner reduces stale-release, shell-transcription, and evidence-path risk before the already-authorized physical helper-install ceremony.

It does not install the helper.

It does not execute any emitted step.

## Production state before this seal

The currently sealed production release is:

`1475adef55a98fedc298591d3d6570cde1852558`

Its production verification established:

```text
paper_manifest_manager_status=ABSENT
```

and uploaded the sealed read-only helper-status evidence artifact while observer, PAPER evidence, and PAPER campaign remained active/running with zero restarts.

Protected FL9 remained:

```text
HOLD_NO_COMPATIBLE
```

The install-plan implementation merged to main as:

`2e15c7aef2ed5a380fa125b011a43ae490170d8b`

Its exact merged-main CI:

`35619204787`

completed with:

- Python: 3559 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Its downstream workflows correctly skipped because the implementation merge subject was `feat:`:

- release `35619655733`: SKIPPED;
- deploy `35619662789`: SKIPPED.

Therefore production does not yet contain the planner merely because the implementation is on `main`.

## Planner implementation

The release-local console script is:

```text
shreks-g1c-v2-paper-manifest-manager-install-plan
```

implemented by:

```text
shreks_brain.g1c_v2_paper_manifest_manager_install_plan
```

The planner takes one explicit argument:

```text
<expected-release-source-sha>
```

It is root-only because it reuses the already-sealed installation-proof read-only preflight over protected campaign/sudoers/service evidence.

## Exact first-install boundary

The planner is intentionally limited to a first-install ceremony.

It requires the fixed helper destination to report exactly:

```text
ABSENT
```

Any existing helper state fails planning, including:

- `MATCHED_CURRENT_RELEASE`;
- `PRESENT_DIFFERENT_BYTES`;
- `PRESENT_METADATA_MISMATCH`;
- `PRESENT_UNSAFE_TYPE`.

This planner is not a repair, replacement, idempotent reinstall, or retrospective proof surface.

## Release authentication

The planner authenticates:

- explicit 40-character expected release SHA;
- `/opt/shreks/current` resolving to that exact immutable release;
- exact current release virtualenv Python;
- canonical release manifest;
- exactly one manifest-hashed Shreks wheel;
- exact sealed PAPER manifest-manager member.

All emitted Python argv arrays use the exact resolved current release virtualenv Python.

No ambient PATH-selected Python is trusted for planned executable steps.

## Protected host preflight

The planner reuses the already-sealed installation-proof `prepare` logic in memory.

That read-only preflight requires:

- effective uid 0;
- protected campaign manifest mode `0640`;
- exact narrow root-owned deployment sudoers;
- healthy observer service;
- healthy PAPER evidence service;
- healthy PAPER campaign service;
- exact release/wheel/manager identity.

The only system command available through this preflight remains the sealed allowlist of read-only `systemctl show` calls.

The planner does not persist this preflight snapshot.

## Stability requirements

The planner observes helper status before and after the protected preflight.

Both observations must be exactly equal and remain `ABSENT`.

The derived evidence directory must not exist before or after preflight.

Any drift fails closed.

## Evidence directory

The planner derives exactly:

```text
/root/shreks-paper-manifest-manager-install-<release-sha>
```

and requires the path to be absent.

It emits:

```text
directory mode = 0700
required umask = 0077
```

but does not create the directory.

## Planned ceremony

A successful plan contains exactly four ordered step records:

```text
create root-private evidence directory
  -> installation-proof prepare
  -> exact release-bound helper installer
  -> installation-proof verify
```

The three release-local Python steps are represented as argv arrays using:

```text
<exact-release>/.venv/bin/python -m <exact-module> ...
```

The plan also binds the exact output paths:

- `installation-proof-pre.json`;
- `installer-receipt.json`;
- `installation-proof.json`.

The planner executes none of those steps.

## Plan evidence

Success emits canonical JSON with:

- `status = READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY`;
- exact release directory;
- exact runtime Python;
- wheel relative path and SHA-256;
- sealed manager SHA-256;
- fixed helper destination;
- helper status `ABSENT`;
- read-only preflight snapshot fingerprint;
- protected campaign manifest SHA-256;
- deployment sudoers SHA-256;
- service observations;
- exact root-private evidence directory;
- exact ordered argv/output-path records;
- `stop_on_any_failure = true`;
- `plan_preflight_is_not_installation_proof = true`;
- plan fingerprint.

The in-memory preflight snapshot is planning evidence only.

It is not accepted as `installation-proof-pre.json`.

The real `prepare` command must still run immediately before the actual installer.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic release/deploy chain to:

1. build and verify the exact immutable release;
2. include the planner CLI in the release-local Python environment;
3. create the immutable GitHub release;
4. deploy through the existing narrow release-manager path;
5. run the existing production PAPER verifier;
6. continue read-only helper-status observation/evidence upload;
7. continue runtime service/process provenance verification;
8. continue protected FL9 read-only discovery.

Automatic deployment does not execute the planner.

## Trusted-administrator planner authority granted by this seal

Only after the exact sealed release containing this planner is active on production and ordinary production verification succeeds, a trusted administrator may run:

```text
shreks-g1c-v2-paper-manifest-manager-install-plan <exact-current-release-sha>
```

as a read-only pre-ceremony check.

A successful plan is permission to consider executing the already-authorized separate ceremony.

It is not installation proof.

It is not itself installation authority exercised.

## Existing installer authority remains separate

The previously sealed trusted-administrator first-install authority remains:

```text
installation-proof prepare
  -> exact sealed installer
  -> installation-proof verify
```

through a trusted administrator channel.

This seal does not broaden that authority.

The helper installer remains unavailable to automatic GitHub deployment.

## Automatic actions still forbidden

No GitHub workflow is authorized to:

- execute the install planner;
- create the root evidence directory;
- run installation-proof `prepare`;
- invoke the helper installer;
- run installation-proof `verify`;
- repair or replace helper bytes;
- chmod/chown the helper destination;
- widen `shreks-deploy` sudoers;
- execute rotation-readiness proof;
- invoke the manifest manager;
- rotate the production campaign manifest;
- score V2;
- fit models;
- publish a champion;
- promote PAPER;
- access wallets/signing material;
- submit transactions;
- enable LIVE.

## Meaning of planner success

`READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY` proves only that the current host state is suitable to begin the separately authorized administrator ceremony.

It does not prove installation occurred.

It does not create `installation-proof-pre.json`.

It does not substitute for a canonical `VERIFIED` installation proof.

It does not authorize rotation.

## Rotation/readiness boundary

After a real successful installation ceremony produces canonical:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
```

the already-sealed rotation-readiness proof may be run as previously authorized.

Even a successful:

```text
READY_EVIDENCE_ONLY
```

readiness proof still does not authorize production v2 manifest rotation.

That remains a later, separately explicit authority decision.

## Scoring and promotion boundary

This seal does not authorize:

- V2 scoring retry;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- transaction signing;
- transaction submission;
- LIVE trading.

## Expected production proof

The automatic chain for this seal must show:

```text
seal merge
  -> exact sealed-main CI
  -> immutable release
  -> protected PAPER deploy
  -> successful production verify
  -> helper status remains observational
  -> planner present in exact release
```

The automatic chain must not execute the planner or install the helper.

If the helper remains `ABSENT`, that is still the expected physical gate until a trusted administrator performs the separate ceremony.

## Promotion boundary

`G1C_V2_PAPER_MANIFEST_MANAGER_INSTALL_PLAN=SEALED_READ_ONLY`

`TRUSTED_ADMIN_INSTALL_PLANNER_USE=AUTHORIZED_AFTER_PRODUCTION_VERIFY`

`AUTOMATIC_INSTALL_PLANNER_EXECUTION=DISABLED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_EXACT_HELPER_INSTALL=PREVIOUSLY_AUTHORIZED`

`INSTALLATION_PROOF_REQUIRED_FOR_ACCEPTANCE=YES`

`ROTATION_READINESS_REQUIRES_VERIFIED_INSTALLATION_PROOF=YES`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
