# G1C V2 Decision-Backed Transition Binding Production Presence — Release Seal

**Date:** 2026-09-22  
**Decision-backed transition implementation main SHA:** `3bbdcd6eb30e0c39bde9b3f592591fb98f27d5f1`  
**Production-presence implementation main SHA:** `3d66ccfd1ddec0c3c9de49b72d84809299c5ef17`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF TRANSITION-BINDING TOOL PRESENCE ONLY; AUTOMATIC TRANSITION EXECUTION DISABLED; READINESS/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the decision-backed G1C v2 transition-binding bridge together with read-only exact-release production-presence proof.

The bridge closes one provenance gap only: the standard transition binding must be derived from an exact candidate whose source/candidate/cohort/request provenance is already committed by an authenticated decision-backed candidate authority.

The bridge authenticates the source manifest, exact candidate, and decision-backed authority; delegates compatibility assessment to the existing canonical transition binder using the frozen cohort directory and authenticated request authority; requires every overlapping provenance field to match the decision-backed authority; rechecks input stability; and then persists only the standard transition-binding v1 bytes.

This seal deploys tool presence only.

It does not execute transition binding.

## Current production state before this seal

The latest immutable GitHub release remains:

`shreks-0dd909fd1839db4e3389fad115ba3bfb21bfd040`

That release already contains and proves exact-release presence for the decision-backed candidate author.

The decision-backed transition implementation merge:

`3bbdcd6eb30e0c39bde9b3f592591fb98f27d5f1`

completed merged-main CI successfully. Its release workflow `35726375317` and deploy workflow `35726379622` skipped by design because the main commit subject was not `seal:`.

The production-presence implementation merge:

`3d66ccfd1ddec0c3c9de49b72d84809299c5ef17`

completed merged-main CI successfully. Its release workflow `35728336490` and deploy workflow `35728342254` skipped by design because the main commit subject was not `seal:`.

Therefore production has not yet received the decision-backed transition-binding CLI/module.

No transition binding has been automatically created or staged.

## Decision-backed transition implementation

Implementation main SHA:

`3bbdcd6eb30e0c39bde9b3f592591fb98f27d5f1`

Final GREEN implementation head:

`780fa7c71f80319296233bcd4cc195ecd22d4f3f`

CLI:

`shreks-g1c-v2-decision-backed-transition-bind`

Module:

`shreks_brain.g1c_v2_decision_backed_transition_binding`

Inputs are limited to:

- canonical v1 source runtime manifest;
- exact canonical v2 candidate runtime manifest;
- authenticated decision-backed candidate authority;
- frozen V2 cohort directory;
- authenticated V2 host request authority;
- new non-existent transition-binding destination.

There are no raw CLI inputs for:

- paper-run id;
- start timestamp;
- quote mint;
- quote decimals;
- entry input amount;
- candidate-value decision;
- quote valuation review;
- sizing values.

The bridge authenticates the source, candidate, and decision-backed authority before transition derivation.

It then invokes the existing canonical transition binder in a private temporary location using the supplied source/candidate/cohort/request.

Before persistence it requires the resulting standard binding to match the decision-backed authority for:

- source manifest SHA/fingerprint/paper-run/quote identity;
- candidate manifest SHA/fingerprint/paper-run/start time/quote mint/quote decimals/valuation mode;
- frozen cohort fingerprint and quote mint;
- request fingerprint, release source SHA, and hydration-policy fingerprint.

It re-reads source, candidate, and authority after derivation and fails closed if any changed.

The output remains the existing standard schema:

`shreks.g1c_v2_runtime_manifest_transition_binding` version 1.

A successful binding preserves:

```text
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## TDD and implementation proof

### Decision-backed transition bridge

Intentional RED PR #409 head:

`8520679646b8e85aefd702c21f4da3e04b4fcd97`

RED CI:

`35725143082`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_decision_backed_transition_binding` did not yet exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

The first GREEN attempt exposed that the repository's frozen cohort contract is a directory artifact. The branch was rewritten from clean sealed main rather than carrying a corrective commit.

Final GREEN implementation head:

`780fa7c71f80319296233bcd4cc195ecd22d4f3f`

Push CI:

`35725830695`

Independent PR CI:

`35725835061`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`3bbdcd6eb30e0c39bde9b3f592591fb98f27d5f1`

Merged-main CI:

`35726155294`

Result: SUCCESS across all four canonical gates.

Its release/deploy workflows skipped because the merge commit was not a `seal:` commit.

### Production-presence proof

Intentional RED PR #411 head:

`8721daec9570c2940983edd8d2076e7431fd0c01`

RED CI:

`35727368909`

Result:

- Python: exactly 1 failed, 3626 passed, 2 known warnings;
- the only failure was the intentionally absent decision-backed transition-binding production-presence contract;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN production-presence head:

`f7b188971819283d3dede8579a0d19efc42517f2`

Push CI:

`35727725503`

Independent PR CI:

`35727743100`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged production-presence main:

`3d66ccfd1ddec0c3c9de49b72d84809299c5ef17`

Merged-main CI:

`35728078838`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing the bridge:

- the release-local `shreks-g1c-v2-decision-backed-transition-bind` script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_decision_backed_transition_binding` imports through exact release-local Python;
- the module path resolves inside that same expected release.

Expected evidence includes:

```text
g1c_v2_decision_backed_transition_binding=present
g1c_v2_decision_backed_transition_binding_path=<exact-release-local-path>
g1c_v2_decision_backed_transition_binding_module=<exact-release-local-module-path>
```

The verifier must not invoke the bridge.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the decision-backed transition-binding CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, existing trusted-admin tooling, transition-binding presence/provenance, helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute review-backed sizing;
- execute the candidate-value decision;
- execute the decision-backed candidate-authority bridge;
- execute candidate authoring;
- execute the decision-backed transition bridge;
- create or stage a transition binding;
- execute rotation-readiness;
- install, activate, or rotate a runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin transition boundary

Only after production verification proves the transition bridge exact-release-local may a trusted administrator use the documented ceremony against:

- the protected canonical v1 source manifest;
- the exact reviewed decision-backed v2 candidate;
- the exact reviewed decision-backed candidate authority;
- the frozen V2 cohort directory;
- the authenticated V2 request authority;
- one new root-private transition-binding destination.

The trusted-admin command has no raw paper-run, timestamp, quote, entry-amount, candidate-value-decision, review, or sizing arguments.

The bridge writes the existing standard transition-binding v1 schema only after authority-chain and compatibility checks succeed.

A successful binding remains evidence only.

It does not grant readiness or rotation authority.

## Helper/readiness boundary

Deployment of this seal changes the current release SHA.

Any helper installation proof bound to an earlier release becomes stale for later readiness.

A fresh exact-release helper proof remains mandatory before any future rotation-readiness ceremony.

No helper-proof refresh is required merely to create and review an offline transition-binding artifact.

Do not execute rotation-readiness merely because a valid transition binding exists.

## Authority boundary

This seal does not authorize:

- automatic transition binding;
- automatic transition staging;
- rotation-readiness execution;
- production manifest installation/activation/rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_DECISION_BACKED_TRANSITION_BINDING=SEALED_TOOL_PRESENCE_ONLY`

`DECISION_BACKED_TRANSITION_BINDING_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_TRANSITION_BINDING_EXECUTION=DISABLED`

`TRANSITION_BINDING_STAGING=NOT_AUTHORIZED`

`ROTATION_READINESS=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
