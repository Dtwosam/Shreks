# FL9 Reproducible Comparison Input Assembly — Implementation Plan

**Date:** 2026-09-04
**Base:** `ff372a02c95f491ec6bfc0ac974f928c9b08f135` (#190)

1. RED: define versioned execution policy, point-in-time context, assembly result, and batch API.
2. Derive source event identity from each FL8.1 row.
3. Require exact positional context population.
4. Load canonical observer directional probe per row.
5. Delegate forecast/size/capacity construction to the sealed observer/champion adapter.
6. Validate returned champion execution proof against policy and probe.
7. Reconstruct graduation pre-snapshot only from the FL8.1 row.
8. Reuse one exact execution object across FL6.1–FL6.4.
9. Emit exact forecast/cost/capacity provenance.
10. Emit no execution/provenance when either directional route is unavailable.
11. Prove assembled inputs pass the sealed point-in-time hydrator.
12. Lock write/network/superiority/LIVE authority firewall.
13. Update durable docs.
14. Run exact-head four-gate CI.
15. Guarded merge.
16. Next: one durable artifact command for assemble -> hydrate -> bundle -> eight-candidate PAPER run.

FL9 economic superiority remains EVIDENCE PENDING. LIVE remains disabled.
