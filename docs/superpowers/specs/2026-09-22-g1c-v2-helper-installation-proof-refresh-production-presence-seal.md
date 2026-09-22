# G1C V2 Helper Installation-Proof Refresh Production Presence — Release Seal

**Date:** 2026-09-22  
**Helper proof-refresh implementation main SHA:** `6f87b19d8adb53a2c4a7f651595e6e4a38096dea`  
**Production-presence implementation main SHA:** `a97f723092403c7b145563536a55dc19548e515a`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF PROOF-REFRESH TOOL PRESENCE ONLY; AUTOMATIC PROOF REFRESH DISABLED; READINESS/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the exact-release helper installation-proof refresh together with read-only production-presence proof.

The decision-backed readiness wrapper requires a fresh helper installation proof bound to the exact current immutable release. Production verification already reports the installed helper matches the current release, but an earlier proof becomes stale whenever the release SHA or wheel identity changes.

The refresh path closes that evidence gap without adding helper-publication authority.

It captures the existing exact-release prestate, invokes the existing installer only in the narrowed `require_already_installed=True` mode, requires an `ALREADY_INSTALLED` receipt, verifies the existing poststate with the established proof machinery, and returns the existing installation-proof v1 schema.

This seal deploys tool presence only.

It does not execute proof refresh.

## Current production state before this seal

The latest immutable GitHub release remains:

`shreks-e1abcc49cf291234bf0ed4f95fefe948bd63e10a`

Production verification for that release proves:

- the decision-backed rotation-readiness wrapper is exact-release-local;
- `paper_manifest_manager_status=MATCHED_CURRENT_RELEASE`;
- FL9 discovery remains `HOLD_NO_COMPATIBLE`.

The helper proof-refresh implementation merge:

`6f87b19d8adb53a2c4a7f651595e6e4a38096dea`

completed merged-main CI `35740746558` successfully.

Its release workflow `35741018323` and deploy workflow `35741027440` skipped by design because the main commit subject was not `seal:`.

The proof-refresh production-presence implementation merge:

`a97f723092403c7b145563536a55dc19548e515a`

completed merged-main CI `35742039279` successfully.

Its release workflow `35742324921` and deploy workflow `35742331803` skipped by design because the main commit subject was not `seal:`.

Therefore production has not yet received the proof-refresh CLI/module.

No proof refresh has been automatically executed.

No readiness proof, candidate, transition binding, or manifest rotation has been automatically created or executed.

## Exact-release helper proof-refresh implementation

Implementation main SHA:

`6f87b19d8adb53a2c4a7f651595e6e4a38096dea`

Final GREEN implementation head:

`0d7f180c226a89a826f5ac9fffa26197cf28afa8`

CLI:

`shreks-g1c-v2-paper-manifest-manager-install-proof-refresh`

Module:

`shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh`

Input is limited to:

- exact expected current immutable release SHA.

The refresh:

1. captures the existing canonical installation prestate;
2. invokes the existing release-bound installer with `require_already_installed=True`;
3. requires the installer receipt status to be exactly `ALREADY_INSTALLED`;
4. verifies the existing poststate through the established installation-proof implementation;
5. requires the result to remain `VERIFIED`;
6. returns the existing `shreks.g1c_v2_paper_manifest_manager_installation_proof` version 1 proof unchanged.

The narrowed installer mode fails before publication if the helper is absent.

Different helper bytes or mismatched metadata also fail without replacement or repair.

The refresh wrapper contains no helper-publication primitive.

A successful proof preserves:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The ordinary installer default remains unchanged for the separately authorized first-install ceremony.

## TDD and implementation proof

### Helper proof refresh

Intentional RED PR #419 head:

`3f4035b5be7333396b73457592b33a4fbd5fcd31`

RED CI:

`35739379889`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh` did not yet exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN implementation head:

`0d7f180c226a89a826f5ac9fffa26197cf28afa8`

Push CI:

`35740346727`

Independent PR CI:

`35740354558`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`6f87b19d8adb53a2c4a7f651595e6e4a38096dea`

Merged-main CI:

`35740746558`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED PR #421 head:

`7e1a167a09bd3f29dd57bd2844dc4dec064cd6c4`

RED CI:

`35741229233`

Result:

- Python: exactly 1 failed, 3639 passed, 2 known warnings;
- the only failure was the intentionally absent helper proof-refresh production-presence contract;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

GREEN production-presence head:

`13d8c61e777b6d04990cbf927c9b385fb578eeec`

Push CI:

`35741681965`

Independent PR CI:

`35741717741`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged production-presence main:

`a97f723092403c7b145563536a55dc19548e515a`

Merged-main CI:

`35742039279`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing proof refresh:

- the release-local `shreks-g1c-v2-paper-manifest-manager-install-proof-refresh` script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh` imports through exact release-local Python;
- the module path resolves inside that same expected release.

Expected evidence includes:

```text
paper_manifest_manager_installation_proof_refresh=present
paper_manifest_manager_installation_proof_refresh_path=<exact-release-local-path>
paper_manifest_manager_installation_proof_refresh_module=<exact-release-local-module-path>
```

The verifier must not invoke proof refresh.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the helper proof-refresh CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, trusted-admin tooling presence/provenance, read-only helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute proof refresh;
- create or refresh an installation proof;
- execute decision-backed readiness;
- create or stage candidate/binding/readiness artifacts;
- install, replace, or repair the helper;
- install, activate, or rotate a runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin proof-refresh boundary

Only after production verification proves the proof-refresh CLI/module exact-release-local may a trusted administrator use the documented root-private refresh ceremony.

That ceremony accepts only the exact current release SHA.

It requires the helper to already match the exact current release.

If the helper is absent, different, or has wrong metadata, refresh fails closed and does not install or repair it.

A successful refresh produces one fresh existing-schema installation proof bound to the exact active release.

That proof is evidence for a later decision-backed readiness ceremony only.

It does not itself execute readiness or grant manifest-rotation authority.

## Readiness boundary

Deployment of this seal changes the current release SHA and wheel identity.

Any installation proof bound to an earlier release is stale for readiness.

This seal makes the read-only refresh tool production-present but does not authorize automatic refresh.

Even after a fresh proof is produced, decision-backed readiness remains a separate evidence-only trusted-admin ceremony requiring:

- the exact reviewed candidate;
- the exact reviewed standard transition binding;
- the exact reviewed decision-backed candidate authority;
- the fresh exact-release helper installation proof;
- the exact current release SHA.

A successful readiness receipt still records `manifest_rotation_authority=NOT_GRANTED`.

## Authority boundary

This seal does not authorize:

- automatic helper proof refresh;
- helper installation or repair;
- automatic decision-backed readiness;
- candidate/binding/readiness staging;
- manifest-rotation authority;
- production manifest installation/activation/rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_HELPER_INSTALLATION_PROOF_REFRESH=SEALED_TOOL_PRESENCE_ONLY`

`HELPER_INSTALLATION_PROOF_REFRESH_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_HELPER_PROOF_REFRESH=DISABLED`

`AUTOMATIC_DECISION_BACKED_READINESS=DISABLED`

`MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
