# FL9 Fast Policy Run Evidence Batch Codec — Implementation Plan

**Date:** 2026-09-04
**Base:** `3fb4c0321323a88945a3f4234116656d31d3dc71` (#191)

1. RED: exact canonical batch round trip, tamper rejection, lexical ordering.
2. Extract one shared run-fingerprint material helper from the existing builder.
3. Expose run-evidence fingerprint recomputation.
4. Encode each nested trading evaluation through the sealed E10 evidence codec.
5. Decode/rebuild exact E5 evaluation evidence.
6. Reconstruct exact `FastPolicyRunEvidence`.
7. Verify every run fingerprint.
8. Verify lexical uniqueness.
9. Verify top-level batch fingerprint.
10. Export codec API.
11. Update durable docs.
12. Run exact-head four-gate CI.
13. Guarded merge.
14. Next: deterministic campaign artifact writer using evidence bundle + run batch codec.

FL9 superiority remains EVIDENCE PENDING. LIVE remains disabled.
