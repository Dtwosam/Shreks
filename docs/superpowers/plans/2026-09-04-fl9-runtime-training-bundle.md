# FL9 Runtime Training Bundle — Implementation Plan

**Date:** 2026-09-04
**Base:** `b2304cf423429af93354cbb6429aab1191507768` (#200)

1. Add intentional RED contracts for storage-free FL5/FL8.1 logical assembly.
2. Expose canonical FL5 logical rows + manifest without importing PyArrow.
3. Make the existing Parquet writer delegate to the same logical FL5 builder.
4. Add exact in-memory FL8.1 component assembly.
5. Recompute/authenticate feature and FL4 logical fingerprints before bundle creation.
6. Reuse the sealed FL8.1 join validator and manifest/fingerprint builder.
7. Add production-shaped JSONL + read-only SQLite bundle assembly.
8. Reuse the existing FL5 canonical source loader for every decision/horizon/version.
9. Require exact FL5 provenance equality with the corresponding FL4 row.
10. Preserve missing execution evidence as UNKNOWN; never synthesize fills.
11. Require an explicit positive finite research counterfactual base quantity.
12. Prove logical equality with the existing Parquet bundle on the Rust-generated FL8.1 fixture.
13. Prove runtime assembly does not import PyArrow.
14. Prove feature and FL4 fingerprint tampering fails closed.
15. Keep providers, SQLite mutation, PAPER mutation, trade intent, promotion, signing, submission, and LIVE authority absent.
16. Run exact-head Python/Rust/repository-safety/ARM64 CI.
17. Guarded squash merge and merged-main four-gate seal.
18. Next: build the first standard-library non-fixture champion + FL9 evidence orchestration using MEAN_REGRESSOR / PRIOR_CLASSIFIER.

TDD RED: `93378caa0f0495500f95fc71fe0891e7d50f2482`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
