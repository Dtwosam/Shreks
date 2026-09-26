# Fast Lane Runtime Feature Feed — Design

**Date:** 2026-09-26  
**Base main SHA:** `a10388126fc4eb0c9c5c96cf2c940c6c820be4d4`  
**Migration plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Add a bounded, deterministic, restart-safe feature feed for the learned Fast Lane
PAPER runtime without changing the active PAPER service or mutating the
authoritative PaperLedger.

The feed must emit the same canonical point-in-time Fast Lane feature rows used
by training, but it must select runtime decisions directly from unseen
`fast_events` rather than from future-path labels.

## Source and snapshot semantics

The runtime feed reads only the existing current-schema observer SQLite database
through `ShreksDb::open_existing_read_only(...)`.

One batch:

1. opens a SQLite read snapshot/savepoint;
2. captures the current maximum canonical FastEvent sequence;
3. authenticates the supplied cursor against the exact stored event identity;
4. selects at most the requested number of events with sequence greater than
   the cursor and no greater than the snapshot watermark;
5. constructs decision rows directly from those canonical events;
6. reuses the exact shared FastMarketState replay/snapshot feature builder used
   by the sealed training exporter;
7. releases the snapshot;
8. returns the rows plus the captured watermark.

Events appended after the read snapshot begins are not visible to the current
batch and belong to the next batch.

## No future-label authority

The runtime feed must not read or import:

- `fast_future_path_labels`;
- future-path label generation;
- training target/counterfactual code;
- training economics labels.

For runtime decision rows:

- event identity comes from `fast_events`;
- executable entry price is the event's canonical price;
- training-only `decision_entry_total_quote` remains absent unless a later
  separately reviewed point-in-time execution-economics feed supplies it.

## Shared feature construction

The current training exporter already computes features correctly from canonical
event/lifecycle replay. Its replay/snapshot construction must be factored into a
shared internal path used by both:

- labeled historical training export; and
- unlabeled runtime feature feed.

A parity test must prove that when both paths select the same canonical event
and the training decision carries no extra entry-total economics, the resulting
feature row is byte/struct identical.

## Runtime batch protocol

Rust schema:

`shreks.fast_paper_runtime_feature_batch` version 1.

The batch binds:

- requested previous cursor, if any;
- captured snapshot max sequence;
- ordered feature records;
- deterministic batch fingerprint.

Cursor identity is explicit:

- decision sequence;
- decision signature;
- decision ordinal;
- decision observed timestamp.

A non-empty cursor must match the exact persisted canonical event or the batch
fails closed.

## Binary and immutable transport

Add release-local:

`export_fast_runtime_features`

It accepts:

`<observer-db> <maximum-decisions> [<sequence> <signature> <ordinal> <observed-at-ms>]`

It opens the database read-only and prints exactly one canonical JSON batch to
stdout.

The historical `shreks.fast_proof_tools` v1 three-tool package is an immutable
compatibility surface and must remain exactly unchanged. The runtime feature
exporter therefore travels in a separate nested wheel package:

`shreks_brain/_sealed_fast_runtime_tools/`

with `shreks.fast_runtime_tools` v1 binding exact source SHA, platform, tool
name, size, tool SHA-256, and manifest fingerprint. Private materialization
writes the executable as owner-only `0700` and rejects drift.

It has no provider, signer, transaction, PAPER-ledger, training-label, score, or
LIVE authority.

## Python runtime adapter

`shreks_brain.fast_paper_runtime` will:

- advance manifest schema to v2;
- bind the feature-feed binary path and SHA-256;
- use explicit cursor identity fields;
- invoke the exact bound binary;
- strictly decode and authenticate its batch;
- reuse the canonical Python training-feature record decoder;
- verify rows are strictly ordered, unseen, and bounded by the snapshot
  watermark;
- return the records plus the deterministic next runtime state.

The adapter does not persist the state automatically and does not execute any
economic action.

## No-scoring / no-execution boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
FUTURE_LABEL_ACCESS=FORBIDDEN
COUNTERFACTUAL_ACCESS=FORBIDDEN
ACTIVE_SYSTEMD_PAPER_RUNTIME=UNCHANGED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
FAST_LANE_PAPER_EXECUTION=NOT_GRANTED
CHAMPION_PROMOTION=BLOCKED
LIVE=DISABLED
```
