# Shreks Phase A2 Operational Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a restart-safe SQLite WAL operational database with explicit versioned migrations for the first Phase A observation records.

**Architecture:** Rust owns the operational ingestion schema. A dedicated `shreks-storage` crate opens the database, applies safe SQLite pragmas, and runs idempotent migrations. Provider and strategy logic remain outside the storage crate; later adapters write normalized Shreks-owned records through repository APIs built on this foundation.

**Tech Stack:** Rust 2021, rusqlite 0.40.2 with bundled SQLite, SQLite WAL.

**Spec:** `docs/superpowers/specs/2026-08-23-shreks-master-design.md`

## Global Constraints

- SQLite runs in WAL mode for file-backed operational databases.
- Foreign keys are enabled on every Shreks connection.
- Migrations are explicit, ordered, transactional, and idempotent.
- Phase A2 stores no wallet secrets and contains no live execution code.
- Schema timestamps use Unix milliseconds in UTC.
- Provider-specific JSON never becomes the normalized domain model.

---

### Task 1: Define storage behavior with failing tests

**Files:**
- Modify: `Cargo.toml`
- Create: `crates/shreks-storage/Cargo.toml`
- Test: `crates/shreks-storage/tests/database.rs`
- Create scaffold: `crates/shreks-storage/src/lib.rs`

**Interfaces:**
- Produces later: `ShreksDb::open(path) -> Result<ShreksDb, StorageError>`.
- Produces later: `ShreksDb::diagnostics() -> Result<DatabaseDiagnostics, StorageError>`.
- `DatabaseDiagnostics` contains `journal_mode`, `foreign_keys_enabled`, and `schema_version`.

- [ ] **Step 1: Add `shreks-storage` workspace member and crate metadata**

Use `rusqlite = { version = "0.40.2", features = ["bundled"] }`.

- [ ] **Step 2: Write failing integration tests**

Tests must prove:

1. opening a file-backed database creates its parent directory,
2. the connection reports WAL mode and foreign keys enabled,
3. schema version becomes `1`,
4. required Phase A tables exist,
5. reopening the same database keeps exactly one migration record.

Required tables after migration 1:

- `schema_migrations`
- `provider_health`
- `token_candidates`
- `market_snapshots`
- `raw_observations`
- `ingestion_checkpoints`

- [ ] **Step 3: Run CI and verify RED**

Run: `cargo test -p shreks-storage`
Expected: failure because `ShreksDb` and diagnostics are not implemented.

---

### Task 2: Implement SQLite open/configuration path

**Files:**
- Modify: `crates/shreks-storage/src/lib.rs`

**Interfaces:**
- `ShreksDb::open<P: AsRef<Path>>(path: P)` creates missing parent directories, opens SQLite, enables foreign keys, configures WAL, uses `synchronous=NORMAL`, and sets a 5-second busy timeout.
- `StorageError` wraps filesystem and SQLite errors without panics.

- [ ] **Step 1: Implement minimal connection opening and pragmas**
- [ ] **Step 2: Keep migration call present but minimal until Task 3**
- [ ] **Step 3: Run targeted tests and confirm remaining failures are migration-related**

---

### Task 3: Add migration 0001 and idempotent runner

**Files:**
- Create: `crates/shreks-storage/migrations/0001_operational.sql`
- Modify: `crates/shreks-storage/src/lib.rs`

**Interfaces:**
- Migration registry is compiled into the binary with `include_str!`.
- `schema_migrations(version, name, applied_at_unix_ms)` records applied migrations.
- Each unapplied migration executes in a transaction before its record is inserted.

- [ ] **Step 1: Add migration SQL**

Create Phase A operational tables with primary keys, uniqueness constraints, foreign keys, and indexes required for chronological candidate/snapshot lookups.

- [ ] **Step 2: Implement bootstrap + migration runner**

Create `schema_migrations` first, then apply ordered migrations exactly once.

- [ ] **Step 3: Implement diagnostics**

Return current journal mode, foreign-key state, and maximum applied schema version.

- [ ] **Step 4: Run `cargo test -p shreks-storage`**
Expected: all storage tests pass.

- [ ] **Step 5: Run `cargo test --workspace`**
Expected: all Rust tests pass.

---

### Task 4: CI verification and documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document Phase A2 database path and migration behavior**
- [ ] **Step 2: Verify the full GitHub Actions workflow**

Expected jobs: Repository safety, Rust tests, Python tests — all success.

---

## Completion Gate

Phase A2 is complete only when a fresh file path creates a WAL database at schema version 1, all six required tables exist, reopen is migration-idempotent, the full workspace remains green, and no provider/strategy/live-trading logic is mixed into storage.
