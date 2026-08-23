# Phase A9 Future Outcome Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a restart-safe, budget-aware future-outcome dataset for every observed candidate at 1m, 5m, 15m, 30m, 1h, 4h, and 24h without enabling trading.

**Architecture:** Rust remains the owner of operational observation state. SQLite schema v4 stores one idempotent checkpoint row per candidate/horizon, linked to the actual baseline and checkpoint market snapshots so provider and venue identity remain auditable. The observer schedules checkpoints when a candidate first enters durable storage, revisits only due candidates in bounded batches, captures a normal provider-neutral market snapshot through existing adapters, then finalizes metrics from data actually observed. Unsupported metrics stay NULL rather than being guessed; no high-frequency 24-hour resampling loop is introduced merely to manufacture MFE/MAE.

**Tech Stack:** Rust 2021/2024 workspace, rusqlite 0.40.2 bundled SQLite/WAL, Tokio, existing `shreks-core`, `shreks-providers`, `shreks-storage`, and `shreks-observer` crates.

**Spec:** `docs/superpowers/specs/2026-08-23-shreks-master-design.md` section 8 plus `docs/superpowers/specs/2026-08-23-venue-priority-amendment.md`.

## Global Constraints

- Solana only for V1.
- Free external data/API/RPC sources only.
- Observe mode cannot sign or submit transactions.
- All seven approved horizons are scheduled: 60, 300, 900, 1800, 3600, 14400, and 86400 seconds.
- Every observed candidate is eligible for outcome scheduling, including candidates later rejected by strategy/safety layers.
- Provider and venue identities remain separate and auditable through referenced market snapshots.
- Missing/unsupported data is NULL or remains pending; it is never guessed.
- Outcome processing is bounded so it cannot bypass free-tier request budgets.
- Live trading remains disabled.

---

### Task 1: Schema v4 and typed outcome-checkpoint storage

**Files:**
- Create: `crates/shreks-storage/migrations/0004_candidate_outcome_checkpoints.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Create: `crates/shreks-storage/tests/outcome_checkpoints.rs`

**Interfaces:**
- Consumes: `token_candidates` and `market_snapshots` from schema v3.
- Produces:
  - schema version 4,
  - `OutcomeCheckpointStatus::{Pending, Completed}`,
  - `OutcomeCheckpointRecord`,
  - `DueOutcomeCheckpoint`,
  - `ShreksDb::ensure_outcome_checkpoints(candidate_id, discovered_at_unix_ms)`,
  - `ShreksDb::due_outcome_checkpoints(now_unix_ms, limit)`,
  - `ShreksDb::complete_outcome_checkpoint(...)`.

The table must use `(candidate_id, horizon_seconds)` as a unique identity and foreign keys to candidate/baseline/checkpoint snapshots. Numeric outcome fields are nullable: `return_pct`, `mfe_pct`, `mae_pct`, `liquidity_change_pct`, `volume_m5_change_pct`, `buys_m5_change`, `sells_m5_change`, `rug_or_dead_pool`, and `exitability` (`exitable`/`not_exitable`/NULL). `due_at_unix_ms`, `completed_at_unix_ms`, and both snapshot IDs remain explicit for latency/audit analysis.

- [x] **Step 1: Write failing migration/storage tests**

Tests must prove a fresh DB reports schema v4; scheduling inserts exactly seven rows with the approved horizons and exact due timestamps; scheduling is idempotent across restart; `due_outcome_checkpoints` returns only pending rows whose due time has arrived, in deterministic due-time order; completion links real snapshot IDs and removes the row from the due set.

- [x] **Step 2: Run full CI and verify RED**

Expected: Rust fails on schema version 3/missing outcome types and methods while Python and repository safety remain unchanged.

- [x] **Step 3: Add migration and minimal typed storage API**

Use checked timestamp addition so overflow becomes `StorageError::InvalidData`. Validate horizon values against the approved set. Completion must reject snapshot IDs owned by another candidate and must never overwrite a completed checkpoint.

- [x] **Step 4: Run full CI and verify GREEN**

Expected: Rust, Python, and repository-safety checks all pass.

---

### Task 2: Schedule every durable candidate without changing candidate identity

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Modify: `crates/shreks-observer/tests/cycle.rs`
- Modify: `crates/shreks-observer/tests/pump_verification.rs`

**Interfaces:**
- Consumes: candidate IDs returned by `ShreksDb::upsert_candidate` and `ensure_outcome_checkpoints` from Task 1.
- Produces: exactly seven durable future checkpoints for candidates discovered through generic discovery and verified Pump creation.

- [x] **Step 1: Write failing observer tests**

After one discovery cycle, query SQLite and assert seven checkpoint rows exist for the candidate. Repeat the cycle and assert the count remains seven. Verify a Pump-created candidate gets the same schedule. A rejected Pump log signal that never becomes a candidate must not create checkpoint rows.

- [x] **Step 2: Verify RED**

Expected: candidate rows exist but outcome schedules are absent.

- [x] **Step 3: Schedule immediately after every successful candidate upsert**

Use the candidate's durable `discovered_at_unix_ms` as the anchor. Do not create a second candidate or modify discovery identity.

- [x] **Step 4: Verify GREEN**

Run full CI.

---

### Task 3: Bounded due-checkpoint market observation

**Files:**
- Modify: `crates/shreks-storage/src/lib.rs`
- Modify: `crates/shreks-observer/src/lib.rs`
- Create: `crates/shreks-observer/tests/outcome_sampling.rs`

**Interfaces:**
- Consumes: `due_outcome_checkpoints(now, limit)`, existing `MarketDataProvider`, request pacer, and normalized market snapshot persistence.
- Produces: due candidates are re-observed through the same market-provider path in a bounded batch without duplicating candidate rows or triggering chain-state calls solely for outcome sampling.

- [x] **Step 1: Write failing timing/budget tests**

Use deterministic fake market providers and due checkpoint fixtures. Prove: a not-yet-due candidate causes no extra market call; a due candidate causes one market-observation pass even if several horizons are overdue; the due batch is capped; existing provider pacing still applies; outcome sampling does not request mint state solely because a checkpoint is due.

- [x] **Step 2: Verify RED**

Expected: due candidates are currently ignored by the observer.

- [x] **Step 3: Add a bounded `OUTCOME_DUE_CANDIDATE_LIMIT` path**

Load distinct due candidates at the start of a normal full cycle, merge them with newly discovered candidates by candidate ID, mark whether each candidate needs chain enrichment, and reuse the existing market provider orchestration/pacing. Realtime Pump wake-ups between cycles remain durable-write-only and do not trigger outcome sampling.

- [x] **Step 4: Verify GREEN**

Run full CI.

---

### Task 4: Finalize point-in-time outcome metrics from observed snapshots

**Files:**
- Modify: `crates/shreks-storage/src/lib.rs`
- Modify: `crates/shreks-observer/src/lib.rs`
- Extend: `crates/shreks-observer/tests/outcome_sampling.rs`

**Interfaces:**
- Consumes: market snapshots already stored for a candidate and pending due checkpoint rows.
- Produces: completed outcome rows using only observable data available at completion time.

For each due horizon, choose a baseline price-bearing snapshot at/after discovery and the latest price-bearing snapshot collected at/after the checkpoint due time. Store both snapshot IDs. Compute return from `price_usd`; compute liquidity and 5m-volume percentage changes only when both endpoints are valid and the baseline denominator is positive; compute signed buy/sell-count changes when both values exist. Compute MFE/MAE from price-bearing snapshots between the baseline and checkpoint snapshot using the baseline price. If the available snapshot history is insufficient for a metric, leave it NULL. `rug_or_dead_pool` and `exitability` remain NULL until an explicit detector/quote proves them; absence of a provider pair is not enough to guess either state.

- [x] **Step 1: Write failing metric tests**

Fixtures must cover positive/negative return, MFE/MAE, nullable denominator handling, signed flow changes, multiple provider/venue snapshots with preserved snapshot IDs, and no fabricated rug/exitability values.

- [x] **Step 2: Verify RED**

Expected: due observations are stored but checkpoint rows remain pending/uncomputed.

- [x] **Step 3: Implement deterministic finalization**

Finalize only after the due candidate market observation pass. If no usable post-due price-bearing snapshot exists, keep the checkpoint pending for a later cycle rather than marking false completion.

- [x] **Step 4: Verify GREEN**

Run full CI.

---

### Task 5: Restart, operator visibility, and regression documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-a9-outcome-checkpoints.md`
- Extend: `crates/shreks-observer/tests/runtime.rs`

**Interfaces:**
- Consumes: completed A9 scheduler/finalizer.
- Produces: documented restart semantics and a regression proving pending checkpoints survive process restart and complete later without duplicate schedules.

- [x] **Step 1: Add restart regression**

Schedule a candidate, close/reopen SQLite before a horizon is completed, run a due observation with deterministic market data, and assert the same checkpoint row completes exactly once.

- [x] **Step 2: Verify RED/GREEN as appropriate**

If the existing implementation already passes the regression, record that as verification rather than manufacturing a failure.

The regression passed without a production-code change on clean A9 commit `8679cf7cc628e8d9eb52615694f88b5b3e5faf88` in CI run `32654661976`; Rust, Python, and repository-safety jobs were all green.

- [x] **Step 3: Update README operator notes**

Document the seven horizons, bounded/full-cycle-only sampling behavior, NULL semantics for unavailable metrics, and that no trading is enabled by A9.

- [x] **Step 4: Run final full CI**

Final documentation-complete commit `2aa751b4f95ab463d0782a660631ea9c7dd49cbe` passed full CI run `32654776507`: Rust, Python, workspace metadata validation, and repository-safety checks were green.

---

## Verification record

- Task 4's implementation was fully green at commit `80153d1e800d865d6ee206861ac58e02a432483b` in CI run `32651274531`.
- Task 5's restart regression passed the existing implementation at commit `8679cf7cc628e8d9eb52615694f88b5b3e5faf88` in CI run `32654661976`; no production fix was needed.
- A9 documentation-complete commit `2aa751b4f95ab463d0782a660631ea9c7dd49cbe` passed final full CI run `32654776507`.

## Self-review

- **Spec coverage:** section 8's seven horizons, return, MFE, MAE, liquidity/volume/buyer/seller changes, rug/dead-pool and exitability fields are represented. Metrics unsupported by current evidence remain explicitly nullable. Rejected future strategy candidates remain eligible because scheduling occurs at durable discovery time before strategy/safety decisions exist.
- **Venue amendment:** outcome records reference real market snapshots, preserving provider and venue instead of flattening them.
- **Free-source constraint:** due sampling is bounded and uses existing paced providers; no paid fallback or forced high-frequency resampling is introduced.
- **Look-ahead safety:** completion uses only snapshots whose timestamps were already observed by the runtime; future outcomes are never written back into point-in-time feature rows.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
- **Type consistency:** Task 2-5 consume the storage interfaces defined by Task 1.
