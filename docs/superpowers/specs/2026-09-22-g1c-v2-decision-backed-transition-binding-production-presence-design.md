# G1C V2 Decision-Backed Transition Binding Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic transition execution

## Purpose

The decision-backed transition bridge is implemented and merged separately.

Before a trusted administrator may use it with protected source/candidate/authority/cohort/request artifacts, the ordinary production verifier must prove that the exact active immutable release contains the bridge CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-decision-backed-transition-bind`;
- regular non-symlink executable;
- resolved console-script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_decision_backed_transition_binding`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_decision_backed_transition_binding=present
g1c_v2_decision_backed_transition_binding_path=<exact-release-local-path>
g1c_v2_decision_backed_transition_binding_module=<exact-release-local-module-path>
```

The production verifier must not execute the bridge.

## Runbook contract

Document one trusted-admin ceremony over explicit existing:

- canonical v1 source runtime manifest;
- exact canonical v2 candidate authored from the decision-backed authority;
- authenticated decision-backed candidate authority;
- frozen V2 cohort directory;
- authenticated V2 host request authority;
- new private transition-binding destination.

There are no raw paper-run, timestamp, quote, entry-amount, candidate-value-decision, review, or sizing inputs.

The bridge must preserve the existing standard `shreks.g1c_v2_runtime_manifest_transition_binding` v1 output schema so later readiness compatibility is unchanged.

## Authority boundary

A successful standard binding still records:

```text
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This presence slice does not authorize:

- automatic transition binding;
- rotation-readiness execution;
- production manifest installation/activation/rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
