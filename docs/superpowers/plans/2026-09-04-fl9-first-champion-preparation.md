# FL9 Atomic First Champion Preparation — Implementation Plan

**Date:** 2026-09-04
**Base:** `1eba5696ed1dc5921c55b5f32e4c0d559cb24d83` (#207)

1. Add intentional RED tests for absent atomic preparation API.
2. Strict-read source #206 proof workspace.
3. Seal current observer DB + optional WAL.
4. Create private staging root.
5. Copy complete #206 proof workspace into staging.
6. Strict-read source and copy; require identical manifest and feature evidence.
7. Build exact #201 runtime logical bundle from copied feature JSONL + current read-only DB.
8. Require bundle feature byte/logical fingerprints equal copied #206 workspace.
9. Run #207 into an internal `context-hydration/` child artifact.
10. Strict-read hydration child.
11. Require exact validation policy, horizon, bundle, feature, DB, and WAL cross-links.
12. Build canonical #205 request with internal relative feature/context/destination paths.
13. Write canonical `first-champion-request.json`.
14. Run #205 into internal `first-champion/`.
15. Strict-read first-champion child.
16. Rehash current DB + WAL and require exact parent before/after equality.
17. Cross-link #205 request, feature, DB/WAL, bundle, context, and champion evidence to #207/#206.
18. Bind release/source/child/request/champion/selection fingerprints into parent manifest.
19. Strict-read full staged parent artifact.
20. Atomically rename only when destination remains absent.
21. Remove staging on every failure.
22. Reject child substitution, request substitution, policy/horizon drift, source races, or cross-chain fingerprint mismatch.
23. Keep network, direct SQLite queries, new model/regime/cost logic, PAPER execution, promotion, signing/submission, and LIVE absent.
24. Run exact-head Python/Rust/repository-safety/ARM64 CI.
25. Add design/plan docs without changing production semantics.
26. Run exact final-doc-head four-gate CI.
27. Guarded squash merge only on exact 4/4 GREEN.
28. Run merged-main four-gate CI and seal.
29. Next: canonical file-backed #208 request + one host CLI command.

TDD RED: `173b653dfcd407dd878218e6fa5ac065b4bd8b36`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
