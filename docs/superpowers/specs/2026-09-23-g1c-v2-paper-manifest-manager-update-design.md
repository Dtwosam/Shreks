# G1C V2 Exact PAPER Manifest-Manager Helper Replacement — Design

**Date:** 2026-09-23  
**Status:** IMPLEMENTATION SLICE; NO PRODUCTION UPDATE AUTHORITY UNTIL SEALED + DEPLOYED + VERIFIED

## Problem

The protected PAPER manifest-manager is installed as a root-owned standalone helper at:

`/usr/local/sbin/shreks-paper-manifest-manager`

The existing installer intentionally supports only first install or exact idempotence. It fails closed when a later immutable release contains different sealed manager bytes.

That no-overwrite rule is correct for first installation, but it means a legitimate sealed manager fix cannot be installed by reusing the first-install authority.

The 2026-09-23 production rotation attempt exposed a sealed import defect before any runtime mutation. The active helper failed to import `release_manager`, so no campaign stop, manifest replacement, or rotation evidence occurred.

The import implementation is fixed separately. A distinct helper-replacement authority is required before production can receive changed manager bytes.

## Design goal

Permit one exact helper replacement only when all of the following are true:

1. a prior canonical `VERIFIED` helper installation proof exists;
2. the currently installed helper bytes and metadata still match that proof exactly;
3. the prior proof binds an earlier immutable release;
4. the exact current immutable release authenticates;
5. its manifest-hashed Shreks wheel authenticates;
6. the sealed manager member in that wheel authenticates;
7. the helper destination parent remains root-owned and non-writable by group/other;
8. the current release remains stable through replacement.

No runtime-manifest, service, scoring, promotion, wallet, signing, submission, or LIVE authority is included.

## Input authority

The updater accepts only:

- exact current release SHA;
- explicit path to one prior root-private `installation-proof.json`.

The destination is fixed:

`/usr/local/sbin/shreks-paper-manifest-manager`

There is no arbitrary destination input and no operator-supplied replacement payload.

## Prior-proof authentication

The updater requires the prior proof to be:

- a regular non-symlink file;
- root-owned mode `0600`;
- canonical JSON;
- schema `shreks.g1c_v2_paper_manifest_manager_installation_proof` version 1;
- `status=VERIFIED`;
- fingerprint-valid;
- bound to the fixed helper destination;
- bound to exact root-owned `0755` helper metadata;
- marked `campaign_manifest_unchanged=true`;
- marked `deploy_sudoers_unchanged=true`;
- marked `service_lifecycle_unchanged=true`;
- `installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY`;
- manifest rotation/scoring/PAPER promotion/LIVE still blocked.

The installed helper SHA-256 must equal the prior proof's `manager_sha256`.

## Current-release authentication

The updater reuses the sealed installer primitives to require:

- exact `/opt/shreks/current` release SHA;
- exact current-release virtualenv Python;
- canonical release manifest;
- exactly one manifest-hashed Shreks wheel;
- exact wheel size and SHA-256;
- exact sealed manager wheel member and executable shape.

The new manager SHA must differ from the prior proven helper SHA. If it already matches, the update fails and the ordinary proof-refresh path is the correct operation.

## Replacement semantics

The destination parent must be a real root-owned directory that is not group- or world-writable.

The updater:

1. re-reads and authenticates the old helper;
2. writes the exact new sealed bytes to a same-directory temporary file;
3. fsyncs content;
4. applies root ownership and mode `0755`;
5. rechecks the old helper immediately before publication;
6. atomically replaces the helper path;
7. fsyncs the destination directory;
8. rechecks current-release identity;
9. re-authenticates final helper bytes and metadata.

If post-replacement verification fails, the updater atomically restores the exact prior proven helper bytes and verifies the restoration. It never claims success after an unverified replacement.

## Receipt

Success emits canonical JSON with:

```text
status=UPDATED
helper_update_authority=EXERCISED_EXACT_RELEASE_BOUND_HELPER_REPLACEMENT_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The receipt binds:

- current release SHA/directory;
- current wheel path/SHA;
- new manager SHA;
- prior proof SHA/fingerprint;
- prior release SHA;
- prior manager SHA;
- fixed destination and metadata.

## Post-update proof

The update receipt is not accepted as rotation-readiness proof.

Immediately after a successful helper replacement, the trusted administrator must run the already-sealed exact-release proof-refresh ceremony. Only a fresh current-release:

`status=VERIFIED`

installation proof can later be supplied to decision-backed rotation readiness.

## Production presence

Automatic production verification may prove only that the release-local updater CLI/module are present and resolve inside the exact active immutable release.

Automatic workflows must not invoke the updater.

## Authority firewall

The updater contains no authority to:

- stop/start/restart systemd services;
- read or replace the protected PAPER runtime manifest;
- mutate SQLite/E11;
- mutate G7 state;
- run readiness;
- invoke the manifest manager;
- score/model-fit;
- publish a champion;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Production boundary

Landing implementation on `main` does not authorize production replacement.

A later docs-only `seal:` commit must explicitly authorize immutable release/deploy of updater presence and trusted-admin use after production verification.

Even after helper replacement and fresh proof refresh, the protected PAPER manifest rotation remains a separate explicit trusted-administrator decision.
