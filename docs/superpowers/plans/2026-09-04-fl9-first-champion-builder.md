# FL9 Dependency-Free First Champion Builder — Implementation Plan

**Date:** 2026-09-04
**Base:** `41adf1c75142d178df5ab951a117c0a8a060ff9b` (#202)

1. Add an intentional RED contract for a first-champion composition API.
2. Keep the sealed FL8.5 public API exact and unchanged.
3. Add isolated `shreks_brain.fast_first_champion`.
4. Fix the required FL9 target set to endpoint cost-adjusted return, raw endpoint return, MAE, reversal probability, and route-unavailability probability.
5. Fix continuous members to sealed `MEAN_REGRESSOR`.
6. Fix binary members to sealed `PRIOR_CLASSIFIER`.
7. Require exact caller-supplied chronological validation policy.
8. Require exact caller-supplied FL8.4 point-in-time context corpus.
9. Require TEST-only FL8.4 evaluation policy.
10. Require explicit selection reference/time/reason.
11. Require selection time after the latest TEST interval plus target horizon.
12. Require a positive explicit minimum TEST scored-observation floor for every member.
13. Run sealed FL8.3 validation separately for every required target.
14. Run sealed FL8.4 TEST evaluation separately for every required target.
15. Derive final refit identities only from target-mature pre-selection decisions.
16. Refit with the existing FL8.2 subset trainer; add no new forecasting math.
17. Verify every runtime artifact remains chronologically mature at selection.
18. Package exact artifact/run/report triples through sealed FL8.5.
19. Return the five artifacts, validation runs, TEST reports, and champion as one immutable result.
20. Cross-link every returned champion member to the exact artifact/run/report evidence.
21. Keep heavy dependencies, databases, providers, PAPER execution, transaction authority, and LIVE absent.
22. Run exact-head Python/Rust/repository-safety/ARM64 CI.
23. Guarded squash merge only after 4/4 GREEN.
24. Seal merged-main with the same four gates.
25. Next: file-backed host request + authenticated FL8.4 context corpus over #201 runtime evidence.

TDD RED: `016efcfffe99c1f77f83ad89d554edf4f6d9fd5a`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
