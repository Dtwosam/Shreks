# G1C V2 PAPER Manifest-Manager Import Fix + Exact Helper Update — Release Seal

**Date:** 2026-09-23  
**Import-fix implementation main SHA:** `18f2e8bfc1797ae0f6902af1b9ec4733d43be0d3`  
**Helper-update implementation main SHA:** `261eae83b95bf87a976422c114ac307b4408e57b`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF FIXED MANAGER AND HELPER-UPDATE TOOL PRESENCE; AUTOMATIC HELPER UPDATE DISABLED; TRUSTED-ADMIN EXACT HELPER REPLACEMENT AUTHORIZED ONLY AFTER PRODUCTION VERIFY; OLD ROTATION READINESS/PLAN STALE AFTER RELEASE CHANGE; SCORING/PAPER PROMOTION/LIVE BLOCKED

## Purpose

Seal the production recovery for the protected PAPER manifest-manager import failure and the separately bounded mechanism required to install changed helper bytes safely.

The protected manager is transported inside the manifest-hashed Shreks wheel and installed separately at:

`/usr/local/sbin/shreks-paper-manifest-manager`

The previous helper was exact for the then-active release but failed at process import before any rotation logic because the standalone script imported `release_manager` as an unavailable top-level module.

The fix and helper-replacement authority remain separate concerns:

1. fix the sealed manager/control-package import contract;
2. deploy a new immutable release containing that fix;
3. only then, through a separate trusted-admin action, replace the prior proven helper with the exact helper bytes from the new release.

## Production state before this seal

The current production-verified immutable release remains:

`6fa8b337fb5b71601e473e06907f4b8ba23ae0ee`

The trusted-admin helper proof for that release records:

- `status=VERIFIED`;
- manager SHA-256 `e612ca524d633fb5ee58be2e4bb38ad5e1ff1bba418354ca2176561a74fef104`;
- proof fingerprint `39432c7e6a938733b29405ab6eeb4b18f94bd59f10c5d9bd84bf2c531255b963`;
- `installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY`;
- manifest rotation/scoring/PAPER promotion/LIVE still blocked.

A separately reviewed candidate chain was completed through:

- exact decision-backed candidate;
- exact transition binding;
- fresh exact-release helper proof;
- `READY_EVIDENCE_ONLY` rotation readiness;
- read-only rotation plan.

The reviewed plan bound candidate SHA:

`9975c63c023c6133ba0d16290ecce1d0390e1cb3a0e304d4720ba1775a673d1b`

and transition-binding fingerprint:

`d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`.

The trusted administrator explicitly authorized that old-release plan.

When the manager was invoked, Python terminated at import with:

`ModuleNotFoundError: No module named 'release_manager'`

before the manager entered its rotation function.

The trusted-admin transcript showed:

- exit code 1;
- no terminal rotation receipt;
- no rotation evidence directory.

Because module import occurs before root checks, systemd calls, evidence creation, or manifest replacement, that attempt exercised no protected runtime-manifest mutation.

Do not retry that installed helper.

## Root cause

Release construction intentionally places deployment-control companions inside:

`shreks_brain._sealed_deploy_control`

including:

- `release_bundle.py`;
- `release_manager.py`;
- `paper_manifest_manager.py`.

The installed manifest manager is a standalone root helper under `/usr/local/sbin`.

The old manager imported:

`release_manager`

as a top-level module. The source-tree unit test masked the production gap by adding `deploy/release` to `sys.path`.

## Import fix

PR #470 fixed the contract so the manager:

- uses package-relative imports when loaded inside the sealed deployment-control package;
- uses adjacent checkout control files only for explicit source-tree execution;
- when installed standalone without adjacent source control files, imports release-control companions from `shreks_brain._sealed_deploy_control`.

The sealed `release_manager` itself now uses a package-relative `release_bundle` import when executed from the sealed package while preserving its existing standalone source/deployment behavior.

A regression test recreates an extensionless production-style:

`/usr/local/sbin/shreks-paper-manifest-manager`

and proves that it resolves both control dependencies from the sealed package.

### Import-fix proof

PR #470 final head:

`49cd29765611d9f31036d930c0e4e8d1bc873dd3`

Final PR CI:

`35882676188`

Result:

- Python: SUCCESS, including the standalone-helper regression;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Merged main:

`18f2e8bfc1797ae0f6902af1b9ec4733d43be0d3`

Merged-main CI:

`35883042341`

Result: SUCCESS across all four canonical gates.

## Why the existing installer cannot update the helper

The existing release-bound installer is deliberately first-install/idempotence only.

It authorizes:

- destination absent -> exact first install;
- destination already equals exact sealed bytes/metadata -> `ALREADY_INSTALLED`.

It intentionally rejects different existing bytes.

Therefore changing the sealed manager bytes makes the old helper:

`PRESENT_DIFFERENT_BYTES`

after the new release becomes current.

Deleting, manually copying, overwriting, chmodding, or otherwise repairing the helper would bypass the established authority model and remains forbidden.

## Exact helper-update implementation

PR #471 adds:

`shreks-g1c-v2-paper-manifest-manager-update`

implemented by:

`shreks_brain.g1c_v2_paper_manifest_manager_update`.

Input is restricted to:

- exact expected current immutable release SHA;
- explicit prior root-private canonical `VERIFIED` installation proof.

Destination is fixed:

`/usr/local/sbin/shreks-paper-manifest-manager`

There is no arbitrary replacement payload and no arbitrary destination input.

The updater requires the installed helper bytes and root-owned `0755` metadata to equal the prior proof exactly before replacement.

It authenticates the new current release, release manifest, manifest-hashed wheel, and sealed manager member, then atomically replaces only the helper.

If post-replacement verification fails, it restores the exact prior proven helper and verifies that restoration before reporting failure.

Success records:

```text
status=UPDATED
helper_update_authority=EXERCISED_EXACT_RELEASE_BOUND_HELPER_REPLACEMENT_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

### Helper-update proof

PR #471 final head:

`c46d5154e4ccf8267dea685768de5012714bc94a`

PR CI:

`35883972297`

Result:

- Python: SUCCESS;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Merged main:

`261eae83b95bf87a976422c114ac307b4408e57b`

Merged-main CI:

`35884519451`

Result: SUCCESS across all four canonical gates.

## Production-presence boundary

The ordinary production verifier now proves without invoking the updater:

- release-local updater console script exists;
- it is a regular non-symlink executable;
- its resolved path is inside the exact expected immutable release;
- the updater module imports through exact release-local Python;
- the module path resolves inside the same expected release.

Expected evidence includes:

```text
paper_manifest_manager_update=present
paper_manifest_manager_update_path=<exact-release-local-path>
paper_manifest_manager_update_module=<exact-release-local-module-path>
```

The verifier does not execute helper replacement.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. carry the corrected sealed PAPER manifest manager;
3. carry the helper-update CLI/module;
4. publish the immutable GitHub release;
5. deploy that exact release through the existing protected release manager;
6. activate and verify the ordinary protected PAPER runtime;
7. verify fixed-manager/update-tool production presence and read-only helper status;
8. continue protected FL9 read-only discovery.

Automatic deployment must not:

- replace or repair the root manifest-manager helper;
- execute the helper updater;
- refresh helper proof;
- execute rotation readiness;
- execute a rotation plan;
- invoke the manifest manager;
- rotate the protected PAPER manifest;
- retry scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit;
- enable LIVE.

## Expected helper status after deploy

Because the installed helper still contains the prior exact release bytes while the new sealed release contains the fixed manager bytes, the expected physical observation before trusted-admin update is:

`PRESENT_DIFFERENT_BYTES`

That is expected recovery evidence, not permission for automation to replace the helper.

## Trusted-admin exact helper replacement authority

Only after the new sealed release is active and ordinary production verification succeeds, a trusted administrator may use the documented updater ceremony with the exact prior `VERIFIED` installation proof for release:

`6fa8b337fb5b71601e473e06907f4b8ba23ae0ee`.

The updater must independently prove the currently installed helper still equals the prior proof before replacement.

This seal authorizes consideration/execution of that helper-only maintenance action through the trusted administrator channel.

It does not authorize automatic execution.

It does not authorize manifest rotation.

## Mandatory post-update proof refresh

A successful update receipt is not rotation-readiness evidence.

Immediately after helper replacement, the trusted administrator must run the current release's exact proof-refresh ceremony.

The resulting current-release proof must preserve:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

If proof refresh fails, stop. Do not proceed to readiness or rotation.

## Candidate-chain reuse and stale release-bound evidence

The exact candidate, decision-backed authority, and transition binding are not themselves authorized by the old current-release SHA and may be re-authenticated under the new release.

However the existing readiness receipt and read-only rotation plan are explicitly bound to:

`6fa8b337fb5b71601e473e06907f4b8ba23ae0ee`

and become stale as soon as a different release is current.

Therefore after helper update and fresh proof refresh:

1. re-run decision-backed rotation readiness against the new exact release;
2. require a new `READY_EVIDENCE_ONLY` receipt;
3. build a new read-only rotation plan;
4. review the new plan completely;
5. require a **new explicit trusted-admin rotation authorization**.

The prior explicit rotation authorization must not be reused for the new release-bound plan.

## Rotation boundary

Even after successful helper replacement and fresh proof:

`manifest_rotation_authority=NOT_GRANTED`

until the later new plan is separately reviewed and explicitly authorized.

The manager itself must still independently recheck source/candidate/binding/release/G7/runtime state at invocation.

## Scoring and promotion boundary

This seal does not authorize:

- V2 scoring/model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- transaction signing;
- transaction submission;
- LIVE.

## Promotion boundary

`PAPER_MANIFEST_MANAGER_IMPORT_FIX=SEALED_FOR_RELEASE`

`EXACT_HELPER_UPDATE_TOOL=SEALED_FOR_RELEASE_PRESENCE`

`AUTOMATIC_HELPER_UPDATE=DISABLED`

`TRUSTED_ADMIN_EXACT_HELPER_UPDATE=AUTHORIZED_ONLY_AFTER_NEW_RELEASE_PRODUCTION_VERIFY`

`FRESH_POST_UPDATE_HELPER_PROOF=REQUIRED`

`OLD_ROTATION_READINESS=STALE_AFTER_RELEASE_CHANGE`

`OLD_ROTATION_PLAN_AUTHORIZATION=NOT_REUSABLE`

`MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
