# FL9 Authenticated Forecast Evaluation Context Corpus — Implementation Plan

**Date:** 2026-09-04
**Base:** `e290efc9701f366730265b7760e63d4aefc18119` (#203)

1. Add RED contracts for a canonical FL8.4 context corpus.
2. Reuse exact `FastForecastEvaluationContext`; do not define a competing context model.
3. Reuse sealed `fast_forecast_context_fingerprint_sha256`; do not define a competing logical fingerprint.
4. Add schema `shreks.fast_forecast_evaluation_context_corpus` v1.
5. Canonicalize caller context order by timestamp, sequence, signature, ordinal.
6. Reject duplicate decision identities.
7. Require exact row fields only.
8. Encode optional finite floats with `float.hex()` tags.
9. Reject raw JSON floats and non-finite constants.
10. Encode compact sorted canonical JSON with exactly one trailing newline.
11. Decode exact keys/types and reconstruct exact FL8.4 contexts.
12. Recompute/verify the FL8.4 context fingerprint.
13. Require decode payload to equal canonical re-encoding.
14. Add no-overwrite writer and strict file reader.
15. Export the corpus API only from the #203 composition package.
16. Keep DB, provider, training, PAPER, promotion, signing, submission, and LIVE authority absent.
17. Run exact-head Python/Rust/repository-safety/ARM64 CI.
18. Guarded squash merge only on exact 4/4 GREEN head.
19. Run merged-main four-gate CI and seal.
20. Next: file-backed first-champion request using #201 runtime bundle + this context corpus + #203 builder.

TDD RED: `e0004586610f61e3e083c79105b0cab118e827c9`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
