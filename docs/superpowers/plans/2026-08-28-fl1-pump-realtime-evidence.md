# FL1 Pump Realtime Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse Shreks' existing confirmed Pump websocket to decode authoritative Pump trade events immediately and persist immutable raw economic evidence without adding a second websocket, a per-trade RPC fetch, or any trading authority.

**Architecture:** `PumpLogStream` will expose a realtime envelope that may contain an existing lifecycle signal and zero or more decoded `PumpTradeEvidence` rows from the same notification. The observer remains the only durable writer: it records lifecycle inbox rows through existing methods and writes trade evidence to a new immutable `(signature, ordinal)` SQLite table. Raw amounts stay raw until verified mint decimals are available; this slice does not normalize them to `FastEvent` in production.

**Tech Stack:** Rust 2024, Tokio, tokio-tungstenite, serde_json, base64/bs58, rusqlite/SQLite WAL, existing Shreks provider/observer/storage crates.

**Spec:** `SHREKS_MASTER_SOURCE_OF_TRUTH.md` and `SHREKS_BUILD_ORDER.md` FL1.

## Global Constraints

- LIVE trading remains disabled.
- Use the existing single Pump `logsSubscribe` connection at confirmed commitment; do not create another Pump websocket.
- Do not add a `getTransaction` request to the realtime trade hot path.
- Decode only Pump-active `Program data` using the already pinned `tradeEvent` schema.
- Requested instruction max/min amounts are never treated as actual fills.
- Do not assume base-token or quote-token decimals; raw evidence is persisted first.
- Preserve existing Create/Migrate lifecycle APIs and tests.
- Duplicate `(signature, ordinal)` evidence with identical economics is idempotent; conflicting evidence for the same identity fails closed.
- Persist full Solana `u64` values as decimal text where SQLite INTEGER cannot represent the entire domain.
- The observer remains incapable of creating or executing trade intents.

---

### Task 1: Realtime Pump notification contract

**Files:**
- Modify: `crates/shreks-providers/src/pump_trade.rs`
- Modify: `crates/shreks-providers/src/pump.rs`
- Modify: `crates/shreks-providers/src/lib.rs`
- Test: `crates/shreks-providers/tests/pump_realtime.rs`
- Compatibility test: `crates/shreks-providers/tests/pump_stream.rs`

**Interfaces:**
- Produces: `PumpRealtimeNotification { signature, slot, lifecycle, trades }`.
- Produces: `PumpLogStream::next_realtime_notification()`.
- Produces: `PumpRealtimeSignalSource` and `forward_pump_realtime_signals`.
- Preserves: `PumpLogStream::next_lifecycle_signal()`, `PumpSignalSource`, and `forward_pump_signals`.

- [ ] Write RED tests proving one confirmed Pump notification containing `BuyV2` plus a valid `tradeEvent` yields one realtime notification with the decoded actual economics, while lifecycle-only notifications still work and trade-only notifications are skipped by the legacy lifecycle API.
- [ ] Add RED coverage that failed transactions, spoofed `Program data`, malformed trade events, and unrelated notifications do not become valid economic evidence.
- [ ] Prove RED fails because the realtime envelope/API does not exist.
- [ ] Refactor the existing private trade-event log collector into a crate-visible/public parser usable directly from a `logsNotification` without a transaction RPC response.
- [ ] Implement `PumpRealtimeNotification` and `next_realtime_notification()` using the same websocket frame/reconnect/heartbeat loop.
- [ ] Implement the new realtime forwarding trait/function while leaving legacy lifecycle forwarding intact.
- [ ] Run focused provider tests and full Rust tests.

### Task 2: Immutable raw Pump trade evidence storage

**Files:**
- Create: `crates/shreks-storage/migrations/0010_fast_lane_pump_trade_evidence.sql`
- Create: `crates/shreks-storage/src/fast_lane.rs`
- Modify: `crates/shreks-storage/src/lib.rs`
- Test: `crates/shreks-storage/tests/pump_trade_evidence_storage.rs`

**Interfaces:**
- Produces: `StoredPumpTradeEvidence` read model.
- Produces: `ShreksDb::record_pump_trade_evidence(provider, signature, ordinal, slot, observed_at_unix_ms, evidence) -> Result<bool, StorageError>` where `true` means inserted and `false` means an identical row already existed.
- Produces: query helper(s) for deterministic verification/replay tests.

- [ ] Write RED tests for schema version 10, full-u64 decimal-text round trip, deterministic ordinal ordering, identical duplicate no-op, conflicting duplicate rejection, and invalid identity/time rejection.
- [ ] Prove RED fails because migration/table/storage API does not exist.
- [ ] Add migration 0010 with primary key `(signature, ordinal)`, source provider, raw identity/economic/reserve fields, and indexes for mint/time and observation time.
- [ ] Implement strict validation and canonical row comparison. Never use `INSERT OR REPLACE` for immutable economic truth.
- [ ] Run focused storage tests and full Rust tests.

### Task 3: Observer single-writer realtime persistence

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Test: `crates/shreks-observer/tests/pump_realtime_evidence.rs`
- Compatibility tests: existing Pump launch/migration ingestion and verification tests.

**Interfaces:**
- Produces: `Observer::with_pump_realtime_receiver(...)`.
- Reuses: existing launch/migration inbox storage methods.
- Reuses: new `record_pump_trade_evidence` storage boundary.

- [ ] Write RED test sending a realtime trade notification into the observer and proving raw evidence is durably stored without any transaction-provider/network call.
- [ ] Add RED test for a notification carrying lifecycle plus trade data, proving both durable paths are written once.
- [ ] Add report counters for received/stored Pump trade events where useful for acceptance evidence.
- [ ] Implement realtime receiver draining and persistence in both cycle and between-cycle wakeup paths.
- [ ] Preserve the existing lifecycle-only receiver for compatibility tests and callers.
- [ ] Run focused observer tests and full Rust tests.

### Task 4: Production binary uses the same single Pump socket

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Test: `crates/shreks-observer/tests/runtime.rs` or a focused source-contract test if existing runtime tests cannot observe construction safely.

**Interfaces:**
- Consumes: `forward_pump_realtime_signals` and `Observer::with_pump_realtime_receiver`.
- Preserves: one `PumpLogStream` instance when Helius is enabled.

- [ ] Add RED source/runtime contract proving the production binary wires one Pump stream/forwarder and does not add a second Pump subscription or per-trade transaction fetch loop.
- [ ] Switch the existing forwarder/channel from lifecycle-only to realtime notification envelopes.
- [ ] Keep logging redaction and shutdown semantics unchanged.
- [ ] Run full workspace CI: Rust, Python, repository safety, native ARM64 release build.
- [ ] Audit the PR diff for no risk/executor/PAPER/LIVE changes and no second Pump websocket.
- [ ] Merge only after all gates are GREEN, then verify merged-main CI.

## Deferred to the next FL1 slice

- Resolve/cache base and quote decimals efficiently and convert stored raw evidence into canonical `FastEvent` rows.
- Durable FastEvent replay/checkpoint normalization.
- PumpSwap/post-graduation swap-event decoding.
- Production VPS read-only acceptance/throughput measurements after the complete FL1 event path is ready.
