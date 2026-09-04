# FL9 Deterministic First Champion Evidence Plan — Implementation Plan

**Date:** 2026-09-04
**Base:** `c44fcd7ffc71d64ca593718761239e36db3c0bc2` (#208)

1. Add intentional RED tests for absent evidence-plan module.
2. Require exact FL8.1 bundle and validate bundle/feature/future-path fingerprints.
3. Require explicit horizon, selection timestamp, raw partition floor, and TEST evidence floor.
4. Compute the maturity cutoff as `selection_at - horizon`.
5. Select only feature rows strictly earlier than the maturity cutoff.
6. Keep equal decision timestamps in the same partition.
7. Require enough rows for all three raw partitions.
8. Choose one fixed training boundary nearest 60% by raw count.
9. Choose one fixed validation/test boundary nearest 80% by raw count.
10. Never search another split based on target/model/economic results.
11. Build one exact chronological validation policy.
12. Reuse #203's exact required target/family tuple.
13. Dry-run sealed FL8.3 once for every required member using dependency-free families.
14. Require all target runs to preserve identical partition/quarantine/TEST populations.
15. Count exact FL4 TEST target availability at the requested horizon.
16. Require every target to meet the explicit TEST-scored floor.
17. Preserve missing target evidence as missing.
18. Bind bundle/source/future-path/policy/quarantine/target-run evidence into one plan fingerprint.
19. Add strict canonical encode/decode and file read/write helpers.
20. Reject field drift, enum drift, count drift, member-order drift, non-canonical JSON, or tampering.
21. Keep wall clock, network, SQLite, economic optimization, execution, promotion, signing/submission, and LIVE absent.
22. Run exact-head four-gate CI.
23. Add final design/plan docs.
24. Run exact final-head four-gate CI.
25. Guarded squash merge only on exact 4/4 GREEN.
26. Seal merged-main four-gate CI.
27. Next: file-backed host first-champion command combining #206/#201/#209/#207/#208.

TDD RED: `3142ded0eb9056e28fca810a14f54a9358cac175`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
