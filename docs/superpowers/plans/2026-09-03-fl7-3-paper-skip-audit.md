# FL7.3 Fast Lane PAPER SKIP Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist valid Fast Lane PAPER `SKIP` assessments with exact reasons and canonical FastEvent identity, then resolve versioned FL4 future-path labels later without future leakage.

**Architecture:** Rust `shreks-storage` owns migration 0017 and Python `shreks_brain.fast_paper` reads/writes only an already-migrated SQLite database. SKIP rows are append-only/idempotent and store a canonical FL4 decision link; future labels remain in `fast_future_path_labels` and are joined on read rather than copied at decision time. Canonical FastEvent linkage follows the repository's migration-12 journal pattern: exact insert validation plus reverse-delete restriction through SQLite triggers rather than a new direct FK layered onto the rebuilt cross-venue journal.

**Tech Stack:** Rust, rusqlite, SQLite WAL migrations, Python 3.12 stdlib `sqlite3`, dataclasses, SHA-256, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-fl7-3-paper-skip-audit-design.md`

## Global Constraints

- Base is sealed FL7.2 merge `10d5db43e52d3317e06e78dd189dcf78071d9285`.
- LIVE remains disabled.
- Rust owns schema migration; Python does not create/migrate operational tables.
- Recording SKIP must never mutate `fast_future_path_labels`.
- No fill, `TradeIntent`, risk decision, PAPER ledger mutation, provider I/O, wall clock, signer, submission, or LIVE authority.
- Exact replay must be idempotent; conflicting replay must fail closed.
- Future labels are joined only by canonical decision identity and exact FL4 label version.

---

### Task 1: Freeze the RED contract

**Files:**
- Create: `crates/shreks-storage/tests/fl7_paper_skip_migration.rs`
- Create: `python/tests/test_fast_paper_skip_audit.py`

**Interfaces:**
- Consumes: existing `FastPaperActionAssessment`, `FastPaperAction`, operational SQLite schema.
- Produces: required public FL7.3 names and migration-17 expectations that production code must satisfy.

- [x] **Step 1: Make Rust migration expectations RED**

Add a focused migration test requiring schema version `17`, table `fast_paper_skip_records`, indexes `idx_fast_paper_skip_records_future_labels` and `idx_fast_paper_skip_records_market_time`, and migration version 17 exactly once across reopen.

- [x] **Step 2: Add the Python RED test file**

The test imports:

```python
from shreks_brain.fast_paper import (
    FAST_PAPER_SKIP_AUDIT_VERSION,
    FastPaperSkipAuditError,
    FastPaperSkipLabelLink,
    FastPaperSkipAuditRecord,
    FastPaperSkipFutureLabel,
    FastPaperSkipAuditView,
    record_fast_paper_skip,
    load_fast_paper_skip_with_future_labels,
)
```

The behavioral matrix asserts:

- `FAST_PAPER_SKIP_AUDIT_VERSION == "fl7.3-v1"`;
- non-SKIP assessment rejected;
- exact save preserves assessment/link/reasons;
- exact replay idempotent and row count stays one;
- same logical assessment with different reasons/link fails closed;
- canonical event sequence/time/mint/quote/venue mismatch fails closed;
- save does not create future labels;
- inserting FL4 labels later makes them visible without rewriting the SKIP row;
- wrong FL4 label version remains excluded;
- horizons sort ascending;
- MFE/MAE/reversal/capacity/cost-adjusted fields round-trip;
- missing database and database without migration 0017 fail closed.

- [x] **Step 3: Run canonical CI on intentional RED**

Verified run `33750634673`:

- Repository safety GREEN;
- Rust RED only on the new migration-17 test (`schema_version` 16 versus required 17);
- Python RED only on the missing FL7.3 public import;
- ARM64 release build GREEN.

Production code was not written until those failure signatures were confirmed.

- [x] **Step 4: Commit RED**

RED consists only of the focused Rust migration test and the new Python behavioral test after the already-committed design/plan.

---

### Task 2: Add Rust-owned migration 0017

**Files:**
- Create: `crates/shreks-storage/migrations/0017_fast_paper_skip_records.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Modify: `crates/shreks-storage/tests/database.rs`
- Modify: existing storage tests that explicitly pin the latest schema version
- Test: `crates/shreks-storage/tests/fl7_paper_skip_migration.rs`

**Interfaces:**
- Consumes: existing `fast_events` canonical identity and `fast_future_path_labels` research table.
- Produces: append-only `fast_paper_skip_records` schema owned by Rust migration version 17.

- [x] **Step 1: Create the table**

Required columns:

```text
record_id
record_version
assessment_version
source_event_id
market_key
source_sequence
as_of_unix_ms
strategy_family
strategy_version
reasons_json
decision_signature
decision_ordinal
decision_mint
decision_quote_mint
decision_venue
future_path_label_version
```

Constraints:

- non-empty strings;
- non-negative timestamps/ordinals;
- positive source sequence and label version;
- 64-character record ID;
- logical uniqueness `(source_event_id, strategy_family, strategy_version, assessment_version)`.

Do not add a new direct FK to `fast_events`. Migration 12 rebuilt that journal as a cross-venue canonical table with trigger-backed source integrity. FL7.3 must preserve that established journal model.

- [x] **Step 2: Add canonical-integrity triggers**

Before insert, require a `fast_events` row matching:

```sql
signature = decision_signature
ordinal = decision_ordinal
sequence = source_sequence
mint = decision_mint
quote_mint = decision_quote_mint
venue = decision_venue
observed_at_unix_ms = as_of_unix_ms
```

Otherwise `RAISE(ABORT, 'fast PAPER SKIP decision must match canonical FastEvent')`.

Also add a reverse-delete restriction on `fast_events`: if a SKIP row references the old signature/ordinal, abort deletion with `FastEvent is referenced by Fast PAPER SKIP audit`.

This preserves both forward exact canonical validation and reverse reference protection without weakening migration-12 journal integrity.

- [x] **Step 3: Add research indexes**

```sql
CREATE INDEX idx_fast_paper_skip_records_future_labels
    ON fast_paper_skip_records (
        decision_signature, decision_ordinal, future_path_label_version
    );

CREATE INDEX idx_fast_paper_skip_records_market_time
    ON fast_paper_skip_records (
        decision_mint, decision_quote_mint, decision_venue, as_of_unix_ms
    );
```

- [x] **Step 4: Register migration 17**

Append only:

```rust
Migration {
    version: 17,
    name: "fast_paper_skip_records",
    sql: include_str!("../migrations/0017_fast_paper_skip_records.sql"),
},
```

Prior migrations remain unchanged.

- [x] **Step 5: Advance storage compatibility expectations**

Update `crates/shreks-storage/tests/database.rs` only for the new schema boundary:

- expected schema version 16 -> 17;
- migration singularity loops include 17;
- generic table inventory includes `fast_paper_skip_records`;
- generic index inventory includes both FL7.3 indexes;
- existing reopen and legacy upgrade-preservation assertions remain otherwise unchanged.

The focused migration test also requires both FL7.3 trigger names to exist.

An exhaustive repository code search found ten exact assertions pinning `diagnostics().unwrap().schema_version` to 16. `database.rs` is one; the other nine storage tests are advanced mechanically to 17 with no behavioral changes:

- `fast_event_storage.rs`
- `fl3_execution_economics_source.rs`
- `fl4_future_path_labels.rs`
- `outcome_checkpoints.rs`
- `paper_quote_storage.rs`
- `pump_migration_storage.rs`
- `pump_swap_trade_evidence_storage.rs`
- `pump_trade_evidence_storage.rs`
- `safety_evidence_storage.rs`

---

### Task 3: Implement the Python SKIP audit boundary

**Files:**
- Create: `python/src/shreks_brain/fast_paper/skip.py`
- Modify: `python/src/shreks_brain/fast_paper/__init__.py`
- Test: `python/tests/test_fast_paper_skip_audit.py`

**Interfaces:**
- Consumes: `FastPaperActionAssessment`, operational SQLite tables `fast_events`, `fast_paper_skip_records`, `fast_future_path_labels`.
- Produces: the FL7.3 public API listed in Task 1.

- [x] **Step 1: Define immutable models and validation**

Implement:

```python
FAST_PAPER_SKIP_AUDIT_VERSION = "fl7.3-v1"

class FastPaperSkipAuditError(ValueError): ...

@dataclass(frozen=True, slots=True)
class FastPaperSkipLabelLink:
    decision_signature: str
    decision_ordinal: int
    mint: str
    quote_mint: str
    venue: str
    future_path_label_version: int
```

`FastPaperSkipAuditRecord` contains deterministic `record_id`, version, the original `FastPaperActionAssessment`, and `FastPaperSkipLabelLink`.

`FastPaperSkipFutureLabel` mirrors the existing FL4 derived-label fields without action reinterpretation.

`FastPaperSkipAuditView` contains one record plus `tuple[FastPaperSkipFutureLabel, ...]`.

- [x] **Step 2: Implement deterministic canonical record identity**

Build compact canonical JSON over all stable record content, preserving reason order, then SHA-256 the UTF-8 bytes.

No wall-clock values enter the record ID.

- [x] **Step 3: Open only an existing operational database**

Before connecting, require `Path(database_path).is_file()`.

Connect in existing read/write mode; enable foreign keys; set `sqlite3.Row` row factory; require table `fast_paper_skip_records` exists.

A missing file/table raises `FastPaperSkipAuditError`.

- [x] **Step 4: Implement `record_fast_paper_skip`**

Validation order:

1. assessment/link types;
2. assessment action exactly `FastPaperAction.SKIP`;
3. canonical FastEvent exact match;
4. create deterministic incoming record;
5. `BEGIN IMMEDIATE`;
6. look up logical key;
7. exact stored match -> rollback/read-only idempotent return;
8. differing stored row -> rollback + typed conflict;
9. insert incoming row;
10. commit;
11. return decoded record.

The function never touches `fast_future_path_labels`.

- [x] **Step 5: Implement `load_fast_paper_skip_with_future_labels`**

Lookup by 64-character `record_id`.

If no SKIP row exists, raise typed error rather than fabricating a record.

Select FL4 labels where:

```sql
decision_signature = record.link.decision_signature
AND decision_ordinal = record.link.decision_ordinal
AND label_version = record.link.future_path_label_version
ORDER BY horizon_ms ASC
```

Decode all existing FL4 fields into immutable label objects. Empty label tuple is valid before future coverage exists.

- [x] **Step 6: Export only FL7.3 symbols**

Update `fast_paper/__init__.py` without changing existing FL7.1/FL7.2 imports or behavior.

---

### Task 4: Candidate verification and history cleanup

**Files:** all 18 planned FL7.3 files only.

- [x] **Step 1: Audit PR scope**

Expected files exactly:

1. FL7.3 design doc
2. FL7.3 plan doc
3. migration 0017
4. `shreks-storage/src/lib.rs`
5. `shreks-storage/tests/database.rs`
6. `shreks-storage/tests/fl7_paper_skip_migration.rs`
7. `shreks-storage/tests/fast_event_storage.rs`
8. `shreks-storage/tests/fl3_execution_economics_source.rs`
9. `shreks-storage/tests/fl4_future_path_labels.rs`
10. `shreks-storage/tests/outcome_checkpoints.rs`
11. `shreks-storage/tests/paper_quote_storage.rs`
12. `shreks-storage/tests/pump_migration_storage.rs`
13. `shreks-storage/tests/pump_swap_trade_evidence_storage.rs`
14. `shreks-storage/tests/pump_trade_evidence_storage.rs`
15. `shreks-storage/tests/safety_evidence_storage.rs`
16. `fast_paper/skip.py`
17. `fast_paper/__init__.py`
18. `python/tests/test_fast_paper_skip_audit.py`

- [ ] **Step 2: Run candidate canonical CI**

Require all four canonical gates GREEN.

- [ ] **Step 3: Collapse post-RED authoring history**

Preserve exactly:

`design -> plan -> RED -> implementation`

The clean implementation commit must point to the same final tree as the proven candidate.

- [ ] **Step 4: Verify clean compare**

Require exactly four commits ahead of sealed FL7.2 and exactly the 18 planned files.

- [ ] **Step 5: Run fresh exact-clean-head CI**

Require all four canonical gates GREEN on the immutable clean head.

---

### Task 5: Guarded merge and seal

- [ ] **Step 1: Update PR body with RED/candidate/clean proof and scope audit**
- [ ] **Step 2: Mark PR ready**
- [ ] **Step 3: Guarded merge using `expected_head_sha` equal to the verified clean head**
- [ ] **Step 4: Require fresh push-triggered merged-main four-gate CI on returned merge SHA**
- [ ] **Step 5: Mark PR body `SEALED` only after merged-main CI is fully GREEN**

After FL7.3 is SEALED, branch FL7.4 from that verified merge and connect `HOLD/REDUCE/SELL` to preserved PAPER position/exit accounting.

## Completion Claim Boundary

Do not claim FL7.3 SEALED before both exact-head and fresh merged-main canonical CI are green.

Do not claim profitability, LIVE readiness, or capital authority from FL7.3.
