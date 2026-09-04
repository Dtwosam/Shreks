# FL9 Champion-Derived FL3 Execution Evidence — Implementation Plan

**Date:** 2026-09-04
**Base:** `78f9a48f2da5a27889d0bbd72b13ae06e521307e` (#188)

1. RED: define champion-to-execution evidence contract.
2. Load only through the sealed champion codec.
3. Select exact raw `ENDPOINT_RETURN_BPS` member at the requested horizon.
4. Reject champion selection after the FL8.1 decision.
5. Reject runtime artifact training that reaches or follows the FL8.1 decision.
6. Run sealed FL8 prediction.
7. Convert raw endpoint return bps to gross forecast exit price.
8. Combine only with explicit cost model, size, capacity, edge, and risk margin.
9. Emit champion/artifact/validation/test/source provenance.
10. Reject cost-adjusted substitution and non-positive gross forecast price.
11. Update durable docs.
12. Run exact-head four-gate CI.
13. Guarded merge.
14. Next: assemble real post-selection hydration inputs and execute the immutable eight-candidate PAPER comparison.

FL9 economic superiority remains EVIDENCE PENDING. LIVE remains disabled.
