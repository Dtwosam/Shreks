# FL9 Deterministic Lifecycle Canonical Wire — Design

**Date:** 2026-09-04

## Status

Design after explicit deterministic lifecycle candidates merged as `471834933420dbfb1e34ffa465843bece93eca2d` (PR #171).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Create one canonical, cross-language result wire for explicit deterministic lifecycle decisions so Rust-produced baseline decisions can be consumed by Python Fast PAPER infrastructure without pretending they are learned-policy forecast results.

The existing learned `FastCampaignDecisionResult` includes model-specific reward/risk/horizon fields. Deterministic FL6 lifecycles do not produce those values. They must not be filled with zero/sentinel/fabricated values merely to reuse the learned schema.

## Schema

`shreks.fast_deterministic_lifecycle_results`, version `1`.

### Policy wire

- lifecycle version;
- entry baseline kind;
- manager baseline kind;
- entry target exposure fraction;
- REDUCE remaining-exposure fraction.

### Decision wire

- source event ID;
- market key;
- source sequence;
- as-of timestamp;
- posture: `FLAT` or `OPEN`;
- selected component kind;
- selected component version;
- action;
- current exposure fraction, nullable only for FLAT;
- target exposure fraction.

No learned forecast fields exist in this schema.

### Batch

- schema name;
- schema version;
- policy;
- ordered decisions;
- `batch_fingerprint_sha256`.

## Batch fingerprint boundary

The batch fingerprint covers the canonical JSON representation of:

- schema name/version;
- lifecycle policy wire;
- all ordered decision wire fields.

It excludes only `batch_fingerprint_sha256` itself.

This hash is explicitly a **decision-batch fingerprint**.

It is **not** the final deterministic candidate/config fingerprint because the merged lifecycle result does not retain every underlying component policy/evidence parameter. A later manifest slice must create full candidate provenance before PAPER identity can claim a candidate fingerprint.

## Rust surface

Add `crates/shreks-storage/src/fast_deterministic_lifecycle_wire.rs`.

Public:

- schema constants;
- wire structs;
- `FastDeterministicLifecycleWireError`;
- `fast_deterministic_lifecycle_to_wire(...)`;
- `encode_fast_deterministic_lifecycle_results_json(...)`;
- `decode_fast_deterministic_lifecycle_results_json(...)`.

Conversion accepts only the sealed `FastDeterministicLifecycleBatchAssessment`.

## Validation

Rust and Python both fail closed on:

- wrong schema;
- empty decisions;
- invalid policy family pair;
- invalid exposure fractions;
- duplicate source identity;
- per-market sequence non-increase;
- per-market timestamp regression;
- posture/component mismatch;
- invalid action for posture;
- invalid current-exposure nullability/range;
- target exposure inconsistent with the explicit lifecycle policy;
- component version mismatch for the declared FL6 kind;
- malformed/non-lowercase SHA-256;
- fingerprint mismatch;
- non-canonical JSON on Python decode.

## Python package

Add:

`python/src/shreks_brain/fast_deterministic_lifecycle/`

with exact immutable dataclasses and codec.

Public:

- schema constants;
- policy/decision/results dataclasses;
- `decode_fast_deterministic_lifecycle_results(...)`;
- `fast_deterministic_lifecycle_to_paper_assessment(...)`.

### Fast PAPER assessment translation

Translation requires caller-supplied:

- assessment version;
- strategy family;
- strategy version.

It maps exact identity/action and emits truthful reasons only:

- component kind;
- component version;
- posture;
- current exposure (or `none`);
- target exposure.

It does not synthesize model reward, risk, horizon, or forecast values.

## Shared golden fixture

Commit one canonical JSON fixture under:

`python/tests/fixtures/fast_deterministic_lifecycle_results_v1.json`.

Both Rust and Python tests consume the exact same fixture and verify the same batch fingerprint/canonical representation.

This is the cross-language codec seal.

## Authority boundary

This slice does not:

- source quotes;
- execute PAPER;
- build entry authority;
- create risk context;
- mutate a ledger;
- create E11/E5 evidence;
- evaluate superiority;
- create a final candidate/config fingerprint;
- promote;
- enable LIVE.

## Next slice

Create a full deterministic candidate manifest/config fingerprint, then add a PAPER executor adapter that consumes this lifecycle decision wire plus explicit contemporaneous PAPER evidence through the sealed FL7/E11/E5 path.

No synthetic fills. No fake candidate provenance.
