# G1C V2 Candidate-Value Decision Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic decision execution

## Purpose

The candidate-value decision tool is implemented and tested separately.

Before a trusted administrator may use it against a protected review-backed sizing proposal, the ordinary production verifier must prove that the exact active immutable release physically contains the CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-candidate-value-decision`;
- regular non-symlink executable;
- resolved console-script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_candidate_value_decision`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_candidate_value_decision=present
g1c_v2_candidate_value_decision_path=<exact-release-local-path>
g1c_v2_candidate_value_decision_module=<exact-release-local-module-path>
```

The production verifier must not execute the decision CLI.

## Runbook contract

Document one trusted-admin ceremony over an explicit existing review-backed sizing proposal.

The operator must supply:

- exact sizing-proposal path;
- explicit decision: `ACCEPT_PROPOSAL`, `REJECT_PROPOSAL`, or `REPLACE_PROPOSAL`;
- non-empty decision reason;
- replacement raw amount only for `REPLACE_PROPOSAL`;
- new non-existent private destination.

The command authenticates the proposal and requires:

`quote_evidence_authority=MULTI_REFERENCE_REVIEW`

An accepted/replaced result may record:

`candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND`

but always keeps candidate authoring and downstream runtime authority blocked.

## Authority boundary

This slice adds no automatic decision execution and no:

- quote review or sizing execution;
- SQLite read;
- candidate-authority invocation;
- candidate authoring/staging;
- transition binding;
- readiness;
- manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
