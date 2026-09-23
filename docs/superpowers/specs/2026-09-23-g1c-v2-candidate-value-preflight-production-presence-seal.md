# G1C V2 Candidate-Value Compatibility Preflight Production Presence — Release Seal

**Date:** 2026-09-23  
**Candidate-value preflight implementation main SHA:** `1564b43e9bdc5358557009f6a97e23a96d0868d4`  
**Production-presence implementation main SHA:** `0ad839d5acc798d2feb1d6385946c4eef45b9298`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF PREFLIGHT TOOL PRESENCE ONLY; AUTOMATIC PREFLIGHT EXECUTION DISABLED; CANDIDATE-VALUE APPROVAL/AUTHORING/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the G1C V2 candidate-value compatibility preflight together with its exact-release production-presence proof.

The preflight authenticates one review-backed sizing proposal, derives the exact hypothetical new-run candidate from that proposal plus explicit future run identity/time, and requires the existing canonical FL9 V2 candidate assessment to return exactly `COMPATIBLE`.

It writes one evidence-only provenance receipt.

It does not approve the proposed value.

It does not persist or stage a runtime-manifest candidate.

This seal exists only to transport and verify the preflight CLI/module in the protected PAPER production release.

It does not authorize automatic preflight execution, candidate-value approval, candidate authority, candidate authoring, transition binding, manifest rotation, V2 scoring/model fitting, champion publication, PAPER promotion, wallet access, signing/submission, or LIVE.

## Current production state before this seal

The latest immutable GitHub release is:

`shreks-cd16d574390be8e292ba40ced9531b81bf7cb51b`

Its protected PAPER deploy/verify run:

`35791753270`

completed successfully.

Production verification proved:

```text
current_release=/opt/shreks/releases/cd16d574390be8e292ba40ced9531b81bf7cb51b
expected_release=/opt/shreks/releases/cd16d574390be8e292ba40ced9531b81bf7cb51b
fl9_v2_discovery_backed_request_prepare=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

The candidate-value compatibility preflight implementation merge:

`1564b43e9bdc5358557009f6a97e23a96d0868d4`

passed merged-main CI `35800883783`.

Its release workflow `35801080267` and deploy workflow `35801095194` skipped by design because the main commit subject was not `seal:`.

The production-presence implementation merge:

`0ad839d5acc798d2feb1d6385946c4eef45b9298`

passed merged-main CI `35801896017`.

Its release workflow `35802076415` and deploy workflow `35802079154` also skipped by design because the main commit subject was not `seal:`.

Therefore production does not yet contain the candidate-value compatibility preflight CLI/module.

No production preflight has been automatically executed.

No candidate value has been automatically approved.

No runtime-manifest candidate has been automatically authored or staged.

No manifest rotation or V2 scoring/model fitting has been automatically executed.

## Candidate-value compatibility preflight implementation

Implementation main SHA:

`1564b43e9bdc5358557009f6a97e23a96d0868d4`

Final GREEN implementation head:

`88926b52fbf0599a8d212c69a226d38b103340b6`

CLI:

`shreks-g1c-v2-candidate-value-preflight`

Module:

`shreks_brain.g1c_v2_candidate_value_preflight`

The preflight accepts only:

- canonical v1 source runtime manifest;
- authenticated `MULTI_REFERENCE_REVIEW` sizing proposal;
- frozen FL9 V2 cohort;
- preserved authenticated V2 host-request authority;
- explicit future `paper_run_id`;
- explicit future `start_at_unix_ms`;
- one new non-existing private receipt destination.

It does not accept operator-supplied raw target quote mint, quote decimals, quote USD value, or entry-input amount.

Those candidate economics come only from the authenticated review-backed sizing proposal.

The preflight:

1. authenticates source and proposal;
2. requires the proposal to remain evidence-only;
3. verifies source/proposal provenance equality;
4. derives the exact hypothetical candidate;
5. writes that candidate only to a private temporary file;
6. delegates compatibility to the existing canonical FL9 V2 candidate assessment;
7. requires exact `COMPATIBLE`;
8. removes the temporary candidate;
9. rechecks source/proposal stability;
10. writes one canonical mode-`0600`, write-once preflight receipt.

A successful receipt remains:

```text
status=READY_FOR_EXPLICIT_CANDIDATE_VALUE_DECISION
candidate_compatibility=COMPATIBLE
preflight_authority=EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## TDD and implementation proof

### Candidate-value compatibility preflight

Intentional RED head:

`754d550d9e0f78a48a1f49a22a092ef76ad036ea`

RED CI:

`35800156864`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_candidate_value_preflight` did not yet exist;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

The first implementation run exposed an intentional safety distinction rather than accepting inconsistent evidence: the older synthetic candidate-authority test fixture used quote mint `quote-sol`, while the review-backed evidence fixture used canonical WSOL. The implementation correctly refused to call that combination compatible.

The fixture was corrected so cohort/request/review/candidate identities all represented the same WSOL authority. No compatibility rule was weakened.

Final GREEN implementation head:

`88926b52fbf0599a8d212c69a226d38b103340b6`

PR #434 CI:

`35800648543`

Result:

- Python: 3656 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged implementation main:

`1564b43e9bdc5358557009f6a97e23a96d0868d4`

Merged-main CI:

`35800883783`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED head:

`cc84b13b81c22afb6a724832f9fcb3a59a56eb9d`

RED CI:

`35801419209`

Result:

- Python: exactly 1 failed, 3656 passed, 2 known warnings;
- the only failure was the intentionally absent `CANDIDATE_VALUE_PREFLIGHT` production-presence surface;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN production-presence head:

`5e155c577ac757ecccac102e779147c4ff85c9bf`

PR #435 CI:

`35801647572`

Result:

- Python: 3657 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged production-presence main:

`0ad839d5acc798d2feb1d6385946c4eef45b9298`

Merged-main CI:

`35801896017`

Result: SUCCESS across all four canonical gates.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing the preflight command:

- `shreks-g1c-v2-candidate-value-preflight` exists in release-local Python;
- the script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_candidate_value_preflight` imports through exact release-local Python;
- the module path resolves inside that same expected release.

Expected evidence includes:

```text
g1c_v2_candidate_value_preflight=present
g1c_v2_candidate_value_preflight_path=<exact-release-local-path>
g1c_v2_candidate_value_preflight_module=<exact-release-local-module-path>
```

The production verifier must not invoke the preflight command.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the candidate-value preflight CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, exact-release preflight tool presence/provenance, existing trusted-admin tooling, request-preparation presence, manifest-manager status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute the candidate-value preflight;
- approve a candidate value;
- create a candidate-value decision;
- bind candidate-authoring authority;
- persist or stage a runtime-manifest candidate;
- create a transition binding;
- execute rotation readiness;
- rotate the protected manifest;
- execute V2 scoring or model fitting;
- publish champion evidence;
- promote PAPER;
- change risk intent;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin preflight boundary

Only after production verification proves the preflight CLI/module exact-release-local may a trusted administrator run the documented root-private preflight ceremony.

That ceremony may write only one evidence-only candidate-value preflight receipt.

A successful receipt may prove that the exact proposal-derived hypothetical candidate is compatible with the frozen V2 authority, but it still records:

`candidate_value_authority=NOT_GRANTED`

A separate explicit candidate-value decision remains mandatory.

Preflight receipt existence does not grant:

- candidate-value approval;
- candidate authoring;
- transition binding;
- rotation;
- scoring;
- PAPER promotion;
- LIVE.

## Authority boundary

This seal does not authorize:

- automatic preflight execution;
- automatic or implicit candidate-value approval;
- candidate-authority execution merely because preflight succeeded;
- persistent candidate authoring/staging;
- transition binding;
- manifest rotation;
- V2 scoring/model fitting;
- champion evidence publication;
- PAPER promotion;
- risk intent;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_CANDIDATE_VALUE_PREFLIGHT=SEALED_TOOL_PRESENCE_ONLY`

`CANDIDATE_VALUE_PREFLIGHT_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_CANDIDATE_VALUE_PREFLIGHT=DISABLED`

`PREFLIGHT_AUTHORITY=EVIDENCE_ONLY_WHEN_EXPLICITLY_INVOKED`

`CANDIDATE_VALUE_AUTHORITY=NOT_GRANTED`

`CANDIDATE_AUTHORING_AUTHORITY=NOT_GRANTED`

`ROTATION_AUTHORITY=NOT_GRANTED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
