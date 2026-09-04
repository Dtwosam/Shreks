# FL9 Deterministic PAPER Prefix-Replay Session — Implementation Plan

**Date:** 2026-09-04
**Base:** `66413bc881292cf7ce4accff975106e60cb8d0c0`

## TDD

1. Commit RED tests for canonical lifecycle-result builder and prefix-replay session.
2. Open draft PR and record exact missing APIs.
3. Add canonical Python lifecycle result builder.
4. Add immutable prefix-replay session + posture reconstruction.
5. Export APIs.
6. Run existing deterministic PAPER adapter and learned executor regressions.
7. Run full four-gate CI.
8. Freeze exact GREEN head and guarded squash merge.

## Scope

Python lifecycle codec/models exports, Fast Campaign PAPER session module/exports, focused tests, docs.

No Rust strategy, provider, database, promotion, or LIVE changes.

## Following work

Canonical stateful Rust row-evaluator protocol, then chronological real-evidence campaign orchestration.
