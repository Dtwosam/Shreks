# FL9 Proof Workspace — Empty WAL Source-Seal Correction

**Date:** 2026-09-14  
**Status:** SEALED FOR NEW IMMUTABLE RELEASE; PHYSICAL POST-FL4 PROOF NOT YET RE-RUN

## Production evidence

A post-FL4 production proof-workspace attempt on immutable release
`4fcbaee62ab33431875109edf98d9b0d5c01cbae` failed closed with:

```text
ValueError: Fast proof workspace database source changed during export
```

The attempt did not publish a workspace and restored the PAPER runtime successfully.
It was not an OOM, timeout, disk-pressure, or service-crash failure.

A subsequent fully quiesced source-stability probe established:

- all PAPER writers inactive;
- telemetry inactive;
- dashboard inactive;
- no open database holders before the probe;
- SQLite `PRAGMA data_version` remained stable;
- the main database physical metadata remained stable;
- no WAL existed before the read-only SQLite open;
- the read-only SQLite open created a zero-byte `-wal` plus `-shm`;
- the zero-byte WAL remained stable while the connection was open and after close.

Therefore the source-seal failure was a false positive caused solely by representing
`missing WAL` as `None` before export and `stable empty WAL` as the SHA-256 of zero bytes
after export.

## Correction

`fast_proof_workspace._capture_database(...)` keeps the existing stable-file SHA-256
read for any present WAL. After that stable read:

- missing WAL -> `None`;
- stable zero-byte WAL -> `None`;
- stable non-empty WAL -> its SHA-256 fingerprint.

This makes a missing WAL and an empty WAL equivalent only at the proof source-identity
layer. It does not delete, truncate, checkpoint, or otherwise mutate SQLite files.

## Fail-closed invariants preserved

The correction does not weaken these gates:

- any main database byte mutation still changes `database_sha256` and fails;
- creation of a non-empty WAL from an initially missing/empty WAL changes `wal_sha256`
  and fails;
- mutation of an existing non-empty WAL changes `wal_sha256` and fails;
- WAL hashing still uses the stable-file fingerprint routine, which rejects device,
  inode, size, or mtime changes while hashing;
- the workspace remains staged privately and publishes atomically only after strict
  readback;
- PAPER promotion remains blocked;
- LIVE remains disabled.

## TDD provenance

RED commit:

`c52f51badfb1b831c563516bfb8512e56e889b14`

RED CI:

`34835767633`

The Python suite failed only at:

```text
test_workspace_treats_exporter_created_empty_wal_as_absent
```

with the production-matching source-changed exception. The run reported
`1 failed, 3378 passed`.

Minimal implementation commit:

`fa22ca571af9679a972f65f770735ef37f3d839b`

The implementation normalizes only the stable SHA-256 of zero bytes to `None`.

Additional boundary-test commit:

`2b25e298f05122b989eed9f7701012356893b65a`

It proves absent and empty WAL states normalize identically while non-empty WAL bytes
remain SHA-bound.

PR #297 final exact-head CI:

`34836830034`

All four required PR gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Squash-merged implementation main:

`739652c97a65ce713df919b117f65f768a47df7f`

Exact merged-main CI:

`34837216746`

All four canonical main gates passed again:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

## Immutable release authorization

The implementation is now eligible for a follow-up main commit whose subject starts
with `seal:`. The repository release workflow recognizes that exact sealed source SHA
only after its push-to-main CI completes successfully, and then builds the immutable
ARM64 release from that exact SHA.

The release seal changes no runtime implementation beyond the already verified
`739652c97a65ce713df919b117f65f768a47df7f` tree except this documentary binding.

## Production boundary

The existing production release
`4fcbaee62ab33431875109edf98d9b0d5c01cbae` remains immutable and must not be patched
in place or reused for the post-correction proof attempt.

After this seal lands on `main`, the next production sequence is strictly:

1. exact sealed-main CI passes all four canonical gates;
2. automatic immutable ARM64 release for the exact sealed SHA completes and its three
   release assets verify;
3. protected deployment installs that exact release;
4. `/opt/shreks/current`, `RELEASE_MANIFEST.json`, and runtime process identity all bind
   to the sealed SHA;
5. PAPER, telemetry, and dashboard database readers are explicitly quiesced;
6. the database holder gate is empty;
7. a fresh post-FL4 proof workspace is generated at a new immutable destination;
8. the workspace must contain exactly `421278` feature rows and pass strict readback;
9. PAPER runtime is restored and health/restart gates pass.

No failed pre-correction workspace may be reused. Training economics and V2 champion
scoring remain separate later slices and are not authorized by this seal.

PAPER promotion remains **BLOCKED**.
LIVE remains **DISABLED**.
