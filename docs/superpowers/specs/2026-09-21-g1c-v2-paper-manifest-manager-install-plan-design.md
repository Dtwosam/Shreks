# G1C V2 PAPER Manifest Manager Trusted-Admin Install Plan — Design

**Date:** 2026-09-21  
**Status:** implementation slice; production transport/use remains unauthorized until separately sealed

## Purpose

Add one root-only, read-only planner for the already-authorized trusted-administrator first installation of the sealed PAPER manifest-manager helper.

The planner reduces shell transcription and stale-release risk while preserving the existing authority split.

It does not install the helper.

## Exact first-install boundary

The planner is intentionally limited to a first-install ceremony.

It requires the fixed helper destination to report exactly:

`ABSENT`

Any existing helper state, including exact-current-release bytes, fails the planner.

This prevents the planning surface from becoming a repair, replacement, or retrospective-proof path.

## Release authentication

The planner reuses the sealed helper-status and installation-proof primitives to authenticate:

- explicit 40-character current release SHA;
- current release symlink;
- exact current release virtualenv Python;
- canonical release manifest;
- exactly one manifest-hashed Shreks wheel;
- exact sealed manager member.

The exact release-local Python path is used in every planned executable argv.

## Protected host preflight

The planner runs the existing read-only installation-proof `prepare` logic in memory.

That requires:

- effective uid 0;
- protected campaign manifest mode `0640`;
- exact narrow root-owned deployment sudoers;
- healthy observer, PAPER evidence, and PAPER campaign service observations;
- exact release/wheel/manager identity.

Only the existing allowlisted `systemctl show` calls are available through this preflight.

The planner does not persist the preflight snapshot.

## Stability check

Helper status is observed before and after the installation-proof preflight.

The two observations must be exactly equal and remain `ABSENT`.

The derived evidence directory must not exist both before and after preflight.

Any drift fails closed.

## Evidence directory

The planner derives exactly:

`/root/shreks-paper-manifest-manager-install-<release-sha>`

and requires that path to be absent.

It emits the required ceremony directory mode `0700` and umask `0077`.

It does not create the directory.

## Planned steps

The canonical plan contains four ordered step records:

1. create the root-private evidence directory;
2. run installation-proof `prepare`, writing `installation-proof-pre.json`;
3. run the exact release-bound installer, writing `installer-receipt.json`;
4. run installation-proof `verify`, writing `installation-proof.json`.

Python steps use:

`<exact-release>/.venv/bin/python -m <exact-module> ...`

rather than resolving an ambient executable from PATH.

The plan does not execute any step.

## Plan evidence

Success emits canonical JSON containing:

- `status = READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY`;
- exact release directory and runtime Python;
- wheel and manager hashes;
- helper destination and `ABSENT` status;
- in-memory preflight snapshot fingerprint;
- protected campaign manifest SHA-256;
- deployment sudoers SHA-256;
- service observations;
- exact evidence paths;
- exact ordered argv arrays;
- plan fingerprint.

The preflight fingerprint is readiness evidence only.

It is not accepted as the real pre-install snapshot by the post-install proof.

## Authority boundary

The plan records:

- `planning_authority = READ_ONLY`;
- `installation_authority = NOT_EXERCISED`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

The implementation contains no helper-install function call, post-install verification call, file creation/write path, service lifecycle command, rotation call, scoring, promotion, signing, submission, or LIVE runtime authority.

## Tests

Focused tests cover:

1. exact absent-helper success with canonical ordered plan;
2. any existing helper rejection;
3. pre-existing evidence-directory rejection;
4. unhealthy service preflight rejection;
5. helper-status drift during preflight rejection;
6. root requirement;
7. static no-mutation/no-rotation authority firewall plus runbook/entry-point contract.

## Production boundary

Merging this implementation does not release or deploy the planner.

A later seal is required before a trusted administrator may use it on production.

The previously sealed direct ceremony remains authoritative and unchanged.

No GitHub workflow receives authority to execute the planner or installer.

Production v2 manifest rotation remains separately unauthorized.

**TRUSTED-ADMIN INSTALL PLAN: IMPLEMENTED, NOT YET SEALED.**  
**AUTOMATIC HELPER INSTALL: DISABLED.**  
**PRODUCTION V2 MANIFEST ROTATION: NOT AUTHORIZED.**  
**V2 SCORING: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE: DISABLED.**
