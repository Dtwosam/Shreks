# G1C V2 Candidate-Value Preflight Transactional Authority Stability — Release Seal

**Date:** 2026-09-23  
**Transactional preflight implementation main SHA:** `cb38fc516d49cf9cc1f622c261e371dfec9ba487`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF HARDENED PREFLIGHT TOOL PRESENCE ONLY; AUTOMATIC PREFLIGHT EXECUTION DISABLED; CANDIDATE/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the hardened G1C V2 candidate-value preflight implementation so its final evidence receipt can be published only while the complete non-manifest V2 authority remains authenticated and unchanged.

The preflight already held the source runtime manifest and authenticated review-backed sizing proposal stable through candidate assessment.

This hardening extends the same transactional boundary to:

- the frozen FL9 V2 cohort;
- the preserved V2 host-request authority;
- the request-bound hydration policy and its policy fields.

The hardened path:

1. authenticates the exact non-manifest V2 request authority before candidate derivation;
2. derives the hypothetical candidate without persisting it as runtime state;
3. delegates compatibility to the existing canonical candidate assessment;
4. requires the assessment's returned authority document to equal the initial authenticated authority exactly;
5. rechecks source and proposal stability;
6. re-authenticates the cohort/request/hydration authority immediately before final publication;
7. requires the final authenticated authority object to equal the initial one exactly;
8. publishes the write-once mode-`0600` evidence receipt only after all checks pass.

If request/cohort/hydration authority changes or can no longer authenticate, the command fails closed and the requested final preflight destination remains absent.

This seal transports and verifies that hardened implementation only.

It does not execute candidate-value preflight.

It does not approve candidate economics, grant candidate authority, author/stage a candidate, bind a transition, run readiness/rotation, score/model-fit, promote PAPER, access wallets, sign/submit, or enable LIVE.

## Current production state before this seal

The active immutable protected PAPER release remains:

`shreks-bbb7663ccedbbc9ecb1aa4508182f9900f595147`

Protected PAPER deploy/verify run:

`35852263653`

completed successfully.

That production verification proved exact-release presence of:

```text
g1c_v2_review_backed_entry_sizing=present
g1c_v2_candidate_value_preflight=present
g1c_v2_candidate_value_decision=present
g1c_v2_decision_backed_candidate_authority=present
g1c_v2_decision_backed_candidate_authoring=present
g1c_v2_decision_backed_transition_binding=present
g1c_v2_decision_backed_rotation_readiness=present
g1c_v2_decision_backed_rotation_plan=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

That release contains the earlier candidate-value preflight implementation, not the transactional authority-stability hardening merged at `cb38fc51...`.

Repository authority still does not record a completed production review-backed sizing proposal, candidate-value preflight, candidate-value decision, schema-v2 candidate-authority artifact, runtime-manifest V2 candidate, or decision-backed transition binding.

## Failure mode closed by this seal

Before this hardening, the preflight:

- authenticated the V2 request/cohort/hydration authority during compatibility assessment;
- rechecked source/proposal stability afterward;
- then published the final receipt.

It did not re-authenticate the non-manifest authority before publication.

Therefore a request-authority mutation after candidate compatibility assessment could leave a final receipt based on an earlier authority snapshot even though the current authority path had changed.

The hardened implementation prevents that failed-ceremony residue.

## TDD proof

Intentional RED head:

`b3faa8d000073dd174621830604be025892187a2`

RED PR #452 CI:

`35856474542`

Result:

- Python: exactly 1 failed, 3663 passed, 2 known warnings;
- the sole failure proved that mutating the authenticated V2 request immediately after compatibility assessment did not raise and still allowed final receipt publication;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN implementation head:

`833d910beee79242040dca5743b7a129ecdcab92`

GREEN PR #453 CI:

`35856856806`

Result:

- Python: SUCCESS;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged implementation main:

`cb38fc516d49cf9cc1f622c261e371dfec9ba487`

Merged-main CI:

`35857208529`

Result: SUCCESS across all four canonical gates.

Because the implementation merge was not a `seal:` commit:

- release workflow `35857479934`: SKIPPED;
- deploy workflow `35857484698`: SKIPPED.

Therefore production still contains the pre-hardening candidate-value preflight implementation until this seal succeeds.

## Existing production-presence verifier

The repository already verifies without executing preflight that:

- `shreks-g1c-v2-candidate-value-preflight` is a regular non-symlink executable;
- the resolved script belongs to the exact expected immutable release;
- `shreks_brain.g1c_v2_candidate_value_preflight` imports through the exact release-local Python environment;
- the module resolves inside that same immutable release.

Expected evidence after this seal includes:

```text
g1c_v2_candidate_value_preflight=present
g1c_v2_candidate_value_preflight_path=<exact-release-local-path>
g1c_v2_candidate_value_preflight_module=<exact-release-local-module-path>
```

The production verifier must continue to avoid invoking candidate-value preflight.

Because immutable release activation replaces the release-local Python tree atomically, exact-release module presence proves that the transactional authority-stability implementation is the implementation available to a later trusted-administrator ceremony.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the hardened candidate-value preflight implementation in release-local Python;
3. publish the immutable GitHub release;
4. validate and download the exact immutable release assets through the existing fail-closed API-ID transport;
5. locally verify the release bundle before host contact;
6. deploy that exact release through the protected PAPER release manager;
7. activate the ordinary protected PAPER runtime;
8. verify exact release identity, service/process health, exact-release candidate-chain tool presence/provenance, manifest-manager state, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute review-backed sizing;
- execute candidate-value preflight;
- approve or replace a candidate value;
- execute candidate-value decision;
- execute candidate-authority binding;
- author or stage a runtime-manifest candidate;
- bind a transition;
- run rotation readiness or rotation planning;
- rotate the protected manifest;
- score or model-fit;
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

A successful explicit preflight still records:

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

This seal does not authorize automatic preflight execution or any downstream production authority.

## Promotion boundary

`G1C_V2_CANDIDATE_VALUE_PREFLIGHT=SEALED_TRANSACTIONAL_AUTHORITY_STABILITY`

`PREFLIGHT_FINAL_PUBLISH=AFTER_SOURCE_PROPOSAL_AND_V2_AUTHORITY_STABILITY_ONLY`

`AUTOMATIC_CANDIDATE_VALUE_PREFLIGHT=DISABLED`

`CANDIDATE_VALUE_AUTHORITY=NOT_GRANTED`

`CANDIDATE_AUTHORING_AUTHORITY=NOT_GRANTED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
