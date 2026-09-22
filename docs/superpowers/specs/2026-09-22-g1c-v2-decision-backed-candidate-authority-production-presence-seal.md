# G1C V2 Decision-Backed Candidate Authority Production Presence — Release Seal

**Date:** 2026-09-22  
**Decision-backed authority implementation main SHA:** `61345007c26390bc64552b229d749360f5f46484`  
**Production-presence implementation main SHA:** `c45c2ccdbcd61a6126b6dd2a9dc0f80713b102f1`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF BRIDGE PRESENCE ONLY; AUTOMATIC BRIDGE EXECUTION DISABLED; CANDIDATE FILE AUTHORING/STAGING NOT AUTHORIZED; TRANSITION/READINESS/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the decision-backed G1C v2 candidate-authority bridge together with read-only exact-release production-presence proof.

The bridge closes one provenance gap only: an approved candidate-value decision must not be reduced back to raw quote mint/decimals/entry-amount CLI inputs before candidate-authoring authority is derived.

The bridge authenticates the approved decision and supplies its exact bound economics into the existing candidate-authority derivation.

This seal deploys tool presence only.

It does not execute the bridge.

## Current production state before this seal

The currently active immutable release is:

`64696a67d6185ea52cca577e2f02527006214a09`

Production verification for that release proved the candidate-value decision CLI/module exact-release-local and preserved:

```text
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

The production candidate-value decision tool may grant value authority only after one explicit reviewed ACCEPT/REPLACE decision over authenticated `MULTI_REFERENCE_REVIEW` sizing evidence.

No candidate has been authored or staged through the decision-backed path.

## Decision-backed authority implementation

The implementation was merged to main as:

`61345007c26390bc64552b229d749360f5f46484`

CLI:

`shreks-g1c-v2-decision-backed-candidate-authority-bind`

Module:

`shreks_brain.g1c_v2_decision_backed_candidate_authority`

Inputs are limited to:

- canonical v1 source runtime manifest;
- frozen V2 cohort;
- authenticated V2 host request authority;
- approved candidate-value decision;
- explicit new paper run id;
- explicit new start timestamp;
- new non-existent destination.

There are no raw quote-mint, quote-decimals, or entry-input-amount CLI arguments.

The bridge requires the decision to preserve:

```text
status=CANDIDATE_VALUE_APPROVED
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
quote_evidence_authority=MULTI_REFERENCE_REVIEW
```

The supplied source manifest must match the source authority committed by the decision.

The bridge then delegates exact candidate derivation to the existing candidate-authority binder using only the decision-bound quote mint, decimals, and selected raw amount plus separately explicit new-run identity/time.

A successful artifact may record:

```text
authority_status=BOUND_EXACT_CANONICAL_CANDIDATE
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This is candidate-authoring authority evidence only. It does not emit or stage a candidate.

## TDD and implementation proof

### Decision-backed bridge

Intentional RED PR #399 head:

`93b11fabeb5c100e318b7d764d8cea4ce2d28b36`

RED CI:

`35711537249`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_decision_backed_candidate_authority` did not yet exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN implementation head:

`5e24e4cb0bbc825fb91e912fa1e9f80657db6a4b`

Push CI:

`35712088894`

Independent PR CI:

`35712092529`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`61345007c26390bc64552b229d749360f5f46484`

Merged-main CI:

`35712367129`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED PR #401 head:

`903828e5c82323eb375e5349bcb7a1a9bc11f367`

RED CI:

`35712698447`

Result:

- Python: exactly 1 failed, 3613 passed, 2 known warnings;
- the only failure was the intentionally absent decision-backed authority production-presence contract;
- Repository safety, Rust, and ARM64: SUCCESS.

Final GREEN production-presence head:

`568ab6fec6c38fb22c1ce33503be1e5d1ce1e967`

Push CI:

`35712993995`

Independent PR CI:

`35713010338`

Both: SUCCESS across all four canonical gates.

Merged production-presence main:

`c45c2ccdbcd61a6126b6dd2a9dc0f80713b102f1`

Merged-main CI:

`35714543586`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing the bridge:

- the release-local `shreks-g1c-v2-decision-backed-candidate-authority-bind` script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_decision_backed_candidate_authority` imports through exact release-local Python;
- the module path resolves inside that same release.

Expected evidence includes:

```text
g1c_v2_decision_backed_candidate_authority=present
g1c_v2_decision_backed_candidate_authority_path=<exact-release-local-path>
g1c_v2_decision_backed_candidate_authority_module=<exact-release-local-module-path>
```

The verifier must not invoke the bridge.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the decision-backed authority CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, existing trusted-admin tooling, decision-tool provenance, decision-backed authority presence/provenance, helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute review-backed sizing;
- execute the candidate-value decision;
- execute the decision-backed authority bridge;
- author or stage a runtime candidate;
- create a transition binding;
- execute readiness;
- install, activate, or rotate a runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin boundary

Only after production verification proves the bridge exact-release-local may a trusted administrator use the documented ceremony against explicit protected source/cohort/request/approved-decision artifacts plus explicit new-run identity/time.

A successful authority artifact must be reviewed separately.

It is not itself a runtime-manifest candidate.

The later exact candidate-authoring step must reproduce the candidate manifest SHA/fingerprint committed by the decision-backed authority.

Do not run transition binding from this authority alone.

## Helper/readiness boundary

Deployment of this seal changes the current release SHA.

Any helper installation proof bound to an earlier release becomes stale for later readiness.

A fresh exact-release helper proof remains mandatory before any future rotation-readiness ceremony.

No helper-proof refresh is required merely to create the offline decision-backed authority artifact.

## Authority boundary

This seal does not authorize:

- automatic decision-backed bridge execution;
- candidate file authoring/staging;
- transition binding;
- rotation-readiness execution;
- production manifest rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_DECISION_BACKED_CANDIDATE_AUTHORITY=SEALED_AUTHORITY_EVIDENCE_ONLY`

`DECISION_BACKED_CANDIDATE_AUTHORITY_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_DECISION_BACKED_AUTHORITY_EXECUTION=DISABLED`

`CANDIDATE_FILE_AUTHORING=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
