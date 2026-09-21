# G1C V2 PAPER Manifest Manager Install Planner Production Presence Proof — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `aa3765cd5cd291f2b8f16a0a0a4b2fabf1f7805a`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY PLANNER PRESENCE/PROVENANCE; PLANNER EXECUTION DISABLED; HELPER INSTALLATION DISABLED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the production-verifier change that proves the already-sealed trusted-administrator install planner is physically present in the exact deployed immutable release.

This closes the production-proof gap in the prior install-plan seal.

It does not execute the planner.

It does not install, repair, replace, chmod, or chown the PAPER manifest-manager helper.

## Verified implementation

The implementation merged to `main` as:

`aa3765cd5cd291f2b8f16a0a0a4b2fabf1f7805a`

Exact merged-main CI run:

`35627057667`

completed successfully with:

- Python: 3559 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The TDD RED commit was:

`6220f437f8acfa8c7a2b84fb7ff062defa3d276c`

Its Python CI failed only because the production verifier did not yet contain the required planner-presence contract:

`1 failed, 3558 passed, 2 warnings`

The GREEN implementation commit on the feature branch was:

`1578843d070f5e6bfcb6840b26b05f9b0e71a29b`

and its push and PR CI matrices completed successfully before merge.

## Read-only production verification added

After authenticating the exact current release SHA and release manifest, the production verifier now checks the release-local console script:

`/opt/shreks/current/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install-plan`

The verifier requires that path to be:

- present;
- a regular file;
- not a symlink;
- executable;
- resolved inside the exact expected immutable release directory.

The verifier then uses the exact release virtualenv Python to import:

`shreks_brain.g1c_v2_paper_manifest_manager_install_plan`

and requires the resolved module path to remain inside the exact expected immutable release.

No ambient Python is trusted for this module-provenance check.

## Production evidence emitted

Successful verification emits read-only lines including:

`paper_manifest_manager_install_planner=present`

plus the resolved release-local console-script path and module path.

These lines are evidence of presence/provenance only.

They are not installation proof.

They are not planner output.

They are not permission to rotate the protected PAPER manifest.

## Planner execution firewall

The production verifier does not invoke:

`shreks-g1c-v2-paper-manifest-manager-install-plan <release-sha>`

It does not call the planner module's `main()`.

It does not build an install plan.

It does not create the root-private ceremony evidence directory.

It does not run installation-proof `prepare` or `verify`.

It does not invoke the helper installer.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build the exact immutable release;
2. publish the immutable GitHub release;
3. deploy through the existing narrow protected PAPER release-manager path;
4. run the production PAPER verifier;
5. prove the install-planner console script and module are present in the exact deployed release;
6. continue the existing read-only helper-status observation and evidence upload;
7. continue existing runtime/service provenance verification;
8. continue existing protected FL9 read-only discovery.

## Automatic actions still forbidden

No GitHub workflow is authorized to:

- execute the install planner;
- create the root ceremony evidence directory;
- run installation-proof `prepare`;
- invoke the helper installer;
- run installation-proof `verify`;
- repair or replace helper bytes;
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

The previously sealed trusted-administrator authority remains unchanged.

Only after the exact sealed release is active and ordinary production verification succeeds may a trusted administrator run the read-only first-install planner.

A successful planner result may then precede the separately authorized ceremony:

`installation-proof prepare -> exact release-bound helper installer -> installation-proof verify`

The required canonical post-install result remains:

`status=VERIFIED`

with exact release-bound helper identity.

Only after that proof may the already-sealed evidence-only rotation-readiness proof be run.

Production v2 manifest rotation remains a later, separate explicit authority decision.

## Expected production proof

The automatic chain for this seal must show:

`seal merge -> sealed-main CI -> immutable release -> protected PAPER deploy -> successful production verify -> planner presence/provenance lines -> helper status observation -> FL9 read-only discovery`

Expected planner evidence includes:

`paper_manifest_manager_install_planner=present`

The helper may still correctly remain:

`paper_manifest_manager_status=ABSENT`

until the trusted-administrator installation ceremony is physically performed.

## Promotion boundary

`G1C_V2_INSTALL_PLANNER_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_INSTALL_PLANNER_EXECUTION=DISABLED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_INSTALL_PLANNER_USE=PREVIOUSLY_AUTHORIZED_AFTER_PRODUCTION_VERIFY`

`TRUSTED_ADMIN_EXACT_HELPER_INSTALL=PREVIOUSLY_AUTHORIZED`

`INSTALLATION_PROOF_REQUIRED_FOR_ACCEPTANCE=YES`

`ROTATION_READINESS_REQUIRES_VERIFIED_INSTALLATION_PROOF=YES`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
