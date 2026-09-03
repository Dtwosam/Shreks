# FL6.6 Longer-Runner Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure deterministic Rust open-position baseline that compares exit-now value with cost/risk-adjusted expected continuation, while ensuring protective exits remain unconditional backstops.

**Architecture:** Add one focused `shreks-core::fast_lane::longer_runner` module. It consumes a current `FastMarketSnapshot`, exact-clock protective state, optional versioned continuation evidence, and an explicit policy. It computes exit-leg economics directly from existing `ExecutionLegCostInput` fields without recharging sunk entry costs.

**Tech Stack:** Rust 2024 workspace, `shreks-core`, existing `FastMarketKey`, `FastMarketSnapshot`, `FastLaneAction`, and `ExecutionLegCostInput`; GitHub Actions four-gate CI.

**Spec:** `docs/superpowers/specs/2026-09-03-fl6-6-longer-runner-design.md`

## Global constraints

- Base exactly sealed FL6.5 merge `b3e7bc2b99e99c324e86125ef592e16d637f67bd`.
- FL6.6 emits only `HOLD`, `REDUCE`, `SELL`; never `BUY`/`SKIP`.
- Entry cost is sunk and must not be charged in continuation economics.
- Missing continuation evidence => REDUCE unless a protective backstop requires SELL.
- Protective exit flags override favorable economics.
- Current/future full-position capacity shortfall => SELL.
- No production default forecast or policy thresholds.
- No provider/storage/observer/runtime/PAPER/risk-authority/signer/submission/deployment/secret/LIVE changes.
- Intentional RED before production implementation; exact-head and merged-main four-gate GREEN required.

---

### Task 1: Define FL6.6 at intentional RED

**Files:**
- Create: `crates/shreks-core/tests/fl6_longer_runner.rs`

**Public API required by the RED test:**

```rust
pub const LONGER_RUNNER_EVIDENCE_VERSION: u16 = 1;
pub const LONGER_RUNNER_BASELINE_VERSION: u16 = 1;

pub struct LongerRunnerProtectiveState { /* spec fields */ }
pub struct LongerRunnerContinuationEvidence { /* spec fields */ }
pub struct LongerRunnerPolicy { /* spec fields */ }
pub enum LongerRunnerReason { /* canonical reasons */ }
pub struct LongerRunnerAssessment { /* audit fields */ }
pub enum LongerRunnerError { /* fail-closed structural errors */ }

pub fn assess_longer_runner(
    snapshot: &FastMarketSnapshot,
    protective: &LongerRunnerProtectiveState,
    continuation: Option<&LongerRunnerContinuationEvidence>,
    policy: &LongerRunnerPolicy,
) -> Result<LongerRunnerAssessment, LongerRunnerError>;
```

- [ ] Write failing tests for favorable HOLD, marginal REDUCE, unfavorable SELL, all three protective overrides, missing evidence REDUCE, protective+missing SELL, current/future capacity SELL, cost/holding-cost reversal, downside-risk reversal, identity/time errors, NaN/cost errors, no BUY/SKIP, determinism.
- [ ] Commit only the RED test as `test: define FL6.6 longer runner contract`.
- [ ] Run canonical CI. Require safety/Python/ARM64 GREEN and Rust RED exactly on absent FL6.6 symbols.

---

### Task 2: Implement pure continuation economics

**Files:**
- Create: `crates/shreks-core/src/fast_lane/longer_runner.rs`
- Test: `crates/shreks-core/tests/fl6_longer_runner.rs`

- [ ] Implement versioned structs/enums exactly as the design spec.
- [ ] Validate policy, snapshot, protective exact market/time identity, continuation version/source/market/time, positive prices/quantity/horizon/capacity, finite nonnegative holding cost.
- [ ] Validate each exit-cost leg:

```text
component bps <= 10_000
combined variable bps < 10_000
fixed quote costs finite and >= 0
```

- [ ] Implement exit net projection:

```text
net = base * price * (1 - variable_bps/10_000) - fixed_quote
```

- [ ] Implement derived economics from the spec:

```text
gross expected continuation = future net - current net - holding cost
downside loss = max(current net - downside future net, 0)
risk penalty = downside loss * downside risk weight
risk-adjusted continuation = gross continuation - risk penalty
risk-adjusted continuation bps = risk-adjusted continuation / current gross exit * 10_000
```

All arithmetic must remain finite.

- [ ] Implement exact action precedence:

```text
protective flag -> SELL
else missing continuation -> REDUCE
else capacity shortfall -> SELL
else continuation_bps <= sell threshold -> SELL
else continuation_bps >= hold threshold -> HOLD
else -> REDUCE
```

- [ ] Emit canonical ordered reasons and audit fields. Protective-only/missing-evidence paths leave unavailable economics as None.
- [ ] Run focused Rust test to GREEN.
- [ ] Commit implementation.

---

### Task 3: Export without widening authority

**Files:**
- Modify: `crates/shreks-core/src/fast_lane/mod.rs`
- Modify: `crates/shreks-core/src/lib.rs`

- [ ] Add `mod longer_runner;` and focused public re-exports.
- [ ] Extend only the existing root Fast Lane export block.
- [ ] Audit `lib.rs` PR patch before trusting CI; unrelated changes are a blocker.
- [ ] Commit exports.

---

### Task 4: Prove, clean, merge, and seal

- [ ] Require candidate four-gate GREEN.
- [ ] Scope audit exactly six files:

```text
crates/shreks-core/src/fast_lane/longer_runner.rs
crates/shreks-core/src/fast_lane/mod.rs
crates/shreks-core/src/lib.rs
crates/shreks-core/tests/fl6_longer_runner.rs
docs/superpowers/plans/2026-09-03-fl6-6-longer-runner.md
docs/superpowers/specs/2026-09-03-fl6-6-longer-runner-design.md
```

- [ ] Preserve design -> plan -> RED and collapse post-RED authoring commits into one clean implementation commit if useful.
- [ ] Require fresh four-gate GREEN on the exact cleaned SHA.
- [ ] Guarded-merge with `expected_head_sha=<proven SHA>`.
- [ ] Require fresh merged-main four-gate GREEN.
- [ ] Update PR body to SEALED with RED/exact-head/merge/merged-main/scope proof.
- [ ] Record FL6 exit criterion as satisfied at the deterministic evaluator-contract layer; do not claim profitability.

LIVE remains disabled.
