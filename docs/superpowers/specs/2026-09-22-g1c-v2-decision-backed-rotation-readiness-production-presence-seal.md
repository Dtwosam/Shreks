# G1C V2 Decision-Backed Rotation Readiness Production Presence — Release Seal

**Date:** 2026-09-22  
**Decision-backed readiness implementation main SHA:** `fb0115cc0f37239b5f9f4733e14647cfbc0b65b0`  
**Production-presence implementation main SHA:** `26b87c04b75d40630e4263c404ede6ce64e23c7c`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READINESS-WRAPPER TOOL PRESENCE ONLY; AUTOMATIC READINESS EXECUTION DISABLED; HELPER-PROOF REFRESH NOT AUTHORIZED; MANIFEST ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the decision-backed G1C v2 rotation-readiness wrapper together with read-only exact-release production-presence proof.

The wrapper closes one provenance gap only: the existing readiness engine must receive an exact candidate and standard transition binding that still authenticate back to the reviewed decision-backed candidate authority, while the operator no longer supplies a separate binding fingerprint.

The wrapper authenticates the exact candidate, standard binding, and decision-backed authority; derives the binding fingerprint from the authenticated binding; delegates release/helper/service/G7/preflight checks to the existing evidence-only readiness implementation; validates the returned standard readiness receipt against the same authority chain; and rechecks input stability.

This seal deploys tool presence only.

It does not execute readiness.

## Current production state before this seal

The latest immutable GitHub release remains:

`shreks-b8b3e1510dc10a024ae0620ca08f4a031195e1c8`

That release already contains and proves exact-release presence for the decision-backed transition-binding bridge.

The decision-backed readiness implementation merge:

`fb0115cc0f37239b5f9f4733e14647cfbc0b65b0`

completed merged-main CI `35734063442` successfully.

The readiness production-presence implementation merge:

`26b87c04b75d40630e4263c404ede6ce64e23c7c`

completed merged-main CI `35735423865` successfully.

Its release workflow `35735704471` and deploy workflow `35735724334` skipped by design because the main commit subject was not `seal:`.

Therefore production has not yet received the decision-backed readiness CLI/module.

No readiness proof has been automatically executed.

No candidate, transition binding, or readiness receipt has been automatically staged or created.

## Decision-backed readiness implementation

Implementation main SHA:

`fb0115cc0f37239b5f9f4733e14647cfbc0b65b0`

GREEN implementation head:

`fdb96a2072f27690cf7a9c09500750b76badb25f`

CLI:

`shreks-g1c-v2-decision-backed-rotation-readiness`

Module:

`shreks_brain.g1c_v2_decision_backed_rotation_readiness`

Inputs are limited to:

- exact canonical v2 candidate runtime manifest;
- exact standard transition binding;
- authenticated decision-backed candidate authority;
- exact current-release helper installation-proof bytes;
- explicit expected immutable release SHA.

The CLI does not accept:

- an operator-supplied binding fingerprint;
- paper-run id;
- start timestamp;
- quote mint;
- quote decimals;
- entry amount;
- candidate-value decision;
- valuation review;
- sizing values.

The wrapper derives the binding fingerprint from the authenticated standard transition binding.

It requires candidate and binding provenance to match the decision-backed authority before delegating to the existing readiness proof.

The existing readiness proof remains solely responsible for:

- exact immutable release authentication;
- manifest-hashed wheel identity;
- exact release-bound helper installation proof;
- installed manifest-manager bytes/metadata;
- deployment sudoers identity;
- runtime environment contract;
- protected active source identity;
- G7 risk-control stability;
- PAPER service health/lifecycle stability;
- private candidate preflight against operational PAPER runtime inputs.

After delegation the wrapper requires the standard readiness receipt to remain bound to the same source/candidate/binding/release identities and to preserve:

```text
status=READY_EVIDENCE_ONLY
installation_authority=PROVEN
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

It returns the existing standard readiness receipt unchanged.

## TDD and implementation proof

### Decision-backed readiness wrapper

Intentional RED PR #414 head:

`da1061d4d6c81e8edc488453dc1e0f8cbba6a16c`

RED CI:

`35733427906`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_decision_backed_rotation_readiness` did not yet exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

GREEN implementation head:

`fdb96a2072f27690cf7a9c09500750b76badb25f`

Push CI:

`35733661485`

Independent PR CI:

`35733691224`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`fb0115cc0f37239b5f9f4733e14647cfbc0b65b0`

Merged-main CI:

`35734063442`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED PR #416 head:

`f7ede117a58bcc68f35e7a250d3b6e453a699df1`

RED CI:

`35734567340`

Result:

- Python: exactly 1 failed, 3632 passed, 2 known warnings;
- the only failure was the intentionally absent decision-backed readiness production-presence contract;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

GREEN production-presence head:

`653fb97ee20bd4b1a2d6b432f7750cd0c83d97de`

Push CI:

`35734997613`

Independent PR CI:

`35735049473`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged production-presence main:

`26b87c04b75d40630e4263c404ede6ce64e23c7c`

Merged-main CI:

`35735423865`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing readiness:

- the release-local `shreks-g1c-v2-decision-backed-rotation-readiness` script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_decision_backed_rotation_readiness` imports through exact release-local Python;
- the module path resolves inside that same release.

Expected evidence includes:

```text
g1c_v2_decision_backed_rotation_readiness=present
g1c_v2_decision_backed_rotation_readiness_path=<exact-release-local-path>
g1c_v2_decision_backed_rotation_readiness_module=<exact-release-local-module-path>
```

The verifier must not invoke readiness.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the decision-backed readiness CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, trusted-admin tooling presence/provenance, helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute candidate-value selection;
- execute candidate authority binding;
- execute candidate authoring;
- execute transition binding;
- execute decision-backed readiness;
- refresh or create a helper installation proof;
- create or stage candidate/binding/readiness artifacts;
- install, activate, or rotate a runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin readiness boundary

Only after production verification proves the wrapper exact-release-local may a trusted administrator use the documented evidence-only readiness ceremony.

That ceremony additionally requires:

- the exact reviewed decision-backed candidate;
- the exact reviewed standard transition binding;
- the exact reviewed decision-backed authority;
- a fresh exact-release helper installation proof;
- the exact current release SHA.

The wrapper itself does not install or refresh the helper and does not create the installation proof.

A successful `READY_EVIDENCE_ONLY` receipt remains evidence for a later separate rotation-authority decision.

It does not authorize manifest mutation.

## Helper-proof boundary

Deployment of this seal changes the current release SHA and wheel identity.

Any helper installation proof bound to an earlier release is stale for this new release.

Even if the installed manifest-manager bytes remain identical and production status reports a matching helper, the decision-backed readiness ceremony requires a **fresh exact-release installation proof** before it can succeed.

This seal does not authorize or perform that refresh automatically.

## Authority boundary

This seal does not authorize:

- automatic readiness execution;
- helper installation/proof refresh;
- candidate/binding staging;
- manifest-rotation authority;
- production manifest installation/activation/rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_DECISION_BACKED_ROTATION_READINESS=SEALED_TOOL_PRESENCE_ONLY`

`DECISION_BACKED_ROTATION_READINESS_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_ROTATION_READINESS_EXECUTION=DISABLED`

`HELPER_INSTALLATION_PROOF_REFRESH=NOT_AUTHORIZED`

`MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
