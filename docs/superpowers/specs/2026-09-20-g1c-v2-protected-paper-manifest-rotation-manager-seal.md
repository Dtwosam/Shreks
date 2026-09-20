# G1C V2 Protected PAPER Runtime-Manifest Rotation Manager — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `05d8fd09f5ead25b325e42f528c24f38b92e8089`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF MANAGER CODE TRANSPORT ONLY; ROOT HELPER INSTALLATION NOT AUTHORIZED BY THIS SEAL; V2 MANIFEST ROTATION NOT AUTHORIZED BY THIS SEAL; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the protected PAPER runtime-manifest rotation manager implementation for immutable release transport and ordinary protected PAPER deployment.

The implementation adds an administrator-only manager capable of authenticating one already-bound G1C runtime-manifest v1 -> v2 transition, quiescing only the PAPER campaign writer, proving the exact candidate against the real protected PAPER state, atomically replacing only the protected campaign manifest, verifying release-bound runtime health, and restoring the exact source manifest on failure.

This seal authorizes deployment of that code capability only.

It does not authorize:

- installing or replacing `/usr/local/sbin/shreks-paper-manifest-manager`;
- invoking the manager on production;
- staging a production v2 candidate or transition binding;
- changing `/etc/shreks/paper-campaign.json`;
- rotating the active v1 campaign to v2;
- retrying V2 scoring;
- PAPER promotion;
- wallet access, signing, transaction submission, or LIVE trading.

The active production v1 campaign remains runtime authority unless a later separately sealed administrator transition explicitly changes it.

## Implemented authority boundary

The manager is a separate root-only maintenance surface.

Its production command shape is:

```text
/usr/local/sbin/shreks-paper-manifest-manager rotate <candidate> <binding> <binding-fingerprint> <release-sha>
```

The implementation requires effective uid 0.

The existing `shreks-deploy` sudoers contract is unchanged. The automatic GitHub deployment account still has authority only to invoke the historical verified release-manager install command and receives no passwordless invocation path for the manifest manager.

The manager is transported inside the manifest-hashed Shreks wheel as:

```text
shreks_brain/_sealed_deploy_control/paper_manifest_manager.py
```

The completed release wheel is checked byte-for-byte against the exact sealed checkout during release construction.

This keeps the historical top-level release allowlist unchanged.

## Pre-mutation authentication

Before any campaign stop or protected-manifest replacement, the manager requires:

- configured production DB, E11, campaign-manifest, and G7 paths in `/etc/shreks/shreks.env` equal the protected paths used by the manager;
- `/opt/shreks/current` resolves to the explicit expected release SHA;
- the current release's canonical `RELEASE_MANIFEST.json` source SHA equals that release SHA;
- current release Python is a regular non-symlink file;
- active campaign manifest is a regular non-symlink canonical v1 manifest with mode 0640;
- candidate is a regular non-symlink canonical v2 manifest;
- transition binding is canonical and fingerprint-valid;
- explicit operator binding fingerprint equals the binding fingerprint;
- source raw SHA-256, runtime-manifest fingerprint, paper run, and quote mint equal the binding;
- candidate raw SHA-256, runtime-manifest fingerprint, paper run, start timestamp, quote mint, and quote decimals equal the binding;
- G7 operator risk-control state is readable and valid.

Any failure before campaign quiesce performs no systemd action and no protected campaign-manifest mutation.

## Campaign-only quiesce

After all pre-mutation checks pass, the manager stops only:

`shreks-paper-campaign.service`

The observer and PAPER evidence services remain outside this maintenance stop.

The manager does not stop or restart the whole Shreks target merely to rotate a campaign manifest.

## Private rollback evidence

After campaign stop succeeds, the manager creates one write-once evidence directory:

`/var/lib/shreks/manifest-rotations/<binding-fingerprint>/`

The directory is mode 0700.

It records mode-0600 copies of:

- the exact source campaign manifest bytes;
- the exact candidate campaign manifest bytes;
- the exact transition-binding bytes;
- the PREPARED receipt.

Existing evidence for the same binding fingerprint is not overwritten.

## Candidate preflight binding

The candidate is authenticated from its staged input path, but the read-only PAPER preflight does not trust that staging path afterward.

Instead, preflight is run against the manager's own private copied candidate inside the rotation-evidence directory.

Therefore the bytes preflighted are exactly the bytes later installed.

Preflight uses the existing sealed PAPER runtime path with:

- real operational SQLite state;
- real E11 evidence;
- the private candidate manifest copy;
- real G7 operator-control state.

The preflight does not execute a PAPER cycle.

A new paper run is allowed to coexist with historical SQLite and E11 state because the sealed coordinator restores and validates state by paper-run attribution.

No source-run history is deleted.

## Atomic protected replacement

Only after private candidate preflight succeeds may the manager replace:

`/etc/shreks/paper-campaign.json`

The replacement:

- writes a temporary regular file in the same parent directory;
- fsyncs content;
- preserves the source manifest's uid, gid, and exact 0640 mode;
- uses atomic replacement;
- fsyncs the parent directory.

The manager does not replace:

- the operational SQLite database;
- E11 evidence;
- G7 operator-control state;
- `/etc/shreks/shreks.env`;
- release payloads;
- systemd units;
- secrets;
- wallet/signing material.

## Active-path preflight and restart

After candidate replacement but before service start, the manager runs the existing PAPER preflight again against the protected active manifest path.

It then starts only the ordinary release-managed PAPER campaign service.

All existing systemd startup gates remain authoritative.

Successful activation additionally requires:

- campaign service active;
- positive MainPID;
- process cwd equals the exact expected immutable release;
- campaign Python executable is from that release's copied virtualenv;
- protected campaign-manifest bytes equal the authenticated candidate bytes.

Only then may the manager write an ACTIVATED receipt.

## Automatic rollback

Any failure after campaign quiesce triggers source restoration.

If candidate bytes were installed, the manager atomically restores the exact authenticated source bytes with the original metadata.

It then:

1. preflights the protected source manifest;
2. starts the PAPER campaign service;
3. verifies service/process identity against the expected immutable release;
4. verifies protected active manifest bytes equal the source bytes;
5. writes a ROLLED_BACK receipt when the evidence directory exists.

If rollback itself cannot be proven, the command reports rotation-and-rollback failure rather than claiming recovery.

Candidate-run checkpoints or E11 rows are never erased as part of rollback. Preserving written evidence is safer than fabricating a history in which the failed activation never occurred.

## Receipt authority

PREPARED, ACTIVATED, and ROLLED_BACK receipts bind the transition to release and manifest identity while explicitly preserving:

- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

The manager contains no scorer, model fit, promotion, signer, transaction construction, transaction submission, or LIVE runtime authority.

## Release transport

The release builder copies the exact manager into the sealed deployment-control package before constructing the Shreks wheel.

The completed wheel must contain exact checkout bytes for:

- `release_bundle.py`;
- `release_manager.py`;
- `paper_manifest_manager.py`.

This proof occurs before the wheel enters the ordinary release bundle.

The ordinary release bundle remains manifest-hashed and retains its historical top-level payload schema and allowlist.

Automatic deployment installs the verified release and release-local Python environment under `/opt/shreks/releases/<sha>` and switches `/opt/shreks/current` through the existing G2 manager.

It does not install the separate root-owned helper into `/usr/local/sbin`.

## Implementation proof

Implementation PR:

`#344 — G1C: add protected PAPER manifest rotation manager`

Implementation branch head:

`3313f590cd76184bf880346dc43b5afd3bd884f6`

PR CI:

`35539085050`

Result:

- Python: 3521 passed, 1 warning;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`05d8fd09f5ead25b325e42f528c24f38b92e8089`

Exact merged-main CI:

`35539259120`

Result:

- Python: 3521 passed, 1 warning;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The warning is the pre-existing duplicate-member warning exercised intentionally by the sealed fast-proof-tool transport negative test.

## Changed implementation surfaces

The sealed implementation is bounded to:

- new root-only PAPER manifest manager;
- protected source/candidate/binding authentication;
- campaign-only quiesce;
- private write-once rollback evidence;
- candidate and active-path PAPER preflight;
- atomic protected manifest replacement;
- release-bound runtime process verification;
- automatic source-manifest rollback;
- release-wheel transport of exact manager bytes;
- tests;
- release runbook and design documentation.

It does not change:

- trading strategy;
- candidate economics;
- risk limits;
- G7 control semantics;
- scorer behavior;
- frozen cohort bytes;
- V2 request bytes;
- model fitting;
- champion publication;
- wallet or signing logic;
- transaction submission;
- LIVE runtime mode.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. inclusion of the exact protected PAPER manifest manager bytes in the manifest-hashed release wheel;
3. automatic protected PAPER deployment of that release through the existing G2 release manager;
4. automatic production verification of the existing production PAPER runtime;
5. confirmation that the currently active production campaign remains unchanged by deployment;
6. confirmation that protected FL9 discovery remains evidence-only and does not create scoring authority.

This seal grants no production manifest-rotation invocation.

## Root helper installation boundary

The released manager bytes may later be extracted from the exact verified current release wheel and installed root-owned at:

`/usr/local/sbin/shreks-paper-manifest-manager`

only by a separately authorized trusted-administrator maintenance action.

That future installation must prove:

- current release SHA;
- current release-manifest source SHA;
- exact wheel member path;
- byte-for-byte equality to the sealed manager source;
- destination root ownership;
- destination mode 0755;
- installed-byte SHA-256;
- no sudoers expansion.

This seal does not itself authorize that installation.

## Production manifest-rotation boundary

Even after the helper is installed, a production v2 manifest rotation still requires a separately authorized operator action with:

- exact candidate bytes;
- exact transition binding;
- explicit binding fingerprint;
- exact active release SHA;
- active source-manifest identity;
- preserved G7 state;
- campaign-only maintenance window.

The automatic release/deploy workflows must not stage or invoke those inputs.

## Expected automatic production proof

The automatic release/deploy chain for this seal must demonstrate:

`seal merge -> exact sealed-main CI -> immutable release -> protected PAPER deploy -> existing campaign restart/health -> protected FL9 discovery -> reusable production verification`

Production verification must show:

- active release SHA equals the sealed SHA;
- release-manifest source SHA equals the sealed SHA;
- observer service healthy;
- PAPER evidence service healthy;
- PAPER campaign service healthy;
- process identity rooted in the sealed release;
- existing active campaign remains the production authority;
- no manager invocation occurs;
- no protected campaign-manifest replacement occurs because of deployment;
- no scoring request is created by this deployment;
- FL9 discovery remains a read-only authority-discovery surface.

The semantic FL9 result may reflect whatever authenticated evidence exists at verification time.

A `FOUND_COMPATIBLE` result is discovery evidence only and does not authorize scoring or rotation.

## Next separate authority slice

After successful automatic deployment of this seal, the next slice may prove administrator installation of the exact release-bound manager helper into `/usr/local/sbin`.

That slice must remain installation-only.

It must not simultaneously rotate the production manifest.

Only after helper installation is independently proven should a separate production v2 rotation action be considered.

## Promotion boundary

`G1C_V2_PROTECTED_ROTATION_MANAGER=SEALED_CODE_TRANSPORT`

`ROOT_MANIFEST_MANAGER_INSTALL=NOT_AUTHORIZED_BY_THIS_SEAL`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED_BY_THIS_SEAL`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
