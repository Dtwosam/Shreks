# Phase A7-A8 Normalized Persistence and Observer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Shreks persist provider-neutral, venue-aware observations and run restart-safe autonomous observation cycles without trading.

**Architecture:** Extend the existing SQLite schema with an additive v2 migration, then expose narrow storage methods over Shreks-owned domain types. Build a new Rust observer crate that depends only on provider traits and storage APIs so real providers and deterministic test doubles use the same orchestration path. Provider failures degrade health independently and never become market signals.

**Tech Stack:** Rust 2021/2024 workspace, rusqlite 0.40.2 bundled SQLite, async-trait, Tokio for the eventual loop, existing `shreks-core`, `shreks-providers`, and `shreks-storage` crates.

**Spec:** `docs/superpowers/specs/2026-08-23-shreks-master-design.md` plus `docs/superpowers/specs/2026-08-23-venue-priority-amendment.md`

## Global Constraints

- Solana only for V1.
- Free external data/API/RPC sources only.
- Observe mode cannot sign or submit transactions.
- Provider and venue identities remain separate.
- Critical provider failures are explicit health states; no guessed data.
- Schema migrations are explicit, transactional, and restart-safe.
- Live trading remains disabled.

---

### Task 1: Schema v2 for venue-aware observations

**Files:**
- Create: `crates/shreks-storage/migrations/0002_observer_normalization.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Test: `crates/shreks-storage/tests/observer_storage.rs`

**Interfaces:**
- Consumes: existing schema version 1.
- Produces: schema version 2 with `venue` on candidates/snapshots, `rate_limited` provider health support, and normalized `token_mint_states` storage.

- [ ] **Step 1: Write failing migration tests**

Tests open a fresh database and assert schema version 2, `venue` columns, provider health accepts `rate_limited`, and `token_mint_states` exists with candidate foreign-key ownership.

- [ ] **Step 2: Run CI and verify RED**

Expected: Rust tests fail because schema version is still 1 and new columns/table do not exist.

- [ ] **Step 3: Implement migration 2 and register it**

Migration must rebuild `provider_health` with allowed statuses `healthy`, `degraded`, `rate_limited`, `unavailable`; add nullable `venue` columns to `token_candidates` and `market_snapshots`; create `token_mint_states` with `supply` stored as text to avoid u64-to-SQLite signed overflow.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: all Rust, Python, and repository-safety checks pass.

---

### Task 2: Typed operational persistence API

**Files:**
- Modify: `crates/shreks-storage/Cargo.toml`
- Modify: `crates/shreks-storage/src/lib.rs`
- Test: `crates/shreks-storage/tests/observer_storage.rs`

**Interfaces:**
- Consumes: `DiscoveredToken`, `PairMarketData`, `TokenMintState`, `ProviderId`, `ProviderHealthState` from `shreks-core`.
- Produces:
  - `ShreksDb::upsert_candidate(&DiscoveredToken) -> Result<i64, StorageError>`
  - `ShreksDb::insert_market_snapshot(i64, &PairMarketData) -> Result<(), StorageError>`
  - `ShreksDb::insert_mint_state(i64, &TokenMintState) -> Result<(), StorageError>`
  - `ShreksDb::upsert_provider_health(...) -> Result<(), StorageError>`
  - `ShreksDb::set_ingestion_checkpoint(...) -> Result<(), StorageError>`
  - `ShreksDb::ingestion_checkpoint(...) -> Result<Option<String>, StorageError>`

- [ ] **Step 1: Write failing behavior tests**

Cover candidate idempotency, venue persistence, numeric market snapshot persistence, mint-authority/freeze-authority persistence, `rate_limited` health state, and checkpoint replacement/restart recovery.

- [ ] **Step 2: Verify RED**

Expected: compile failures on missing methods/types.

- [ ] **Step 3: Add `shreks-core` dependency and minimal methods**

Storage parses numeric price strings strictly; malformed numeric provider-neutral values return `StorageError::InvalidData` rather than silently becoming NULL.

- [ ] **Step 4: Verify GREEN**

Run full CI.

---

### Task 3: Provider error to health-state mapping

**Files:**
- Modify: `crates/shreks-providers/src/lib.rs`
- Test: `crates/shreks-providers/tests/contracts.rs`

**Interfaces:**
- Consumes: `ProviderErrorKind`.
- Produces: `ProviderError::health_state() -> ProviderHealthState`.

- [ ] **Step 1: Write failing mapping tests**

Expected mapping:
- `RateLimited -> RateLimited`
- `Timeout | Unavailable -> Unavailable`
- `Unauthorized | NotFound | InvalidRequest | InvalidResponse -> Degraded`

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement minimal mapping**
- [ ] **Step 4: Verify GREEN**

---

### Task 4: One-cycle autonomous observer orchestration

**Files:**
- Create: `crates/shreks-observer/Cargo.toml`
- Create: `crates/shreks-observer/src/lib.rs`
- Create: `crates/shreks-observer/tests/cycle.rs`
- Modify: workspace `Cargo.toml` only if explicit membership is required.

**Interfaces:**
- Consumes: `DiscoveryProvider`, `MarketDataProvider`, `ChainDataProvider`, typed storage methods.
- Produces:
  - `Observer::run_cycle() -> ObserverCycleReport`
  - independent provider health updates
  - persisted candidates, pair snapshots, and mint states
  - no trade intents and no execution calls.

- [ ] **Step 1: Write deterministic failing tests with in-memory provider test doubles**

Tests prove:
- duplicate discoveries do not duplicate candidates,
- one market provider failure does not erase successful observations from another,
- rate limiting is recorded as health state rather than market data,
- Helius/chain failure does not fabricate mint state,
- successful provider calls return to `healthy`.

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement the smallest observer cycle**

The observer first discovers candidates, then enriches each candidate through configured market providers and optional chain provider. Each provider result is isolated and reflected in health state.

- [ ] **Step 4: Verify GREEN**

---

### Task 5: Restart-safe continuous loop shell

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Create: `crates/shreks-observer/src/main.rs` only if a runnable binary remains small and testable.
- Test: `crates/shreks-observer/tests/restart.rs`
- Modify: `README.md`

**Interfaces:**
- Consumes: provider config budgets and ingestion checkpoints.
- Produces: observe-only loop with bounded cadence, graceful cancellation, and restart-safe checkpoint progression.

- [ ] **Step 1: Write failing restart/cadence tests**

Use a finite-cycle runner in tests rather than sleeping indefinitely. Reopening the same database must preserve checkpoint state and candidate idempotency.

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement finite runner plus continuous wrapper**

No live trading code is reachable from this binary.

- [ ] **Step 4: Verify GREEN and update operator docs**

---

## Self-review

- Spec coverage: A7 normalized model is already represented by `shreks-core`; this plan makes it durable. A8 gets provider isolation, storage, restart recovery, and an unattended loop shell.
- Venue amendment coverage: candidate and snapshot venue are persisted independently of provider.
- Free-source coverage: budgets/config are consumed; no paid fallback exists.
- Deliberately deferred from this slice: direct Pump.fun/PumpSwap program-firehose discovery and A9 future-outcome checkpoints. Those are separate Phase A tasks after the observer shell is stable, because they require program-specific event decoding and temporal scheduling respectively.
- Placeholder scan: no implementation-critical TBD/TODO placeholders.
