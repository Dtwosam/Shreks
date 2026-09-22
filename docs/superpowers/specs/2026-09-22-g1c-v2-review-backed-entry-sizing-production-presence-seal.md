# G1C V2 Review-Backed Entry Sizing Production Presence — Release Seal

**Date:** 2026-09-22  
**Review-backed sizing implementation main SHA:** `d070837ea49739b3a24cc65574ce04e5f01a2754`  
**Production-presence implementation main SHA:** `d1ca376d31968bda99c5c01341b2952ff02c1e35`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF REVIEW-BACKED SIZING TOOL PRESENCE ONLY; AUTOMATIC REVIEW/SIZING EXECUTION DISABLED; PRODUCTION CANDIDATE VALUES NOT AUTHORIZED; CANDIDATE AUTHORITY NOT AUTHORIZED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED

## Purpose

Seal the provenance-safe bridge from the canonical multi-reference G1C v2 quote-valuation review to the existing evidence-only entry-sizing proposal, together with read-only exact-release production-presence proof for that bridge.

The bridge exists because feeding the multi-reference review through the legacy single-reference sizing path would falsely record:

`quote_evidence_authority=EXPLICIT_REFERENCE_ONLY`

The sealed review-backed path authenticates the canonical review artifact directly and records:

`quote_evidence_authority=MULTI_REFERENCE_REVIEW`

This seal deploys tool presence only.

It does not execute the review-backed sizing command.

## Current production boundary before this seal

The currently published and successfully deployed sealed release is:

`4327a182f381b91f41f87cf32522c1e9e962011b`

That release contains the previously sealed quote-reference, entry-sizing, and multi-reference quote-review evidence tooling, but predates the review-backed sizing bridge.

The protected trusted-admin review has already produced one canonical evidence-only multi-reference review over twelve exact references.

Its known review summary is:

```text
reference_count=12
quote_mint=So11111111111111111111111111111111111111112
median_quote_asset_usd_per_token=118.17810687350131
quote_evidence_observed_at_unix_ms=1790028815338
status=REVIEW_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The exact 64-hex review fingerprint must be read from and authenticated against the canonical review artifact itself when the later sizing command is run. This seal does not transcribe a shortened display form into authority.

No production candidate value has been approved.

## Review-backed sizing implementation

The implementation was merged to main as:

`d070837ea49739b3a24cc65574ce04e5f01a2754`

CLI:

`shreks-g1c-v2-review-backed-entry-sizing`

Module:

`shreks_brain.g1c_v2_review_backed_entry_sizing`

The bridge:

1. accepts one explicit source runtime-manifest path;
2. accepts one explicit canonical quote-valuation review path;
3. accepts explicit target quote decimals;
4. authenticates the review through the existing review decoder;
5. uses only the review quote mint, exact median quote USD-per-token, review fingerprint, and conservative evidence timestamp;
6. invokes the existing sizing calculation under `MULTI_REFERENCE_REVIEW`;
7. writes the existing `shreks.g1c_v2_entry_sizing_proposal` schema;
8. preserves the legacy explicit-reference path as `EXPLICIT_REFERENCE_ONLY`;
9. re-reads the review and fails if it changes during derivation;
10. writes no candidate, runtime manifest, transition binding, readiness artifact, or rotation artifact.

The bridge never reads SQLite and never selects a market row.

## Sizing authority boundary

A successful review-backed proposal always remains:

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

The review median is input evidence, not an approved production candidate value.

The proposed raw amount is evidence, not an approved production candidate value.

## TDD and implementation proof

### Review-backed sizing

Intentional RED PR #388 head:

`c116553f59400b81a2165eda7a64f6089e4f3099`

Final GREEN implementation head:

`bd822ad382c847a3d4a6d7a7f2ddec0939a3b48c`

Push CI:

`35672527333`

Result: SUCCESS across all four canonical gates.

Independent PR CI:

`35672550485`

Result: SUCCESS across all four canonical gates.

Merged implementation main:

`d070837ea49739b3a24cc65574ce04e5f01a2754`

Merged-main CI:

`35673528052`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

### Production-presence proof

Intentional RED PR #390 head:

`d090aa0eaa0d47a4f03b08165e9a8e5e5815e210`

RED CI:

`35673747030`

Result:

- Python: exactly 1 failed, 3597 passed, 2 known warnings;
- the only failure was the intentionally absent review-backed sizing production-presence contract;
- Repository safety, Rust, and ARM64 succeeded.

Final GREEN implementation head:

`ddc2727d30aab6c1f513142aded98c1380d45e83`

Push CI:

`35673917707`

Result: SUCCESS across all four canonical gates.

Independent PR CI:

`35673925128`

Result: SUCCESS across all four canonical gates.

Merged production-presence main:

`d1ca376d31968bda99c5c01341b2952ff02c1e35`

Merged-main CI:

`35674106204`

Result: SUCCESS across all four canonical gates.

Both implementation commits are `feat:`/merge commits rather than a sealed main commit, so automatic production release/deploy remains unexercised for these changes.

## Production-presence verifier

After this seal deploys, the ordinary protected production verifier must prove without executing sizing:

- the release-local `shreks-g1c-v2-review-backed-entry-sizing` console script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- the `shreks_brain.g1c_v2_review_backed_entry_sizing` module imports through the exact release-local Python;
- the module path resolves inside the same exact release.

Expected evidence includes:

```text
g1c_v2_review_backed_entry_sizing=present
g1c_v2_review_backed_entry_sizing_path=<exact-release-local-path>
g1c_v2_review_backed_entry_sizing_module=<exact-release-local-module-path>
```

The verifier must not invoke the sizing CLI.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the review-backed sizing CLI/module in the release-local Python environment;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, restart state, existing trusted-admin tool provenance, quote-review provenance, review-backed sizing presence/provenance, helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute the quote-valuation review;
- execute review-backed entry sizing;
- read the protected review artifact on behalf of sizing;
- read observer SQLite on behalf of sizing;
- capture new quote references;
- choose or approve a quote value;
- choose or approve a raw entry amount;
- invoke candidate authority;
- author/stage a candidate;
- create a transition binding;
- execute rotation readiness;
- rotate the runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Post-deploy trusted-admin sizing

Only after production verification proves the review-backed sizing CLI/module physically belong to the exact active release may a trusted administrator supply the exact canonical review artifact to the release-local review-backed sizing CLI.

The runbook command requires explicit:

- source runtime-manifest path;
- review artifact path;
- target quote decimals;
- new non-existent destination.

The tool authenticates the review artifact directly.

The operator must not manually copy the review median/fingerprint/timestamp into the legacy explicit-reference CLI.

The resulting proposal remains evidence only.

## Candidate-value decision boundary

After reviewing the complete proposal, a later separate explicit production candidate-value decision may:

- accept the proposed raw entry amount;
- reject it; or
- replace it with a separately justified reviewed value.

Only after that separate decision may candidate authority be invoked with one explicit reviewed input set.

This seal does not define that decision artifact or exercise candidate authority.

## Existing helper and readiness boundary

The root manifest-manager helper remains:

`/usr/local/sbin/shreks-paper-manifest-manager`

Automatic deployment must not install, replace, chmod, chown, or execute it.

Any helper installation proof is release-bound.

If this seal deploys a new release SHA, any helper proof bound to an earlier release becomes stale for later rotation-readiness. A fresh exact-release helper proof remains mandatory before any later readiness or rotation ceremony.

No helper-proof refresh is required merely to create the offline review-backed sizing proposal.

## Rotation, scoring, promotion, and LIVE boundary

This seal does not authorize:

- production candidate-value approval;
- candidate-authority invocation;
- candidate authoring/staging;
- transition binding;
- rotation-readiness execution;
- production manifest rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_REVIEW_BACKED_ENTRY_SIZING=SEALED_EVIDENCE_ONLY`

`REVIEW_BACKED_ENTRY_SIZING_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_QUOTE_VALUATION_REVIEW=DISABLED`

`AUTOMATIC_REVIEW_BACKED_ENTRY_SIZING=DISABLED`

`PRODUCTION_CANDIDATE_VALUES=NOT_AUTHORIZED`

`AUTOMATIC_CANDIDATE_AUTHORITY_EXECUTION=DISABLED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
