# G1C V2 Candidate-Value Preflight Transactional Authority Stability — Design

**Date:** 2026-09-23  
**Status:** evidence-publication hardening only; no candidate/runtime authority

## Problem

The candidate-value preflight already snapshots and rechecks the canonical source runtime manifest and authenticated review-backed sizing proposal before publishing its final receipt.

Its compatibility assessment also authenticates the frozen FL9 V2 cohort, preserved V2 host-request authority, and request-bound hydration policy.

However, the preflight currently does not bind those non-manifest authority inputs across the full preflight operation. If the request/cohort/hydration authority changes after compatibility assessment but before receipt publication, the command can still publish a final evidence receipt derived from the earlier authenticated authority snapshot.

That is inconsistent with the transactional evidence-publication boundary already required for source/proposal provenance.

## Required behavior

Before hypothetical candidate assessment, authenticate the exact non-manifest V2 request authority and preserve that authenticated authority object.

The canonical compatibility assessment must still perform its own ordinary authentication.

After assessment:

1. require the assessment's returned non-manifest authority document to match the initially authenticated authority exactly;
2. re-authenticate the same cohort/request/hydration authority immediately before final receipt publication;
3. require the final authenticated authority to equal the initial authenticated authority;
4. if any authentication fails or any authority differs, fail closed;
5. leave the requested final preflight destination absent.

The existing source/proposal stability checks remain unchanged.

## Authority boundary

This hardening grants no new authority.

A successful receipt remains evidence-only:

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

No automatic preflight, decision, candidate authority, authoring/staging, transition binding, readiness/rotation, scoring/model fitting, PAPER promotion, wallet access, signing/submission, or LIVE behavior is added.
