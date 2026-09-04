# FL9 Deterministic Campaign Artifact — Design

**Date:** 2026-09-04

## Status

Implementation slice after canonical Fast policy run evidence batch codec merge
`4ad2ad60437a43634a45d012fa6654b7af946ce7` (#192).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Create one durable, immutable artifact for the complete deterministic comparison campaign without crossing into superiority or promotion.

The artifact workflow executes:

`assemble -> hydrate -> immutable v2 comparison bundle -> eight-candidate PAPER matrix -> canonical run batch -> root manifest`.

## Root layout

The published directory contains exactly:

- `comparison_bundle/`
- `comparison_catalog.json`
- `policy_runs.json`
- `manifest.json`

No other root entry is allowed when reading.

## Self-contained catalog

The existing Python comparison catalog decoder already authenticates the exact eight-candidate Rust-authored catalog.

This slice adds canonical Python encoding for the same object.

The encoder:

- accepts only exact `FastDeterministicComparisonCatalog`;
- serializes the exact eight candidate manifests;
- recomputes the existing catalog fingerprint material;
- refuses a catalog object whose stored fingerprint does not match;
- emits canonical compact sorted-key JSON.

The campaign artifact persists that exact catalog so future replay/audit does not depend on an external fixture path.

## Atomic publication

The destination is immutable and must not already exist.

The workflow creates a private staging directory next to the requested destination.

Every stage writes only into staging.

Only after:

1. assembly succeeds;
2. hydration succeeds;
3. comparison bundle succeeds;
4. catalog persistence succeeds;
5. all eight PAPER candidates succeed;
6. canonical run-batch encoding succeeds;
7. root manifest construction succeeds;
8. the complete staged artifact is read back through the strict artifact reader and its manifest round-trips exactly;

is the staging directory renamed to the final destination.

Any exception recursively removes staging.

A failed matrix, failed child artifact, or failed staged self-verification therefore never leaves a published partial campaign directory.

## Pipeline delegation

The workflow does not reproduce existing logic.

It calls only the sealed seams:

- `assemble_fast_deterministic_comparison_hydration_inputs`;
- `hydrate_fast_deterministic_comparison_evidence`;
- `write_fast_deterministic_comparison_evidence_bundle`;
- `run_fast_deterministic_comparison_catalog_matrix`;
- `encode_fast_policy_run_evidence_batch`.

The artifact layer is orchestration + authentication only.

## Root manifest

Schema:

`shreks.fast_deterministic_campaign_artifact` v1.

Manifest fields:

- catalog fingerprint;
- physical catalog-file SHA-256;
- comparison-bundle fingerprint;
- row count;
- shared event-population fingerprint;
- run count;
- run-batch logical fingerprint;
- physical run-file SHA-256;
- root artifact fingerprint.

Exactly eight runs are required.

The root artifact fingerprint hashes all manifest material except itself.

## Reader authentication

`read_fast_deterministic_campaign_artifact(...)` requires:

1. exact root entry set;
2. canonical root manifest;
3. valid root artifact fingerprint;
4. catalog physical SHA match;
5. catalog canonical decode + fingerprint match;
6. comparison bundle decode + bundle fingerprint match;
7. comparison bundle catalog fingerprint match;
8. comparison bundle row count match;
9. run file physical SHA match;
10. run batch logical fingerprint match;
11. canonical run-batch decode;
12. exact eight-run count;
13. run candidate versions match embedded catalog exactly;
14. run candidate fingerprints match embedded catalog exactly;
15. every run event-population fingerprint matches the root manifest.

The child codecs remain the source of truth for their own internal semantics and fingerprints.

## What this artifact proves

A successfully readable artifact proves that one immutable evidence population was used to execute all eight authenticated deterministic candidates and that the resulting PAPER run evidence is preserved without cross-candidate population drift.

It does **not** prove economic superiority.

## Authority boundary

The artifact module contains no:

- superiority evaluator call;
- promotion logic;
- LIVE runtime mode;
- signing/submission;
- provider/network client.

It does perform the already-sealed PAPER matrix through the existing comparison runner.

## TDD

Intentional RED commits:

- `1d27cf07cbe7ed6083d0614408afd49a8997a287` — missing canonical Python catalog encoder;
- `a04d379bc09db143fc2f35746d9d3e7d0af617d9` — missing campaign artifact workflow.

Tests require:

1. exact pipeline call order;
2. exact four-entry root layout;
3. exact catalog persistence;
4. physical run-file SHA;
5. root manifest fingerprint;
6. atomic failure cleanup;
7. child artifact reader authentication;
8. run-file tamper rejection;
9. no superiority/promotion/LIVE authority.

## Following slice

Add a durable command/input codec around this artifact API so a real non-fixture campaign can be launched from:

- exact FL8.1 Parquet;
- exact observer DB;
- authenticated champion;
- versioned execution policy;
- explicit point-in-time contexts;
- sealed Rust binaries;
- PAPER/risk/evaluation policies.

Then run that command on real post-selection evidence.
