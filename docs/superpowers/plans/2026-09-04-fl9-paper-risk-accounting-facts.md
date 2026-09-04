# FL9 Shared PAPER Risk Accounting Facts — Implementation Plan

**Date:** 2026-09-04
**Base:** `a8e8b68a449ca48afacc94cd6d9b959d33fea822`

1. Add RED tests for shared accounting facts and observer delegation.
2. Open draft PR and capture missing helper RED.
3. Add pure `paper.risk_facts` model + derivation.
4. Export through `shreks_brain.paper`.
5. Refactor observer risk-context builder to consume shared facts.
6. Preserve all observer output/error behavior.
7. Run full four-gate CI.
8. Freeze exact GREEN head and guarded squash merge.

No deterministic risk policy, execution, superiority, promotion, or LIVE logic
is added in this slice.
