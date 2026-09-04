# FL9 Sealed Proof-Tool Transport — Design

**Date:** 2026-09-04

## Status

Implementation slice after the authenticated learned-comparison request merged as
`238ed6cfc08f2f802d057355a4729be25321dd90` (#199).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

The verified production release currently contains the running PAPER binaries plus the
manifest-hashed Python wheel, but the real FL9 evidence path also requires three native offline
executables that were not part of the release payload:

- `export_fast_training_features`;
- `shreks-fast-entry-authority`;
- `shreks-fast-campaign-decision`.

Those tools already exist and are independently tested in the repository, but a genuine on-host
FL9 proof run must use exact binaries from the same verified immutable source release rather than
building ad hoc on the VPS or copying unverified executables around the deployment boundary.

## Compatibility constraint

The historical G2 root verifier accepts an exact top-level release payload allowlist. Expanding that
allowlist directly would make the first newer release unverifiable by the already-installed older
root verifier.

Therefore this slice keeps the top-level G2 payload contract unchanged.

The three offline proof tools are transported inside the existing Shreks wheel, which is already a
top-level manifest-hashed release payload. This is the same compatibility pattern already used for
sealed deployment-control scripts.

## Nested package

The copied Python build tree receives:

`shreks_brain/_sealed_fast_tools/`

containing exactly:

- `__init__.py`;
- `manifest.json`;
- `export_fast_training_features.bin`;
- `shreks-fast-campaign-decision.bin`;
- `shreks-fast-entry-authority.bin`.

Setuptools package-data includes only the manifest and native `.bin` payloads for this package.

## Manifest contract

Schema:

`shreks.fast_proof_tools` v1.

The manifest binds:

- exact 40-character source commit SHA;
- exact supported native GNU platform;
- exact canonical three-tool name set;
- byte size for every tool;
- SHA-256 for every tool;
- canonical manifest fingerprint.

The canonical tool order is fixed:

1. `export_fast_training_features`;
2. `shreks-fast-campaign-decision`;
3. `shreks-fast-entry-authority`.

Unknown, missing, duplicate, reordered, malformed, non-canonical, or tampered entries fail closed.

## Release build

The release builder compiles the two existing runtime binaries plus all three proof binaries in the
same native release build.

Before wheel construction it:

1. computes the nested manifest from the actual native release binaries;
2. stages exact binary bytes into the copied Python build tree;
3. creates the sealed nested package.

After wheel construction it:

1. opens the completed wheel;
2. requires the exact nested member set;
3. decodes and authenticates the nested manifest;
4. verifies every embedded binary's size and SHA-256;
5. verifies every embedded binary matches the just-built native source binary.

Only after those checks pass may the wheel enter the ordinary G2 release staging tree.

The top-level release manifest continues to contain only the historical G2 payload set.

## Materialization contract

Runtime/research orchestration may materialize the nested proof tools to a caller-supplied private
directory.

Materialization:

- requires explicit expected source SHA and platform;
- re-verifies the nested package first;
- writes under a source-SHA-specific directory;
- writes executable tool files with owner-only `0700` permissions;
- persists the authenticated nested manifest;
- is idempotent only when existing bytes and manifest are still exact;
- rejects local drift rather than replacing an existing modified toolset;
- rejects symlinked package/tool destinations.

The package helper itself does not choose `/var/lib/shreks` or any operational path. The later
on-host proof runner owns that deployment/runtime decision.

## Authority boundary

This slice performs artifact transport, hashing, verification, and private file materialization
only.

It does not:

- open or query SQLite;
- export production features itself;
- train or select models;
- run deterministic or learned campaigns;
- collect provider/network data;
- mutate PAPER state;
- promote a champion;
- construct, sign, or submit a transaction;
- enable LIVE.

The three transported native tools retain their already-sealed offline semantics; transport does
not grant them additional authority.

## TDD provenance

Intentional RED:

`feb8ebafabaa1106826b13a1725b558e6a809414`

The RED was isolated to the absent new Python transport API. Rust tests, ARM64 release build, and
repository safety remained green.

An implementation ARM64 run later failed before compilation because the build-script edit contained
a literal escaped newline argument. That shell-formatting defect was corrected without changing the
transport design.

## Verification targets

The slice is sealed only when an exact final head proves:

- canonical manifest round trip;
- exact name/source/platform/size/hash authentication;
- missing/unknown/duplicate/tamper rejection;
- staging package verification;
- wheel member-set verification;
- wheel bytes equal native build outputs;
- private idempotent materialization;
- materialized drift rejection;
- unchanged historical top-level G2 release allowlist;
- existing G2 workflow/release tests remain green;
- full Python suite;
- full Rust suite;
- native ARM64 release build;
- repository safety.

## Following work

Once sealed and deployed through the existing verified release path, the VPS can possess
source-authenticated offline binaries required by the real FL9 evidence chain without widening SSH
or root-state access.

The next slice should build the PAPER-only on-host proof preparation/execution path under the
existing `shreks` service identity. It should materialize these tools, read the real protected
runtime evidence through already-authorized paths, create immutable non-fixture FL8.1/FL9 inputs,
execute the sealed request/proof chain, and preserve the measured result exactly as
`SUPERIOR`, `FAILED`, or `INSUFFICIENT_EVIDENCE`.

LIVE remains disabled.
