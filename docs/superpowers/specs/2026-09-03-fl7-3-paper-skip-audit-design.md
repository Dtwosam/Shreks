# FL7.3 Fast Lane PAPER SKIP Audit — Design

## Status

Design for build-order phase **FL7.3 SKIP**.

Base: FL7.2 is SEALED at merged-main commit `10d5db43e52d3317e06e78dd189dcf78071d9285` with fresh merged-main CI run `33749284225` four-gate green.

LIVE remains disabled.

## Build-order requirement

The canonical build order says:

> **FL7.3 SKIP** — Record why a valid observed opportunity was skipped and preserve its future labels.

FL7.3 must make SKIP decisions durable and researchable without creating fills, positions, synthetic execution evidence, or future leakage.

## Goal

Persist every valid Fast Lane PAPER `SKIP` assessment as an append-only audit record tied to the canonical FastEvent decision identity, and expose a read path that later joins the already-versioned FL4 future-path labels for that same decision.

A SKIP record answers:

- what event/state caused the assessment;
- which strategy/version produced it;
- why the action was `SKIP`;
- which canonical market event anchors the decision;
- which FL4 label version should be used when future evidence becomes available.

It does **not** claim that future labels already exist when the SKIP is recorded.

## Non-goals

FL7.3 does not:

- alter any FL6 strategy evaluator;
- reinterpret `SKIP` reasons in Python;
- create a `TradeIntent`;
- request or simulate a quote/fill;
- mutate the PAPER ledger;
- create a position or cash movement;
- create placeholder FL4 labels;
- calculate future labels itself;
- change FL4/FL5 research semantics;
- add provider I/O, background polling, wall-clock reads, or randomness;
- add signer/submission/deployment/LIVE authority.

## Storage ownership

Preserve the repository's existing operational-storage rule:

- Rust `shreks-storage` owns SQLite migrations.
- Python may read/write an already-migrated operational database through stdlib `sqlite3`.
- Python must not create or migrate the FL7.3 table itself.
- Opening a missing database must fail closed rather than silently create a new one.

Migration `0017_fast_paper_skip_records.sql` adds one append-only table: `fast_paper_skip_records`.

## Durable record

Each row stores:

- deterministic `record_id` (SHA-256);
- `record_version = fl7.3-v1`;
- FL7.1 assessment version;
- source event ID;
- Fast Lane market key;
- source sequence;
- assessment timestamp;
- strategy family and version;
- ordered reasons as canonical JSON;
- canonical FastEvent decision signature and ordinal;
- canonical mint, quote mint, and venue;
- required FL4 future-path label version.

The table has a logical uniqueness fence over:

`(source_event_id, strategy_family, strategy_version, assessment_version)`.

This means an exact replay is idempotent, while a second row claiming different reasons, market/time, or canonical decision linkage for the same logical assessment is a conflict and fails closed.

## Canonical decision linkage

New immutable Python input:

`FastPaperSkipLabelLink`

Fields:

- `decision_signature: str`
- `decision_ordinal: int`
- `mint: str`
- `quote_mint: str`
- `venue: str`
- `future_path_label_version: int`

`record_fast_paper_skip(...)` requires the supplied assessment to be `FastPaperAction.SKIP` and validates that the linked `fast_events` row exactly matches:

- signature + ordinal;
- assessment `source_sequence`;
- assessment `as_of_unix_ms`;
- supplied mint;
- supplied quote mint;
- supplied venue.

The storage layer enforces the same canonical relationship with triggers rather than a new direct foreign key. This is deliberate: migration 12 rebuilt `fast_events` as the canonical cross-venue journal and replaced its original single-source FK model with venue-aware trigger integrity so Pump bonding-curve and PumpSwap evidence can share one append-only journal.

Migration 17 therefore adds:

- `fast_paper_skip_records_canonical_source_guard`, which rejects a SKIP row unless the complete canonical FastEvent identity, sequence, market, venue, and observation time match; and
- `fast_paper_skip_records_restrict_canonical_delete`, which rejects deletion of a FastEvent referenced by a SKIP audit row.

Together these preserve both forward canonical validation and reverse delete restriction without weakening the journal's established migration-12 integrity model.

`market_key` remains the Fast Lane orchestration key and is persisted verbatim. FL7.3 does not invent a parser that tries to reinterpret that opaque compatibility key as canonical market identity.

## Future-label preservation without future leakage

The critical invariant is:

**Recording SKIP never writes to `fast_future_path_labels`.**

At decision time the future path may not be complete yet. Creating placeholder or guessed labels would violate the point-in-time research boundary.

Instead the SKIP row stores the canonical FL4 decision identity and required label version. A later read:

`load_fast_paper_skip_with_future_labels(database_path, record_id)`

joins `fast_future_path_labels` using:

- `decision_signature`;
- `decision_ordinal`;
- `future_path_label_version`.

Therefore:

- immediately after SKIP, the returned label tuple may be empty;
- when FL4 later writes one or more horizons, the same immutable SKIP record resolves those labels automatically;
- labels from a different FL4 version are not silently mixed in;
- the SKIP record itself is never rewritten when labels arrive.

This satisfies "preserve its future labels" by preserving the exact versioned linkage, not by copying future information into the decision-time record.

## Public Python contract

`python/src/shreks_brain/fast_paper/skip.py` owns the small FL7.3 API:

- `FAST_PAPER_SKIP_AUDIT_VERSION = "fl7.3-v1"`
- `FastPaperSkipAuditError`
- `FastPaperSkipLabelLink`
- `FastPaperSkipAuditRecord`
- `FastPaperSkipFutureLabel`
- `FastPaperSkipAuditView`
- `record_fast_paper_skip(...)`
- `load_fast_paper_skip_with_future_labels(...)`

The existing `FastPaperActionAssessment` remains the source assessment type; FL7.3 does not introduce another action model.

## Record identity

`record_id` is deterministic SHA-256 over a canonical UTF-8 payload containing all stable audit content:

- record version;
- assessment version;
- source event ID;
- market key;
- source sequence;
- assessment timestamp;
- strategy family/version;
- ordered reasons;
- canonical decision signature/ordinal;
- canonical mint/quote/venue;
- future-path label version.

Exact content therefore produces the same ID across restart/replay.

The logical uniqueness fence is still required because a conflicting replay would otherwise produce a different hash and create a second row.

## Canonical reasons

Assessment reasons are preserved in the original order.

Storage uses compact canonical JSON equivalent to:

`json.dumps(list(reasons), ensure_ascii=False, separators=(",", ":"))`

On read, malformed JSON, a non-list value, empty reasons, or non-string/blank reasons fails closed.

## Future-label read model

`FastPaperSkipFutureLabel` exposes the existing FL4 evidence without reinterpretation, including:

- horizon/version/completeness;
- coverage complete-through timestamp and contiguity;
- event count and no-trade state;
- endpoint identity/time/price;
- endpoint return;
- MFE/MAE;
- time to peak/trough;
- reversal evidence;
- minimum/endpoint exit capacity;
- route unavailability evidence;
- best/endpoint cost-adjusted return.

Labels are returned ordered by `horizon_ms ASC`.

FL7.3 performs no action-label transformation. FL5 remains the separate counterfactual/action-label research boundary.

## Failure behavior

Fail closed when:

- the database path does not exist;
- migration 0017/table is absent;
- assessment is not `SKIP`;
- canonical decision link is missing or contradictory;
- sequence/time/market identity differs from canonical FastEvent evidence;
- an existing logical SKIP key has different stored content;
- stored reasons or numeric/boolean label fields are malformed;
- SQLite query/write fails.

An exact duplicate save returns the same decoded record without adding another row.

## Transaction behavior

`record_fast_paper_skip` uses `BEGIN IMMEDIATE` around duplicate detection and insert so two writers cannot turn one logical assessment into ambiguous audit history.

The function commits only the SKIP row. No other table is mutated.

## Migration

Migration 17 adds:

- table `fast_paper_skip_records`;
- canonical-source insert guard trigger tied to the exact `fast_events` decision identity;
- reverse-delete restriction trigger protecting referenced FastEvents;
- index for future-label joins;
- index for market/time research scans.

Existing migrations are not rewritten. The repository-wide storage compatibility contract advances from schema 16 to 17. `database.rs` adds the new migration/table/index expectations, while every pre-existing storage test that explicitly pinned the latest schema number is mechanically advanced from 16 to 17. Their behavioral assertions are unchanged.

## TDD proof requirements

RED establishes that both required boundaries are absent before implementation:

- focused Rust test `crates/shreks-storage/tests/fl7_paper_skip_migration.rs` expects schema version 17, the FL7.3 table, its indexes, and singular migration application before migration 0017 exists;
- Python tests import the FL7.3 public API before `skip.py`/exports exist.

Intentional RED was verified in CI run `33750634673`:

- Repository safety GREEN;
- Rust RED only on `schema_version` 16 versus required 17 in the new focused migration test;
- Python RED only on missing FL7.3 public symbols;
- native ARM64 release build GREEN.

GREEN tests cover:

1. only `SKIP` assessments are accepted;
2. exact SKIP persistence preserves ordered reasons and metadata;
3. exact replay is idempotent;
4. conflicting replay fails closed;
5. canonical event identity/sequence/time/market contradictions fail closed;
6. saving SKIP does not create a future label;
7. future labels attached later become visible through the immutable SKIP link;
8. a different FL4 label version is not mixed in;
9. multiple horizons are returned in ascending horizon order;
10. label fields are preserved without reinterpretation;
11. missing/unmigrated database fails closed;
12. migration 17 is applied exactly once and produces the expected table, indexes, and canonical-integrity triggers;
13. generic storage schema/reopen/upgrade compatibility advances to version 17 without changing preserved evidence;
14. every existing storage test that pins the latest schema advances mechanically from 16 to 17;
15. existing Python/Rust suites remain green.

## Scope

Expected changed files are exactly 18:

- `docs/superpowers/specs/2026-09-03-fl7-3-paper-skip-audit-design.md`
- `docs/superpowers/plans/2026-09-03-fl7-3-paper-skip-audit.md`
- `crates/shreks-storage/migrations/0017_fast_paper_skip_records.sql`
- `crates/shreks-storage/src/lib.rs` — migration registration only
- `crates/shreks-storage/tests/database.rs` — generic schema-version/table/index compatibility only
- `crates/shreks-storage/tests/fl7_paper_skip_migration.rs` — focused migration/table/index/trigger expectations only
- `crates/shreks-storage/tests/fast_event_storage.rs` — schema-version pin only
- `crates/shreks-storage/tests/fl3_execution_economics_source.rs` — schema-version pin only
- `crates/shreks-storage/tests/fl4_future_path_labels.rs` — schema-version pin only
- `crates/shreks-storage/tests/outcome_checkpoints.rs` — schema-version pin only
- `crates/shreks-storage/tests/paper_quote_storage.rs` — schema-version pin only
- `crates/shreks-storage/tests/pump_migration_storage.rs` — schema-version pin only
- `crates/shreks-storage/tests/pump_swap_trade_evidence_storage.rs` — schema-version pin only
- `crates/shreks-storage/tests/pump_trade_evidence_storage.rs` — schema-version pin only
- `crates/shreks-storage/tests/safety_evidence_storage.rs` — schema-version pin only
- `python/src/shreks_brain/fast_paper/skip.py`
- `python/src/shreks_brain/fast_paper/__init__.py` — export-only
- `python/tests/test_fast_paper_skip_audit.py`

No PAPER fill, ledger, risk, provider, existing FL4 label writer, Rust strategy evaluator, signer, deployment, or LIVE authority file should change.

## Exit criterion

FL7.3 is complete when every valid Fast Lane `SKIP` can be durably and idempotently audited with exact reasons and canonical decision identity, and later versioned FL4 future-path labels can be retrieved for that immutable skipped opportunity without any decision-time future leakage or capital behavior.
