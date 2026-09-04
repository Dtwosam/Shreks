# FL9 Sealed Proof Workspace Export — Implementation Plan

**Date:** 2026-09-04
**Base:** `8fb1576d6d1270e513bbecd01b56ea715e927198` (#205)

1. Add intentional RED tests for absent proof-workspace module/CLI.
2. Add schema `shreks.fast_proof_workspace` v1.
3. Require explicit database, destination, tool root, release SHA, platform, and timeout.
4. Call sealed #200 proof-tool materialization.
5. Verify returned toolset source SHA/platform/order.
6. Reread and authenticate the materialized tool manifest.
7. Bind exact exporter binary SHA.
8. Capture stable DB + optional WAL hashes before export.
9. Create a private sibling staging directory.
10. Launch exporter via direct argv; never use a shell.
11. Enforce explicit timeout and successful exit code.
12. Require a new regular feature JSONL file.
13. Strict-read it with sealed FL8.1 JSONL parser.
14. Require dataset source SHA equal the file byte SHA.
15. Rehash DB + optional WAL and require exact before/after equality.
16. Bind source/tool/feature hashes plus population bounds into manifest.
17. Write feature/manifest private 0600.
18. Strict-read staged workspace.
19. Rename atomically only if destination remains absent.
20. Remove staging on all failure paths.
21. Add console entry point `shreks-fast-proof-workspace`.
22. Keep network, Python DB queries, model/champion logic, PAPER execution, signing/submission, and LIVE absent.
23. Run exact-head Python/Rust/repository-safety/ARM64 CI.
24. Guarded squash merge only on exact 4/4 GREEN.
25. Run merged-main four-gate CI and seal.
26. Next: point-in-time FL8.4 context hydration from persisted observer evidence + explicit policies.

TDD RED: `28f90387738fa2ad7046411854e2a5be76eb593f`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
