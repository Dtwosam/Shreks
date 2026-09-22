# G1C V2 Decision-Backed Candidate Authority Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic authority execution

## Purpose

The decision-backed candidate-authority bridge is implemented and tested separately.

Before a trusted administrator may use it against protected source/cohort/request/decision artifacts, the ordinary production verifier must prove that the exact active immutable release physically contains the bridge CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-decision-backed-candidate-authority-bind`;
- regular non-symlink executable;
- resolved console-script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_decision_backed_candidate_authority`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_decision_backed_candidate_authority=present
g1c_v2_decision_backed_candidate_authority_path=<exact-release-local-path>
g1c_v2_decision_backed_candidate_authority_module=<exact-release-local-module-path>
```

The production verifier must not execute the bridge.

## Runbook contract

Document one trusted-admin ceremony over explicit existing:

- canonical v1 source runtime manifest;
- frozen V2 cohort;
- authenticated V2 host request authority;
- approved candidate-value decision;
- explicit new-run id;
- explicit start timestamp;
- new private destination.

The command has no raw quote mint/decimals/entry-amount inputs.

Those economics must come only from the authenticated approved decision.

A successful result may record:

`candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND`

but it remains offline authority evidence only and does not emit/stage/activate a candidate.

## Authority boundary

This slice adds no automatic bridge execution and no:

- sizing or decision execution;
- SQLite read;
- candidate file authoring/staging;
- transition binding;
- readiness;
- installation/activation/manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
