# FL9 Shared-Memory Marker Directory Alias — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `38131cb41e1b4e1d7e356bb1361ea6b301e18acb`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the portability fix for the FL9 discovery-control marker directory.

Production telemetry repeatedly ran successfully while the verifier observed no FL9 result. The processor previously returned no result whenever the marker directory itself was a symlink. Debian-family systems may legitimately expose `/dev/shm` through a compatibility symlink/bind location such as `/run/shm`.

This seal authorizes a production proof of the trusted marker-directory alias behavior without changing marker-file trust, systemd authority, deploy privileges, or trading authority.

## Implemented behavior

Merged PR #320, `fix: support trusted shared-memory marker alias`, adds:

1. ordinary marker directories continue unchanged;
2. a symlinked marker directory is accepted only when:
   - the symlink is owned by the configured trusted directory owner;
   - the fully resolved target exists and is a directory;
   - the resolved target is owned by the same trusted directory owner;
   - the resolved target mode is exactly `01777`;
3. individual marker-file symlinks remain rejected;
4. untrusted-owner or non-sticky/non-world-writable directory aliases return no trusted work;
5. production default trusted directory owner remains root (`uid 0`);
6. timeout diagnostics now report `/dev/shm` lstat type/mode/owner, resolved path, followed-target metadata, existing marker metadata, and recent telemetry journal evidence.

No systemd unit, timer, sudoers rule, release-manager path, protected-state permission, wallet/signing/submission path, PAPER promotion authority, or LIVE authority changes.

## Evidence

Intentional RED head: `9bd6a3fe91144519d9bcb7048a8cb0b97fb399d4`

RED PR CI: `35508917676`

- Python failed only on the newly introduced marker-directory alias/diagnostic contracts;
- ARM64 release build: SUCCESS;
- Rust tests: SUCCESS;
- Repository safety: SUCCESS.

GREEN feature head: `108b5a582b19da166bb9ec23d78c0786e9b9329d`

GREEN PR CI: `35509081118` — all four canonical gates passed.

Squash-merged implementation main: `38131cb41e1b4e1d7e356bb1361ea6b301e18acb`

Exact merged-main CI: `35509221344` — all four canonical gates passed.

## Production proof authorized by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact seal SHA;
2. automatic protected PAPER deployment of that immutable release;
3. automatic production verification;
4. telemetry-mediated read-only FL9 discovery;
5. inspection of the new shared-memory directory diagnostics if discovery still times out.

A terminal `FOUND_COMPATIBLE` or HOLD result remains evidence only.

## Authority not granted

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`

No model fitting, fresh scoring request, champion publication, risk-intent creation, signing, submission, wallet handling, or live-capital action is authorized by this seal.
