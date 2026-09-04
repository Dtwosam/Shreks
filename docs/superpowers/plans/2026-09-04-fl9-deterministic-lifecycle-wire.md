# FL9 Deterministic Lifecycle Canonical Wire — Implementation Plan

**Date:** 2026-09-04
**Base:** `471834933420dbfb1e34ffa465843bece93eca2d`

## TDD

1. Commit shared golden lifecycle-result JSON fixture.
2. Commit Rust RED tests for missing wire module/API and golden round-trip.
3. Commit Python RED tests for missing package/decoder/assessment translation.
4. Open draft PR and record exact RED.
5. Implement Rust wire conversion/validation/fingerprint/codec.
6. Implement Python models/decoder/translation with identical validation.
7. Run full repository four-gate CI.
8. Freeze exact GREEN head and guarded squash merge.

## Scope

Rust:
- one new storage wire module;
- storage exports;
- one Rust test.

Python:
- one focused package;
- focused model/codec tests;
- one shared golden fixture.

Docs:
- design;
- plan.

No provider/database/PAPER execution/risk/promotion/LIVE changes.

## Following work

Full deterministic candidate config manifest/fingerprint, then PAPER execution adapter and real chronological evidence campaign.
