# FL9 Runtime-Backed Forecast Context Hydration Policy — Implementation Plan

**Date:** 2026-09-04
**Base:** `7fcc5d0b9301419e0e319adf76853fa3e2db2723`

1. Add intentional RED tests for absent runtime-to-hydration policy bridge.
2. Reuse the sealed G1C runtime-manifest codec rather than introducing a new runtime policy schema.
3. Re-authenticate direct in-memory manifests through the sealed encoder.
4. Copy only manifest-backed regime/safety/probe/global-halt/provider/quote-decimal fields.
5. Require explicit hydration-policy version.
6. Require explicit strategy-family labels.
7. Reject duplicate/empty strategy families and canonicalize order.
8. Require explicit maximum EXIT quote age.
9. Require explicit execution-cost policy version.
10. Require explicit expected round-trip cost value or literal `unknown`.
11. Preserve `unknown` as #207 `None`, never zero.
12. Use #207's existing canonical hydration-policy encoder/fingerprint.
13. Stable-read the runtime manifest before derivation.
14. Stage output privately, flush/fsync, chmod 0600.
15. Stable-reread runtime source and require exact byte equality.
16. Refuse overwrite or destination races.
17. Atomically publish only after all checks.
18. Expose one release-wheel CLI.
19. Keep provider/network, DB query, model, PAPER execution, promotion, signing/submission, and LIVE absent.
20. Run Python/Rust/repository-safety/ARM64 CI.
21. Freeze design/plan docs.
22. Run exact final-head four-gate CI.
23. Guarded squash merge only after 4/4 GREEN.
24. Seal merged-main.
25. Produce a new immutable ARM64 release through the existing `seal:` release path.
26. Next: protected PAPER deployment and genuine host evidence execution.

TDD RED: `a950cfe3df9f97ab376132950e49acee4c361f46`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
