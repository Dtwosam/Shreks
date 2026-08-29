# FL1 Fork Conflict Quarantine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the observe-only runtime alive when confirmed-fork replay delivers conflicting economics for an existing `(signature, ordinal)`, while durably quarantining the alternate evidence and preventing ambiguous identities from canonicalizing.

**Architecture:** Preserve the existing strict raw-evidence writers for callers/tests that require a hard conflict error. Add runtime-facing quarantine writers that persist the incoming conflicting variant into dedicated append-only tables and return a typed outcome instead of terminating the observer. Pending-normalization queries exclude identities with unresolved quarantine rows, so no ambiguous first-fork economics can become a FastEvent. Acceptance reporting exposes quarantine activity so physical-host evidence remains truthful.

**Tech Stack:** Rust, rusqlite/SQLite migrations, Tokio observer runtime, existing FL1 acceptance reporter.

**Spec:** `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`

## Global Constraints

- LIVE TRADING remains disabled.
- No signing, submission, wallet authority, strategy, risk, PAPER policy, or FL2 behavior changes.
- Preserve all conflicting evidence; never overwrite or silently accept disputed economics.
- The existing strict `record_*_trade_evidence` APIs must continue to fail closed on economic disagreement.
- Runtime quarantine is allowed only for the exact existing raw-evidence identity conflict; SQLite/clock/schema/validation failures remain fatal.
- Canonical normalization must skip any `(signature, ordinal)` with unresolved quarantined variants.
- All changes require RED tests before production implementation and full repository CI before merge.

---

### Task 1: Durable conflict quarantine storage

**Files:**
- Create: `crates/shreks-storage/migrations/0013_fast_lane_conflict_quarantine.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Modify: `crates/shreks-storage/src/fast_lane.rs`
- Modify: `crates/shreks-storage/src/pump_swap_fast_lane.rs`
- Test: `crates/shreks-storage/tests/fast_lane_conflict_quarantine.rs`

**Interfaces:**
- Produces: `EvidenceWriteOutcome::{Inserted, Duplicate, QuarantinedConflict}`.
- Produces: `ShreksDb::record_pump_trade_evidence_or_quarantine` and `record_pump_swap_trade_evidence_or_quarantine`.
- Produces: read-only conflict counters for acceptance evidence.

- [ ] **Step 1: Write failing storage tests**

Test that strict writers still return `StorageError::InvalidData` for changed economics. Test runtime-facing writers return `QuarantinedConflict`, preserve the original raw row, persist the incoming variant, and do not duplicate canonical source rows.

- [ ] **Step 2: Run the focused storage test and capture RED**

Run `cargo test -p shreks-storage --test fast_lane_conflict_quarantine` and require failure because the migration/types/APIs do not exist.

- [ ] **Step 3: Add migration 13**

Create dedicated Pump and PumpSwap conflict tables containing the complete incoming economic payload, provider, slot, and observation timestamp. Add indexes beginning with `(signature, ordinal)` so normalizer exclusion and diagnostics remain bounded. Do not mutate migrations 1-12.

- [ ] **Step 4: Add typed quarantine writers**

Keep strict writers unchanged. The new runtime-facing methods use the same validation and same-economic comparison; only an exact existing-identity economic disagreement is appended to the matching quarantine table and returned as `QuarantinedConflict`. Any other storage error propagates.

- [ ] **Step 5: Run focused storage tests GREEN**

Run `cargo test -p shreks-storage --test fast_lane_conflict_quarantine` and existing fork-replay/storage tests.

### Task 2: Prevent ambiguous canonicalization and keep realtime alive

**Files:**
- Modify: `crates/shreks-storage/src/fast_lane.rs`
- Modify: `crates/shreks-storage/src/pump_swap_fast_lane.rs`
- Modify: `crates/shreks-observer/src/runtime.rs`
- Test: `crates/shreks-observer/tests/pump_realtime_writer.rs` or the existing realtime-writer integration test file.
- Test: `crates/shreks-observer/tests/fast_event_normalizer.rs`

**Interfaces:**
- Consumes: `EvidenceWriteOutcome` from Task 1.
- Produces: runtime writer behavior where `QuarantinedConflict` is non-fatal but all other storage failures remain fatal.

- [ ] **Step 1: Write failing runtime tests**

Feed two notifications with the same raw identity and different economics. Assert the writer continues to a later unrelated valid notification, the conflict count increments, and the ambiguous identity never appears in pending-normalizer results while the unrelated identity does.

- [ ] **Step 2: Capture RED**

Run the focused observer tests and require current code to terminate on the conflicting write.

- [ ] **Step 3: Wire typed outcomes into the writer**

Use only the new quarantine methods in `run_pump_realtime_writer`. Increment the inserted-row counter only for `Inserted`; ignore `Duplicate` and `QuarantinedConflict` for the inserted count. Do not string-match error messages.

- [ ] **Step 4: Exclude quarantined identities from pending normalization**

Add `NOT EXISTS` predicates against the matching conflict tables in Pump and PumpSwap pending queries. The original raw evidence remains queryable for audit, but cannot become canonical until a future explicit resolver clears/resolves the quarantine.

- [ ] **Step 5: Run focused tests GREEN**

Run observer writer and normalizer tests plus the storage suite.

### Task 3: Make physical-host acceptance conflict-aware

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-fast-lane-acceptance/main.rs`
- Modify: `crates/shreks-observer/tests/fast_lane_acceptance_report.rs`
- Modify: `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`

**Interfaces:**
- Consumes: conflict count APIs from Task 1.
- Produces: report keys `pump_quarantined_conflicts` and `pumpswap_quarantined_conflicts` for the selected window/current unresolved state as supported by schema.

- [ ] **Step 1: Add failing reporter tests**

Seed one quarantined Pump and one PumpSwap conflict and require the acceptance report to expose them without altering raw/canonical counts.

- [ ] **Step 2: Capture RED**

Run `cargo test -p shreks-observer --test fast_lane_acceptance_report`.

- [ ] **Step 3: Add read-only reporter fields and runbook language**

Report quarantine counts explicitly. Document that a quarantined fork conflict is preserved evidence, not a duplicate and not a canonical event; unresolved conflict growth is an FL1.5 HOLD condition until reconciliation evidence exists.

- [ ] **Step 4: Run focused tests GREEN**

Run acceptance reporter/binary/subcommand tests.

### Task 4: Release verification

**Files:**
- No production changes after final test head.

**Interfaces:**
- Produces: one exact tested PR head eligible for merge/seal/release.

- [ ] **Step 1: Run `cargo fmt --all -- --check` and full Rust workspace tests**
- [ ] **Step 2: Require repository safety, Python, Rust, and native ARM64 CI GREEN on exact PR head**
- [ ] **Step 3: Merge only that exact tested head**
- [ ] **Step 4: Require independent merged-main CI GREEN**
- [ ] **Step 5: Create byte-identical `seal:` commit, require seal CI GREEN, then verify immutable release**
- [ ] **Step 6: Deploy only through `Deploy verified Shreks release`; LIVE remains disabled**
