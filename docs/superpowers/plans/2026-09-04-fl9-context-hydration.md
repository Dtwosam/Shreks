# FL9 Point-in-Time Forecast Context Hydration — Implementation Plan

**Date:** 2026-09-04
**Base:** `fc35dd86580468c4e525824ac6336f0d0dae835c` (#206)

1. Add intentional RED tests for the absent context-hydration module.
2. Define an immutable explicit hydration policy.
3. Canonically encode/fingerprint all strategy, regime, safety, probe, freshness, and cost assumptions.
4. Reject raw JSON floats, non-finite values, duplicate/malformed fields, and inconsistent quote/probe policy.
5. Derive the required context population by running sealed FL8.3 with a fixed dependency-free mean-regressor request.
6. Use only validation + TEST prediction identities emitted after sealed leakage quarantine.
7. Require unique population identities and exact mapping back to FL8.1 feature records.
8. Resolve one unambiguous observer candidate per decision mint.
9. Reject candidate discovery after decision time.
10. Require exact persisted candidate/FL8.1 venue equality.
11. Replay aggregate regime at the exact decision timestamp through sealed observer/regime logic.
12. Use market-only regime semantics in v1; do not inject unpersisted recent performance.
13. Construct exact persisted directional EXIT quote identity.
14. Treat missing/stale quote as unknown, unavailable route as zero, and fresh available route as minimum-output quote capacity.
15. Copy strategy-family context only from the explicit policy.
16. Copy expected round-trip cost only from the explicit versioned policy.
17. Build the canonical #204 context corpus.
18. Reconcile exit-evidence counts to exact context count.
19. Add immutable three-file hydration artifact.
20. Seal DB + WAL before/after hydration and abort on race.
21. Persist the full exact chronological validation policy and its fingerprint in the manifest.
22. Bind bundle/source/database/policy/population/context/file fingerprints into the artifact manifest.
23. Strict-read staged artifact before atomic publication.
24. Reject overwrite, symlink, file-set drift, policy substitution, corpus tampering, or manifest tampering.
25. Keep provider/network, PAPER execution, selection, promotion, signing/submission, and LIVE absent.
26. Run exact-head Python/Rust/repository-safety/ARM64 CI.
27. Guarded squash merge only after exact 4/4 GREEN.
28. Run merged-main four-gate CI and seal.
29. Next: atomic host first-champion preparation chaining #206 -> #201 -> #207 -> #205.

TDD RED: `2db11aafde9672aa7ae46f776227b17bf4a7e559`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
