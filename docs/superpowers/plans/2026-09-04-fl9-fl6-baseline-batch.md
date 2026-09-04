# FL9 FL6 Ordered Baseline Campaign Batch — Implementation Plan

**Date:** 2026-09-04  
**Base:** `3cbc494aa2ceb7be5f641113ed2045ca7d596b2d`

## Goal

Add deterministic batch evaluation for one homogeneous FL6 baseline across ordered exact FL8.1 rows.

## Scope

Production:

- new `crates/shreks-storage/src/fast_baseline_batch.rs`;
- storage root export wiring.

Tests:

- new `crates/shreks-storage/tests/fl9_fast_baseline_batch.rs`.

Docs:

- design;
- plan.

No migrations/provider/runtime/PAPER/risk/promotion/LIVE changes.

## TDD sequence

1. Commit RED contract tests with missing module/API.
2. Open draft PR and record exact Rust missing-contract failure.
3. Implement:
   - request wrapper;
   - homogeneous baseline-kind validation;
   - ordered single-row campaign evaluation;
   - duplicate/per-market order validation;
   - exact-order output.
4. Run full four-gate CI.
5. Freeze exact GREEN head.
6. Update PR provenance.
7. Guarded squash merge using expected head SHA.

## Error model

Use explicit batch errors for:

- empty batch;
- mixed baseline kind;
- indexed single-row campaign failure;
- duplicate source event identity;
- sequence regression;
- timestamp regression.

Do not convert a row failure into SKIP/NotApplicable.

## Following work

Build authoritative per-row evidence adapters and then feed learned/baseline streams through the same FL7 PAPER quote/fill/accounting path before the sealed FL9 superiority proof.
