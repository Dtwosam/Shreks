# FL9 Point-in-Time Comparison Evidence Hydrator — Implementation Plan

**Date:** 2026-09-04
**Base:** `a2d8919a7d675405d414e749ae1e241dfba90f59` (#186)

1. RED: define strict batch hydration API and real observer-store integration test.
2. Add positional hydration input/result contracts.
3. Read Helius token decimals + exact observer ENTRY/EXIT quotes as-of each row evaluation clock.
4. Reconstruct directional quote-denominated PAPER evidence without swapping directions.
5. Validate quote chronology and market attribution.
6. Lock risk price-impact fields to persisted ENTRY quote evidence.
7. Require exact shared execution economics across FL6.1–FL6.4.
8. Require explicit forecast/cost/capacity source provenance when execution evidence exists.
9. Derive PAPER entry authority only through the sealed FL3 offline adapter.
10. Attach exact catalog candidate authority coverage.
11. Emit positional comparison rows + provenance.
12. Keep immutable bundle writing as the next separate call.
13. Update durable docs.
14. Run exact-head Python, Rust, ARM64, and repository-safety CI.
15. Guarded merge.
16. Next: hydrate a real chronological FL8.1 population, write the v2 bundle, and run the eight-candidate PAPER matrix.

FL9 economic superiority remains EVIDENCE PENDING. LIVE remains disabled.
