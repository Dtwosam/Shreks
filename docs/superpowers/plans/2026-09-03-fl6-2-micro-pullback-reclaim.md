# FL6.2 Micro Pullback / Reclaim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic ordered-path evidence and a cost-aware FL6.2 Micro Pullback / Reclaim BUY/SKIP baseline without granting capital authority.

**Architecture:** First extend canonical `FastWindowSummary` with point-in-time peak/trough ordering so the strategy can prove `impulse -> pullback -> reclaim` instead of inferring order from extrema values. Then add a focused `micro_pullback.rs` pure evaluator that consumes those summaries plus explicit existing execution economics and reuses `FastLaneAction`.

**Tech Stack:** Rust workspace (`shreks-core`), existing Fast Lane state/economics contracts, GitHub Actions four-gate CI.

**Spec:** `docs/superpowers/specs/2026-09-03-fl6-2-micro-pullback-reclaim-design.md`

## Global Constraints

- Base from merged-main proof `b13a6898e6c1382f6900cfdb8a8eb068694fdc7c`, CI run `33690287679` four-gate GREEN.
- No `TradeIntent`, PAPER execution, signing/submission, LIVE enablement, provider topology, deployment, or secret changes.
- No future-path or counterfactual labels may enter point-in-time decisions.
- Execution uncertainty fails closed. Missing economics never becomes zero cost.
- No production default strategy thresholds.
- FL6.1 behavior must remain unchanged and green.
- TDD: intentional RED before each production behavior, then exact-head four-gate GREEN.

---

### Task 1: Ordered peak/trough path evidence — RED contract

**Files:**
- Modify: `crates/shreks-core/tests/fast_lane_state.rs`

**Interfaces:**
- Consumes: existing `FastMarketState::snapshot(...) -> FastMarketSnapshot`.
- Produces test contract for new `FastWindowSummary` fields:
  - `local_high_sequence: Option<u64>`
  - `local_high_observed_at_unix_ms: Option<i64>`
  - `local_low_sequence: Option<u64>`
  - `local_low_observed_at_unix_ms: Option<i64>`
  - `post_high_low_price_quote: Option<f64>`
  - `post_high_low_sequence: Option<u64>`
  - `post_high_low_observed_at_unix_ms: Option<i64>`

- [ ] **Step 1: Add failing ordered-path tests**

Add tests that build real `FastEvent`s through `FastMarketState` and assert:

```rust
assert_eq!(window.local_low_sequence, Some(1));
assert_eq!(window.local_high_sequence, Some(2));
assert_eq!(window.post_high_low_sequence, Some(3));
assert_eq!(window.post_high_low_price_quote, Some(0.011));
assert_eq!(window.post_high_low_observed_at_unix_ms, Some(1_200));
```

Cover these event sequences:

1. low -> higher impulse peak -> lower post-peak trough -> reclaim,
2. high -> trough -> strictly higher new high resets post-high trough to `None`,
3. equal-price high retest does not rewrite the first maximum identity,
4. replaying identical events returns identical ordered-path summary fields.

- [ ] **Step 2: Run focused RED**

Run:

```bash
cargo test -p shreks-core --test fast_lane_state
```

Expected: compile failure because the new `FastWindowSummary` fields do not exist yet.

- [ ] **Step 3: Commit RED contract**

Commit only the test change with message:

```text
test: define ordered Fast Lane path evidence
```

- [ ] **Step 4: Open/update draft PR and capture RED CI**

Require Repository safety, Python and ARM64 to remain green while Rust fails on the intentionally missing ordered-path fields.

---

### Task 2: Ordered peak/trough path evidence — GREEN implementation

**Files:**
- Modify: `crates/shreks-core/src/fast_lane/state.rs`
- Modify: `crates/shreks-core/tests/fl6_impulse_scalp.rs`
- Test: `crates/shreks-core/tests/fast_lane_state.rs`

**Interfaces:**
- Consumes: `FastEvent.sequence`, `FastEvent.observed_at_unix_ms`, `FastEvent.price_quote`.
- Produces: the seven ordered-path fields defined in Task 1 on every `FastWindowSummary`.

- [ ] **Step 1: Add fields and zero/empty initialization**

Add the seven fields to `FastWindowSummary` and initialize all as `None` in `FastWindowSummary::empty`.

- [ ] **Step 2: Track extrema identity in `apply`**

Use strict comparisons so equal-price retests do not rewrite identity.

Pseudo-code contract:

```rust
if event.price_quote > current_high {
    local_high = event.price_quote;
    local_high_sequence = Some(event.sequence);
    local_high_observed_at = Some(event.observed_at_unix_ms);
    post_high_low = None;
} else if local_high_sequence.is_some_and(|high_seq| event.sequence > high_seq) {
    if post_high_low.is_none_or(|low| event.price_quote < low) {
        post_high_low = Some(event.price_quote);
        post_high_low_sequence = Some(event.sequence);
        post_high_low_observed_at = Some(event.observed_at_unix_ms);
    }
}

if event.price_quote < current_low {
    local_low = event.price_quote;
    local_low_sequence = Some(event.sequence);
    local_low_observed_at = Some(event.observed_at_unix_ms);
}
```

For the first event, initialize both local high and local low identity to that event. Do not treat the high event itself as a post-high trough.

- [ ] **Step 3: Preserve FL6.1 test fixtures**

Update the manual `FastWindowSummary` constructor in `fl6_impulse_scalp.rs` with deterministic ordered-path fixture values. Do not change FL6.1 policy or expected behavior.

- [ ] **Step 4: Run focused GREEN**

Run:

```bash
cargo test -p shreks-core --test fast_lane_state
cargo test -p shreks-core --test fl6_impulse_scalp
```

Expected: both PASS.

- [ ] **Step 5: Run Rust workspace**

Run:

```bash
cargo test --workspace
```

Expected: PASS.

- [ ] **Step 6: Commit ordered-path implementation**

Commit message:

```text
feat: add ordered Fast Lane peak trough evidence
```

---

### Task 3: FL6.2 evaluator — RED contract

**Files:**
- Create: `crates/shreks-core/tests/fl6_micro_pullback.rs`

**Interfaces:**
- Consumes:
  - `FastMarketSnapshot`
  - ordered path fields from Tasks 1-2
  - `ExecutionCostModel`
  - `ExecutionTradeInput`
  - existing `FastLaneAction`
- Defines expected public API:

```rust
pub const MICRO_PULLBACK_BASELINE_VERSION: u16 = 1;

pub struct MicroPullbackPolicy { ... }
pub struct MicroPullbackExecutionInput { ... }
pub enum MicroPullbackReason { ... }
pub struct MicroPullbackAssessment { ... }
pub enum MicroPullbackError { ... }

pub fn assess_micro_pullback(
    snapshot: &FastMarketSnapshot,
    execution: Option<&MicroPullbackExecutionInput>,
    policy: &MicroPullbackPolicy,
) -> Result<MicroPullbackAssessment, MicroPullbackError>;
```

- [ ] **Step 1: Build strong ordered fixture**

Create a structure window with:

```text
pre-low sequence 10 at price 0.0100
high sequence 20 at price 0.0120
post-high trough sequence 30 at price 0.0110
latest sequence 40 at price 0.0117
```

Derived expectations:

```text
impulse move = 20%
pullback depth = 8.333...%
reclaim fraction = 70%
```

Create a shorter reclaim window with strong recent buys, low seller arrival, positive count/quote imbalance, positive velocity, and positive acceleration.

- [ ] **Step 2: Add failing behavior tests**

Cover:

1. strong ordered structure + strong reclaim + positive economics -> `BUY`,
2. local low not before high -> `SKIP`,
3. trough at latest sequence -> `SKIP`,
4. impulse below minimum -> `SKIP`,
5. pullback too shallow -> `SKIP`,
6. pullback too deep -> `SKIP`,
7. reclaim fraction below minimum -> `SKIP`,
8. reclaim buy participation below threshold -> `SKIP`,
9. recent seller arrival above ceiling -> `SKIP`,
10. weak/negative reclaim imbalance/velocity/acceleration -> `SKIP`,
11. missing execution input -> `SKIP` with economic fields `None`,
12. insufficient exit capacity -> `SKIP`,
13. non-positive post-cost forecast -> `SKIP`,
14. executable entry above maximum acceptable entry price -> `SKIP`,
15. market/timestamp mismatch -> error,
16. invalid policy -> error,
17. repeated identical inputs -> identical assessment and canonical reasons.

- [ ] **Step 3: Run focused RED**

Run:

```bash
cargo test -p shreks-core --test fl6_micro_pullback
```

Expected: compile failure on missing FL6.2 public API.

- [ ] **Step 4: Commit RED contract**

Commit message:

```text
test: define FL6.2 micro pullback contract
```

- [ ] **Step 5: Capture exact RED CI**

Expected Rust RED only; repository safety, Python, and ARM64 remain green.

---

### Task 4: FL6.2 evaluator — GREEN implementation

**Files:**
- Create: `crates/shreks-core/src/fast_lane/micro_pullback.rs`
- Modify: `crates/shreks-core/src/fast_lane/mod.rs`
- Modify: `crates/shreks-core/src/lib.rs`
- Test: `crates/shreks-core/tests/fl6_micro_pullback.rs`

**Interfaces:**
- Produces the public API defined in Task 3.
- Reuses `FastLaneAction::{Buy, Skip}` and `ExecutionEconomics::assess`.

- [ ] **Step 1: Implement policy and validation**

`MicroPullbackPolicy` fields:

```rust
pub version: u16,
pub reclaim_window_ms: u64,
pub structure_window_ms: u64,
pub min_impulse_move_fraction: f64,
pub min_pullback_depth_fraction: f64,
pub max_pullback_depth_fraction: f64,
pub min_reclaim_fraction: f64,
pub min_reclaim_buy_count: u64,
pub min_reclaim_unique_buy_actors: u64,
pub min_reclaim_buy_arrival_rate_per_second: f64,
pub max_reclaim_sell_arrival_rate_per_second: f64,
pub min_reclaim_count_imbalance: f64,
pub min_reclaim_quote_flow_imbalance: f64,
pub min_reclaim_quote_flow_velocity_per_second: f64,
pub min_reclaim_quote_flow_acceleration_per_second2: f64,
```

Reject unsupported version, invalid window ordering, zero counts, non-finite values, invalid fractions, non-positive required impulse/buy-arrival/velocity/acceleration, negative seller ceiling, and min pullback > max pullback.

- [ ] **Step 2: Implement ordered structure derivation**

Require:

```rust
local_low_sequence < local_high_sequence
local_high_sequence < post_high_low_sequence
post_high_low_sequence < snapshot.last_sequence
```

Then compute and retain:

```rust
impulse_move_fraction
pullback_depth_fraction
reclaim_fraction
```

Missing or contradictory path evidence becomes stable `SKIP` reasons rather than fabricated structure.

- [ ] **Step 3: Implement reclaim flow checks**

Evaluate recent participation, buyer arrival, seller-arrival ceiling, count imbalance, quote-flow imbalance, velocity, and acceleration independently. Append reasons in one canonical semantic order.

- [ ] **Step 4: Implement execution checks**

If execution input is `None`, append `ExecutionEconomicsUnavailable` and leave economic output fields `None`.

For valid input:

```rust
match ExecutionEconomics::assess(&execution.cost_model, &execution.trade) {
    Ok(economics) => { ... }
    Err(ExecutionEconomicsError::InsufficientExitCapacity) => SKIP reason,
    Err(error) => return Err(MicroPullbackError::ExecutionEconomics(error)),
}
```

Append `ForecastNetPnlNotPositive` when `forecast_net_pnl_quote <= 0.0` and `EntryPriceAboveMaximum` when the executable entry exceeds the computed boundary.

- [ ] **Step 5: Export API**

Add `mod micro_pullback;` and re-exports in `fast_lane/mod.rs`, then root re-exports in `lib.rs`. Do not change unrelated public types.

- [ ] **Step 6: Run focused GREEN**

Run:

```bash
cargo test -p shreks-core --test fl6_micro_pullback
cargo test -p shreks-core --test fl6_impulse_scalp
cargo test -p shreks-core --test fast_lane_state
```

Expected: PASS.

- [ ] **Step 7: Run full four-gate verification**

Require:

```text
Repository safety: PASS
Rust workspace: PASS
Python suite: PASS
Native ARM64 release build + bundle verification: PASS
```

- [ ] **Step 8: Commit clean implementation**

Commit message:

```text
feat: add FL6.2 micro pullback reclaim baseline
```

---

### Task 5: Scope audit, guarded merge, merged-main proof

**Files:**
- No production behavior beyond Tasks 1-4.
- Update PR description with proof hashes/runs.

**Interfaces:**
- Consumes exact verified FL6.2 head.
- Produces a merged-main proof record and the base SHA for FL6.3.

- [ ] **Step 1: Audit final diff**

Expected scope only:

```text
docs/superpowers/specs/2026-09-03-fl6-2-micro-pullback-reclaim-design.md
docs/superpowers/plans/2026-09-03-fl6-2-micro-pullback-reclaim.md
crates/shreks-core/src/fast_lane/state.rs
crates/shreks-core/src/fast_lane/micro_pullback.rs
crates/shreks-core/src/fast_lane/mod.rs
crates/shreks-core/src/lib.rs
crates/shreks-core/tests/fast_lane_state.rs
crates/shreks-core/tests/fl6_impulse_scalp.rs
crates/shreks-core/tests/fl6_micro_pullback.rs
```

No PAPER/risk/signer/submission/provider/deployment/LIVE authority files may change.

- [ ] **Step 2: Verify pure-evaluator boundary**

Confirm `micro_pullback.rs` has no wall clock, provider call, DB access, randomness, future-path labels, counterfactual labels, mutable global state, `TradeIntent`, signer, or submission dependency.

- [ ] **Step 3: Require exact-head four-gate GREEN**

Do not merge a different SHA from the one verified.

- [ ] **Step 4: Guarded merge exact head**

Merge with `expected_head_sha` equal to the verified FL6.2 head.

- [ ] **Step 5: Require fresh merged-main four-gate GREEN**

Record merge SHA and push-triggered main CI run.

- [ ] **Step 6: Seal FL6.2**

Update PR description with:

- ordered-path RED head/run,
- ordered-path GREEN head/run,
- evaluator RED head/run,
- exact final GREEN head/run,
- merge SHA,
- merged-main four-gate run,
- explicit LIVE-disabled statement.

FL6.3 may start only after this proof is green.