# Fast Lane Event-State Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first deterministic Rust Fast Lane domain contract: replayable trade events plus per-market rolling microstructure state, without wiring providers or granting trading authority.

**Architecture:** `shreks-core` remains the owner of provider-neutral shared Rust domain primitives. Add a focused `fast_lane` module split into event identity/validation and rolling state aggregation. The state engine consumes a pre-ordered, deduplicated event stream and produces deterministic rolling summaries; provider parsing, SQLite persistence, execution economics, forecasting, and trading decisions stay out of this PR.

**Tech Stack:** Rust 2021, `shreks-core`, standard library only, Cargo integration tests, GitHub Actions CI including native ARM64.

**Spec:** `SHREKS_MASTER_SOURCE_OF_TRUTH.md`; sequencing: `SHREKS_BUILD_ORDER.md` FL0 and FL2.

## Global Constraints

- LIVE trading remains disabled.
- This slice must not create or execute `TradeIntent`s.
- Manipulation/wallet/creator activity is data, not a token-level veto; this slice performs no strategy filtering.
- Prediction horizons are not timers; rolling windows are feature/state summaries only.
- DEX Screener is not introduced into the Fast Lane state contract.
- No paid dependency or new infrastructure is introduced.
- No database migration in this slice.
- No learned model in this slice.
- TDD is mandatory: RED test commit before production implementation.
- Replaying the same ordered event stream must reproduce the same snapshot exactly for the same inputs.

---

## Repository Map Used By This Plan

Existing boundaries inspected before implementation:

- `crates/shreks-core/src/lib.rs` owns shared provider-neutral domain primitives such as `ProviderId`, `VenueId`, `DiscoveredToken`, and lifecycle/wallet types.
- `crates/shreks-core/src/lifecycle.rs` currently represents Pump graduation only; it does not represent buy/sell micro-events.
- `crates/shreks-providers/src/pump.rs` currently discovers/verifies Create/CreateV2 and Migrate/MigrateV2 signals; it does not yet expose canonical Pump buy/sell Fast Lane events.
- `crates/shreks-observer/src/lib.rs` owns observe-only orchestration, persists Pump lifecycle inboxes, verifies transactions, and is intentionally incapable of creating/executing trade intents.
- `crates/shreks-storage` owns durability/checkpoints and is intentionally not changed by this slice.
- `crates/shreks-core/tests/` already uses external integration tests for public domain contracts.

This means the first safe build unit is a pure core state engine. FL1 provider wiring follows in a separate PR after this contract is proven.

---

## File Structure

**Create:** `crates/shreks-core/src/fast_lane/mod.rs`  
Public module surface and re-exports only.

**Create:** `crates/shreks-core/src/fast_lane/event.rs`  
Owns `FastMarketKey`, `FastEventId`, `FastEventKind`, `FastEvent`, constructors/validation, and event validation errors.

**Create:** `crates/shreks-core/src/fast_lane/state.rs`  
Owns default window constants, `FastMarketState`, `FastWindowSummary`, `FastMarketSnapshot`, apply/snapshot errors, ordering checks, retention, and rolling aggregation.

**Modify:** `crates/shreks-core/src/lib.rs`  
Expose the new public Fast Lane domain surface; no behavior changes elsewhere.

**Create:** `crates/shreks-core/tests/fast_lane_state.rs`  
External contract tests proving validation, ordering, exact window boundaries, aggregation, key isolation, and deterministic replay.

No other crate changes in this slice.

---

### Task 1: RED — Define the public event/state contract through tests

**Files:**
- Create: `crates/shreks-core/tests/fast_lane_state.rs`

**Interfaces consumed:**
- Existing `ProviderId`
- Existing `VenueId`

**Interfaces the test requires production to provide:**

```rust
pub const DEFAULT_FAST_WINDOWS_MS: [u64; 7] = [100, 250, 500, 1_000, 2_000, 5_000, 10_000];

pub struct FastMarketKey { ... }
pub struct FastEventId { ... }
pub enum FastEventKind { Buy, Sell }
pub struct FastEvent { ... }
pub struct FastMarketState { ... }
pub struct FastMarketSnapshot { ... }
pub struct FastWindowSummary { ... }
pub enum FastEventError { ... }
pub enum FastStateError { ... }
```

Constructors/methods required by tests:

```rust
FastMarketKey::new(mint, quote_mint, venue) -> Result<FastMarketKey, FastEventError>
FastEventId::new(signature, ordinal) -> Result<FastEventId, FastEventError>
FastEvent::new(...) -> Result<FastEvent, FastEventError>
FastMarketState::with_default_windows(key) -> FastMarketState
FastMarketState::apply(event) -> Result<(), FastStateError>
FastMarketState::snapshot(as_of_unix_ms) -> Result<FastMarketSnapshot, FastStateError>
```

`FastEvent::new` arguments in this slice:

```rust
pub fn new(
    id: FastEventId,
    sequence: u64,
    provider: ProviderId,
    market: FastMarketKey,
    kind: FastEventKind,
    actor: Option<String>,
    slot: u64,
    occurred_at_unix_ms: i64,
    observed_at_unix_ms: i64,
    base_quantity: f64,
    quote_quantity: f64,
    price_quote: f64,
) -> Result<Self, FastEventError>
```

- [ ] **Step 1: Write one integration test for valid buy/sell aggregation**

Use one Pump bonding-curve market with a buy at `1000ms` and sell at `1250ms`, snapshot at `1300ms`. Assert:

- 100ms window sees only the sell,
- 250ms window sees only the sell because the buy is older than the cutoff,
- 500ms window sees both,
- buy/sell counts are correct,
- buy/sell quote quantities are correct,
- net quote flow is `buy_quote_quantity - sell_quote_quantity`,
- last price equals the latest accepted event price.

- [ ] **Step 2: Write the exact-boundary inclusion test**

An event at `1000ms` must be included in the `250ms` window of a snapshot at `1250ms`. The window is inclusive at the lower boundary: `[as_of - window_ms, as_of]`.

- [ ] **Step 3: Write state-identity and ordering tests**

Assert:

- an event for a different market key is rejected,
- sequence must strictly increase,
- event `occurred_at_unix_ms` must not move backward relative to the last accepted event,
- a later sequence with the same occurrence timestamp is allowed.

- [ ] **Step 4: Write deterministic replay test**

Apply the exact same event vector to two fresh states and assert identical snapshots at the same `as_of_unix_ms`.

- [ ] **Step 5: Write constructor validation tests**

Reject:

- empty mint,
- empty quote mint,
- empty signature,
- empty actor when `Some`,
- negative timestamps,
- `observed_at_unix_ms < occurred_at_unix_ms`,
- non-finite/negative quantities,
- non-finite/non-positive price.

Zero quantity is allowed because parsers may later represent zero-quantity lifecycle/economic markers with a different kind; Buy/Sell events in this slice should require positive base and quote quantities. The test must therefore assert Buy/Sell zero quantities are rejected.

- [ ] **Step 6: Run focused RED**

Run:

```bash
cargo test -p shreks-core --test fast_lane_state
```

Expected: compilation/test failure because the `fast_lane` public contract does not exist yet. Confirm no unrelated failure is responsible.

- [ ] **Step 7: Commit RED only**

Commit message:

```text
test: define Fast Lane event-state contract
```

Do not add production files in this commit.

---

### Task 2: GREEN — Implement canonical Fast Lane event primitives

**Files:**
- Create: `crates/shreks-core/src/fast_lane/mod.rs`
- Create: `crates/shreks-core/src/fast_lane/event.rs`
- Modify: `crates/shreks-core/src/lib.rs`

**Consumes:** Existing `ProviderId`, `VenueId`.

**Produces:** Validated immutable market/event types consumed by Task 3 and later FL1 provider parsers.

- [ ] **Step 1: Add `fast_lane` module and public re-exports**

`crates/shreks-core/src/fast_lane/mod.rs` should initially contain:

```rust
mod event;
mod state;

pub use event::{
    FastEvent, FastEventError, FastEventId, FastEventKind, FastMarketKey,
};
pub use state::{
    FastMarketSnapshot, FastMarketState, FastStateError, FastWindowSummary,
    DEFAULT_FAST_WINDOWS_MS,
};
```

`lib.rs` should expose the module's public surface using the repository's existing re-export style.

- [ ] **Step 2: Implement `FastMarketKey`**

Fields:

```rust
pub mint: String,
pub quote_mint: String,
pub venue: VenueId,
```

Validation:

- mint/quote mint trimmed strings must be non-empty,
- keep venue explicit so pre-graduation bonding curve and post-graduation PumpSwap state cannot be accidentally merged.

- [ ] **Step 3: Implement `FastEventId`**

Fields:

```rust
pub signature: String,
pub ordinal: u32,
```

The future FL1 parser assigns `ordinal` deterministically within one transaction/signature. This avoids assuming one Solana transaction contains only one economic event.

- [ ] **Step 4: Implement `FastEventKind`**

Only:

```rust
Buy,
Sell,
```

Do not add creation/graduation/liquidity variants in this PR; lifecycle events already have a separate contract and FL1 will extend only when real parser requirements are known.

- [ ] **Step 5: Implement `FastEvent` validation**

Fields exactly matching the Task 1 constructor contract.

Validation:

- timestamps non-negative,
- observed timestamp cannot precede occurrence timestamp,
- `base_quantity` and `quote_quantity` finite and strictly positive,
- `price_quote` finite and strictly positive,
- `Some(actor)` must not be blank.

Keep quote values in **quote-asset units**, not mislabeled USD. FL3 later attaches explicit cost/FX/execution economics.

- [ ] **Step 6: Run focused test**

At this point state symbols may still be missing; event-constructor tests should compile only once Task 3 is present. Do not weaken RED assertions to get an intermediate pass.

---

### Task 3: GREEN — Implement deterministic rolling FastMarketState

**Files:**
- Create: `crates/shreks-core/src/fast_lane/state.rs`

**Consumes:** `FastEvent`, `FastEventKind`, `FastMarketKey`.

**Produces:** Deterministic snapshots for later feature, execution-economics, baseline-strategy, labeling, and model layers.

- [ ] **Step 1: Define default windows**

```rust
pub const DEFAULT_FAST_WINDOWS_MS: [u64; 7] = [
    100, 250, 500, 1_000, 2_000, 5_000, 10_000,
];
```

These are feature windows, not action timers.

- [ ] **Step 2: Define `FastWindowSummary`**

Fields:

```rust
pub window_ms: u64,
pub buy_count: u64,
pub sell_count: u64,
pub buy_base_quantity: f64,
pub sell_base_quantity: f64,
pub buy_quote_quantity: f64,
pub sell_quote_quantity: f64,
pub net_quote_quantity: f64,
```

`net_quote_quantity = buy_quote_quantity - sell_quote_quantity`.

- [ ] **Step 3: Define `FastMarketSnapshot`**

Fields:

```rust
pub market: FastMarketKey,
pub as_of_unix_ms: i64,
pub last_sequence: Option<u64>,
pub last_price_quote: Option<f64>,
pub windows: Vec<FastWindowSummary>,
```

Provide a deterministic lookup helper:

```rust
pub fn window(&self, window_ms: u64) -> Option<&FastWindowSummary>
```

- [ ] **Step 4: Define `FastMarketState` internals**

Use standard-library structures only:

```rust
market: FastMarketKey,
windows_ms: Vec<u64>,
events: VecDeque<FastEvent>,
last_sequence: Option<u64>,
last_occurred_at_unix_ms: Option<i64>,
last_price_quote: Option<f64>,
```

`with_default_windows` clones the canonical window list.

- [ ] **Step 5: Implement strict apply policy**

Reject when:

- event market differs,
- sequence is not strictly greater than the last accepted sequence,
- occurrence timestamp moves backward.

Accept equal occurrence timestamps when sequence increases.

On accept:

- append event,
- update last sequence/time/price,
- prune events strictly older than `latest_occurrence - max_window_ms`.

Use `< cutoff`, not `<= cutoff`, so exact lower-bound events remain eligible.

- [ ] **Step 6: Implement snapshot aggregation**

Reject negative `as_of_unix_ms` and `as_of` earlier than the last accepted occurrence time.

For each window include accepted events satisfying:

```text
as_of - window_ms <= occurred_at_unix_ms <= as_of
```

Aggregate by `FastEventKind` without strategy filtering.

- [ ] **Step 7: Verify focused GREEN**

Run:

```bash
cargo test -p shreks-core --test fast_lane_state
```

Expected: PASS.

- [ ] **Step 8: Run all core tests**

```bash
cargo test -p shreks-core
```

Expected: all `shreks-core` tests PASS.

- [ ] **Step 9: Commit GREEN**

Commit message:

```text
feat: add deterministic Fast Lane market state
```

---

### Task 4: Verification and architecture audit

**Files:**
- No new behavior expected; only fix issues uncovered by verification.

- [ ] **Step 1: Run full Rust workspace tests**

```bash
cargo test --workspace
```

Expected: PASS.

- [ ] **Step 2: Run repository CI through the PR**

Required gates:

- Rust tests GREEN,
- Python tests GREEN,
- Repository safety GREEN,
- ARM64 native release build GREEN.

- [ ] **Step 3: Audit diff**

The completed PR should touch only:

- implementation plan,
- `shreks-core` module export,
- Fast Lane event/state files,
- Fast Lane integration test.

It must not touch:

- live executor,
- risk thresholds,
- PAPER economics,
- provider pacing,
- SQLite schema,
- systemd/deploy files,
- model training.

- [ ] **Step 4: Architecture assertions**

Verify from the diff/tests:

- no trade intent exists in the new module,
- no provider HTTP/WebSocket dependency exists in the new module,
- no token is rejected based on manipulation/suspicion,
- rolling windows are queried at arbitrary `as_of` timestamps,
- replay determinism is tested,
- quote quantities are not falsely labeled USD.

- [ ] **Step 5: Merge only after GREEN**

Use squash merge and record exact merge SHA plus branch and merged-main CI run IDs.

---

## Follow-On Slice — Explicitly Out of Scope Here

After this PR is merged, FL1 begins with a separate RED-first provider/parser PR:

1. pin Pump Buy/Sell instruction/event discriminators and account layouts from authoritative protocol evidence/code,
2. extend the existing Pump websocket/transaction path to identify economic signatures without weakening Create/Migrate verification,
3. normalize verified buys/sells into the new `FastEvent` contract,
4. preserve deterministic `ordinal` and ingestion sequence,
5. persist/replay with restart-safe checkpoints,
6. feed the proven state engine read-only,
7. benchmark event-to-state latency on the VPS.

Do not guess Pump trade layouts in the core-state PR.

---

## Self-Review

### Spec coverage

- Provider-neutral Fast Lane boundary: Task 2.
- Deterministic rolling state: Task 3.
- 100ms–10s windows: Task 3.
- Event ordering/out-of-order policy: Tasks 1 and 3.
- Replay determinism: Tasks 1 and 3.
- No token-level manipulation veto: architecture audit.
- No LIVE/trading authority: global constraints and audit.
- Real provider ingestion: deliberately deferred to the next FL1 PR because current Pump provider only verifies Create/Migrate and the trade parser must be designed from authoritative event layouts.

### Placeholder scan

No TODO/TBD/“similar to” implementation placeholders are permitted. Every task has an explicit contract and verification command.

### Type consistency

All state types consume the `FastEvent`/`FastMarketKey` contract defined earlier in the same plan. `quote_quantity` remains quote-asset units throughout; USD conversion/cost economics is intentionally FL3.
