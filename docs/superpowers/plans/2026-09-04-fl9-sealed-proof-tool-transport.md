# FL9 Sealed Proof-Tool Transport — Implementation Plan

**Date:** 2026-09-04
**Base:** `238ed6cfc08f2f802d057355a4729be25321dd90` (#199)

1. Add RED contracts for authenticated native proof-tool transport.
2. Define `shreks.fast_proof_tools` v1.
3. Fix the canonical native tool set to the FL8.1 exporter, FL9 entry-authority binary, and FL9 campaign-decision binary.
4. Bind every tool to exact size and SHA-256 plus exact source SHA and native platform.
5. Add canonical manifest fingerprinting and strict decoder validation.
6. Add staging-package creation with no overwrite.
7. Add package verification with exact member-set and byte authentication.
8. Add completed-wheel verification.
9. Require wheel payload bytes to equal the native release binaries produced in the same build.
10. Package the sealed tool payload under `shreks_brain._sealed_fast_tools`.
11. Preserve the historical G2 top-level release payload allowlist unchanged.
12. Extend the native release build to compile the three offline proof executables.
13. Stage the nested package before wheel build.
14. Verify the nested package inside the completed wheel before release bundling.
15. Add private source-SHA-scoped materialization with `0700` executable permissions.
16. Make materialization idempotent only for already-authentic existing bytes.
17. Fail closed on materialized drift, symlinks, wrong platform, wrong source SHA, or tampered nested package.
18. Keep provider/network, SQLite, PAPER mutation, campaign execution, promotion, signing, submission, and LIVE authority absent.
19. Run full Python/Rust/repository-safety/native ARM64 CI on the exact head.
20. Guarded squash merge only after 4/4 GREEN.
21. Run merged-main four-gate CI and seal.
22. Next: build the PAPER-only on-host real-evidence runner using the sealed transported tools and existing protected runtime state.

TDD RED: `feb8ebafabaa1106826b13a1725b558e6a809414`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
