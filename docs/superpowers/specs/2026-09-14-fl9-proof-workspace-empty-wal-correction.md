# FL9 Proof Workspace — Empty WAL Source-Seal Correction

**Date:** 2026-09-14  
**Status:** PR #297 GREEN; MERGE PENDING

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

Complete implementation head before this documentation-only status update:

`13fb2b64ce28c79b42e1bc8cb4d0f29eb96f3986`

GREEN CI:

`34836476709`

All four required PR gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

## Production boundary

The existing production release remains immutable and must not be patched in place.
After PR #297 merges and exact-main CI passes, production evidence may proceed only via
a new immutable ARM64 release and protected deployment.

The next physical proof attempt must still use explicit quiescence and a fresh immutable
workspace destination. No failed pre-correction workspace may be reused.
