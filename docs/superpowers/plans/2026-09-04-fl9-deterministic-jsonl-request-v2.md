# FL9 Deterministic Campaign JSONL Request v2 — Implementation Plan

**Date:** 2026-09-04
**Base:** `0b049bf9584d95dcd11de1f120fd8d8a9531a063` (#201)

1. Preserve deterministic campaign request v1 exactly.
2. Add request schema v2 with explicit `feature_jsonl_path`.
3. Give v2 an exact field set and canonical fingerprint material.
4. Keep the existing decoder as the single strict decoder for v1 and v2.
5. Keep the existing encoder as the single strict encoder for both exact request types.
6. Require v2 feature sources to be explicit JSONL paths.
7. Route v1 only through the Parquet reader.
8. Route v2 only through the canonical Rust feature JSONL reader.
9. Converge both versions on the same deterministic campaign artifact writer.
10. Preserve context population and starting-ledger chronology checks.
11. Add invocation schema v2 corresponding to request v2.
12. Add source-snapshot schema v2 with `feature_jsonl_path` replacing only the v1 Parquet source label.
13. Keep v1 invocation/source label order and schema readable unchanged.
14. Derive invocation/source schema from the decoded request and reject cross-version substitution.
15. Preserve before/after source hashing, request mutation detection, WAL capture, campaign reread, and no-overwrite behavior.
16. Export only the public v2 request/invocation symbols needed by callers.
17. Prove v1 round-trip remains exact.
18. Prove v2 never invokes the Parquet reader.
19. Prove v2 invocation seals authenticate the JSONL source bytes.
20. Keep provider, promotion, signing, submission, and LIVE authority absent.
21. Run exact-head Python/Rust/repository-safety/ARM64 CI.
22. Guarded squash merge only on exact 4/4 GREEN head.
23. Run merged-main four-gate CI and seal.
24. Next: dependency-free first-real champion/evidence-plan builder over actual runtime FL8.1 evidence.

TDD RED:
- `4be039b0192c4c6ff34e672bf478adbead3df5c5`
- `770483d461584057bcd10b2240ce3df187e637c9`

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
