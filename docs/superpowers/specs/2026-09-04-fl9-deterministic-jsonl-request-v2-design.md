# FL9 Deterministic Campaign JSONL Request v2 — Design

**Date:** 2026-09-04

## Status

Implementation slice after the PyArrow-free runtime training bundle merged as
`0b049bf9584d95dcd11de1f120fd8d8a9531a063` (#201).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

The real host evidence path now has a dependency-free FL8.1 logical bundle and a canonical Rust
feature exporter that emits JSONL. The deterministic FL9 baseline request, however, still requires
`feature_parquet_path`, forcing the campaign launcher back through the PyArrow-only persistence
path.

Silently allowing JSONL through a field named `feature_parquet_path` would weaken the existing
versioned contract and make sealed request provenance ambiguous.

## Decision

Preserve request schema v1 exactly and add request schema v2 for canonical JSONL.

The schema name remains:

`shreks.fast_deterministic_campaign_request`

Versions:

- v1: existing `feature_parquet_path` request;
- v2: explicit `feature_jsonl_path` request.

Both versions use the same canonical tagged JSON codec, strict exact-field validation, immutable
request fingerprint, economic/risk policy types, point-in-time contexts, destination semantics, and
campaign writer.

## Request v1 compatibility

The existing v1 dataclass, builder, request field order, schema version, canonical encoding, and
fingerprint material are unchanged.

The shared decoder continues to accept old v1 payloads and reconstruct the exact v1 request type.

The runner keeps v1 behavior unchanged:

`feature_parquet_path -> read_fast_training_feature_parquet`.

Existing sealed v1 request and invocation evidence therefore remains readable without migration.

## Request v2

The v2 request type replaces only the physical feature source field:

`feature_jsonl_path`.

The v2 builder requires an explicit `.jsonl` source path and uses the same policy/context fields as
v1.

Its canonical request fingerprint includes:

- the same schema name;
- schema version 2;
- the exact v2 request field set;
- the explicit `feature_jsonl_path` value;
- the same canonical encodings for dataclasses, enums, tuples, frozensets, and floats.

The v2 runner resolves the JSONL source as an immutable source file and calls only the sealed
`read_fast_training_feature_jsonl` parser. It never calls the Parquet reader.

After feature loading, v1 and v2 converge on the exact same deterministic campaign artifact writer.

## Invocation seal compatibility

The deterministic invocation seal remains the strict boundary that authenticates request bytes,
all file sources, and the produced campaign artifact.

Invocation schema versions now mirror request source semantics:

- invocation v1 -> request v1 / `feature_parquet_path`;
- invocation v2 -> request v2 / `feature_jsonl_path`.

The source snapshot schema follows the same version mapping.

Each invocation still contains exactly six source labels:

v1:
1. `candidate_binary_path`
2. `champion_path`
3. `comparison_catalog_path`
4. `entry_authority_binary_path`
5. `feature_parquet_path`
6. `observer_database_path`

v2:
1. `candidate_binary_path`
2. `champion_path`
3. `comparison_catalog_path`
4. `entry_authority_binary_path`
5. `feature_jsonl_path`
6. `observer_database_path`

The observer database continues to authenticate the database plus WAL when present; volatile SHM
state remains excluded.

The invocation reader decodes the sealed request first, derives the expected invocation/source
schema from that request version, and rejects cross-version source or manifest substitution.

## Mutation/race guarantees

Both versions preserve the existing fail-closed behavior:

- request bytes are reread after campaign execution;
- all sources are fingerprinted before and after execution;
- source changes abort and remove the generated campaign;
- the reopened campaign artifact fingerprint must equal the writer result;
- request file hash, request logical fingerprint, source snapshot fingerprint, and campaign
  fingerprint are all bound into the invocation fingerprint;
- existing campaign/invocation destinations are never overwritten.

## Downstream proof compatibility

The learned comparison/proof layers consume deterministic invocation seals through the strict
invocation reader.

They do not require `feature_parquet_path` specifically.

Therefore v2 invocation seals can feed the existing #198/#199 proof chain without creating a new
economic comparison format or bypassing the same-population controls.

## Authority boundary

This slice changes only local immutable feature-source transport into the existing deterministic
campaign.

It adds no:

- provider/network calls;
- SQLite mutation;
- PAPER state mutation outside the already-sealed campaign writer;
- champion training or promotion;
- transaction intent;
- signing;
- transaction submission;
- LIVE enablement.

## TDD provenance

Intentional RED commits:

- `4be039b0192c4c6ff34e672bf478adbead3df5c5`
- `770483d461584057bcd10b2240ce3df187e637c9`

The RED contract required explicit v2 request/invocation APIs while preserving v1 behavior.

Verified production head before documentation:

`f37cec4a4a84d0589541f55a141040e733d3263f`

CI `33893824593`:

- Repository safety: GREEN
- Python: GREEN — 3115 passed
- Rust: GREEN
- ARM64 release build: GREEN

## Following work

With #200, #201, and this slice, the release/runtime path can transport authenticated native proof
tools, export canonical FL8.1 JSONL, assemble the logical training bundle without PyArrow, and feed
that same canonical JSONL into the deterministic FL9 baseline campaign.

The next slice should build the first genuine non-fixture FL8.5 champion and evidence-plan from real
runtime data using only dependency-free model families:

- `MEAN_REGRESSOR` for continuous targets;
- `PRIOR_CLASSIFIER` for binary targets.

It must derive chronological training/validation/test intervals from the real evidence population,
fail closed if the population is too immature, and explicitly package the selected champion before
any learned/deterministic comparison is run.

LIVE remains disabled.
