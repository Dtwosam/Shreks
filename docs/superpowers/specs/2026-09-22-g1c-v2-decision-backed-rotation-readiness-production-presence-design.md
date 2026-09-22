# G1C V2 Decision-Backed Rotation Readiness Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic readiness execution

## Purpose

The decision-backed rotation-readiness wrapper is implemented and merged separately.

Before a trusted administrator may use it against protected candidate/binding/authority
artifacts and current-release helper evidence, the ordinary production verifier must
prove that the exact active immutable release contains the wrapper CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-decision-backed-rotation-readiness`;
- regular non-symlink executable;
- resolved console-script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_decision_backed_rotation_readiness`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_decision_backed_rotation_readiness=present
g1c_v2_decision_backed_rotation_readiness_path=<exact-release-local-path>
g1c_v2_decision_backed_rotation_readiness_module=<exact-release-local-module-path>
```

The production verifier must not execute readiness.

## Runbook contract

Document one trusted-admin evidence-only ceremony over:

- exact canonical decision-backed v2 candidate;
- exact standard transition binding;
- exact authenticated decision-backed candidate authority;
- fresh helper installation proof bound to the exact current immutable release;
- the exact current release SHA.

The CLI derives the binding fingerprint from the authenticated transition binding.
There is no operator-supplied binding-fingerprint argument and no raw candidate
run/time/economic/decision/review/sizing input.

A successful result remains the existing standard readiness receipt:

```text
status=READY_EVIDENCE_ONLY
installation_authority=PROVEN
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## Authority boundary

This presence slice does not authorize:

- automatic readiness execution;
- helper installation or proof refresh;
- candidate/binding staging;
- production manifest installation/activation/rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
