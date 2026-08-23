# Phase B4a Graduation Lifecycle Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and test-driven-development task-by-task.

**Goal:** Add restart-safe, transaction-verified Pump.fun graduation evidence and normalized Pump.fun -> PumpSwap lifecycle events without increasing the existing Pump transaction-verification budget.

**Architecture:** `shreks-core` owns normalized lifecycle types. `shreks-storage` owns the migration inbox and lifecycle-event persistence. `shreks-providers::pump` detects and verifies official `migrate` / `migrate_v2` instructions. `shreks-observer` routes creation and migration through the existing one Pump websocket and verifies them during bounded full cycles.

**Tech Stack:** Rust stable, rusqlite 0.40.x, serde_json, bs58, tokio, tokio-tungstenite, existing Shreks provider/observer boundaries.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b4a-graduation-lifecycle-design.md`

## Global Constraints

- Pinned official Pump IDL blob: `062e66f032bb9f295353b573be3400070bd55e5b`.
- Pump program: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`.
- PumpSwap program: `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`.
- Legacy migrate discriminator: `[155, 234, 231, 146, 236, 158, 162, 30]`.
- Migrate-v2 discriminator: `[187, 203, 18, 31, 206, 237, 254, 41]`.
- Migration evidence must come from a verified Pump instruction, never a PumpSwap pair alone.
- Keep one Pump websocket and at most 32 Pump transaction verifications per full cycle.
- Realtime signals are durable-write-only; transaction verification stays in full cycles.
- `detected_at_unix_ms` remains the decision-safe lifecycle timestamp.
- No lifecycle strategy thresholds, B2 schema change, paper trading, signing, or live execution.

---

### Task 1: Normalized lifecycle domain and durable migration storage

**Files:**
- Modify `crates/shreks-core/src/lib.rs`
- Create `crates/shreks-storage/migrations/0005_pump_graduation_lifecycle.sql`
- Modify `crates/shreks-storage/src/lib.rs`
- Create `crates/shreks-storage/tests/pump_migration_storage.rs`
- Modify `crates/shreks-storage/tests/database.rs`

**Produces:**

```rust
pub enum LifecycleEventKind { PumpGraduation }
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
pub struct PumpMigrationSignalRecord { /* signal/retry fields from spec */ }
```

Storage API:

```rust
record_pump_migration_signal(signature, slot, observed_at_unix_ms)
pending_pump_migration_signals(limit)
record_pump_migration_attempt(signature, attempted_at_unix_ms, error)
complete_pump_migration(signature, attempted_at_unix_ms, events)
mark_pump_migration_rejected(signature, attempted_at_unix_ms, reason)
lifecycle_events_for_mint(mint)
```

- [ ] **RED:** Write tests proving schema version 5; both new tables/indexes; u64 slot TEXT round-trip; earliest-observation preservation; terminal-state preservation; restart replay; oldest-first bounded pending query; attempt counting; atomic completion; multiple events per signature; deterministic mint lookup; rejection auditability; input validation.

Completion replay semantics are exact:

- pending + valid non-empty event set -> atomically insert events and mark verified;
- already verified + identical event set -> idempotent no-op returning 0 inserted rows;
- already verified + any missing/different event -> fail closed;
- rejected or unknown signature -> fail closed;
- event signature must equal inbox signature;
- empty event set -> fail closed.

- [ ] **Verify RED:** Full CI must fail in Rust only because lifecycle/storage APIs do not exist.
- [ ] **GREEN:** Add lifecycle enum/type, migration 5, validation helpers, migration inbox methods, atomic completion transaction, lifecycle mint query.
- [ ] **Verify GREEN:** Full repository CI.

---

### Task 2: Pump lifecycle signal and migration transaction verification

**Files:**
- Modify `crates/shreks-providers/src/pump.rs`
- Modify `crates/shreks-providers/tests/pump.rs`
- Modify `crates/shreks-providers/tests/pump_stream.rs`

**Produces:**

```rust
pub const PUMP_MIGRATE_DISCRIMINATOR: [u8; 8];
pub const PUMP_MIGRATE_V2_DISCRIMINATOR: [u8; 8];
pub const WRAPPED_SOL_MINT: &str;
pub struct PumpMigrationSignal { pub signature: String, pub slot: u64 }
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
pub fn parse_pump_lifecycle_log_notification(body: &str)
    -> Result<Option<PumpLifecycleSignal>, ProviderError>;
pub fn classify_pump_migration_transaction(body: &str, signature: &str)
    -> Result<PumpMigrationVerification, ProviderError>;
```

`PumpLogStream::next_lifecycle_signal()` is added while creation-only APIs remain compatible until Task 3.

- [ ] **RED:** Prove Create/CreateV2 and Migrate/MigrateV2 lifecycle classification; explicit `MigrateBondingCurveCreator` negative case; reconnecting stream lifecycle delivery; Pending on result-null; legacy and v2 account extraction; Pump/PumpSwap identity checks; minimum account lengths; blockTime conversion/null/invalid handling; inner instruction support; deterministic deduplication.
- [ ] **Verify RED:** Rust fails only on missing lifecycle protocol APIs.
- [ ] **GREEN:** Implement exact-suffix log matching and pinned-IDL discriminator/account decoding. Legacy requires >=15 accounts with PumpSwap at 8, pool 9, mint 2, WSOL 14. V2 requires >=11 accounts with PumpSwap 9, pool 10, base mint 2, quote mint 3.
- [ ] **Verify GREEN:** Full repository CI, including all existing creation tests.

---

### Task 3: Single-stream observer integration and bounded verification

**Files:**
- Modify `crates/shreks-providers/src/lib.rs`
- Modify `crates/shreks-observer/src/lib.rs`
- Modify `crates/shreks-observer/src/bin/shreks-observe.rs`
- Modify `crates/shreks-observer/tests/pump_forwarding.rs`
- Modify `crates/shreks-observer/tests/pump_signal_ingestion.rs`
- Modify `crates/shreks-observer/tests/pump_verification.rs`
- Create `crates/shreks-observer/tests/pump_migration_verification.rs`

`PumpSignalSource`, `forward_pump_signals`, and the observer channel carry `PumpLifecycleSignal`.

`ObserverCycleReport` adds:

```rust
pump_migration_signals_received
pump_migration_signals_processed
pump_migration_signals_pending
pump_migration_signals_verified
pump_migration_signals_rejected
lifecycle_events_stored
```

- [ ] **RED:** Prove creation + migration forwarding; durable-only realtime migration ingestion; Pending/Verified/Rejected/provider-failure behavior; normalized event construction uses actual `TransactionProvider::provider_id()`; existing creation candidate/checkpoint path stays intact; total transaction calls <=32; migration has 8 reserved slots when backlog exists; creation can use all 32 when migrations are absent; spare creation capacity can be used by additional migrations.
- [ ] **Verify RED:** Rust fails because observer/forwarder are creation-only.
- [ ] **GREEN:** Add:

```rust
const PUMP_TOTAL_PENDING_BATCH_LIMIT: usize = 32;
const PUMP_MIGRATION_RESERVED_BATCH: usize = 8;
```

Scheduling is: process up to 8 reserved migrations, then creations up to remaining budget, then extra migrations with unused budget. Every fetch uses the existing chain pacing lane. Verified migration evidence is converted to `TokenLifecycleEvent` using the durable signal signature/slot/detection time and actual transaction-provider ID, then atomically completed in storage.
- [ ] **Verify GREEN:** Full repository CI.

---

### Task 4: Documentation and exact-head completion

**Files:**
- Modify `README.md`
- Modify this plan

- [ ] Document that Shreks observes protocol-verified Pump graduation via one websocket, supports legacy and v2 migration, preserves restart-safe detection time/optional block time/quote mint/pool/venue transition, and still does not make Graduation/Breakout decisions or trade.
- [ ] Run code/docs full CI.
- [ ] Record exact RED/GREEN commits and CI run IDs for Tasks 1-3.
- [ ] Run a fresh full CI on the documentation-only verification-record head.
- [ ] Open/update a stacked **draft** PR against `feat/phase-b3-fresh-launch`; keep it unmerged. Include final head SHA, CI run ID, pinned Pump IDL SHA, and explicit no-strategy/no-execution scope.

## Self-review

- Official indexes/discriminators must match the pinned spec.
- Protocol decoder must remain provider-neutral.
- `MigrateBondingCurveCreator` must never be graduation.
- Verified replay cannot mutate normalized lifecycle truth.
- Total Pump verification budget remains 32, not 32+32.
- Migration completion and normalized event persistence are atomic.
- Existing Pump creation behavior remains green.
