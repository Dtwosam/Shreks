# FL9 Deterministic Campaign PAPER Evidence Selector — Implementation Plan

**Date:** 2026-09-04
**Base:** `022e4de7e6dc210b7019721ab6055e89a0bab6d6`

1. Add RED tests for SKIP/BUY/position evidence projection and driver integration.
2. Open draft PR and record missing API RED.
3. Add immutable raw campaign PAPER evidence model.
4. Add pure action-aware materializer.
5. Change chronological campaign rows to store raw evidence.
6. Materialize after Rust decision and before sealed PAPER session step.
7. Update campaign tests to provide rich pre-decision evidence.
8. Run full four-gate CI.
9. Freeze exact GREEN head and guarded squash merge.

No sealed PAPER executor behavior changes.

Following work: deterministic same-population candidate matrix and superiority
evidence bundle.
