# G1C V2 Review-Backed Entry Sizing Transactional Publish — Release Seal

**Date:** 2026-09-23  
**Transactional sizing implementation main SHA:** `13c8d23eb91c51b6d65708e0cb3574f5a8f26cc5`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF TRANSACTIONAL REVIEW-BACKED SIZING TOOL PRESENCE ONLY; AUTOMATIC SIZING EXECUTION DISABLED; CANDIDATE/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the hardened G1C V2 review-backed entry-sizing implementation that publishes its final evidence artifact only after both protected inputs remain stable through derivation.

The hardened path:

1. stably snapshots the canonical source runtime manifest;
2. stably snapshots and authenticates the canonical multi-reference quote-valuation review;
3. derives the sizing proposal only to private temporary storage;
4. lets the existing canonical sizing implementation authenticate and recheck the source during derivation;
5. re-reads both source and review after derivation;
6. requires both byte sequences to remain identical to their initial snapshots;
7. publishes the requested final proposal only after those checks pass;
8. uses the existing write-once mode-`0600` writer and canonical decoder for final publication;
9. removes temporary material automatically.

If either source or review changes before final publication, the command fails closed and the requested final proposal destination remains absent.

This seal transports and verifies that hardened implementation only.

It does not execute sizing.

It does not read the protected review on behalf of sizing.

It does not choose or approve candidate economics.

It does not grant candidate authority, author/stage a candidate, bind a transition, run readiness/rotation, score/model-fit, promote PAPER, access wallets, sign/submit, or enable LIVE.

## Current production state before this seal

The active immutable production release is:

`shreks-23f79a38207894e694f7c9d077a89a0cf795e6e3`

Protected PAPER deploy/verify run:

`35842040979`

completed successfully.

Production verification proved:

```text
current_release=/opt/shreks/releases/23f79a38207894e694f7c9d077a89a0cf795e6e3
expected_release=/opt/shreks/releases/23f79a38207894e694f7c9d077a89a0cf795e6e3
g1c_v2_review_backed_entry_sizing=present
g1c_v2_review_backed_entry_sizing_path=/opt/shreks/releases/23f79a38207894e694f7c9d077a89a0cf795e6e3/.venv/bin/shreks-g1c-v2-review-backed-entry-sizing
g1c_v2_review_backed_entry_sizing_module=/opt/shreks/releases/23f79a38207894e694f7c9d077a89a0cf795e6e3/.venv/lib/python3.12/site-packages/shreks_brain/g1c_v2_review_backed_entry_sizing.py
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

That release contains the earlier review-backed sizing implementation, but not the transactional publication hardening merged at `13c8d23e...`.

No production review-backed sizing proposal is recorded in repository authority.

No candidate-value preflight, candidate-value decision, schema-v2 candidate-authority artifact, runtime-manifest V2 candidate, transition binding, readiness artifact, or rotation has been produced by this seal.

## Transactional hardening

Implementation main SHA:

`13c8d23eb91c51b6d65708e0cb3574f5a8f26cc5`

Final GREEN implementation head:

`e4acb359631e8f44613b250bcfbbc7259f23159d`

CLI remains:

`shreks-g1c-v2-review-backed-entry-sizing`

Module remains:

`shreks_brain.g1c_v2_review_backed_entry_sizing`

The existing proposal schema remains:

`shreks.g1c_v2_entry_sizing_proposal`

No proposal schema or authority level is widened.

## Failure mode closed by this seal

Before this hardening, the wrapper delegated sizing directly to the requested final destination and only then re-read the review.

That allowed this failed-ceremony residue:

1. final proposal written;
2. review mutation detected afterward;
3. command returns failure;
4. final proposal artifact remains on disk despite the failed provenance check.

The wrapper also did not hold the source runtime manifest stable from the beginning of the review-backed ceremony through final publication.

The transactional path closes both conditions by deriving privately first and publishing only after both final stability checks pass.

## TDD proof

Intentional RED head:

`19eefcab39512bbddb9341a7efd5b4dddb0746dc`

RED PR CI:

`35849626333`

Result:

- Python: exactly 2 failed, 3661 passed, 2 known warnings;
- failure 1 proved a changed review could leave the requested final proposal behind;
- failure 2 proved a source runtime manifest changed immediately after delegated derivation was not detected by the wrapper;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN head:

`e4acb359631e8f44613b250bcfbbc7259f23159d`

GREEN PR CI:

`35849927481`

Result:

- Python: 3663 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged implementation main:

`13c8d23eb91c51b6d65708e0cb3574f5a8f26cc5`

Merged-main CI:

`35850203285`

Result:

- Python: 3663 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Because the implementation merge was not a `seal:` commit:

- release workflow `35850505890`: SKIPPED;
- deploy workflow `35850511355`: SKIPPED.

Therefore production still contains the pre-transactional implementation until this seal succeeds.

## Existing production-presence verifier

The repository already has exact-release production-presence verification for:

`shreks-g1c-v2-review-backed-entry-sizing`

The verifier proves without invoking the sizing command that:

- the release-local script is a regular non-symlink executable;
- the resolved script path belongs to the exact expected immutable release;
- the review-backed sizing module imports through exact release-local Python;
- the module resolves inside that same release.

Expected evidence after this seal includes:

```text
g1c_v2_review_backed_entry_sizing=present
g1c_v2_review_backed_entry_sizing_path=<exact-release-local-path>
g1c_v2_review_backed_entry_sizing_module=<exact-release-local-module-path>
```

The ordinary verifier must continue to avoid executing review-backed sizing.

Because the module is replaced atomically with the immutable release, exact-release presence proves the transactional implementation is the one available to trusted administrators.

## Trusted-admin sizing ceremony after deploy

The trusted-admin runbook remains explicit and evidence-only.

It uses:

```text
SOURCE_MANIFEST=/etc/shreks/paper-campaign.json
REVIEW=<exact-authenticated-quote-valuation-review.json>
TARGET_QUOTE_DECIMALS=9
PROPOSAL=<new non-existing private destination>
```

The operator must authenticate/use the canonical protected review artifact itself.

The exact review fingerprint is not to be transcribed from display text.

The runbook requires the proposal destination to be absent before execution.

A successful proposal remains:

```text
status=PROPOSAL_EVIDENCE_ONLY
quote_evidence_authority=MULTI_REFERENCE_REVIEW
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The proposed amount is evidence, not an approved production candidate value.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the transactional review-backed sizing implementation in release-local Python;
3. publish the immutable GitHub release;
4. validate/download the exact immutable release assets through the existing fail-closed API-ID transport;
5. locally verify the release bundle before host contact;
6. deploy that exact release through the protected PAPER release manager;
7. activate the ordinary protected PAPER runtime;
8. verify exact release identity, service/process health, exact-release review-backed sizing presence/provenance, existing candidate-chain tool presence, manifest-manager state, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute quote-valuation review;
- execute review-backed sizing;
- access the protected review artifact on behalf of sizing;
- approve a raw entry amount;
- execute candidate-value preflight;
- execute candidate-value decision;
- execute candidate-authority binding;
- author/stage a runtime-manifest candidate;
- bind a transition;
- run rotation readiness;
- rotate the protected manifest;
- score/model-fit;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Helper/readiness boundary

Deployment of this seal changes the active release SHA.

Any helper installation-proof artifact bound to an earlier release SHA is stale for later rotation-readiness.

A fresh exact-release helper proof remains mandatory before any future readiness/rotation ceremony.

No helper-proof refresh is required merely to create/review the offline sizing proposal, preflight, decision, authority, candidate, or transition artifacts.

## Authority boundary

This seal does not authorize:

- automatic review-backed sizing;
- candidate-value approval;
- candidate-authority execution;
- candidate authoring/staging;
- transition binding;
- readiness/rotation;
- V2 scoring/model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_REVIEW_BACKED_ENTRY_SIZING=SEALED_TRANSACTIONAL_EVIDENCE_ONLY`

`REVIEW_BACKED_SIZING_FINAL_PUBLISH=AFTER_SOURCE_AND_REVIEW_STABILITY_ONLY`

`AUTOMATIC_REVIEW_BACKED_ENTRY_SIZING=DISABLED`

`PRODUCTION_CANDIDATE_VALUES=NOT_AUTHORIZED`

`CANDIDATE_AUTHORING_AUTHORITY=NOT_GRANTED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
