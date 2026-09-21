# G1C V2 PAPER Manifest Rotation Readiness Production Presence Proof — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `71f4e356aa3a84376b1b18ec136f53883c4b6852`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY ROTATION-READINESS PRESENCE/PROVENANCE; AUTOMATIC READINESS EXECUTION DISABLED; HELPER INSTALLATION DISABLED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the production-verifier change that proves the already-sealed rotation-readiness capability is physically present in the exact deployed immutable release.

This closes the production-proof gap in the earlier rotation-readiness seal.

It does not execute the readiness proof.

It does not install, repair, replace, chmod, or chown the PAPER manifest-manager helper.

It does not invoke the manifest manager or rotate the protected PAPER campaign manifest.

## Verified implementation

The implementation merged to `main` as:

`71f4e356aa3a84376b1b18ec136f53883c4b6852`

Exact merged-main CI run:

`35632350455`

completed successfully with:

- Python: 3559 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The TDD RED commit was:

`d49bd89fb7f1ae4d4d3660805217e563508c939f`

Its CI run `35630925614` failed only because the production verifier did not yet contain the required readiness-presence contract:

`1 failed, 3558 passed, 2 warnings`

while Repository safety, Rust tests, and ARM64 release build succeeded.

The GREEN implementation commit on the feature branch was:

`684d56ccd466dd69de569e56d0ba801ba26ecb53`

with push CI `35631317396` and PR CI `35631854125` both completing successfully before merge.

Implementation PR:

`#363 — feat: prove deployed rotation-readiness presence read-only`

## Read-only production verification added

After authenticating the exact current release SHA and release manifest, the production verifier checks the release-local console script:

`/opt/shreks/current/.venv/bin/shreks-g1c-v2-paper-manifest-rotation-readiness`

The verifier requires that path to be:

- present;
- a regular file;
- not a symlink;
- executable;
- resolved inside the exact expected immutable release directory.

The verifier then uses the exact release virtualenv Python to import:

`shreks_brain.g1c_v2_paper_manifest_rotation_readiness`

and requires the resolved module path to remain inside the exact expected immutable release.

No ambient Python is trusted for this module-provenance check.

## Production evidence emitted

Successful verification emits read-only lines including:

`paper_manifest_rotation_readiness=present`

plus the resolved release-local console-script path and module path.

These lines prove presence/provenance only.

They are not a readiness receipt.

They are not helper-installation proof.

They are not permission to rotate the protected PAPER manifest.

## Readiness execution firewall

The production verifier does not invoke:

`shreks-g1c-v2-paper-manifest-rotation-readiness`

with candidate, binding, installation-proof, fingerprint, or release arguments.

It does not call the readiness module's `main()`.

It does not create a readiness evidence directory.

It does not run the candidate PAPER preflight through the readiness command.

It does not invoke the manifest manager.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build the exact immutable release;
2. publish the immutable GitHub release;
3. deploy through the existing narrow protected PAPER release-manager path;
4. run the production PAPER verifier;
5. prove the rotation-readiness console script and module are present in the exact deployed release;
6. continue proving install-planner presence/provenance;
7. continue the existing read-only helper-status observation and evidence upload;
8. continue existing runtime/service provenance verification;
9. continue existing protected FL9 read-only discovery.

## Automatic actions still forbidden

No GitHub workflow is authorized to:

- execute the rotation-readiness proof;
- execute the install planner;
- create the root installation or readiness evidence directories;
- run installation-proof `prepare`;
- invoke the helper installer;
- run installation-proof `verify`;
- install, repair, or replace helper bytes;
- chmod/chown the helper destination;
- widen `shreks-deploy` sudoers;
- invoke the PAPER manifest manager;
- rotate the production PAPER campaign manifest;
- execute V2 scoring;
- fit models;
- publish or promote a champion;
- promote PAPER;
- access wallet signing material;
- sign or submit transactions;
- enable LIVE.

## Trusted-administrator boundary

The physical trusted-administrator gate remains unchanged.

The helper installation ceremony must still complete first with canonical:

`status=VERIFIED`

and exact release-bound helper identity.

Only after that successful helper-install proof may a trusted administrator run the already-sealed evidence-only rotation-readiness proof.

A successful readiness result remains only:

`status=READY_EVIDENCE_ONLY`

and still records:

`manifest_rotation_authority=NOT_GRANTED`

Production v2 manifest rotation remains a later, separate explicit authority decision.

## Expected production proof

The automatic chain for this seal must show:

`seal merge -> sealed-main CI -> immutable release -> protected PAPER deploy -> successful production verify -> rotation-readiness presence/provenance lines -> install-planner presence/provenance lines -> helper status observation -> FL9 read-only discovery`

Expected readiness evidence includes:

`paper_manifest_rotation_readiness=present`

The helper may still correctly remain:

`paper_manifest_manager_status=ABSENT`

until the trusted-administrator installation ceremony is physically performed.

Protected FL9 discovery may still correctly remain:

`HOLD_NO_COMPATIBLE`

until separately authorized protected manifest rotation creates compatible runtime authority.

## Promotion boundary

`G1C_V2_ROTATION_READINESS_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_ROTATION_READINESS_EXECUTION=DISABLED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_READINESS_USE=PREVIOUSLY_AUTHORIZED_AFTER_VERIFIED_HELPER_INSTALL`

`INSTALLATION_PROOF_REQUIRED_FOR_READINESS=YES`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
