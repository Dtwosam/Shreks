# G1C V2 PAPER Manifest Manager Status Observability — Design

**Date:** 2026-09-21  
**Status:** implementation slice; production transport remains unauthorized until separately sealed

## Purpose

Make the remaining physical helper-installation gate visible in ordinary production verification without granting installation or rotation authority.

The release-local status probe answers one question:

Does the fixed root-helper destination currently contain the exact sealed manager from the active immutable release?

## Release authentication

Before inspecting the destination, the probe authenticates:

- exact expected current release SHA;
- current-release symlink resolution;
- execution from that exact release virtualenv;
- canonical release manifest source SHA;
- exactly one Shreks wheel record;
- exact manifest-recorded wheel size and SHA-256;
- exactly one sealed PAPER manifest-manager wheel member.

The expected manager SHA-256 comes only from those authenticated release bytes.

## Destination inspection

The probe reads:

`/usr/local/sbin/shreks-paper-manifest-manager`

without following symlinks.

It never creates or replaces the destination.

It never chmods or chowns the destination.

It never invokes the helper.

It emits one of:

- `ABSENT`;
- `MATCHED_CURRENT_RELEASE`;
- `PRESENT_DIFFERENT_BYTES`;
- `PRESENT_METADATA_MISMATCH`;
- `PRESENT_UNSAFE_TYPE`.

For a regular file it records:

- SHA-256;
- uid;
- gid;
- mode;
- exact-byte match against current sealed release;
- exact-metadata match against root:root 0755.

For an absent path, no file is created.

For a symlink or other non-regular object, the object is classified without following or reading through it.

## Production verifier integration

The reusable production PAPER verifier runs the release-local status CLI after proving the current release manifest SHA and before runtime service checks.

It logs:

- `paper_manifest_manager_status_json=<canonical-json>`;
- `paper_manifest_manager_status=<compact-status>`.

The workflow validates the status schema and the narrow authority fields.

All five observational states are accepted as observations. This avoids silently turning release deployment into helper-install or helper-upgrade authority.

The status CLI itself must succeed. An inability to safely authenticate the release or inspect a present destination fails production verification because helper state could not be established.

## Authority boundary

The status probe has:

- `observation_authority = READ_ONLY`;
- `installation_authority = NOT_EXERCISED`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

It contains no:

- file publication;
- chmod/chown;
- service command;
- manifest rotation;
- scoring;
- model fitting;
- promotion;
- signing;
- transaction submission;
- LIVE runtime path.

## Tests

Focused tests prove:

1. absent destination reports `ABSENT` and remains absent;
2. exact helper reports `MATCHED_CURRENT_RELEASE`;
3. different bytes report `PRESENT_DIFFERENT_BYTES` without replacement;
4. metadata drift reports `PRESENT_METADATA_MISMATCH` without chmod;
5. symlink reports `PRESENT_UNSAFE_TYPE` without following it;
6. tampered release wheel is rejected before destination trust;
7. static authority firewall and production-verifier wiring remain read-only.

## Production boundary

Merging this implementation does not release or deploy it.

A later seal is required before production verification may rely on this status probe.

The existing trusted-administrator helper-install ceremony remains unchanged.

Production v2 manifest rotation remains separately unauthorized.

**HELPER STATUS OBSERVABILITY: IMPLEMENTED, NOT YET SEALED.**  
**HELPER INSTALLATION: SEPARATE TRUSTED-ADMINISTRATOR ACTION.**  
**PRODUCTION V2 MANIFEST ROTATION: NOT AUTHORIZED.**  
**V2 SCORING: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE: DISABLED.**
