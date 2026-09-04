# FL9 Explicit Deterministic Lifecycle Baselines — Implementation Plan

**Date:** 2026-09-04
**Base:** `2bd91693fbac62c79fbd012cfc019a35a894926a`

## Goal

Create explicit complete deterministic comparison candidates from one sealed FL6 entry family + one sealed FL6 manager, with explicit sizing and no hidden defaults.

## Scope

Production:

- new `crates/shreks-storage/src/fast_deterministic_lifecycle.rs`;
- storage root exports.

Tests:

- new `crates/shreks-storage/tests/fl9_fast_deterministic_lifecycle.rs`.

Docs:

- design;
- plan.

No migration/provider/runtime/PAPER/risk/promotion/signer/LIVE files.

## TDD

1. Commit RED public contract tests.
2. Open draft PR and capture missing-module RED.
3. Implement policy validation.
4. Implement FLAT entry dispatch/mapping.
5. Implement OPEN manager dispatch/mapping.
6. Implement ordered batch duplicate/sequence/time validation.
7. Full four-gate CI.
8. Freeze exact GREEN head.
9. Update PR provenance and guarded squash merge.

## Following slice

Add a canonical cross-language wire/codec/fingerprint for lifecycle decisions so each deterministic candidate can be translated into the already-sealed Python Fast PAPER executor and FL9 run-evidence proof pipeline.

FL9 remains **EVIDENCE PENDING**.
