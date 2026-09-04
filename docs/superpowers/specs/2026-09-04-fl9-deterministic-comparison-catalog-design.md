# FL9 Deterministic Comparison Catalog — Design

**Date:** 2026-09-04

## Status

Design after same-population deterministic candidate matrix merged as
`d57eb0f22b84bff88b03f185d48fc7adbf208499` (PR #180).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Define one explicit, immutable, cross-language FL9 deterministic comparison set
instead of allowing callers to silently choose lifecycle combinations.

The catalog contains the complete Cartesian product of the already-sealed
deterministic lifecycle families:

- entry: FL6.1 Impulse Scalp;
- entry: FL6.2 Micro Pullback;
- entry: FL6.3 Pre-Graduation;
- entry: FL6.4 Graduation Flow;
- manager: FL6.5 Wallet/Cohort;
- manager: FL6.6 Longer Runner.

That produces exactly **8** lifecycle candidates.

The catalog is a comparison reference set only. It does not designate a winner,
does not claim profitability, and does not tune from outcome evidence.

## Rust authority

Add a storage-side module:

`fast_deterministic_comparison_catalog.rs`

Rust remains authoritative for:

- the selected reference FL6 policy parameters;
- lifecycle entry target exposure;
- lifecycle reduction fraction;
- candidate version strings;
- strategy version strings;
- candidate manifest fingerprints;
- catalog ordering and fingerprint.

Python must decode and verify; it must not recreate these thresholds.

## Catalog schema

`shreks.fast_deterministic_comparison_catalog`, version 1.

Fields:

- `schema_name`;
- `schema_version`;
- `catalog_version = "fl9-deterministic-comparison-v1"`;
- `candidates` — exactly eight canonical authenticated
  `FastDeterministicCandidateManifestWire` values;
- `catalog_fingerprint_sha256`.

The fingerprint covers every field except itself through canonical JSON SHA-256.

## Candidate identity

Candidate versions are lexical and stable:

1. `fl9-baseline-graduation-flow-longer-runner-v1`
2. `fl9-baseline-graduation-flow-wallet-cohort-v1`
3. `fl9-baseline-impulse-scalp-longer-runner-v1`
4. `fl9-baseline-impulse-scalp-wallet-cohort-v1`
5. `fl9-baseline-micro-pullback-longer-runner-v1`
6. `fl9-baseline-micro-pullback-wallet-cohort-v1`
7. `fl9-baseline-pre-graduation-longer-runner-v1`
8. `fl9-baseline-pre-graduation-wallet-cohort-v1`

Strategy versions use the same pair without the `fl9-baseline-` prefix and with
`-v1`.

## Explicit lifecycle sizing

Every catalog candidate uses explicit lifecycle policy version 1 with:

- `entry_target_exposure_fraction = 0.8`;
- `reduce_remaining_fraction = 0.5`.

These are catalog v1 reference parameters, not hidden defaults. Any future
change requires a new catalog version and new candidate fingerprints.

## Explicit component reference policies

Use the existing sealed reference-policy values already exercised by the
candidate-manifest contract tests. Move them into catalog construction without
adding production `Default` implementations.

This avoids silently inventing a second set while giving FL9 one auditable
comparison target.

## Exporter

Add narrow binary:

`shreks-fast-deterministic-catalog`

No arguments.

It writes exactly one canonical catalog JSON document to stdout and nothing
else.

The binary has no DB, provider, network, PAPER, risk, promotion, signer, or LIVE
authority.

## Python decoder

Add:

- `FastDeterministicComparisonCatalog`;
- `decode_fast_deterministic_comparison_catalog(payload)`.

The decoder:

1. requires canonical JSON;
2. requires exact schema/catalog version;
3. verifies catalog fingerprint;
4. decodes every embedded candidate through the already-sealed candidate
   manifest decoder;
5. requires exactly eight unique lexical candidate versions and fingerprints;
6. requires the exact 4 × 2 family Cartesian product once each.

No Python policy thresholds are introduced.

## Shared golden

Add one canonical JSON fixture generated from the Rust catalog builder.

Rust tests and Python tests both consume the same fixture and assert exact
fingerprints/order.

## TDD

RED first.

Rust RED proves missing catalog module/API.

Python RED proves missing catalog decoder/model.

GREEN proves:

- exactly eight candidates;
- exact lexical versions;
- complete 4 × 2 pair coverage;
- deterministic repeat;
- all candidate manifests materialize through existing Rust manifest seam;
- catalog fingerprint changes if any candidate identity changes;
- Rust encoder/decoder and Python decoder agree on shared golden;
- binary stdout equals shared golden;
- no provider/PAPER/risk/promotion/LIVE authority.

## Following slice

Build the evidence-spec binder that maps one immutable FL8.1 chronological
population to the eight catalog candidates using explicit per-family strategy
evidence and shared contemporaneous PAPER quote context, then invoke the sealed
candidate matrix.

Real economic evaluation remains fail-closed until non-fixture evidence exists.
