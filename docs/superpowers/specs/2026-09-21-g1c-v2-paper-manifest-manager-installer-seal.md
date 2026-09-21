# G1C V2 Release-Bound PAPER Manifest Manager Installer — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `4095a1b903a3294e01f605e81876127be5917e42`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF INSTALLER CODE; TRUSTED-ADMINISTRATOR FIRST INSTALL OF THE EXACT RELEASE-BOUND HELPER AUTHORIZED AFTER DEPLOY VERIFICATION; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the release-bound installer for the already-sealed protected PAPER runtime-manifest manager.

The installer exists to perform one deliberately narrow host mutation:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

may be created from the exact sealed manager bytes carried by the exact active immutable Shreks release.

This seal separates three authorities that must not collapse into one another:

1. ordinary automatic release/deploy authority;
2. trusted-administrator helper-installation authority;
3. protected PAPER runtime-manifest rotation authority.

Only the first two are authorized here, and the second is constrained to exact first-install or exact-idempotence semantics after the sealed release is active and production verification succeeds.

This seal does not authorize a manifest rotation.

## Production state before this seal

The previous sealed production release is:

`81af7f533d54054e017a5f18898d98420a7c40ba`

Its immutable GitHub release is:

`shreks-81af7f533d54054e017a5f18898d98420a7c40ba`

The prior automatic deploy/verify chain completed successfully.

Production verification showed:

- observer active/running;
- PAPER evidence service active/running;
- PAPER campaign service active/running;
- zero unexpected service restarts;
- expected/observed release SHA equality;
- protected FL9 discovery completed read-only;
- FL9 status `HOLD_NO_COMPATIBLE`.

That FL9 result is evidence only. It does not authorize scoring or rotation.

The implementation merge for this installer was intentionally not a seal and therefore did not create or deploy a new production release.

## Installer implementation

The implementation adds the release-local console script:

```text
shreks-g1c-v2-paper-manifest-manager-install
```

implemented by:

```text
shreks_brain.g1c_v2_paper_manifest_manager_install
```

The production invocation shape is:

```text
<resolved-current-release>/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install <exact-40-char-current-release-sha>
```

The installer requires effective uid 0.

It is not delegated to `shreks-deploy`.

## Exact current-release binding

Before it trusts release content, the installer requires:

- `/opt/shreks/current` is an existing symlink;
- the symlink resolves successfully;
- the resolved release directory basename equals the explicit expected release SHA;
- the installer is executing from that exact release's `.venv/bin`;
- the installer executable is regular and non-symlink.

This prevents a trusted administrator from preparing an invocation for one release while silently sourcing install bytes or installer logic from another.

## Canonical release-manifest binding

The installer reads:

`<resolved-current-release>/RELEASE_MANIFEST.json`

with no-follow semantics.

It requires:

- regular non-symlink file;
- canonical JSON;
- no duplicate keys;
- no non-finite constants;
- exact expected schema fields;
- supported release-manifest schema;
- valid exact source SHA;
- supported platform;
- valid, sorted file records;
- no duplicate file paths;
- safe relative paths;
- exact canonical encoding.

The release-manifest source SHA must equal the explicit expected current release SHA.

## Manifest-hashed wheel binding

The canonical release manifest must identify exactly one Shreks wheel matching:

```text
wheelhouse/shreks_brain-*.whl
```

The installer reads that wheel as a regular non-symlink file and requires:

- exact recorded byte length;
- exact recorded SHA-256.

Only after both checks pass may ZIP contents be considered.

This binds installation to the same release payload admitted by the existing G2 release chain.

## Exact sealed manager-member binding

Inside the verified wheel, the installer requires exactly one member:

```text
shreks_brain/_sealed_deploy_control/paper_manifest_manager.py
```

It rejects duplicate manager members, directory entries, encrypted entries, malformed ZIP content, and payloads that do not have the expected executable shape.

Release construction already verifies this same wheel member byte-for-byte against:

`deploy/release/paper_manifest_manager.py`

Therefore the installation provenance chain is:

```text
sealed manager source
  -> exact release wheel member
  -> manifest-hashed wheel
  -> canonical release manifest
  -> exact immutable current release
  -> installed root helper
```

## Destination policy

The only authorized destination is:

`/usr/local/sbin/shreks-paper-manifest-manager`

Expected final metadata is:

- uid 0;
- gid 0;
- mode 0755;
- regular non-symlink file.

This seal authorizes:

- first installation when the destination is absent;
- exact idempotent recognition when the destination already has identical sealed bytes and exact metadata.

This seal does not authorize replacement or upgrade of a divergent existing helper.

If existing bytes or metadata differ, the installer must fail closed for administrator investigation.

## Publication boundary

Before publication, the installer requires the destination parent to be:

- a real directory;
- root-owned;
- not group-writable;
- not world-writable.

The verified manager bytes are written into a private temporary file in that same destination directory.

The installer:

1. writes the exact payload;
2. flushes and fsyncs it;
3. sets uid/gid 0;
4. sets mode 0755;
5. fsyncs it again;
6. re-resolves `/opt/shreks/current`;
7. requires the same explicit release SHA still be active;
8. publishes using no-overwrite hard-link semantics;
9. removes the temporary name;
10. fsyncs the destination directory;
11. re-reads the final path no-follow;
12. requires exact payload and metadata.

A destination that appears concurrently is never overwritten.

## Installation receipt

Successful installer output is canonical JSON.

It binds:

- installation schema/version;
- `INSTALLED` or `ALREADY_INSTALLED`;
- release source SHA;
- resolved immutable release directory;
- wheel relative path;
- wheel SHA-256;
- sealed manager wheel-member path;
- manager SHA-256;
- destination path;
- destination uid/gid/mode.

Authority fields remain explicit:

- `installation_authority = EXERCISED_EXACT_RELEASE_BOUND_HELPER_ONLY`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

Failure emits a sanitized canonical failure receipt and does not claim installation.

## Automatic release/deploy authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build an immutable ARM64 release for the exact sealed SHA;
2. package the installer entry point inside the release-local Python environment;
3. carry the already-sealed PAPER manifest manager as exact wheel content;
4. verify release bytes and release manifest;
5. create the immutable GitHub release;
6. deploy that exact release through the existing G2 release manager;
7. activate the ordinary protected PAPER runtime;
8. verify release identity, service health, restart state, process provenance, and protected FL9 discovery.

Automatic deployment does not invoke the installer.

Automatic deployment does not create or replace:

`/usr/local/sbin/shreks-paper-manifest-manager`

The existing `shreks-deploy` sudoers boundary remains unchanged.

## Trusted-administrator installation authority granted by this seal

Only after the exact sealed release is active and the ordinary production verifier has succeeded, a trusted administrator is authorized to perform exactly this release-bound helper installation:

```sh
set -euo pipefail

CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"

if [[ ! "$CURRENT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current release identity is invalid" >&2
  exit 2
fi

sudo "$CURRENT_RELEASE/.venv/bin/shreks-g1c-v2-paper-manifest-manager-install" "$CURRENT_SHA"
```

The invocation must use the exact release that has just been verified as production current.

The installer independently re-proves all release, wheel, member, destination, and race boundaries before publication.

This seal does not authorize an administrator to copy helper bytes manually, invoke a repository checkout, install from an unverified wheel, broaden sudoers, or replace a divergent existing destination.

## Required post-install proof

A successful administrator installation is not considered proven merely because the installer exits zero.

The operator proof must preserve the canonical installer receipt and independently confirm:

- `/opt/shreks/current` still resolves to the sealed release SHA;
- release-manifest source SHA equals the sealed release SHA;
- destination is a regular non-symlink file;
- destination uid = 0;
- destination gid = 0;
- destination mode = 0755;
- destination SHA-256 equals the installer receipt's `manager_sha256`;
- receipt wheel SHA-256 equals the canonical release-manifest wheel record;
- no `shreks-deploy` sudoers authority was added for the installer or manager;
- no Shreks service lifecycle action occurred because of helper installation;
- protected campaign-manifest bytes were not changed by helper installation.

The installation proof may report either `INSTALLED` or `ALREADY_INSTALLED`.

A divergent pre-existing destination is a failed proof, not permission to overwrite it.

## Implementation proof

Implementation PR:

`#347 — G1C: install exact release-bound PAPER manifest manager helper`

Final implementation branch head:

`f8eceb307a6cde8849a1b1e0f2c917e791db3424`

PR CI:

`35576122052`

Result:

- Python: 3530 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The two warnings are duplicate-ZIP-member warnings from intentional negative transport tests.

Squash-merged implementation main:

`4095a1b903a3294e01f605e81876127be5917e42`

Exact merged-main CI:

`35576370921`

Result:

- Python: 3530 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Because the implementation merge subject is `feat:`, its automatic release and deploy workflow invocations were correctly skipped.

Therefore no production helper installation occurred merely by landing the implementation.

## Changed implementation surfaces

The sealed implementation is limited to:

- one release-local installer module;
- one console-script entry point;
- focused installer tests;
- release runbook changes;
- installer design documentation.

The installer itself has no authority over:

- systemd;
- campaign service lifecycle;
- `/etc/shreks`;
- `/var/lib/shreks`;
- PAPER runtime preflight;
- active campaign-manifest replacement;
- SQLite;
- E11;
- G7 state;
- scoring;
- model fitting;
- champion state;
- PAPER promotion;
- wallets;
- signing;
- transaction construction;
- transaction submission;
- LIVE mode.

## Production v2 manifest-rotation boundary

The presence of an installed helper does not authorize invocation of:

```text
/usr/local/sbin/shreks-paper-manifest-manager rotate ...
```

A later, separately explicit production-rotation authority slice must bind:

- exact active source manifest;
- exact v2 candidate;
- exact transition binding;
- explicit binding fingerprint;
- exact active immutable release SHA;
- G7 operator-control state;
- campaign-only maintenance window;
- rollback-evidence destination.

That later action must independently prove the active release contains the sealed manager implementation and that the installed helper bytes match that release.

## Scoring and promotion boundary

This seal does not authorize:

- a V2 scoring retry;
- new model fitting;
- champion selection or publication;
- PAPER promotion;
- wallet/signing activity;
- transaction submission;
- LIVE trading.

Protected FL9 discovery remains read-only evidence.

A future `FOUND_COMPATIBLE` result would still not itself authorize scoring or rotation.

## Expected automatic production proof for this seal

The automatic chain must demonstrate:

```text
seal merge
  -> exact sealed-main CI
  -> immutable release
  -> protected PAPER deploy
  -> runtime health/process provenance
  -> protected FL9 read-only discovery
```

The expected result is a production release containing the installer, while the helper destination remains untouched by automation.

Only after that chain succeeds may the trusted-administrator installation authority above be exercised.

## Promotion boundary

`G1C_V2_PAPER_MANIFEST_MANAGER_INSTALLER=SEALED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_EXACT_HELPER_FIRST_INSTALL=AUTHORIZED_AFTER_DEPLOY_VERIFY`

`DIVERGENT_HELPER_REPLACEMENT=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
