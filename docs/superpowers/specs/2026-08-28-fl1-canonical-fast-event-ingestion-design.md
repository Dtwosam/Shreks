# FL1 Canonical FastEvent Ingestion Design

## Purpose

Turn immutable Pump websocket trade evidence into a durable, replayable, strictly sequenced canonical `FastEvent` journal without guessing token decimals or pretending normalized information was usable before it actually was.

This is an FL1 durability/ordering slice. It does not add strategy decisions, PAPER actions, execution economics, risk changes, or LIVE authority.

## Existing inputs

The repository already provides:

- `PumpRealtimeNotification` from one confirmed Pump websocket;
- immutable raw `pump_trade_evidence` keyed by `(signature, ordinal)`;
- `PumpTradeEvidence` and `pump_trade_evidence_to_fast_event(...)`;
- `FastEvent`, `FastEventId`, `FastMarketKey`, and `FastMarketState`;
- verified SPL mint decimals in `token_mint_states` when chain observation has completed.

Raw evidence is authoritative for economic amounts. `FastEvent` quantities must not be created until the required decimal metadata is verified.

## Chosen architecture

### 1. Raw evidence remains immutable source truth

`pump_trade_evidence` is not rewritten or reinterpreted. Its first local websocket observation timestamp remains the source-observation timestamp for audit and latency measurement.

### 2. Canonical FastEvents use a separate append-only journal

Migration 11 adds `fast_events` with:

- durable SQLite-assigned `sequence`;
- unique economic identity `(signature, ordinal)`;
- provider, market, venue, side, actor, slot;
- chain occurrence time;
- canonical observation/acceptance time;
- original raw source-observation time;
- normalized base/quote quantities and quote price;
- exact base/quote decimals used for normalization;
- foreign-key linkage back to `pump_trade_evidence`.

Sequence is stable once assigned. Replay orders by `sequence`, never by a dynamic row number.

### 3. Observation time means usable information time

If raw evidence arrives before verified decimals, the raw row is durable but no canonical `FastEvent` exists yet. When decimals later become available, canonicalization uses the normalization/acceptance clock as `FastEvent.observed_at_unix_ms`.

This prevents a delayed normalization from being inserted later in sequence while carrying an earlier observation timestamp that would make `FastMarketState` move its observation clock backward. The original websocket time remains separately stored as `source_observed_at_unix_ms`.

### 4. Decimals are resolved fail-closed

For a mint, Shreks queries all durable `token_mint_states` associated with candidate rows for that mint:

- no verified value -> pending, do not normalize;
- exactly one distinct value -> use it;
- contradictory durable values -> storage integrity error, stop rather than guess.

SOL/WSOL quote decimals are protocol-known at 9. Non-SOL quote markets require verified quote-mint decimals from durable evidence; otherwise they remain pending.

### 5. Bounded pending normalization

Storage exposes raw Pump trade rows not yet represented in `fast_events`, ordered by first local source observation then signature/ordinal. The observer normalizer processes a bounded batch.

For each row:

1. require Helius provenance for the current Pump parser path;
2. resolve base decimals;
3. resolve quote decimals or use 9 for SOL/WSOL;
4. obtain the next durable append sequence from the canonical journal;
5. call the existing provider-owned evidence-to-`FastEvent` conversion;
6. append idempotently to `fast_events`;
7. leave rows with missing decimals pending without fabrication.

Conflicting canonical replay fails closed. Identical replay is a no-op and preserves the original sequence.

### 6. Realtime writer integration

The existing realtime writer remains the single storage boundary. After accepting each websocket envelope it attempts a bounded normalization pass. A short timer also retries pending rows so an event can become canonical after the slow chain observer writes mint decimals even if no later Pump trade arrives.

The normalizer performs no network calls. Unexpected storage/integrity failures remain fatal to the already supervised writer, causing systemd restart rather than silent evidence loss.

## Ordering policy

Canonical sequence is append/acceptance order, not chain occurrence order. A late chain event is allowed when observed later; its `occurred_at_unix_ms` may precede a previously accepted event while `observed_at_unix_ms` and sequence continue forward. This matches the existing Fast Lane observation-clock contract and prevents future leakage.

Same-signature multi-event order is deterministic through `ordinal`. Duplicate reconnect/replay overlap cannot create a second canonical event because `(signature, ordinal)` is unique.

## Replay contract

Storage provides deterministic canonical replay ordered by `sequence`. Reopening the database preserves sequence and payload exactly. Applying the same replay stream to a fresh `FastMarketState` must reproduce the same snapshot for the same `as_of` time.

## Explicit non-goals

This slice does not:

- decode PumpSwap/post-graduation swaps;
- add lifecycle/liquidity/creator variants to `FastEventKind`;
- claim FL1 complete;
- change FastMarketState feature contents;
- add learned forecasts;
- price execution or compute maximum acceptable entry;
- create `TradeIntent`;
- enable LIVE trading.

PumpSwap/event-family expansion follows after this canonical Pump journal is proven.

## Acceptance

The slice is accepted only when tests prove:

- schema migration preserves prior evidence;
- sequence survives restart and strictly increases for new canonical events;
- identical duplicate raw evidence produces one canonical event;
- conflicting replay fails closed;
- missing decimals never produce a `FastEvent`;
- contradictory decimals fail closed;
- SOL quote uses 9 decimals without a network call;
- non-SOL quote requires verified quote decimals;
- canonical observation time never predates source observation or chain occurrence;
- replay is deterministic and compatible with `FastMarketState`;
- realtime normalization remains bounded and observation-only;
- Rust, Python, repository safety, and native ARM64 CI are GREEN.
