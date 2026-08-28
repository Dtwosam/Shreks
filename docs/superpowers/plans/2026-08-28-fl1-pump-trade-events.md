# FL1 Pump Trade Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode authoritative pre-graduation Pump buy/sell economics into provider-owned evidence and convert that evidence into canonical `FastEvent` values without guessing token decimals or using requested slippage limits as fills.

**Architecture:** Extend `shreks-providers::pump` with exact Pump trade-signal classification, current official `tradeEvent` log decoding, and a pure evidence-to-`FastEvent` conversion. Raw onchain amounts stay integer base units until the caller supplies verified base/quote decimals. This slice is observation-only: no SQLite schema, observer wiring, PAPER action, risk, or LIVE authority changes.

**Tech Stack:** Rust 2024, serde_json, bs58, base64, existing `shreks-core` Fast Lane domain types.

**Spec:** `SHREKS_MASTER_SOURCE_OF_TRUTH.md` and FL1 in `SHREKS_BUILD_ORDER.md`.

## Global Constraints

- LIVE remains disabled.
- DEX Screener is not authoritative for 1–10 second Fast Lane order flow.
- Pump instruction limits (`max_*` / `min_*`) are not treated as actual fills.
- `tradeEvent` actual amounts are the economic source of truth for this slice.
- Non-SOL quote markets must not be silently normalized with SOL decimals.
- Future runtime wiring must remain restart-safe and auditable; this slice does not claim FL1 complete.

---

### Task 1: Define the RED Pump trade evidence contract

**Files:**
- Modify: `crates/shreks-providers/tests/pump.rs`

**Interfaces:**
- Consumes: current Pump program ID and transaction JSON shape.
- Produces tests requiring `PumpTradeEvidence`, `PumpTradeVerification`, `classify_pump_trade_transaction`, exact trade discriminators, and `PUMP_TRADE_EVENT_DISCRIMINATOR`.

- [ ] **Step 1: Write failing tests**

Cover:

```rust
assert_eq!(PUMP_TRADE_EVENT_DISCRIMINATOR, [189, 219, 127, 211, 78, 230, 97, 238]);
```

Build successful `getTransaction` JSON whose Pump-active `Program data:` contains one Borsh-encoded official `tradeEvent`. Assert the decoded evidence preserves:

```rust
mint, raw token amount, raw SOL/quote amount, side, user, timestamp,
post-trade reserves, quote mint, ix_name
```

Also assert:

```text
result=null -> Pending
failed onchain tx -> Rejected
non-Pump Program data with the same bytes -> ignored/rejected
Pump tx without a verified Pump trade instruction -> rejected
malformed trade-event payload -> provider InvalidResponse
multiple real Pump trade events -> deterministic vector order
```

- [ ] **Step 2: Run focused Rust tests and prove RED**

Run:

```bash
cargo test -p shreks-providers --test pump
```

Expected: compile/test failure only because the new trade-evidence API does not exist.

---

### Task 2: Implement authoritative Pump trade-event decoding

**Files:**
- Modify: `crates/shreks-providers/Cargo.toml`
- Modify: `crates/shreks-providers/src/pump.rs`

**Interfaces:**
- Produces:

```rust
pub const PUMP_BUY_DISCRIMINATOR: [u8; 8];
pub const PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR: [u8; 8];
pub const PUMP_BUY_V2_DISCRIMINATOR: [u8; 8];
pub const PUMP_SELL_DISCRIMINATOR: [u8; 8];
pub const PUMP_SELL_V2_DISCRIMINATOR: [u8; 8];
pub const PUMP_TRADE_EVENT_DISCRIMINATOR: [u8; 8];

pub struct PumpTradeEvidence {
    pub mint: String,
    pub quote_mint: String,
    pub user: String,
    pub is_buy: bool,
    pub token_amount_raw: u64,
    pub sol_amount_raw: u64,
    pub quote_amount_raw: u64,
    pub timestamp_unix_seconds: i64,
    pub virtual_sol_reserves_raw: u64,
    pub virtual_token_reserves_raw: u64,
    pub real_sol_reserves_raw: u64,
    pub real_token_reserves_raw: u64,
    pub virtual_quote_reserves_raw: u64,
    pub real_quote_reserves_raw: u64,
    pub ix_name: String,
}

pub enum PumpTradeVerification {
    Pending,
    Verified(Vec<PumpTradeEvidence>),
    Rejected(String),
}

pub fn classify_pump_trade_transaction(
    body: &str,
    signature: &str,
) -> Result<PumpTradeVerification, ProviderError>;
```

- [ ] **Step 1: Add base64 dependency**

Add:

```toml
base64 = "0.22"
```

- [ ] **Step 2: Decode only Pump-active `Program data:`**

Track Solana log invocation stack from:

```text
Program <id> invoke [N]
Program <id> success
Program <id> failed: ...
```

Decode `Program data: <base64>` only while the active program is exactly `PUMP_PROGRAM_ID`.

- [ ] **Step 3: Decode the current official Borsh `tradeEvent` schema**

Read little-endian integers, bool, 32-byte pubkeys (base58), Borsh string, and `Vec<shareholder>` safely with bounds checks. Reject malformed/truncated payloads as `ProviderErrorKind::InvalidResponse`.

- [ ] **Step 4: Require a real Pump trade instruction**

Collect Pump-program instructions from top-level and inner instructions and recognize only pinned official trade discriminators. A decoded event must have a compatible real Pump trade instruction in the same successful transaction; otherwise it is not verified economic evidence.

- [ ] **Step 5: Run focused tests GREEN**

```bash
cargo test -p shreks-providers --test pump
```

Expected: PASS.

---

### Task 3: Convert raw evidence into canonical FastEvent without decimal guesses

**Files:**
- Modify: `crates/shreks-providers/tests/pump.rs`
- Modify: `crates/shreks-providers/src/pump.rs`

**Interfaces:**
- Produces:

```rust
pub fn pump_trade_evidence_to_fast_event(
    evidence: &PumpTradeEvidence,
    signature: &str,
    ordinal: u32,
    sequence: u64,
    slot: u64,
    observed_at_unix_ms: i64,
    base_decimals: u8,
    quote_decimals: u8,
) -> Result<FastEvent, ProviderError>;
```

- [ ] **Step 1: Write RED conversion tests**

Assert:

```text
raw quantities normalize only from supplied decimals
SOL/default quote mint canonicalizes to wrapped SOL market identity
non-SOL quote uses quote_amount_raw and supplied quote decimals
price_quote = normalized_quote_quantity / normalized_base_quantity
actor = event user
provider = Helius
venue = PumpFunBondingCurve
event id = signature + ordinal
occurred timestamp = event seconds * 1000
invalid/zero economic quantities fail closed
observed_at earlier than occurred_at fails closed
```

- [ ] **Step 2: Prove RED**

```bash
cargo test -p shreks-providers --test pump
```

Expected: failure because conversion API does not exist.

- [ ] **Step 3: Implement minimal conversion**

Use existing `FastEventId`, `FastMarketKey`, `FastEventKind`, and `FastEvent::new`. For SOL-paired events use actual `sol_amount_raw`; for generalized quote markets use `quote_amount_raw`. Never substitute instruction slippage limits.

- [ ] **Step 4: Run focused tests GREEN**

```bash
cargo test -p shreks-providers --test pump
```

Expected: PASS.

---

### Task 4: Add exact cheap trade-signal classification for next runtime slice

**Files:**
- Modify: `crates/shreks-providers/tests/pump.rs`
- Modify: `crates/shreks-providers/src/pump.rs`

**Interfaces:**
- Produces exact-log helper(s) that recognize successful Pump `Buy`, `BuyExactSolIn`, `BuyV2`, `Sell`, and `SellV2` transaction signatures without converting the websocket log itself into economic evidence.

- [ ] **Step 1: Write RED tests**

Assert exact instruction-log tails trigger a trade signal, substring/spoof names do not, failed transactions do not, and existing Create/Migrate compatibility APIs remain unchanged.

- [ ] **Step 2: Implement exact classification**

The websocket result remains only a cheap signature+slot trigger. Actual economics always require fetched transaction verification from Task 2.

- [ ] **Step 3: Run focused tests GREEN**

```bash
cargo test -p shreks-providers --test pump
```

Expected: PASS.

---

### Task 5: Full verification and merge gate

**Files:** no new production scope.

- [ ] **Step 1: Run full Rust workspace tests**

```bash
cargo test --workspace
```

- [ ] **Step 2: Run authoritative repository CI**

Require GREEN:

```text
Rust tests
Python tests
Repository safety
ARM64 release build
```

- [ ] **Step 3: Audit diff**

Confirm no SQLite migration, observer/runtime persistence, PAPER/risk/action, executor, signing, deployment, or LIVE-mode change exists.

- [ ] **Step 4: Merge only with exact GREEN evidence**

After merge, verify merged-main CI before beginning the next FL1 slice: durable live Pump/PumpSwap event-stream wiring and checkpoints.
