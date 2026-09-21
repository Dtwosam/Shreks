# G1C V2 PAPER Manifest Manager Install Ceremony Tools Production Presence Proof — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `a6ecca26cfd924c2190396a0acfb51b6e81d3576`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY INSTALLER/INSTALLATION-PROOF PRESENCE/PROVENANCE; AUTOMATIC CEREMONY EXECUTION DISABLED; AUTOMATIC HELPER INSTALL DISABLED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the production-verifier change that proves both already-sealed trusted-administrator helper-install ceremony tools are physically present in the exact deployed immutable release:

- `shreks-g1c-v2-paper-manifest-manager-install`;
- `shreks-g1c-v2-paper-manifest-manager-install-proof`.

This closes the production-proof gaps in the earlier installer and installation-proof seals.

It does not execute either command, create ceremony evidence, install or repair the helper, invoke the manifest manager, rotate the protected PAPER campaign manifest, score V2, promote PAPER, sign/submit, or enable LIVE.

## Verified implementation

The implementation merged to `main` as:

`a6ecca26cfd924c2190396a0acfb51b6e81d3576`

Exact merged-main CI run:

`35639575652`

completed successfully with:

- Python: 3559 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The valid TDD RED commit was:

`56524059fa039ea1cf0546d16d0d1e020f3fd1ea`

Its CI run `35636080807` failed only because the production verifier did not yet contain the required installer-presence contract:

`1 failed, 3558 passed, 2 warnings`

while the unrelated gates remained green.

The GREEN implementation commit was:

`4c5b67d940dc1e1c0ec9048fed6cab24fc9c4530`

with push CI `35636356606` and PR CI `35636847157` both green.

Implementation PR:

`#365 — feat: prove deployed install ceremony tools presence read-only`

Earlier branch-only test-construction commits were superseded before the valid RED and are not release evidence.

## Read-only installer production verification

After authenticating the exact current release SHA and release manifest, the production verifier checks:

`/opt/shreks/current/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install`

The verifier requires that path to be present, a regular non-symlink executable, and resolved inside the exact expected immutable release.

It then uses the exact release virtualenv Python to import:

`shreks_brain.g1c_v2_paper_manifest_manager_install`

and requires the resolved module path to remain inside that same exact release.

## Read-only installation-proof production verification

The production verifier also checks:

`/opt/shreks/current/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install-proof`

with the same release-local requirements.

It then uses the exact release virtualenv Python to import:

`shreks_brain.g1c_v2_paper_manifest_manager_installation_proof`

and requires that module path to remain inside the exact deployed immutable release.

No ambient Python is trusted for either module-provenance check.

## Production evidence emitted

Successful verification emits presence/provenance lines including:

`paper_manifest_manager_installer=present`

`paper_manifest_manager_installation_proof=present`

plus the resolved release-local console-script and module paths for both tools.

These lines are not an installer receipt, not an installation-proof snapshot, not a successful `VERIFIED` installation proof, and not permission to install or rotate anything.

## Ceremony execution firewall

The production verifier does not:

- execute the install planner;
- execute the installer;
- execute installation-proof `prepare` or `verify`;
- call either ceremony module's `main()`;
- create the root-private installation evidence directory;
- create `installation-proof-pre.json`, `installer-receipt.json`, or `installation-proof.json`;
- execute the rotation-readiness proof;
- invoke the PAPER manifest manager.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build the exact immutable release;
2. publish the immutable GitHub release;
3. deploy through the existing narrow protected PAPER release-manager path;
4. run the production PAPER verifier;
5. prove the installer console script and module are present in the exact deployed release;
6. prove the installation-proof console script and module are present in the exact deployed release;
7. continue proving install-planner presence/provenance;
8. continue proving rotation-readiness presence/provenance;
9. continue read-only helper-status observation/evidence upload;
10. continue runtime/service provenance verification;
11. continue protected FL9 read-only discovery.

## Automatic actions still forbidden

No GitHub workflow is authorized to:

- execute the install planner;
- create the root ceremony evidence directory;
- run installation-proof `prepare`;
- invoke the helper installer;
- run installation-proof `verify`;
- execute rotation-readiness;
- install, repair, replace, chmod, or chown helper bytes;
- widen `shreks-deploy` sudoers;
- invoke the PAPER manifest manager;
- rotate the production PAPER campaign manifest;
- execute V2 scoring;
- fit models;
- publish/promote a champion;
- promote PAPER;
- access wallet signing material;
- sign or submit transactions;
- enable LIVE.

## Trusted-administrator boundary

The physical trusted-administrator gate remains unchanged.

Only after the exact sealed release is active and normal production verification succeeds may a trusted administrator run the already-sealed read-only first-install planner.

Planner success remains:

`status=READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY`

The separately authorized physical ceremony remains exactly:

`installation-proof prepare -> exact release-bound helper installer -> installation-proof verify`

Acceptance still requires canonical:

`status=VERIFIED`

with exact release-bound helper identity.

Only after that proof may the already-sealed evidence-only rotation-readiness proof be run.

A successful readiness result remains only:

`status=READY_EVIDENCE_ONLY`

and still records:

`manifest_rotation_authority=NOT_GRANTED`

Production v2 manifest rotation remains a later, separate explicit authority decision.

## Expected production proof

The automatic chain for this seal must show:

`seal merge -> sealed-main CI -> immutable release -> protected PAPER deploy -> successful production verify -> installer presence/provenance -> installation-proof presence/provenance -> rotation-readiness presence/provenance -> install-planner presence/provenance -> helper status observation -> FL9 read-only discovery`

Expected ceremony-tool evidence includes:

`paper_manifest_manager_installer=present`

`paper_manifest_manager_installation_proof=present`

The helper may still correctly remain:

`paper_manifest_manager_status=ABSENT`

until the trusted-administrator installation ceremony is physically performed.

Protected FL9 discovery may still correctly remain:

`HOLD_NO_COMPATIBLE`

until separately authorized protected manifest rotation creates compatible runtime authority.

## Promotion boundary

`G1C_V2_INSTALL_CEREMONY_TOOLS_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_INSTALL_PLANNER_EXECUTION=DISABLED`

`AUTOMATIC_INSTALLATION_PROOF_EXECUTION=DISABLED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`AUTOMATIC_ROTATION_READINESS_EXECUTION=DISABLED`

`TRUSTED_ADMIN_PROOF_USE=PREVIOUSLY_AUTHORIZED_AFTER_DEPLOY_VERIFY`

`TRUSTED_ADMIN_EXACT_HELPER_INSTALL=PREVIOUSLY_AUTHORIZED`

`INSTALLATION_PROOF_REQUIRED_FOR_ACCEPTANCE=YES`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
