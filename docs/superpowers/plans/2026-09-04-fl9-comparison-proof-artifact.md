# FL9 Learned-vs-Baseline Comparison Proof Artifact — Implementation Plan

**Date:** 2026-09-04
**Base:** `601b00df824aa506ec746cd1e49701b4c091f8ca` (#197)

1. RED strict comparison-proof artifact contract.
2. Add canonical authenticated superiority-policy codec.
3. Strictly open #195 baseline invocation.
4. Strictly open #193 deterministic campaign.
5. Require exactly eight baseline runs.
6. Require superiority policy baseline versions equal catalog exactly.
7. Recompute learned run fingerprint.
8. Evaluate with sealed FL9 superiority engine.
9. Persist learned run as one-run canonical batch.
10. Persist canonical authenticated superiority policy.
11. Persist canonical sealed superiority report.
12. Build manifest binding all baseline/learned/proof/file identities.
13. Stage privately and strict-read before atomic publish.
14. Reader reopens baseline chain and recomputes superiority report exactly.
15. Preserve FAILED / INSUFFICIENT / SUPERIOR truthfully.
16. Keep promotion, network, SQLite, signing/submission, and LIVE authority absent.
17. Narrow the older deterministic-driver firewall only enough to exclude the new separate proof layer.
18. Update durable design/plan.
19. Run exact-head Python/Rust/ARM64/repository-safety CI.
20. Guarded squash merge.
21. Next: canonical file-backed learned/proof orchestration request.
22. Then execute real non-fixture FL9 evidence when runtime inputs exist.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
