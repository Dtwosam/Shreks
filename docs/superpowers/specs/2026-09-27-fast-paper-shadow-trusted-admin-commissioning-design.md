# Fast PAPER Shadow Trusted-Administrator Commissioning — Design

**Date:** 2026-09-27  
**Base main SHA:** `552775d1e3a488e422e0c9b7582a912ab5f596c1`

## Purpose

Turn the newly sealed Fast PAPER shadow commissioning assets into one narrow
trusted-administrator host action:

- authenticate the exact active immutable release;
- authenticate the manifest-hashed Shreks wheel;
- authenticate the nested Fast PAPER shadow commissioning manifest;
- install only the exact dormant
  `shreks-fast-paper-shadow.service` bytes into systemd's unit directory;
- prove the installed bytes and metadata;
- stop there.

This slice must not start, enable, reload, restart, stop, or otherwise mutate
any running service. It must not create the protected shadow environment file,
provision the isolated shadow ledger, replace the legacy PAPER campaign, or
grant LIVE authority.

## Console boundary

Add one release-local trusted-administrator CLI:

```text
shreks-fast-paper-shadow-commissioning preflight <expected-release-sha>
shreks-fast-paper-shadow-commissioning install <expected-release-sha>
```

Both commands require effective uid 0 and execution from the exact current
release virtualenv.

## Exact-release authentication

Both commands must require:

1. `/opt/shreks/current` is a symlink resolving to an existing release
   directory whose basename equals the explicit 40-character expected SHA;
2. the CLI runtime executable is a regular non-symlink executable inside that
   release's `.venv/bin`;
3. the release's canonical `RELEASE_MANIFEST.json` has the same source SHA;
4. the manifest contains exactly one Shreks wheel record;
5. the wheel is a regular non-symlink file whose exact size and SHA-256 equal
   the release-manifest record;
6. the wheel contains exactly one sealed Fast PAPER shadow commissioning
   package member set;
7. the nested commissioning manifest source SHA and platform equal the active
   release;
8. the unit payload size/SHA equal the nested manifest;
9. the unit payload retains the expected safety shape:
   - dedicated shadow environment file;
   - immutable release Python supervisor;
   - `PrivateNetwork=true`;
   - dedicated shadow write root;
   - no `WantedBy=shreks.target`;
   - no `PartOf=shreks.target`;
   - no dependency on `shreks-paper-campaign.service`.

## Preflight

`preflight` is read-only.

It must:

- authenticate the exact release and sealed unit;
- inspect the destination parent and require a real root-owned directory that
  is not group/world writable;
- report whether the unit is:
  - `READY_TO_INSTALL`, when absent; or
  - `READY_ALREADY_INSTALLED`, when exact sealed bytes already exist with
    root:root mode 0644;
- fail closed on any existing different bytes, symlink, wrong uid/gid/mode, or
  unsafe destination parent.

Preflight grants no installation, activation, PAPER cutover, or LIVE
authority.

## Install

`install` may publish exactly one file:

```text
/etc/systemd/system/shreks-fast-paper-shadow.service
```

Publication rules:

- parent must pass the same safe-directory check;
- destination is no-replace;
- existing exact bytes/metadata are idempotent;
- an existing divergent file fails closed;
- publication uses a same-directory temporary file, fsync, exact root:root
  mode 0644, hard-link no-replace publication, and directory fsync;
- immediately before publication, `/opt/shreks/current` is re-authenticated
  against the explicit expected SHA;
- after publication, exact bytes and metadata are re-read with no-follow
  semantics.

The installer must not invoke `systemctl`, `sudo`, `daemon-reload`, or any
service mutation command.

## Canonical receipts

Preflight and install output canonical JSON with self-fingerprints.

The install receipt records:

- status `INSTALLED` or `ALREADY_INSTALLED`;
- release SHA/path;
- wheel path/SHA;
- nested commissioning-manifest fingerprint;
- unit SHA;
- fixed destination path and metadata;
- `service_activation_authority=NOT_GRANTED`;
- `paper_cutover_authority=NOT_GRANTED`;
- `signing_submission_authority=NOT_GRANTED`;
- `live_authority=DISABLED`.

## Authority firewall

This source must contain no:

- `systemctl`;
- subprocess/service mutation;
- legacy scoring;
- provider-network code;
- wallet access;
- signing/submission;
- PAPER campaign replacement;
- LIVE mode.

The existing release manager and deployment sudoers remain unchanged.

## RED acceptance

Tests must prove:

1. preflight authenticates exact active release/wheel/nested manifest;
2. wrong release, wrong runtime executable, tampered wheel, malformed nested
   package, or unsafe unit shape fails closed;
3. absent destination produces `READY_TO_INSTALL`;
4. exact installed destination produces `READY_ALREADY_INSTALLED`;
5. divergent/symlink/wrong-metadata destination fails closed;
6. install is no-replace and idempotent;
7. source has no service activation or capital authority;
8. CLI is release-local through `pyproject.toml`;
9. normal release manager and `shreks.target` remain untouched.

## Following slice

After this installer is merged and sealed, add the separate protected
configuration/state provisioning and physical-host acceptance proof required
before the dormant unit may be started in production shadow mode.
