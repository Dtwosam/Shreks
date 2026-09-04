# FL9 Stateful Deterministic Row Evaluation Protocol — Implementation Plan

**Date:** 2026-09-04
**Base:** `b24e35d98214d295fd8740e5513ccae17fcbc5fd`

## TDD

1. Add strict FL8.1 row decode tests and row-protocol RED tests.
2. Add candidate-manifest reverse materialization tests.
3. Open draft PR and record exact missing APIs.
4. Implement FL8.1 JSON row decoder.
5. Implement typed candidate manifest materialization.
6. Implement strict six-family evidence wires and one-row lifecycle evaluator.
7. Implement canonical response codec/fingerprint.
8. Add narrow storage CLI and byte-parity test.
9. Run full four-gate CI.
10. Freeze exact GREEN head and guarded squash merge.

## Scope

Rust storage module/exports/binary/tests plus design/plan. Python is unchanged in this slice.

## Following work

Dedicated Python offline row-evaluator adapter, then a chronological campaign driver that alternates Rust row evaluation with authoritative PAPER prefix replay and finally feeds same-population runs into the sealed FL9 superiority proof.
