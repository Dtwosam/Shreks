# FL1 Canonical FastEvent Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert immutable Pump realtime trade evidence into a durable, replayable, strictly sequenced canonical `FastEvent` journal without guessing decimals or backdating when normalized information became usable.

**Architecture:** Migration 11 adds an append-only `fast_events` journal linked to raw Pump evidence. Storage resolves verified mint decimals and exposes bounded unnormalized raw rows; the observe-only realtime writer uses the existing Pump evidence conversion to append canonical events and periodically retries rows that were waiting for decimals. Canonical sequence is stable SQLite append order and canonical observation time is normalization acceptance time, while the earlier websocket observation remains separate audit provenance.

**Tech Stack:** Rust 2024, SQLite WAL/rusqlite, Tokio, existing `shreks-core` Fast Lane types, existing `shreks-providers::pump_trade` conversion, GitHub Actions native ARM64.

**Spec:** `docs/superpowers/specs/2026-08-28-fl1-canonical-fast-event-ingestion-design.md`

## Global Constraints

- LIVE remains disabled.
- Raw `pump_trade_evidence` remains immutable source truth.
- Never guess base or non-SOL quote decimals.
- SOL/WSOL quote decimals are 9.
- Canonical `FastEvent.observed_at_unix_ms` is when normalized evidence becomes usable, not an earlier raw observation if normalization was delayed.
- Preserve raw `source_observed_at_unix_ms` separately.
- Canonical sequence is durable append order and must survive restart.
- Identical replay is idempotent; conflicting replay fails closed.
- The realtime normalizer performs no network calls.
- DEX Screener is not authoritative Fast Lane order flow.
- No strategy, PAPER action, risk, executor, signing, or LIVE-mode changes.

---

### Task 1: RED — Define canonical FastEvent storage contract

**Files:**
- Create: `crates/shreks-storage/tests/fast_event_storage.rs`

**Interfaces:**
- Consumes: `FastEvent`, `FastEventId`, `FastEventKind`, `FastMarketKey`, `ProviderId`, `VenueId`, `ShreksDb`.
- Requires production APIs:

```rust
pub struct StoredFastEvent {
    pub event: FastEvent,
    pub source_observed_at_unix_ms: i64,
    pub base_decimals: u8,
    pub quote_decimals: u8,
}

impl ShreksDb {
    pub fn next_fast_event_sequence(&self) -> Result<u64, StorageError>;
    pub fn record_fast_event(
        &self,
        event: &FastEvent,
        source_observed_at_unix_ms: i64,
        base_decimals: u8,
        quote_decimals: u8,
    ) -> Result<bool, StorageError>;
    pub fn fast_events_for_market(
        &self,
        mint: &str,
        quote_mint: &str,
        venue: VenueId,
    ) -> Result<Vec<StoredFastEvent>, StorageError>;
}
```

- [ ] **Step 1: Write migration/append/restart RED tests**

Require schema version 11 and table `fast_events`. Insert two valid Pump bonding-curve `FastEvent`s with sequences obtained from `next_fast_event_sequence`; assert sequences 1 then 2, reopen the database, assert replay remains `[1, 2]`, and next sequence is 3.

- [ ] **Step 2: Write idempotency/conflict RED tests**

Re-submit an identical event identity with the next proposed sequence and assert `record_fast_event` returns `false` while the stored original sequence remains unchanged. Re-submit the same `(signature, ordinal)` with changed economics and assert `StorageError::InvalidData`.

- [ ] **Step 3: Write provenance validation RED tests**

Reject canonical rows where `source_observed_at_unix_ms > event.observed_at_unix_ms`, invalid decimals, blank identities, or market/query identity is malformed. Assert replay order is by durable sequence.

- [ ] **Step 4: Push RED commit and require Rust failure only for missing API/schema 11**

Expected focused failure: missing `StoredFastEvent` / `record_fast_event` / schema 11, not unrelated existing tests.

---

### Task 2: GREEN — Add migration 11 and canonical journal APIs

**Files:**
- Create: `crates/shreks-storage/migrations/0011_canonical_fast_events.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Modify: `crates/shreks-storage/src/fast_lane.rs`
- Modify: schema-version assertions in storage tests only where they explicitly mean latest schema.

**Interfaces produced:** APIs from Task 1.

- [ ] **Step 1: Add migration 11**

Create `fast_events` with:

```text
sequence INTEGER PRIMARY KEY AUTOINCREMENT
signature TEXT NOT NULL
ordinal INTEGER NOT NULL
provider TEXT NOT NULL
mint TEXT NOT NULL
quote_mint TEXT NOT NULL
venue TEXT NOT NULL
kind TEXT NOT NULL CHECK(kind IN ('buy','sell'))
actor TEXT
slot TEXT NOT NULL
occurred_at_unix_ms INTEGER NOT NULL
observed_at_unix_ms INTEGER NOT NULL
source_observed_at_unix_ms INTEGER NOT NULL
base_quantity REAL NOT NULL
quote_quantity REAL NOT NULL
price_quote REAL NOT NULL
base_decimals INTEGER NOT NULL CHECK(base_decimals BETWEEN 0 AND 255)
quote_decimals INTEGER NOT NULL CHECK(quote_decimals BETWEEN 0 AND 255)
UNIQUE(signature, ordinal)
FOREIGN KEY(signature, ordinal) REFERENCES pump_trade_evidence(signature, ordinal) ON DELETE RESTRICT
```

Add market/sequence and observation indexes.

- [ ] **Step 2: Register migration 11 and export `StoredFastEvent`**

Latest schema assertions become 11 only where the test means current/latest schema; historical migration-specific tests keep their historical meaning.

- [ ] **Step 3: Implement `next_fast_event_sequence`**

Return `MAX(sequence)+1`, starting at 1. Reject overflow beyond `u64`/SQLite signed range rather than wrapping.

- [ ] **Step 4: Implement immutable `record_fast_event`**

Validate source observation cannot be after canonical observation. Insert the provided sequence. On unique identity replay, fetch the existing row and compare all economic/provenance fields except the caller's newly proposed sequence; identical replay is `false`, conflict is `InvalidData`. Sequence collision with another identity fails closed.

- [ ] **Step 5: Implement deterministic market replay**

Decode all fields back into validated `FastEvent`, preserving slot as full-width decimal text and ordering by sequence ascending.

- [ ] **Step 6: Run focused storage tests GREEN, then full storage crate tests**

Expected: all storage tests PASS.

---

### Task 3: RED — Define verified-decimal and pending-normalization contract

**Files:**
- Modify: `crates/shreks-storage/tests/fast_event_storage.rs`

**Interfaces required:**

```rust
impl ShreksDb {
    pub fn verified_mint_decimals(&self, mint: &str) -> Result<Option<u8>, StorageError>;
    pub fn pending_pump_trade_evidence(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpTradeEvidenceWrite>, StorageError>;
}
```

- [ ] **Step 1: Write verified-decimal RED tests**

No mint state -> `None`. One or repeated consistent durable decimal value -> `Some(value)`. Two contradictory durable decimal values for the same mint -> `StorageError::InvalidData`.

- [ ] **Step 2: Write pending-row RED tests**

Raw rows without canonical events are returned oldest-first by `observed_at_unix_ms, signature, ordinal`, bounded by `limit`. Once canonical identity exists it disappears from pending. `limit=0` returns empty.

- [ ] **Step 3: Prove RED**

Expected: compile failure only because the new query APIs do not exist.

---

### Task 4: GREEN — Implement decimal resolution and bounded pending query

**Files:**
- Modify: `crates/shreks-storage/src/fast_lane.rs`

- [ ] **Step 1: Implement `verified_mint_decimals`**

Join `token_candidates` to `token_mint_states` by candidate id for the requested mint, read distinct durable decimal values, and fail closed if more than one distinct value exists.

- [ ] **Step 2: Implement `pending_pump_trade_evidence`**

Select raw evidence with `NOT EXISTS` matching canonical `(signature, ordinal)`, deterministic oldest-first ordering, bounded limit, using the existing lossless raw decoder.

- [ ] **Step 3: Run focused/full storage tests GREEN**

Expected: PASS.

---

### Task 5: RED — Define raw Pump evidence → canonical FastEvent normalizer

**Files:**
- Create: `crates/shreks-observer/tests/pump_fast_event_normalization.rs`

**Interfaces required:**

```rust
pub struct PumpFastEventNormalizationReport {
    pub raw_rows_seen: usize,
    pub canonical_rows_inserted: usize,
    pub rows_waiting_for_decimals: usize,
}

impl Observer {
    pub fn normalize_pending_pump_fast_events_at(
        db: &ShreksDb,
        accepted_at_unix_ms: i64,
        limit: usize,
    ) -> Result<PumpFastEventNormalizationReport, ObserverError>;
}
```

- [ ] **Step 1: Missing base decimals stays pending**

Persist one valid raw Pump SOL-quote trade with no mint state. Normalize and assert zero canonical rows, one waiting row, raw evidence untouched.

- [ ] **Step 2: Verified base decimals canonicalizes SOL quote**

Insert base mint state with verified decimals. Normalize at a later acceptance time and assert:

```text
sequence = 1
provider = Helius
venue = PumpFunBondingCurve
quote mint = wrapped SOL
quote decimals = 9
base decimals = verified value
source observation = original websocket time
FastEvent observation = supplied acceptance time
occurred time = chain event seconds * 1000
price = normalized quote/base
```

- [ ] **Step 3: Non-SOL quote waits for quote decimals**

With base decimals only, non-SOL quote remains pending. After a durable quote-mint state with consistent decimals exists, the same raw row canonicalizes.

- [ ] **Step 4: Replay and late occurrence remain monotonic by acceptance**

Normalize one event, then later normalize another whose chain occurrence is older but whose acceptance time is newer. Replay into `FastMarketState` and assert both events apply in sequence because observation time is monotonic.

- [ ] **Step 5: Contradictory decimals/provider mismatch fail closed**

Contradictory mint decimals or non-Helius raw provenance must return an observer/storage error rather than fabricate an event.

- [ ] **Step 6: Prove RED**

Expected: compile failure only because normalization report/API do not exist.

---

### Task 6: GREEN — Implement bounded canonical normalizer

**Files:**
- Modify: `crates/shreks-observer/src/runtime.rs`
- Modify: `crates/shreks-observer/src/lib.rs` only for focused public re-export if required; avoid whole-file replacement.
- Modify: `crates/shreks-providers/src/pump_trade.rs` only if a public SOL-quote helper is needed; preserve existing conversion API.

- [ ] **Step 1: Add a single canonical SOL-quote predicate if needed**

Keep SOL/default-quote identity logic provider-owned so observer does not duplicate a magic mint constant.

- [ ] **Step 2: Convert storage raw row to `PumpTradeEvidence` losslessly**

Require Helius provenance. Preserve every raw economic field.

- [ ] **Step 3: Resolve decimals**

Missing base or non-SOL quote decimals increments waiting count and leaves the row pending. Contradiction is fatal.

- [ ] **Step 4: Allocate stable sequence and convert using existing provider function**

Use `next_fast_event_sequence`; call `pump_trade_evidence_to_fast_event` with canonical acceptance time; append with raw source observation and decimals.

- [ ] **Step 5: Run focused observer normalization test GREEN, then Rust workspace tests**

Expected: PASS.

---

### Task 7: RED/GREEN — Retry pending normalization inside supervised realtime writer

**Files:**
- Modify: `crates/shreks-observer/tests/pump_realtime_evidence.rs`
- Modify: `crates/shreks-observer/src/runtime.rs`

**Behavior:**
- each accepted realtime envelope triggers a bounded normalization pass;
- a Tokio interval periodically retries pending rows so mint-state arrival can unlock normalization without requiring another trade;
- no network/provider call is introduced;
- channel closure drains accepted envelopes and performs a final bounded normalization pass;
- storage/integrity error remains fatal to the supervised writer.

- [ ] **Step 1: Write RED runtime tests**

Use deterministic storage fixtures and paused/short Tokio time where appropriate. Require a row waiting for decimals to become canonical after mint state is inserted and the retry tick runs.

- [ ] **Step 2: Implement minimal bounded retry**

Use a fixed internal retry interval and bounded batch constant. Do not add an external configuration surface in this slice.

- [ ] **Step 3: Run focused tests GREEN**

Expected: PASS.

---

### Task 8: Full verification, diff audit, and merge gate

**Files:** no new planned behavior.

- [ ] **Step 1: Run/require full CI**

Required GREEN:

```text
Rust tests
Python tests
Repository safety
ARM64 release build
```

- [ ] **Step 2: Audit diff**

Allowed scope: canonical journal migration/storage, raw-to-canonical normalizer, observation-only writer retry, tests/spec/plan. No strategy/PAPER/risk/executor/systemd/LIVE change.

- [ ] **Step 3: Verify deterministic replay contract**

Tests must demonstrate restart-stable sequence, idempotent duplicate handling, late occurrence with monotonic observation, and no decimal guesses.

- [ ] **Step 4: Merge only with exact GREEN head SHA**

Squash merge, then require merged-main CI GREEN before the next FL1 slice.

- [ ] **Step 5: Next FL1 slice**

After merge, proceed to remaining economically relevant event-family coverage—especially PumpSwap/post-graduation swaps and explicit checkpoint/production acceptance—without claiming FL1 complete beforehand.
