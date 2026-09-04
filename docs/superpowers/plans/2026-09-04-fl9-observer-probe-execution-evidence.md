# FL9 Observer-Probe Execution Evidence — Implementation Plan

**Date:** 2026-09-04
**Base:** `7fee5ef7f7ec00ab1d2b12cefa353a9017b70805` (#189)

1. RED: define canonical observer-probe sizing/capacity contract.
2. Read historical token decimals and exact ENTRY/EXIT quotes through the sealed read-only observer store.
3. Reconstruct directional PAPER quote evidence once.
4. Derive intended base quantity only from executable ENTRY output.
5. Derive conservative proven exit capacity only from executable EXIT input.
6. Return no champion execution evidence when either direction is unavailable.
7. Preserve positive undersized EXIT capacity for FL6 SKIP semantics.
8. Delegate forecast construction only to the sealed authenticated champion adapter.
9. Remove duplicate quote/raw-amount conversion from the hydrator.
10. Require hydrated execution size/capacity to match canonical probe values.
11. Require exit-capacity provenance to equal the exact EXIT probe source identity.
12. Lock write/network/LIVE authority firewall.
13. Update durable docs.
14. Run exact-head four-gate CI.
15. Guarded merge.
16. Next: reproducible real campaign-input assembler and immutable bundle execution.

FL9 economic superiority remains EVIDENCE PENDING. LIVE remains disabled.
