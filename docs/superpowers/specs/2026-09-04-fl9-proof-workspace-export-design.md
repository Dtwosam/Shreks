# FL9 Sealed Proof Workspace Export — Design

**Date:** 2026-09-04

## Status

Implementation slice after the file-backed first champion request merged and sealed as
`8fb1576d6d1270e513bbecd01b56ea715e927198` (#205).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Remove the remaining manual step between a deployed release and production-shaped FL8.1 feature
evidence.

The release wheel already carries three authenticated offline proof tools under #200. The first
tool, `export_fast_training_features`, is the sealed Rust read-only FL8.1 exporter.

This slice provides a small host-side PAPER command that:

1. materializes the exact release-bound native proof tools;
2. executes only the sealed Rust feature exporter against the private runtime database;
3. proves the database/WAL content did not change during export;
4. validates the resulting JSONL using the sealed Python FL8.1 reader;
5. publishes an immutable, strictly reopenable proof workspace.

It does not create FL8.4 contexts or a champion. Those remain later evidence gates.

## Command

The release wheel exposes:

`shreks-fast-proof-workspace`

Required arguments:

- `--database`
- `--destination`
- `--tool-root`
- `--release-source-sha`
- `--platform`
- `--timeout-seconds`

There are no hidden runtime defaults.

The release source SHA and platform must be supplied explicitly so the command cannot silently use a
native payload from a different release or architecture.

## Tool materialization

The workspace calls sealed #200:

`materialize_fast_proof_tools(...)`.

That function already:

- verifies the embedded package manifest;
- requires exact release source SHA and platform;
- verifies all three native payload hashes/sizes;
- materializes the canonical tool set into a private source-SHA directory;
- enforces executable mode 0700;
- rejects local drift rather than overwriting it.

The workspace then rereads the materialized proof-tools manifest and binds its manifest fingerprint
plus the exact exporter binary SHA into the workspace manifest.

Only `export_fast_training_features` is launched in this slice.

The entry-authority and campaign-decision binaries are transported/materialized but not executed.

## Database source seal

Before export, the workspace captures:

- SHA-256 of the main SQLite database;
- SHA-256 of the SQLite `-wal` file when present.

Each hash read checks file device/inode/size/mtime before and after streaming the bytes.

SQLite `-shm` remains excluded as volatile coordination state, matching the existing deterministic
invocation/proof boundaries.

After feature export and JSONL validation, the database + optional WAL snapshot is captured again.

The snapshots must be exactly equal.

A database/WAL mutation means no workspace is published, even if the Rust SQLite read itself
returned a transactionally consistent snapshot. This preserves a simple immutable source identity
for later proof artifacts.

## Export execution

The exporter is launched with a direct argv vector:

`[exporter, database, new_features_jsonl]`.

No shell is used.

The caller supplies a positive timeout.

A timeout, OS execution error, non-zero exit status, missing output, symlink output, malformed JSONL,
or source race fails closed.

Captured process stdout/stderr is not persisted into the evidence artifact.

The Rust executable itself uses `ShreksDb::open_existing_read_only` and its sealed FL8.1 feature
writer.

## Feature validation

After successful native export, Python calls the existing:

`read_fast_training_feature_jsonl(...)`.

The workspace requires:

- non-empty valid FL8.1 rows;
- canonical row/sequence constraints already enforced by the reader;
- JSONL byte SHA equal to `FastTrainingFeatureDataset.source_sha256`.

No PyArrow is involved.

The feature file is made private mode 0600 before publication.

## Workspace schema

Schema:

`shreks.fast_proof_workspace` v1.

The output directory contains exactly:

- `features.jsonl`;
- `manifest.json`.

The directory is staged privately and only renamed into place after strict reopen.

## Manifest

The manifest binds:

- schema name/version;
- release source SHA;
- platform;
- proof-tools manifest fingerprint;
- exporter binary SHA;
- observer database SHA;
- optional observer WAL SHA;
- feature JSONL byte SHA;
- feature logical fingerprint;
- row count;
- min/max decision sequence;
- min/max decision observed timestamp;
- top-level artifact fingerprint.

The artifact fingerprint is SHA-256 over canonical manifest material excluding itself.

The manifest is compact sorted UTF-8 JSON with exactly one trailing newline.

## Strict reopen

`read_fast_proof_workspace(...)` requires:

- a real non-symlink directory;
- exactly two regular files;
- exact manifest key set;
- canonical JSON;
- valid source/fingerprint formats;
- manifest fingerprint recomputation;
- feature file SHA recomputation;
- strict FL8.1 JSONL reread;
- logical fingerprint equality;
- row-count equality;
- decision sequence/timestamp bound equality.

A feature file copied from another workspace or modified after publication is rejected.

## Atomicity and privacy

The destination must not already exist.

Staging uses a sibling temporary directory with mode 0700.

Feature and manifest files are set to mode 0600.

The staged directory is strict-read before rename.

Any failure removes staging.

If the destination appears during work, publication fails instead of overwriting it.

## Authority boundary

This slice adds no:

- provider/network access;
- Python SQLite query implementation;
- model training;
- FL8.4 context generation;
- champion selection;
- PAPER order execution;
- trade-intent construction;
- signer;
- transaction submission;
- LIVE authority.

The only child process is the authenticated offline Rust feature exporter.

## TDD provenance

Intentional RED:

`28f90387738fa2ad7046411854e2a5be76eb593f`.

RED behavior:

- Python fails because `shreks_brain.fast_proof_workspace` is absent;
- repository safety remains GREEN.

Tests cover:

- authenticated tool materialization contract;
- successful sealed export;
- DB/WAL source binding;
- feature logical/byte evidence;
- database mutation rejection;
- exporter failure rejection;
- no-overwrite behavior;
- strict feature tamper rejection;
- console-script installation surface;
- authority firewall.

## Following work

The feature-source gap is closed by this slice.

The next real-evidence gap is FL8.4 context hydration.

The next slice should reconstruct as much context as can be proven from existing read-only observer
evidence, while keeping non-derivable fields explicit:

- map FL8.1 decision mint/venue/time to one unambiguous observer candidate;
- reconstruct point-in-time market regime using sealed observer regime replay and explicit policies;
- hydrate executable exit capacity only from a matching persisted directional EXIT quote;
- bind expected cost only from an explicit versioned execution-cost policy;
- attribute the learned strategy family explicitly, never based on future outcome;
- fail rows that are ambiguous or lack required evidence rather than filling them.

The resulting corpus can then feed #205 and produce the first genuine non-fixture champion if the
runtime data is mature enough.

LIVE remains disabled.
