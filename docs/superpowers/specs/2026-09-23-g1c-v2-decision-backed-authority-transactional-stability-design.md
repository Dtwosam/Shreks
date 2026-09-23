# G1C V2 Decision-Backed Candidate Authority Transactional Authority Stability — Design

**Date:** 2026-09-23  
**Status:** candidate-authority evidence hardening only; no runtime mutation

## Problem

The schema-v2 decision-backed candidate-authority bridge authenticates the canonical source runtime manifest, candidate-value preflight, and accepted candidate-value decision, then delegates ordinary candidate derivation to the existing G1C V2 candidate-authority binder.

The delegated binder authenticates the frozen FL9 V2 cohort, preserved V2 host-request authority, and request-bound hydration policy before deriving its authority artifact. The schema-v2 bridge then checks that derived cohort/request provenance equals the exact preflighted candidate authority.

However, the bridge does not re-authenticate the non-manifest V2 authority after delegated derivation and before publishing its final schema-v2 authority artifact. A request/cohort/hydration change after delegated derivation can therefore leave a final authority artifact based on the earlier authenticated snapshot.

## Required behavior

The schema-v2 bridge must:

1. authenticate the frozen cohort + V2 host-request + request-bound hydration authority before delegated candidate-authority derivation;
2. require the delegated authority artifact to contain the exact same cohort/request/hydration provenance;
3. re-authenticate the same non-manifest authority immediately before final schema-v2 publication;
4. require the final authenticated authority to equal the initial authenticated authority;
5. fail closed and leave the requested final destination absent if authentication fails or authority changes.

The existing source/preflight/decision byte-stability checks remain mandatory.

## Authority boundary

A successful artifact may still grant only the existing decision-backed candidate-authoring authority already defined by schema v2:

```text
authority_status=BOUND_EXACT_CANONICAL_CANDIDATE
candidate_compatibility=COMPATIBLE
preflight_authority=EVIDENCE_ONLY
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

No automatic authority execution, candidate staging, transition binding, readiness/rotation, scoring/model fitting, PAPER promotion, wallet access, signing/submission, or LIVE behavior is added.
