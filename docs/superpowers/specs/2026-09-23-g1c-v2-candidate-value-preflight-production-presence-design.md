# G1C V2 Candidate-Value Compatibility Preflight Production Presence — Design

**Date:** 2026-09-23  
**Status:** read-only production presence proof only; no automatic preflight execution

## Purpose

The candidate-value compatibility preflight is implemented and tested separately.

Before a trusted administrator may use it against protected production sizing/cohort/request artifacts, the ordinary production verifier must prove that the exact active immutable release physically contains the preflight CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-candidate-value-preflight`;
- regular non-symlink executable;
- resolved console-script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_candidate_value_preflight`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_candidate_value_preflight=present
g1c_v2_candidate_value_preflight_path=<exact-release-local-path>
g1c_v2_candidate_value_preflight_module=<exact-release-local-module-path>
```

The production verifier must not execute the preflight CLI.

## Runbook contract

Document one trusted-admin ceremony over explicit existing protected inputs:

- canonical v1 source runtime manifest;
- authenticated `MULTI_REFERENCE_REVIEW` sizing proposal;
- frozen FL9 V2 cohort;
- preserved authenticated V2 host-request authority;
- explicit future `paper_run_id`;
- explicit future `start_at_unix_ms`;
- new non-existent private receipt destination.

The command must authenticate the proposal and require its downstream authority fields to remain blocked before deriving the hypothetical candidate and delegating compatibility to the existing canonical FL9 V2 assessment.

A successful receipt remains evidence only:

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

The runbook must state that the preflight does not approve candidate values and that a separate explicit candidate-value decision remains mandatory.

## Authority boundary

This slice adds no:

- automatic preflight execution;
- candidate-value approval;
- candidate-authority invocation;
- persistent candidate authoring/staging;
- transition binding;
- readiness;
- manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
