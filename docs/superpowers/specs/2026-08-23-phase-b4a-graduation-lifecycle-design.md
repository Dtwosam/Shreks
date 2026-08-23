# Phase B4a Graduation Lifecycle Evidence Design

**Status:** Approved by standing autonomous-build instruction  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`  
**Base:** verified Phase B3 head `a365c77a0b5ecf2739c00e7ad178694de0fa3f2e`

## 1. Purpose

Phase B4a adds trustworthy Pump.fun graduation/migration evidence before Shreks implements the `Graduation/Breakout` setup family.

The master design defines Graduation/Breakout as a token transitioning from launch behavior into sustained liquidity and participation. The venue-priority amendment requires graduation timestamp/event, lifecycle stage, PumpSwap pool identity, and venue transitions to survive into later feature/strategy layers. The current observer verifies Pump creation but does not observe or persist graduation/migration.

B4a closes that data gap. It does **not** implement a strategy, score, paper trade, wallet signer, or live execution path.

## 2. Profitability and Research Rationale

A strategy called “Graduation/Breakout” must not infer graduation merely because generic price/volume momentum looks strong. That would mix lifecycle truth with price action and can create misleading backtests.

B4a therefore records actual protocol evidence first. Later research can measure questions such as:

- how long after detected graduation continuation tends to persist;
- whether post-graduation PumpSwap liquidity/volume expansion predicts net outcomes;
- whether immediate post-migration entries suffer worse price impact or adverse excursion;
- whether the best entry is at migration, after confirmation, or not at all.

The first locally observed migration timestamp is preserved separately from optional on-chain block time so backtests can use decision-safe information that Shreks actually had at the time.

## 3. Official Protocol Contract

B4a is pinned to Pump’s official public IDL as verified on 2026-08-23 from `pump-fun/pump-public-docs`, `idl/pump.json`, blob SHA:

```text
062e66f032bb9f295353b573be3400070bd55e5b
```

Verified program IDs already present in Shreks:

```text
Pump program:     6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P
PumpSwap program: pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA
```

Migration instructions that B4a must support:

### Legacy `migrate`

Discriminator:

```text
[155, 234, 231, 146, 236, 158, 162, 30]
```

Verified instruction-account positions:

- mint: index 2
- PumpSwap program: index 8
- PumpSwap pool: index 9
- quote mint: wrapped SOL, account index 14

### `migrate_v2`

Discriminator:

```text
[187, 203, 18, 31, 206, 237, 254, 41]
```

Verified instruction-account positions:

- base mint: index 2
- quote mint: index 3
- PumpSwap program: index 9
- PumpSwap pool: index 10

B4a must not assume every current/future Pump graduation is SOL-quoted. `migrate_v2` quote mint is persisted exactly as observed.

If Pump changes these instruction layouts in a future IDL, Shreks must add a new verified decoder path instead of silently shifting indexes.

## 4. Chosen Architecture

Three approaches were considered.

### A. Reuse the single Pump websocket and add lifecycle signal variants — chosen

The existing `PumpLogStream` already subscribes to Pump program logs and feeds one bounded channel into the SQLite-owning observer. B4a generalizes the normalized cheap signal into lifecycle variants:

```rust
pub enum PumpLifecycleSignal {
    Creation(PumpCreationSignal),
    Migration(PumpMigrationSignal),
}
```

This preserves one websocket connection, one reconnect loop, one bounded channel, and one SQLite writer.

### B. Open a second Pump websocket only for migration — rejected

This duplicates free-tier websocket traffic, reconnect behavior, and operational state for no data-quality benefit.

### C. Infer graduation from DEX market snapshots — rejected

Seeing a PumpSwap pair is useful enrichment but is not equivalent to proving the Pump migration transaction. It also loses precise first-detection and transaction provenance.

## 5. Cheap Signal Detection

`PumpLogStream` continues one standard Solana `logsSubscribe` on the Pump program.

A successful log notification becomes:

- `Creation` only when logs contain exact Anchor instruction suffix `Instruction: Create` or `Instruction: CreateV2`;
- `Migration` only when logs contain exact Anchor instruction suffix `Instruction: Migrate` or `Instruction: MigrateV2`.

The parser must **not** classify `Instruction: MigrateBondingCurveCreator` as graduation.

Failed on-chain log notifications remain ignored.

A cheap log signal is never lifecycle truth by itself. It only schedules confirmed-transaction verification.

## 6. Confirmed Migration Verification

Public verifier:

```rust
pub fn classify_pump_migration_transaction(
    body: &str,
    signature: &str,
    slot: u64,
    detected_at_unix_ms: i64,
) -> Result<PumpMigrationVerification, ProviderError>
```

`PumpMigrationVerification` has:

- `Pending` — RPC `result: null`; retry later;
- `Verified(Vec<TokenLifecycleEvent>)` — one or more verified Pump migration instructions;
- `Rejected(String)` — fetched transaction is terminally not a valid migration.

Verification requirements for each accepted instruction:

1. transaction succeeded on-chain;
2. instruction `programId` equals the verified Pump program ID;
3. base58-decoded instruction data begins with one of the two verified migration discriminators;
4. account list is long enough for that exact instruction generation;
5. the instruction’s PumpSwap-program account equals the verified PumpSwap program ID;
6. mint, quote mint, and pool values are non-empty;
7. legacy `migrate` quote mint equals the official wrapped-SOL mint;
8. duplicate `(mint, quote_mint, pool)` evidence inside one transaction is deduplicated deterministically.

Both top-level and inner instructions are inspected because protocol calls may appear through CPI/wrapper paths.

A fetched successful transaction with no valid migration instruction is `Rejected`, not `Pending`.

## 7. Normalized Lifecycle Domain Object

`shreks-core` adds:

```rust
pub enum LifecycleEventKind {
    PumpGraduation,
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
```

For B4a verified events:

- kind = `PumpGraduation`
- provider = `Helius`
- from venue = `PumpFunBondingCurve`
- to venue = `PumpSwap`
- `detected_at_unix_ms` = first locally persisted realtime migration-log observation
- `occurred_at_unix_ms` = transaction `blockTime * 1000` when present and valid; otherwise `None`

`detected_at_unix_ms` is the decision-safe timing field. Later strategies must not replace it with a verification time that occurred after the fact.

## 8. Durable Storage

Migration `0005_pump_graduation_lifecycle.sql` adds two boundaries.

### `pump_migration_signals`

Restart-safe verification inbox:

- `signature TEXT PRIMARY KEY`
- `slot TEXT NOT NULL`
- `observed_at_unix_ms INTEGER NOT NULL`
- `status TEXT NOT NULL` in `pending / verified / rejected`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `last_attempt_at_unix_ms INTEGER`
- `last_error TEXT`

Duplicate realtime signals preserve the earliest observation timestamp and never reset a terminal state.

### `token_lifecycle_events`

Normalized durable lifecycle truth:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `event_type TEXT NOT NULL`
- `provider TEXT NOT NULL`
- `mint TEXT NOT NULL`
- `quote_mint TEXT NOT NULL`
- `from_venue TEXT NOT NULL`
- `to_venue TEXT NOT NULL`
- `pool_address TEXT NOT NULL`
- `signature TEXT NOT NULL`
- `slot TEXT NOT NULL`
- `detected_at_unix_ms INTEGER NOT NULL`
- `occurred_at_unix_ms INTEGER`
- unique `(event_type, signature, mint, pool_address)`

The normalized table is mint-keyed rather than candidate-row-keyed because the operational database can legitimately contain multiple provider/pair candidate rows for one mint. Later feature assembly should join lifecycle truth by mint.

Indexes support:

- pending migration replay;
- lifecycle lookup by mint and detection time;
- lookup by event type and detection time.

## 9. Atomic Completion

Storage exposes an operation that atomically:

1. inserts every verified normalized lifecycle event idempotently;
2. marks the matching migration inbox signal `verified`;
3. clears its last error and records the final attempt timestamp.

A crash must not leave a signal terminally verified without its normalized lifecycle event.

Replaying the same verified transaction after restart is idempotent.

Rejection remains terminal and stores a bounded reason.

## 10. Observer Integration

The observer’s channel becomes `mpsc::Receiver<PumpLifecycleSignal>` while keeping one producer and one SQLite owner.

Realtime wake-ups remain durable-write-only:

- creation signal -> existing `pump_launch_signals` inbox;
- migration signal -> new `pump_migration_signals` inbox.

Confirmed transaction fetches still happen in normal observer cycles. This preserves current free-tier pacing and avoids an unbudgeted realtime RPC burst.

To avoid doubling Helius transaction pressure, one full cycle processes at most the existing bounded Pump verification budget. B4a allocates capacity across launch and migration work so neither class can permanently starve the other. Migration work may be prioritized within the bounded budget because graduation timing is more strategy-sensitive, but creation replay must retain guaranteed capacity.

Provider failures leave migration signals pending and increment operational failure telemetry; they never become false rejections.

## 11. Observer Telemetry

Existing creation counters keep their current meaning.

B4a adds explicit migration counters:

- `pump_migration_signals_received`
- `pump_migration_signals_processed`
- `pump_migration_signals_pending`
- `pump_migration_signals_verified`
- `pump_migration_signals_rejected`
- `lifecycle_events_stored`

This avoids silently changing the semantics of historical `pump_signals_*` telemetry.

## 12. Free-Tier / Failure Semantics

B4a adds no paid service and no hidden paid fallback.

- one existing Helius standard websocket remains the realtime source;
- confirmed transaction verification reuses the existing Helius transaction provider and pacing lane;
- `result: null`, rate limits, timeouts, and provider outages remain retryable/pending;
- malformed successful responses are provider failures, not fabricated lifecycle events.

Errors continue to avoid secret-bearing Helius endpoint strings.

## 13. Explicit Non-Goals

B4a does not:

- implement Graduation/Breakout setup thresholds;
- change B2 feature schema;
- create a trade score;
- create `TradeDecision` or `TradeIntent`;
- quote Jupiter;
- paper trade;
- sign or submit transactions;
- scrape Pump’s website;
- infer a migration solely from a PumpSwap market pair.

## 14. Exit Criteria

B4a is complete only when:

1. one Pump websocket emits both creation and migration signal variants without false-classifying `MigrateBondingCurveCreator`;
2. legacy `migrate` and `migrate_v2` confirmed transactions are verified using the pinned official layouts;
3. migration signals survive restart and retry;
4. verified migrations atomically create normalized Pump.fun -> PumpSwap lifecycle events;
5. duplicate signals/verification are idempotent;
6. observer telemetry distinguishes creation and migration;
7. existing Pump creation behavior remains green;
8. full Rust/Python/repository-safety CI passes on the exact final head.

Only after this evidence exists should B4b expose lifecycle features and B4c implement the Graduation/Breakout setup.
