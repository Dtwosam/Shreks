# FL9 One-Command First Champion Host Run — Implementation Plan

**Date:** 2026-09-04
**Base:** `21a4fcf77eb66e6589088f5951a60f66ba5fa76f` (#209)

1. Add intentional RED contracts for an absent host-run module and console command.
2. Define canonical host-request schema v1.
3. Require explicit #206 proof path and expected release source SHA.
4. Require explicit #207 hydration-policy path and expected policy fingerprint.
5. Require exact evaluation/evidence/model/training parameters.
6. Support only `HOST_WALL_CLOCK_AT_RUN_START` selection clock.
7. Capture host wall-clock milliseconds exactly once at run start.
8. Strict-read #206 and #207 inputs before planning.
9. Build exact #201 runtime logical bundle from proof JSONL + read-only DB.
10. Require #201 feature byte/logical identity equal #206.
11. Call sealed #209 to derive the deterministic evidence plan from the captured selection boundary.
12. Persist canonical request, hydration policy, and plan in private staging.
13. Derive champion decision reference from the plan fingerprint.
14. Call sealed #208 using the exact #209 validation policy and selection timestamp.
15. Strict-read the #208 child preparation.
16. Reread request/hydration/proof sources and reject mutation.
17. Cross-link release, feature, bundle, policy, plan, validation, context, champion, and version identities.
18. Bind those identities in a canonical outer manifest.
19. Strict-read the full staged host-run artifact.
20. Atomically rename only when the destination remains absent.
21. Remove staging on all failure paths.
22. Expose `shreks-fast-first-champion-run` in the release wheel.
23. Keep provider/network, direct DB queries, new model/regime/cost logic, PAPER execution, promotion, signing/submission, and LIVE absent.
24. Run exact-head Python/Rust/repository-safety/ARM64 CI.
25. Add design/plan docs after production behavior is fixed.
26. Run exact final-doc-head four-gate CI.
27. Guarded squash merge only on exact 4/4 GREEN.
28. Run merged-main four-gate CI and seal.
29. Next: deploy/run the verified release under the existing PAPER runtime identity and preserve the first genuine host evidence result.

TDD RED: `3752e46a60caa132cc0231e44cca35767be14bd3`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
