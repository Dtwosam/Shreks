# Phase B4a Graduation Lifecycle Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add restart-safe, transaction-verified Pump.fun graduation evidence and normalized Pump.fun -> PumpSwap lifecycle events without increasing the existing per-cycle Pump transaction-verification budget.

**Architecture:** `shreks-core` owns normalized lifecycle types. `shreks-storage` owns a migration-verification inbox plus normalized lifecycle-event persistence. `shreks-providers::pump` detects migration log signals and verifies legacy `migrate` plus `migrate_v2` transactions against the pinned official Pump IDL. `shreks-observer` routes both creation and migration signals through the existing single websocket/channel and performs bounded verification in normal cycles.

**Tech Stack:** Rust stable, rusqlite 0.40.x bundled SQLite, serde_json, bs58, tokio, tokio-tungstenite, existing provider/observer traits and GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b4a-graduation-lifecycle-design.md`

## Global Constraints

- Official Pump IDL blob SHA is `062e66f032bb9f295353b573be3400070bd55e5b`.
- Pump program is `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`.
- PumpSwap program is `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`.
- Legacy `migrate` discriminator is `[155, 234, 231, 146, 236, 158, 162, 30]`.
- `migrate_v2` discriminator is `[187, 203, 18, 31, 206, 237, 254, 41]`.
- Migration evidence comes from a verified Pump instruction, never from seeing a PumpSwap pair alone.
- One Pump websocket remains in use; no second migration websocket is allowed.
- Realtime wake-ups remain durable-write-only; confirmed transaction fetches stay in full cycles.
- Total Pump transaction verifications remain capped at 32 per cycle.
- `detected_at_unix_ms` is the decision-safe lifecycle timestamp; optional block time must not replace it.
- No B2 feature change, setup thresholds, scoring, paper trading, signer, or live execution in B4a.

---

### Task 1: Normalized lifecycle domain and durable migration storage

**Files:**
- Modify: `crates/shreks-core/src/lib.rs`
- Create: `crates/shreks-storage/migrations/0005_pump_graduation_lifecycle.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Create: `crates/shreks-storage/tests/pump_migration_storage.rs`
- Modify: `crates/shreks-storage/tests/database.rs`

**Interfaces:**

```rust
pub enum LifecycleEventKind {
    PumpGraduation,
}

impl LifecycleEventKind {
    pub const fn as_str(self) -> &'static str;
}

pub struct TokenLifecycleEvent {
    pub kind: LifecycleEventKind,
    pub provider: ProviderId,
    pub mint: String,
    pub quote_mint: String,
    pub from_venue: VenueId,
    pub to_venue: VenueId,
    pub pool_address: String,
    pub signature: String,
    pub slot: u64,
    pub detected_at_unix_ms: i64,
    pub occurred_at_unix_ms: Option<i64>,
}

pub struct PumpMigrationSignalRecord {
    pub signature: String,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
    pub status: PumpSignalStatus,
    pub attempt_count: u64,
    pub last_attempt_at_unix_ms: Option<i64>,
    pub last_error: Option<String>,
}
```

Storage methods:

```rust
pub fn record_pump_migration_signal(
    &self,
    signature: &str,
    slot: u64,
    observed_at_unix_ms: i64,
) -> Result<(), StorageError>;

pub fn pending_pump_migration_signals(
    &self,
    limit: usize,
) -> Result<Vec<PumpMigrationSignalRecord>, StorageError>;

pub fn record_pump_migration_attempt(
    &self,
    signature: &str,
    attempted_at_unix_ms: i64,
    error: Option<&str>,
) -> Result<(), StorageError>;

pub fn complete_pump_migration(
    &self,
    signature: &str,
    attempted_at_unix_ms: i64,
    events: &[TokenLifecycleEvent],
) -> Result<usize, StorageError>;

pub fn mark_pump_migration_rejected(
    &self,
    signature: &str,
    attempted_at_unix_ms: i64,
    reason: &str,
) -> Result<(), StorageError>;

pub fn lifecycle_events_for_mint(
    &self,
    mint: &str,
) -> Result<Vec<TokenLifecycleEvent>, StorageError>;
```

- [ ] **Step 1: Write RED storage/domain tests**

Tests must assert:

```rust
assert_eq!(LifecycleEventKind::PumpGraduation.as_str(), "pump_graduation");
assert_eq!(db.diagnostics().unwrap().schema_version, 5);
```

And prove:

- migration 5 creates `pump_migration_signals` and `token_lifecycle_events`;
- migration signal slot is stored as decimal TEXT and supports `u64::MAX`;
- duplicate signal keeps the earliest observation timestamp;
- duplicate signal does not reset `verified` or `rejected` state;
- pending rows survive DB reopen and return oldest-first with a limit;
- attempts increment while remaining pending;
- `complete_pump_migration` inserts normalized event(s), marks the inbox row verified, and returns inserted-event count;
- completion is idempotent for the same event;
- multiple distinct `(mint, quote_mint, pool)` events for one signature can be stored;
- `lifecycle_events_for_mint` returns deterministic `detected_at_unix_ms ASC, signature ASC, pool_address ASC` order;
- rejection removes the signal from pending replay but preserves reason/time;
- completing an unknown/non-pending signature fails closed;
- completion with an empty event slice fails closed;
- invalid empty mint/quote/pool/signature or negative timestamps are rejected by storage rather than persisted.

- [ ] **Step 2: Run CI and verify RED**

Expected: Rust fails because lifecycle types/migration-5 storage APIs are missing. Existing Python and repository-safety jobs remain unchanged.

- [ ] **Step 3: Implement minimal domain + migration + storage APIs**

Migration SQL creates the two tables/indexes from the spec. Add migration version 5 to `MIGRATIONS`.

`complete_pump_migration` must use one SQLite transaction. Within it:

```text
validate pending signal
insert events with ON CONFLICT DO NOTHING
update signal status='verified', attempt_count=attempt_count+1,
       last_attempt_at_unix_ms=?, last_error=NULL
commit
```

Rows in `token_lifecycle_events` use enum/provider/venue `as_str()` values and store `slot` as decimal TEXT.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: all Task 1 storage/domain tests and all pre-existing repository tests pass.

---

### Task 2: Pump lifecycle log classification and migration transaction decoder

**Files:**
- Modify: `crates/shreks-providers/src/pump.rs`
- Modify: `crates/shreks-providers/tests/pump.rs`
- Modify: `crates/shreks-providers/tests/pump_stream.rs`

**Interfaces:**

```rust
pub const PUMP_MIGRATE_DISCRIMINATOR: [u8; 8];
pub const PUMP_MIGRATE_V2_DISCRIMINATOR: [u8; 8];
pub const WRAPPED_SOL_MINT: &str;

pub struct PumpMigrationSignal {
    pub signature: String,
    pub slot: u64,
}

pub enum PumpLifecycleSignal {
    Creation(PumpCreationSignal),
    Migration(PumpMigrationSignal),
}

pub struct PumpMigrationEvidence {
    pub mint: String,
    pub quote_mint: String,
    pub pool_address: String,
    pub occurred_at_unix_ms: Option<i64>,
}

pub enum PumpMigrationVerification {
    Pending,
    Verified(Vec<PumpMigrationEvidence>),
    Rejected(String),
}

pub fn parse_pump_lifecycle_log_notification(
    body: &str,
) -> Result<Option<PumpLifecycleSignal>, ProviderError>;

pub fn classify_pump_migration_transaction(
    body: &str,
    signature: &str,
) -> Result<PumpMigrationVerification, ProviderError>;

impl PumpLogStream {
    pub async fn next_lifecycle_signal(
        &mut self,
    ) -> Result<PumpLifecycleSignal, ProviderError>;
}
```

Keep the existing creation-only `parse_pump_log_notification` and `next_signal` behavior green during this task; they may delegate to the lifecycle parser while filtering to creation so current observer code still compiles until Task 3.

- [ ] **Step 1: Write RED protocol tests**

Add tests proving:

- official migration discriminators and wrapped-SOL mint are exact;
- `Create`/`CreateV2` logs produce `Creation`;
- exact `Migrate`/`MigrateV2` logs produce `Migration`;
- `MigrateBondingCurveCreator`, buy/sell logs, and failed notifications do not produce migration;
- reconnecting `PumpLogStream::next_lifecycle_signal` returns migration as well as creation without opening a second subscription;
- RPC `result:null` -> `Pending`;
- failed on-chain migration transaction -> `Rejected`;
- legacy migration with accounts `[2]=mint`, `[8]=PUMP_AMM_PROGRAM_ID`, `[9]=pool`, `[14]=WRAPPED_SOL_MINT` verifies;
- v2 migration with `[2]=base_mint`, `[3]=quote_mint`, `[9]=PUMP_AMM_PROGRAM_ID`, `[10]=pool` verifies;
- wrong Pump program, wrong discriminator, wrong PumpSwap program account, too-short account list, or blank identity field cannot verify;
- `blockTime` seconds converts to exact milliseconds;
- `blockTime:null` remains `None`;
- negative/overflowing/malformed block time is `InvalidResponse`;
- matching inner instructions verify;
- duplicate migration evidence in outer/inner instructions deduplicates deterministically.

Synthetic transaction helpers must base58-encode the real 8-byte discriminator and use `jsonParsed` partially decoded instruction shape (`programId`, string `accounts`, `data`).

- [ ] **Step 2: Run CI and verify RED**

Expected: Rust fails on missing lifecycle types/constants/parser/verifier while Task 1 storage remains green.

- [ ] **Step 3: Implement minimal lifecycle parser/verifier**

Use exact suffix matching for instruction log names. Reuse the existing top-level + inner instruction scanning pattern and `bs58` decode path.

For legacy migration, require at least 15 accounts and verify account 8 PumpSwap + account 14 wrapped SOL. For v2, require at least 11 accounts and verify account 9 PumpSwap. Extract only the fixed verified indexes from the pinned IDL.

Parse transaction-wide block time once, then attach it to each deduplicated evidence item.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: provider lifecycle tests and all existing creation/stream tests pass.

---

### Task 3: Single-stream observer integration and bounded migration verification

**Files:**
- Modify: `crates/shreks-providers/src/lib.rs`
- Modify: `crates/shreks-observer/src/lib.rs`
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Modify: `crates/shreks-observer/tests/pump_forwarding.rs`
- Modify: `crates/shreks-observer/tests/pump_signal_ingestion.rs`
- Modify: `crates/shreks-observer/tests/pump_verification.rs`
- Create: `crates/shreks-observer/tests/pump_migration_verification.rs`

**Interfaces:**

`PumpSignalSource` and `forward_pump_signals` now carry `PumpLifecycleSignal` rather than creation-only signals. `Observer::with_pump_signal_receiver` accepts `mpsc::Receiver<PumpLifecycleSignal>`.

`ObserverCycleReport` adds:

```rust
pub pump_migration_signals_received: usize,
pub pump_migration_signals_processed: usize,
pub pump_migration_signals_pending: usize,
pub pump_migration_signals_verified: usize,
pub pump_migration_signals_rejected: usize,
pub lifecycle_events_stored: usize,
```

- [ ] **Step 1: Write RED observer/forwarding tests**

Update forwarding/ingestion tests to use lifecycle variants and prove both variants survive the bounded channel.

Migration verification tests must prove:

- realtime migration signal persists in `pump_migration_signals` but does not perform an immediate transaction fetch before a full cycle;
- pending RPC result increments migration pending/processed counters and remains replayable;
- verified legacy and v2 migrations create `token_lifecycle_events` with provider from the actual `TransactionProvider`, Pump.fun -> PumpSwap venues, signal slot/detected timestamp, optional block time, mint/quote/pool;
- provider failure records an attempt/error and leaves signal pending;
- fetched non-migration becomes terminal rejected and is not replayed next cycle;
- existing Pump creation path still creates candidate + outcome checkpoints;
- with migration and creation backlogs, at most 32 total transaction calls occur in one cycle;
- if at least 8 migrations are pending, at least 8 migration calls occur before creation consumes the rest;
- if there are no migrations, creation can still consume all 32 slots;
- unused creation capacity can be consumed by additional migration work.

Use a counting `TransactionProvider` keyed by signature prefix (`launch-` vs `migrate-`) so budget assertions test real observer calls rather than mocks of internal helpers.

- [ ] **Step 2: Run CI and verify RED**

Expected: Rust fails because observer/provider forwarding still uses creation-only signal types and migration counters/processing are absent.

- [ ] **Step 3: Implement lifecycle forwarding and observer processing**

Set constants:

```rust
const PUMP_TOTAL_PENDING_BATCH_LIMIT: usize = 32;
const PUMP_MIGRATION_RESERVED_BATCH: usize = 8;
```

Cycle scheduling:

```text
migration_reserved = min(8, pending_migrations.len())
process reserved migrations
remaining = 32 - migration_reserved
process min(remaining, pending_launches.len()) launches
remaining -= launches_processed
process min(remaining, remaining_migrations.len()) additional migrations
```

Each request uses the existing Helius/transaction `PacingLane::Chain(provider_id)` wait.

For `Verified(evidence)`, construct `TokenLifecycleEvent` using the actual provider ID plus durable signal metadata, then call atomic `complete_pump_migration`.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: observer lifecycle tests, all existing observer tests, provider tests, storage tests, Python tests, metadata, and repository-safety pass.

---

### Task 4: Operator documentation, PR evidence, and exact-head gate

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-b4a-graduation-lifecycle.md`

- [ ] **Step 1: Update README**

Document:

- Shreks now observes actual Pump migration/graduation evidence rather than inferring it from market momentum;
- one Pump websocket carries creation + migration signals;
- both official migration generations are verified;
- migration signals are restart-safe and provider failures remain pending;
- normalized events preserve detection time, optional block time, quote mint, PumpSwap pool, and venue transition;
- B4a is lifecycle evidence only and does not enable Graduation/Breakout decisions or trading.

- [ ] **Step 2: Run code/docs full CI**

Expected: all repository jobs pass.

- [ ] **Step 3: Record exact RED/GREEN commits and CI run IDs in this plan**

Record each task’s actual RED/GREEN evidence. Do not claim B4a complete until this documentation-only verification record itself receives a fresh full CI run.

- [ ] **Step 4: Run exact-final-head CI and update the stacked draft PR**

PR base is `feat/phase-b3-fresh-launch`. Keep it draft and unmerged. The PR body must state exact head SHA, CI run ID, official pinned Pump IDL SHA, and that no strategy/execution behavior was added.

---

## Self-review checklist

- Every official account index in implementation must match the pinned B4a spec.
- Provider decoder must not hardcode Helius as normalized provider identity.
- `MigrateBondingCurveCreator` must have a dedicated negative test.
- Total transaction verification budget must remain 32, not 32 launch + 32 migration.
- Migration verification and normalized event persistence must be atomic.
- Existing creation behavior must remain green throughout final verification.
- No production trading thresholds or execution code enter this branch.
