# FL9 Learned Comparison Request — Implementation Plan

**Date:** 2026-09-04
**Base:** `6ed40f89d6bf55bbda534d9e1de64cdc99a1002f` (#198)

1. RED canonical learned-comparison request/runner contract.
2. Add strict schema `shreks.fast_learned_comparison_request` v1.
3. Authenticate request payload with canonical SHA-256 fingerprint.
4. Carry explicit per-source-event FLAT/OPEN action constraints.
5. Carry optional learned-candidate entry authority with market/price provenance.
6. Content-authenticate the learned Rust decision binary.
7. Reopen the authenticated deterministic baseline invocation and campaign.
8. Authenticate the supplied champion against the sealed invocation source fingerprint.
9. Require request source-event population exactly equal the immutable baseline comparison bundle before learned execution.
10. Reuse the baseline bundle's exact features, quotes, regime, and dynamic risk environment.
11. Inherit starting ledger, fill, risk, position, and evaluation policies from the sealed baseline request.
12. Run the existing state-aware learned chronological PAPER campaign.
13. Re-authenticate binary, champion, request, and baseline invocation after execution.
14. Require learned event-population fingerprint exactly equal baseline campaign population.
15. Delegate immutable learned-vs-baseline proof publication to the sealed #198 writer.
16. Strict-read and return the completed proof artifact.
17. Keep provider/network, operational-storage, signing/submission, and LIVE authority absent.
18. Update durable design/plan.
19. Run exact-head Python/Rust/ARM64/repository-safety CI.
20. Guarded squash merge.
21. Next: locate/produce real non-fixture authenticated FL9 runtime inputs and execute the first genuine learned-vs-baseline evidence campaign.
22. Preserve the measured economic result truthfully: `SUPERIOR`, `FAILED`, or `INSUFFICIENT_EVIDENCE`.

TDD RED: `a9e7eebc66bd2d63ae30fe0aade87259b5129071`.

FL9 remains EVIDENCE PENDING until real non-fixture evidence exists. LIVE remains disabled.
