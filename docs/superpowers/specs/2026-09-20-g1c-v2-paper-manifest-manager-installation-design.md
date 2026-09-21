# G1C V2 Release-Bound PAPER Manifest Manager Installer — Design

**Date:** 2026-09-20  
**Status:** implementation slice; production installation remains unauthorized until a later seal

## Purpose

The protected PAPER manifest rotation manager is now:

- implemented and exact-main tested;
- sealed for immutable release transport;
- present inside the manifest-hashed Shreks wheel;
- deployed to production as release content;
- not installed as a root helper;
- not authorized for production invocation.

The next boundary is narrower than manifest rotation itself.

This slice adds a dedicated release-local installer that can publish exactly one already-sealed manager helper to `/usr/local/sbin/shreks-paper-manifest-manager`.

It does not rotate the PAPER manifest and does not change service state.

## Authority separation

Normal GitHub deployment remains unchanged.

The `shreks-deploy` account retains only the existing exact release-manager sudo command shape.

The new installer is intended for a trusted administrator and requires effective uid 0.

The implementation grants no production authority merely by landing on `main`. A later docs-only seal must separately authorize immutable release/deployment of this installer and the administrator installation action.

Production v2 manifest rotation remains another later authority slice.

## Invocation

After a release containing this installer has been separately sealed, deployed, and verified, the administrator resolves the exact current release and invokes the release-local console script:

```text
<resolved-release>/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install <40-char-release-sha>
```

The explicit SHA prevents a command prepared for one immutable release from silently installing helper bytes from another release.

## Current-release binding

Before reading manager bytes, the installer requires:

- effective uid 0;
- `/opt/shreks/current` is a symlink;
- that symlink resolves successfully;
- the resolved release directory basename equals the explicit expected SHA;
- the installer runtime executable is a regular non-symlink executable inside that exact release's `.venv/bin`.

This binds both the source release and the code performing installation to the same current immutable release.

## Canonical release-manifest verification

The installer reads `RELEASE_MANIFEST.json` with no-follow semantics.

It rejects:

- symlinks;
- non-regular files;
- duplicate JSON keys;
- non-finite JSON constants;
- unexpected top-level fields;
- unsupported schema;
- invalid source SHA;
- unsupported platform;
- malformed file records;
- duplicate file paths;
- unsafe relative paths;
- unsorted records;
- non-canonical JSON encoding.

The manifest source SHA must equal the explicit expected release SHA.

## Wheel binding

The canonical manifest must contain exactly one Shreks wheel path matching the existing release shape:

```text
wheelhouse/shreks_brain-*.whl
```

The wheel is opened as a regular non-symlink file.

Its exact byte length and SHA-256 must equal the canonical release-manifest record before any ZIP member is trusted.

Therefore helper installation is bound to the same manifest-hashed release artifact already admitted by G2.

## Sealed manager-member binding

Inside the verified wheel, the installer requires exactly one member:

```text
shreks_brain/_sealed_deploy_control/paper_manifest_manager.py
```

Duplicate members are rejected rather than accepting ZIP last-entry semantics.

Encrypted or directory entries are rejected.

The extracted bytes must begin with the sealed manager executable shebang.

The installer computes SHA-256 over the exact extracted manager bytes for the installation receipt.

Release construction already verifies this same wheel member byte-for-byte against `deploy/release/paper_manifest_manager.py`, so the chain is:

```text
sealed source
  -> exact wheel member
  -> manifest-hashed wheel
  -> canonical release manifest
  -> exact current release SHA
  -> installed root helper bytes
```

## Destination policy

Production destination is fixed to:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

Expected metadata is:

- uid 0;
- gid 0;
- mode 0755;
- regular non-symlink file.

This slice is first-install / exact-idempotence authority only.

If the destination is absent, the installer may publish the exact verified payload.

If it already contains the exact payload with exact metadata, the operation returns `ALREADY_INSTALLED` without rewriting the file.

If existing bytes or metadata differ, installation fails closed.

The installer has no replacement or upgrade authority for a divergent existing helper.

## Atomic no-overwrite publication

The installer writes the verified payload to a private temporary file in the destination directory.

Before publication it:

1. writes all bytes;
2. flushes and fsyncs the file;
3. sets exact destination ownership;
4. sets mode 0755;
5. fsyncs again.

Immediately before publication, the installer re-resolves `/opt/shreks/current` and requires it still identifies the same explicit release SHA.

The destination parent must be a real directory owned by the expected root identity and must not be group- or world-writable.

Publication uses a same-filesystem hard-link operation to the final path.

Hard-link creation fails if the destination already exists, giving no-overwrite semantics without a replace race.

After publication the temporary name is removed and the parent directory is fsynced.

The final path is re-read with no-follow semantics and exact bytes/metadata are verified before success is reported.

## Receipt

Success emits canonical JSON to stdout.

Receipt fields bind:

- schema/version;
- status: `INSTALLED` or `ALREADY_INSTALLED`;
- release source SHA;
- resolved release directory;
- wheel relative path;
- wheel SHA-256;
- sealed manager member path;
- manager SHA-256;
- destination path;
- destination uid/gid/mode.

Authority fields are explicit:

- `installation_authority = EXERCISED_EXACT_RELEASE_BOUND_HELPER_ONLY`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

Failure emits only a canonical sanitized failure object and does not claim installation.

## Explicit non-authorities

The installer does not contain or call:

- systemd;
- subprocess service management;
- PAPER runtime preflight;
- campaign-manifest decode or replacement;
- SQLite or E11 writes;
- G7 control writes;
- scoring;
- model fitting;
- promotion;
- wallet access;
- signing;
- transaction construction;
- transaction submission;
- LIVE runtime mode.

The implementation source contains no `/etc/shreks` or `/var/lib/shreks` path.

## Runbook cleanup

The historical deployment-control recovery procedure is narrowed back to the release verifier and release manager only.

It no longer manually extracts or overwrites the PAPER manifest manager.

Fresh-host bootstrap likewise does not install the PAPER manifest manager.

The dedicated release-bound installer becomes the documented existing-host path for this helper.

This preserves a clear distinction between:

- release transport/recovery authority;
- exact PAPER manifest manager installation authority;
- future PAPER manifest rotation authority.

## Verification plan

Focused Python tests prove:

1. exact manager bytes are extracted only from a manifest-hashed wheel;
2. first installation publishes exact bytes with exact mode/ownership;
3. exact existing helper is idempotent;
4. different existing helper is never overwritten;
5. a wheel modified after manifest creation is rejected;
6. duplicate sealed manager ZIP members are rejected;
7. installer execution outside the exact current release virtualenv is rejected;
8. non-root execution is rejected before host mutation;
9. CLI registration and runbook contract are present;
10. implementation contains no campaign/service/scoring/LIVE authority surfaces.

After focused tests, canonical CI must pass all existing Python, Rust, repository-safety, and ARM64 release-build lanes.

## Production boundary after merge

Merging this implementation does not install anything on production.

A later seal must authorize:

1. release transport of this installer;
2. exact production deployment of that release;
3. trusted-administrator invocation of the installer;
4. post-install proof of destination hash/metadata.

That later seal must still leave production v2 manifest rotation unauthorized.

**PRODUCTION ROOT HELPER INSTALLATION: NOT AUTHORIZED BY THIS IMPLEMENTATION MERGE.**  
**PRODUCTION V2 MANIFEST ROTATION: NOT AUTHORIZED.**  
**V2 SCORING: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE: DISABLED.**
