# FL9 Deterministic Same-Population Candidate Matrix — Implementation Plan

**Date:** 2026-09-04
**Base:** `f2c2c5f66ae39f5424ac8e7d30fe5056572ad9f7`

1. Add RED tests for whole-matrix parity and action divergence.
2. Open draft PR and record missing API RED.
3. Add candidate spec + matrix result models.
4. Implement whole-matrix preflight:
   exact rows, state clocks, quote timeline, lexical unique candidates.
5. Run each spec through the sealed chronological campaign driver.
6. Verify final run-evidence population fingerprints and evaluation policy.
7. Export API.
8. Run full four-gate CI.
9. Freeze exact GREEN head and guarded squash merge.

No superiority calculation, provider I/O, execution formula, or LIVE authority.

Following work: real deterministic candidate manifest/evidence set and empirical
FL9 superiority campaign.
