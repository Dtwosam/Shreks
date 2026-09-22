# G1C V2 Decision-Backed Candidate Authoring Production Presence — Release Seal

**Date:** 2026-09-22  
**Exact candidate-authoring implementation main SHA:** `9db4980c82fd373aa17de4a15534308b2533ca6a`  
**Production-presence implementation main SHA:** `40f10609ec5ac09afa1a506127eacbc9ec85bb0c`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF AUTHORING TOOL PRESENCE ONLY; AUTOMATIC AUTHORING EXECUTION DISABLED; CANDIDATE GENERATION REMAINS TRUSTED-ADMIN ONLY; TRANSITION/READINESS/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the exact decision-backed G1C v2 candidate-authoring tool together with read-only exact-release production-presence proof.

The author closes one provenance gap only: once a reviewed decision-backed candidate authority commits an exact canonical candidate identity, later materialization must not reintroduce raw paper-run, timestamp, quote, entry-amount, cohort, request, or decision inputs.

The author authenticates the existing source manifest and decision-backed authority, derives the candidate only from values already committed by that authority, requires the exact candidate manifest SHA and runtime-manifest fingerprint to match the authority, re-checks source/authority stability, and writes one canonical private candidate file.

This seal deploys tool presence only.

It does not execute candidate authoring.

## Current production state before this seal

The latest immutable GitHub release remains:

`shreks-74098267320f9a1b36a8c80f5a7ff973c6b35f48`

The non-seal candidate-authoring implementation merge:

`9db4980c82fd373aa17de4a15534308b2533ca6a`

completed merged-main CI successfully, after which release/deploy workflows skipped by design because the main commit subject was not `seal:`.

The production-presence implementation merge:

`40f10609ec5ac09afa1a506127eacbc9ec85bb0c`

also completed merged-main CI successfully. Its release workflow `35723270894` and deploy workflow `35723275769` skipped by design because it is not a seal commit.

Therefore production has not yet received the exact candidate-authoring CLI/module.

No decision-backed candidate file has been automatically authored or staged.

## Exact candidate-authoring implementation

Implementation main SHA:

`9db4980c82fd373aa17de4a15534308b2533ca6a`

Implementation GREEN head:

`27502c74019b68f6ccdd2a6949ce8d20e9f91ee4`

CLI:

`shreks-g1c-v2-decision-backed-candidate-author`

Module:

`shreks_brain.g1c_v2_decision_backed_candidate_authoring`

Inputs are limited to:

- canonical v1 source runtime manifest;
- authenticated decision-backed candidate authority;
- new non-existent destination.

There are no raw CLI inputs for:

- paper-run id;
- start timestamp;
- quote mint;
- quote decimals;
- entry input amount;
- cohort;
- request authority;
- candidate-value decision.

The author authenticates the source and authority and requires their committed source identity to match.

It derives the canonical candidate through the existing author using only authority-bound:

- candidate paper-run id;
- candidate start timestamp;
- candidate quote asset mint;
- candidate quote asset decimals;
- candidate entry input amount.

Before persistence it requires:

- exact canonical encoded candidate SHA-256 equals the authority's `candidate_manifest_sha256`;
- candidate runtime-manifest fingerprint equals the authority's `candidate_runtime_manifest_fingerprint_sha256`;
- derived candidate identity matches the authority-bound run/time/quote/amount fields;
- source and authority bytes remain stable across the operation.

It writes one new canonical candidate file with private mode `0600` and fails closed if the destination already exists.

The implementation does not create a transition binding, execute readiness, install/activate/rotate a runtime manifest, score/model-fit, promote PAPER, sign, submit, or enable LIVE.

## TDD and implementation proof

### Exact candidate authoring

Intentional RED PR #404 head:

`26ee9d68d7ffa01e18043b454af7f8f503403dbd`

RED CI:

`35716282870`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_decision_backed_candidate_authoring` did not yet exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN implementation head:

`27502c74019b68f6ccdd2a6949ce8d20e9f91ee4`

Push CI:

`35716598176`

Independent PR CI:

`35716604159`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`9db4980c82fd373aa17de4a15534308b2533ca6a`

Merged-main CI:

`35716883110`

Result: SUCCESS across all four canonical gates.

Its release/deploy workflows skipped because the merge commit was not a `seal:` commit.

### Production-presence proof

Intentional RED PR #406 head:

`862e7b14d06707006eaaf3135b168e27a97f2d53`

Executed RED CI:

`35719473556`

Result:

- Python: exactly 1 failed, 3619 passed, 2 known warnings;
- the only failure was the intentionally absent decision-backed candidate-authoring production-presence contract;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN production-presence head:

`eb3be57d83f5313307277472830249312b19a6ef`

Push CI:

`35719613060`

Independent PR CI:

`35719632475`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged production-presence main:

`40f10609ec5ac09afa1a506127eacbc9ec85bb0c`

Merged-main CI:

`35723041186`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing the author:

- the release-local `shreks-g1c-v2-decision-backed-candidate-author` script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_decision_backed_candidate_authoring` imports through exact release-local Python;
- the module path resolves inside that same release.

Expected evidence includes:

```text
g1c_v2_decision_backed_candidate_authoring=present
g1c_v2_decision_backed_candidate_authoring_path=<exact-release-local-path>
g1c_v2_decision_backed_candidate_authoring_module=<exact-release-local-module-path>
```

The verifier must not invoke the author.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the exact decision-backed candidate-authoring CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, existing trusted-admin tooling, candidate-authoring presence/provenance, helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute review-backed sizing;
- execute the candidate-value decision;
- execute the decision-backed candidate-authority bridge;
- execute the candidate author;
- write or stage a runtime-manifest candidate;
- create a transition binding;
- execute readiness;
- install, activate, or rotate a runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin authoring boundary

Only after production verification proves the author exact-release-local may a trusted administrator use the documented authoring ceremony against:

- the protected canonical source runtime manifest;
- one exact reviewed decision-backed candidate authority artifact;
- one new root-private destination.

The trusted-admin command has no raw paper-run, timestamp, quote, entry-amount, cohort, request, or candidate-value-decision arguments.

A successful candidate file must reproduce the exact candidate manifest SHA/fingerprint already committed by the authority.

The candidate is an offline artifact only.

Do not run transition binding from this candidate alone. A later separate transition-binding boundary must authenticate the exact candidate and the required authority/provenance chain before any readiness or production mutation can be considered.

## Helper/readiness boundary

Deployment of this seal changes the current release SHA.

Any helper installation proof bound to an earlier release becomes stale for later readiness.

A fresh exact-release helper proof remains mandatory before any future rotation-readiness ceremony.

No helper-proof refresh is required merely to materialize and review the offline exact candidate artifact.

## Authority boundary

This seal does not authorize:

- automatic candidate authoring;
- automatic candidate staging;
- transition binding;
- rotation-readiness execution;
- production manifest installation/activation/rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_DECISION_BACKED_CANDIDATE_AUTHORING=SEALED_TOOL_PRESENCE_ONLY`

`DECISION_BACKED_CANDIDATE_AUTHORING_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_CANDIDATE_AUTHORING_EXECUTION=DISABLED`

`CANDIDATE_STAGING=NOT_AUTHORIZED`

`TRANSITION_BINDING=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
