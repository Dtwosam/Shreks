# FL9 Canonical First Champion Host Request Writer — Implementation Plan

**Date:** 2026-09-04
**Base:** `ead8a1f504e00a6491bb2a01d3240a8bc4d91d6d` (#212)

1. Add intentional RED tests for absent host-request writer.
2. Strict-read #206 proof workspace.
3. Derive exact expected release source SHA from #206 manifest.
4. Stable-read and strict-decode #207/#212 hydration policy.
5. Derive exact hydration-policy fingerprint.
6. Require current observer DB path to be a regular file without freezing its changing content.
7. Require TEST evaluation policy only.
8. Fix selection clock to `HOST_WALL_CLOCK_AT_RUN_START`.
9. Pass all evidence floors, horizon, version strings, and reason explicitly.
10. Encode absolute source and host-run destination paths.
11. Build the canonical request only through #210's sealed builder/encoder.
12. Refuse existing request or host-run destination.
13. Stage request in a sibling file, flush, fsync, and chmod 0600.
14. Recheck hydration-policy bytes before publication.
15. Recheck proof-workspace manifest before publication.
16. Recheck observer DB path still exists as a regular file.
17. Recheck staged bytes equal canonical payload.
18. Recheck both destinations remain absent.
19. Atomically rename the request.
20. Remove staging on all failures.
21. Expose `shreks-fast-first-champion-request` in the release wheel.
22. Emit compact machine-readable success status.
23. Keep network, direct DB queries, model fitting, PAPER execution, promotion, signing/submission, and LIVE absent.
24. Run exact-head repository-safety/Python/Rust/ARM64 CI.
25. Add durable design and plan docs.
26. Run exact final-doc-head four-gate CI.
27. Guarded squash merge only after exact 4/4 GREEN.
28. Run merged-main four-gate CI.
29. Add same-tree `seal:` commit only after merged-main GREEN so the existing automatic ARM64 release workflow can publish the exact sealed source.
30. Next: protected PAPER deployment and first genuine host evidence execution.

TDD RED: `5d326fb51b0762dc5eac0a9be4ede18d2a01b1b1`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
