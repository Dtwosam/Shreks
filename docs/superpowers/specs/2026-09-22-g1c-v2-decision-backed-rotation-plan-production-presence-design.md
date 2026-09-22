# G1C V2 Decision-Backed Rotation Plan Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic planning or manifest rotation

## Purpose

The decision-backed protected PAPER rotation planner is implemented and merged separately.

Before a trusted administrator may use it against protected current-host state, the
ordinary production verifier must prove the exact active immutable release contains the
planner CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-decision-backed-rotation-plan`;
- regular non-symlink executable;
- resolved script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_decision_backed_rotation_plan`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_decision_backed_rotation_plan=present
g1c_v2_decision_backed_rotation_plan_path=<exact-release-local-path>
g1c_v2_decision_backed_rotation_plan_module=<exact-release-local-module-path>
```

The production verifier must not execute the planner.

## Trusted-admin planner ceremony

Document one root-private ceremony that supplies only:

- exact reviewed candidate;
- exact reviewed standard transition binding;
- exact reviewed decision-backed candidate authority;
- exact reviewed `READY_EVIDENCE_ONLY` readiness receipt;
- exact current immutable release SHA.

The ceremony writes only a canonical rotation-plan JSON artifact.

The planner derives the binding fingerprint from the authenticated binding, rechecks
current release/manager/source/runtime/sudoers/G7/service state, and requires the manager's
binding-named rotation evidence directory to remain absent.

A successful plan records:

```text
status=READY_FOR_TRUSTED_ADMIN_ROTATION_CEREMONY
planning_authority=READ_ONLY
manifest_rotation_authority=NOT_EXERCISED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The runbook must state that producing or reviewing the plan does not itself authorize
execution of the manager argv.

## Authority boundary

This slice does not authorize:

- automatic planner execution;
- automatic or manual manager execution merely from plan existence;
- manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

A later separate trusted-administrator decision/invocation remains the actual rotation
authority under the existing protected-rotation design.

A separate seal/deploy step is required before protected production planner use.
