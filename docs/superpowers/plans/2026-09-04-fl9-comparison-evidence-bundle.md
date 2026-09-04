# FL9 Immutable Comparison Evidence Bundle — Implementation Plan

**Date:** 2026-09-04
**Base:** `f4021a72f713fe41174f47c8556a0b5551f861e9` (#183)

1. Define RED tests for immutable self-contained feature+evidence bundle.
2. Add v1 bundle manifest and strict three-file layout.
3. Reuse sealed FL8.1 Parquet writer/reader for the point-in-time feature population.
4. Add canonical deterministic/PAPER evidence JSONL sidecar.
5. Authenticate physical file hashes, logical evidence hash, and bundle manifest fingerprint.
6. Require exact positional FL8.1 population and exact catalog candidate-authority coverage.
7. Bind explicit provenance for quote, forecast/horizon, costs, exit capacity, wallet, graduation, continuation, regime, risk environment, and entry authority; reject evidence/provenance contradictions.
8. Strictly decode sidecar rows back through existing comparison-row validation.
9. Prove tamper detection and absence of future-label/execution/LIVE authority.
10. Run canonical four-gate CI and guarded merge.
11. Next: point-in-time evidence hydrator producing non-fixture bundles from approved sources.

FL9 superiority stays EVIDENCE PENDING until real chronological PAPER/shadow evidence beats the deterministic comparison set.
