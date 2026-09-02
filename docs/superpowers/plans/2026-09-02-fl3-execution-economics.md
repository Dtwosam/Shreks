# FL3 Execution Economics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, provider-neutral execution economics that calculate round-trip cost, exit-capacity eligibility, break-even movement, maximum acceptable entry price, and reprice/abort boundaries without granting trading authority.

**Architecture:** `shreks-core` owns pure quote-asset economics and checked algebra. Provider parsers retain current authoritative Pump/PumpSwap fee and virtual-reserve evidence so configuration/research can validate the cost inputs rather than hard-coding protocol fee constants. Venue-specific capacity helpers consume authoritative Fast Lane reserve context and explicit caller economic boundaries. Historical missing evidence remains unknown.

**Tech Stack:** Rust 2021, `shreks-core`, `shreks-providers`, `shreks-storage`, Cargo integration tests, GitHub Actions native ARM64 verification.

**Spec:** `docs/superpowers/specs/2026-09-02-fl3-execution-economics-design.md`

## Global Constraints

- LIVE remains disabled.
- No signer, transaction submission, wallet secret, or live-money authority changes.
- No `TradeIntent` creation in FL3.
- Keep all economics in quote-asset units; do not label native quote values as USD.
- No production fee/slippage/latency/risk-margin defaults in the core.
- Fee schedules are explicit/versioned inputs and must be verified from current protocol evidence before production use.
- Unknown source fee/virtual-reserve evidence remains unknown; do not backfill current protocol values into historical events.
- Preserve canonical FastEvent identity, source-derived replay, and existing database authority.
- TDD is mandatory: each production behavior gets an intentional RED before GREEN.
- Every GREEN head requires all four repository gates: safety, Rust, Python, native ARM64.

---

## File structure

**Create:** `crates/shreks-core/src/fast_lane/economics.rs`  
Pure cost inputs, assessment results, validation, break-even/max-entry algebra, and reprice invariant.

**Modify:** `crates/shreks-core/src/fast_lane/mod.rs` and `crates/shreks-core/src/lib.rs`  
Public re-exports only.

**Create:** `crates/shreks-core/tests/fast_lane_execution_economics.rs`  
Public FL3 economics contract tests.

**Modify later:** `crates/shreks-providers/src/pump_trade.rs`, `pump_swap_trade.rs`  
Retain fee/virtual-reserve evidence already emitted by protocol events.

**Modify later:** storage raw/source replay types only where required to preserve newly retained source evidence. Do not duplicate derived cost state into `fast_events`.

**Create later:** focused capacity tests/helpers under `shreks-core` Fast Lane.

---

### Task 1: RED — Define the provider-neutral economics contract

**Files:**
- Create: `crates/shreks-core/tests/fast_lane_execution_economics.rs`

**Interfaces required by the test:**

```rust
pub const EXECUTION_ECONOMICS_VERSION: u16 = 1;

pub struct ExecutionLegCostInput {
    pub effective_fee_bps: u32,
    pub expected_impact_bps: u32,
    pub expected_slippage_bps: u32,
    pub expected_latency_bps: u32,
    pub network_fee_quote: f64,
    pub priority_fee_quote: f64,
    pub expected_failure_cost_quote: f64,
}

pub struct ExecutionCostModel {
    pub version: u16,
    pub entry: ExecutionLegCostInput,
    pub exit: ExecutionLegCostInput,
}

pub struct ExecutionTradeInput {
    pub base_quantity: f64,
    pub executable_entry_price_quote: f64,
    pub forecast_exit_price_quote: f64,
    pub exit_capacity_base: f64,
    pub required_edge_bps: u32,
    pub risk_margin_bps: u32,
}

impl ExecutionEconomics {
    pub fn assess(
        model: &ExecutionCostModel,
        trade: &ExecutionTradeInput,
    ) -> Result<Self, ExecutionEconomicsError>;

    pub fn entry_price_is_acceptable(
        &self,
        current_executable_entry_price_quote: f64,
        current_exit_capacity_base: f64,
        intended_base_quantity: f64,
    ) -> Result<bool, ExecutionEconomicsError>;
}
```

- [ ] **Step 1: Test exact round-trip algebra**

Use `Q=100`, `P_entry=0.01`, `P_exit=0.012`, entry fee/impact/slippage/latency `100/50/25/25 bps`, exit `100/40/20/40 bps`, entry fixed `0.0015` quote and exit fixed `0.001` quote. Assert `entry_total_quote`, `forecast_exit_net_quote`, `forecast_net_pnl_quote`, and break-even price against independently calculated formulas.

- [ ] **Step 2: Test fixed costs penalize small notional more heavily**

Assess two trades with identical rates/prices but different base quantity. Assert the smaller trade has a larger break-even move in bps.

- [ ] **Step 3: Test maximum acceptable entry price**

For a fixed forecast exit, assert increasing `required_edge_bps` or `risk_margin_bps` strictly lowers the maximum acceptable entry price.

- [ ] **Step 4: Test reprice/abort boundary**

Assert exactly-at-ceiling entry is accepted, a price above the ceiling is rejected, and reduced exit capacity below intended quantity is rejected.

- [ ] **Step 5: Test fail-closed validation**

Reject zero/negative/non-finite prices or quantities, negative/non-finite fixed costs, cost components above `10_000` bps, exit total variable cost `>= 10_000` bps, model version `0`, insufficient exit capacity, and forecast inputs that produce no positive maximum entry price.

- [ ] **Step 6: Commit RED only**

Commit message:

```text
test: define FL3 execution economics contract
```

- [ ] **Step 7: Run PR CI and require Rust RED**

Expected failure: unresolved imports/types from `shreks_core`. Repository safety/Python/ARM64 may also stop because Rust compilation is incomplete; the authoritative RED is the missing FL3 public contract.

---

### Task 2: GREEN — Implement deterministic round-trip economics

**Files:**
- Create: `crates/shreks-core/src/fast_lane/economics.rs`
- Modify: `crates/shreks-core/src/fast_lane/mod.rs`
- Modify: `crates/shreks-core/src/lib.rs`

**Produces:** `ExecutionLegCostInput`, `ExecutionCostModel`, `ExecutionTradeInput`, `ExecutionEconomics`, `ExecutionEconomicsError`, `EXECUTION_ECONOMICS_VERSION`.

- [ ] **Step 1: Implement checked cost helpers**

Use `bps / 10_000.0` only after validating each component `<= 10_000`. Fixed quote costs must be finite and non-negative. Sum fee + impact + slippage + latency with checked integer addition before conversion.

- [ ] **Step 2: Implement entry and exit algebra**

```text
entry_variable_rate = sum(entry bps) / 10_000
exit_variable_rate  = sum(exit bps) / 10_000
entry_fixed = network + priority + expected_failure
exit_fixed  = network + priority + expected_failure
entry_total = Q * P_entry * (1 + entry_variable_rate) + entry_fixed
exit_net    = Q * P_exit * (1 - exit_variable_rate) - exit_fixed
```

Reject any non-finite result and require exit variable rate `< 1.0`.

- [ ] **Step 3: Implement break-even**

```text
P_break_even = (entry_total + exit_fixed) / (Q * (1 - exit_variable_rate))
break_even_move_bps = (P_break_even / P_entry - 1) * 10_000
```

- [ ] **Step 4: Implement maximum acceptable entry price**

```text
required_return_rate = (required_edge_bps + risk_margin_bps) / 10_000
forecast_exit_net = Q * P_forecast_exit * (1 - exit_rate) - exit_fixed
max_entry_total = forecast_exit_net / (1 + required_return_rate)
max_entry_price = (max_entry_total - entry_fixed) / (Q * (1 + entry_rate))
```

Require a finite, strictly positive result.

- [ ] **Step 5: Implement capacity and reprice invariant**

`assess` requires `exit_capacity_base >= base_quantity`. `entry_price_is_acceptable` validates current values and returns true only when capacity remains sufficient and current entry price is `<= maximum_acceptable_entry_price_quote`.

- [ ] **Step 6: Run focused tests**

```bash
cargo test -p shreks-core --test fast_lane_execution_economics
```

Expected: PASS.

- [ ] **Step 7: Require exact-head four-gate GREEN and commit**

Commit message:

```text
feat: add FL3 execution economics core
```

---

### Task 3: Preserve authoritative Pump/PumpSwap fee evidence

**Files:**
- Modify: `crates/shreks-providers/src/pump_trade.rs`
- Modify: `crates/shreks-providers/src/pump_swap_trade.rs`
- Modify focused provider integration tests.
- Modify source persistence/replay only if current raw storage drops fields required for deterministic replay.

**Consumes:** official current Pump/PumpSwap trade-event layouts and immutable raw event evidence.

**Produces:** source-level fee evidence that can validate/derive `effective_fee_bps` without hard-coded protocol guesses.

- [ ] **Step 1: RED Pump fee evidence test**

Build a current-format Pump event fixture with distinct protocol/creator/newer fee fields. Assert the decoded evidence preserves the authoritative basis points/raw amounts instead of discarding them.

- [ ] **Step 2: RED PumpSwap fee evidence test**

Build current Buy and Sell event fixtures with distinct LP/protocol/creator/cashback/buyback fields and a signed `virtual_quote_reserves`. Assert all fields are retained exactly.

- [ ] **Step 3: Represent historical missing append-only fields as unknown**

Use `Option` for fields that genuinely may be absent from older event layouts. Do not synthesize today’s fee schedule for old rows.

- [ ] **Step 4: GREEN parsers and source replay**

Extend parser evidence structures minimally. If immutable raw storage already contains the complete event bytes/log evidence, derive these fields from source on replay; otherwise persist only the missing immutable source evidence, not a derived economics assessment.

- [ ] **Step 5: Add effective-fee derivation only where semantics are unambiguous**

Do not naïvely sum creator/cashback/buyback fields. Prefer an exact user-vs-market quote delta or a versioned fee configuration whose semantics are proven by protocol evidence. Return unknown when the event/config cannot support a safe derivation.

- [ ] **Step 6: Exact-head four-gate GREEN**

No provider selection/fallback changes are allowed.

---

### Task 4: Venue-specific exit-capacity and PumpSwap effective reserves

**Files:**
- Modify: `crates/shreks-core/src/fast_lane/event.rs` if reserve context needs optional virtual quote reserve.
- Modify: `crates/shreks-core/src/fast_lane/economics.rs` or add focused `capacity.rs` if the module would otherwise become unwieldy.
- Modify provider/storage reserve-context reconstruction tests.
- Add capacity integration tests.

**Produces:** deterministic capacity under an explicit minimum executable-price/economic boundary.

- [ ] **Step 1: RED PumpSwap virtual-reserve test**

Require current PumpSwap source evidence to expose an optional signed virtual quote reserve and prove pricing uses physical quote reserve plus virtual quote reserve when known.

- [ ] **Step 2: RED Pump capacity tests**

For Pump bonding-curve sell/exit math, prove quote output cannot exceed real quote reserves and that increasing intended exit size worsens executable average price under constant-product reserves.

- [ ] **Step 3: RED PumpSwap capacity tests**

Given physical base/quote reserves plus known virtual quote reserves, calculate maximum base exit quantity satisfying an explicit caller minimum executable average exit price. No arbitrary liquidity percentage is introduced.

- [ ] **Step 4: GREEN checked reserve math**

Use checked arithmetic/conversions and fail closed on missing required evidence, non-positive effective reserves, impossible minimum-price boundary, or physical reserve exhaustion.

- [ ] **Step 5: Prove deterministic replay**

The same immutable source evidence must reconstruct the same reserve/capacity result.

- [ ] **Step 6: Exact-head four-gate GREEN**

---

### Task 5: FL3 assessment/reprice integration contract and closure

**Files:**
- Add focused integration test(s) under `crates/shreks-core/tests/`.
- Update `docs/superpowers/plans/2026-09-02-fl3-execution-economics.md` with verification SHAs.

- [ ] **Step 1: End-to-end deterministic assessment test**

Construct a reserve-aware market, explicit cost model, intended size, forecast executable exit price, and required edge/risk margin. Calculate capacity, assess economics, and assert the final max-entry ceiling.

- [ ] **Step 2: Prove immediate reprice abort**

At the exact ceiling: accept. One representable price above: abort. If capacity falls below intended quantity: abort regardless of price.

- [ ] **Step 3: Scope audit**

Confirm the PR does not modify signer, transaction submission, `RuntimeMode::Live` authorization, PAPER ledger authority, provider fallback selection, or release topology.

- [ ] **Step 4: Exact-head four-gate GREEN**

- [ ] **Step 5: Guarded merge, fresh merged-main four-gate GREEN**

Merge only the exact reviewed head SHA.

- [ ] **Step 6: Mark FL3 exit criterion complete**

Record that FL3 can answer the specific price/size economic-worthwhile question with explicit cost/capacity assumptions. Do not proceed to FL4 labels until this is true.

**LIVE remains disabled.**