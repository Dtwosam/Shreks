# G1C V2 PAPER Manifest Rollback Lifecycle Recovery — Release Seal

**Date:** 2026-09-23  
**Rollback-fix implementation main SHA:** `3cfd33a5f6c76c68093ae95333c40551d4d0e6ed`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF CORRECTED ROLLBACK MANAGER; AUTOMATIC HELPER REPLACEMENT DISABLED; ROTATION/SCORING/PAPER PROMOTION/LIVE BLOCKED

## Purpose

Seal the production recovery for the protected PAPER manifest-manager rollback lifecycle bug observed after the reviewed WSOL v2 rotation attempt.

The protected rotation reached candidate service startup, then returned a terminal `ROLLED_BACK` receipt. Host evidence showed the source manifest bytes were restored, but the manager did not issue a second campaign stop before restoring source bytes after candidate activation had already been attempted.

That ordering could leave a candidate process resident in memory behind restored source-manifest bytes on disk.

## Production evidence

The reviewed rotation binding remains:

`d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`

The reviewed candidate SHA remains:

`9975c63c023c6133ba0d16290ecce1d0390e1cb3a0e304d4720ba1775a673d1b`

The rotation produced immutable evidence under:

`/var/lib/shreks/manifest-rotations/d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`

including `prepared.json` and `rolled-back.json`, with no `activated.json`.

The on-disk active manifest SHA after rollback matched the original source:

`3118bc5289b758a02bfd993085ed16f103a524b4d15a29ee50f45922a47fd530`

The failed binding is terminal evidence and must not be retried, deleted, or overwritten.

## Root cause

Before this fix, rollback logic behaved as follows after candidate bytes had already replaced the source:

1. restore source manifest bytes;
2. preflight source;
3. call `systemctl start shreks-paper-campaign.service`;
4. verify generic process health.

If candidate startup had already succeeded but a later health/identity/byte check failed, the candidate process could still be active. In that case `systemctl start` is a no-op and does not guarantee the process reloads the restored source manifest.

## Fix

PR #474 changes rollback ordering so that whenever candidate bytes have already replaced the source, rollback first executes:

`systemctl stop shreks-paper-campaign.service`

before restoring source bytes.

Only after source bytes are restored and preflighted does the manager start the campaign again and verify process health/source bytes.

Regression coverage now proves this ordering for:

- candidate activation health failure;
- candidate runtime-identity failure after startup.

## Proof

PR #474 final head:

`5c3125bb8f44b5e2cf2004603c97b099d3a1fc54`

PR CI:

`35890360126`

Result:

- Python: SUCCESS;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Merged main:

`3cfd33a5f6c76c68093ae95333c40551d4d0e6ed`

Merged-main CI:

`35890679683`

Result: SUCCESS across all four canonical gates.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. carry the corrected sealed PAPER manifest manager;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. activate and verify the ordinary protected PAPER runtime;
6. verify release-local protected manager/update/proof/readiness tool presence and read-only helper status;
7. continue protected FL9 read-only discovery.

Automatic deployment must not:

- replace the root manifest-manager helper;
- execute helper update;
- refresh helper proof;
- create or reuse a rotation readiness receipt;
- create or reuse a rotation plan;
- invoke the manifest manager;
- retry the consumed transition binding;
- retry scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit;
- enable LIVE.

## Trusted-admin helper boundary

The installed root helper remains outside ordinary automatic deployment.

After the new sealed release is active and production verification succeeds, a trusted administrator may separately use the existing exact helper-update ceremony, bound to a reviewed prior `VERIFIED` installation proof, to replace only:

`/usr/local/sbin/shreks-paper-manifest-manager`

with the exact current-release sealed bytes.

A fresh current-release installation proof is mandatory after helper replacement.

## Rotation boundary

The prior binding-specific evidence directory now exists and is terminal.

Do not retry:

`d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`

Any future PAPER manifest rotation requires a separately designed/reviewed new authority chain and a new transition binding. No automatic process may manufacture that replacement authority.

## Promotion boundary

`PAPER_MANIFEST_ROLLBACK_FIX=SEALED_FOR_RELEASE`

`AUTOMATIC_HELPER_UPDATE=DISABLED`

`TRUSTED_ADMIN_HELPER_UPDATE=REQUIRES_POST_DEPLOY_VERIFY`

`FAILED_ROTATION_BINDING=TERMINAL_DO_NOT_RETRY`

`MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
