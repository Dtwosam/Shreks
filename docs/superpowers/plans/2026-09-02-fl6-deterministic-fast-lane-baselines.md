# FL6 Deterministic Fast Lane Baselines Implementation Plan

**Goal:** Build independently measurable deterministic Fast Lane baselines before ML, beginning with FL6.1 Impulse Scalp.

**Base proof:** `2b03514ad95b95a98baa2e4a1ff0f6c6e14aaf35` (FL5 merged-main four-gate GREEN)

**Spec:** `docs/superpowers/specs/2026-09-02-fl6-deterministic-fast-lane-baselines-design.md`

## Global constraints

- Rust may evaluate latency-sensitive approved Fast Lane strategy logic, but FL6 does not create capital authority.
- No `TradeIntent`, PAPER execution, signing/submission, LIVE enablement, provider topology, deployment, or secret changes.
- No future-path or counterfactual labels may enter point-in-time decisions.
- Execution uncertainty fails closed. Missing economics never becomes zero cost.
- Every strategy family is independently measurable and disableable.
- No production default strategy thresholds; policies are explicit hypotheses for replay.
- TDD: intentional RED before production behavior, then exact-head four-gate GREEN.

---

## Task 1 — FL6.1 Impulse Scalp contract and RED proof

**Create:** `crates/shreks-core/tests/fl6_impulse_scalp.rs`

- [ ] Add intentional RED tests for:
  - strong impulse + valid positive economics -> BUY,
  - weak participation/imbalance/velocity/acceleration/path -> SKIP,
  - signal-vs-context velocity expansion requirement,
  - missing execution economics -> SKIP with unknown economic fields,
  - insufficient exit capacity -> SKIP,
  - non-positive post-cost forecast economics -> SKIP,
  - executable entry above maximum acceptable price -> SKIP,
  - market/timestamp mismatch -> error,
  - invalid policy -> error,
  - deterministic repeated output/reason ordering.
- [ ] Run exact-head CI and prove Rust RED while repository safety/Python/ARM64 remain green.

## Task 2 — Implement the pure FL6.1 evaluator

**Create:** `crates/shreks-core/src/fast_lane/baseline.rs`

**Modify:**
- `crates/shreks-core/src/fast_lane/mod.rs`
- `crates/shreks-core/src/lib.rs`

- [ ] Add stable Fast Lane action vocabulary (`BUY/SKIP/HOLD/REDUCE/SELL`).
- [ ] Add explicit versioned `ImpulseScalpPolicy` with validation and no default instance.
- [ ] Add optional explicit execution input wrapping current market/time + existing `ExecutionCostModel`/`ExecutionTradeInput`.
- [ ] Add deterministic `ImpulseScalpReason` values and canonical reason order.
- [ ] Add `ImpulseScalpAssessment` retaining point-in-time identity and available execution economics/price boundary.
- [ ] Implement pure `assess_impulse_scalp(...)`.
- [ ] Treat missing execution evidence and insufficient capacity as SKIP; malformed/contradictory evidence is an error.
- [ ] Run focused Rust test plus full four-gate CI GREEN.

## Task 3 — FL6.1 scope/proof closure

- [ ] Audit branch diff: docs + `shreks-core` Fast Lane baseline/tests only.
- [ ] Confirm no PAPER/risk/signer/submission/provider/deployment/LIVE authority changes.
- [ ] Confirm evaluator has no wall-clock, provider, DB, future-label, counterfactual-label, randomness, or mutable-global dependencies.
- [ ] Require exact-head Repository safety/Rust/Python/native ARM64 GREEN.
- [ ] Guarded merge the exact verified head.
- [ ] Require fresh merged-main four-gate GREEN.
- [ ] Record RED head/run, exact GREEN head/run, merge SHA/run, and LIVE-disabled statement.

## Later FL6 units

After FL6.1 is sealed, continue one independently testable baseline at a time:

1. FL6.2 Micro Pullback/Reclaim,
2. FL6.3 Pre-Graduation Acceleration,
3. FL6.4 Graduation/Migration Flow,
4. FL6.5 Wallet/Cohort Ride/Fade,
5. FL6.6 Longer Runner.

Do not bundle those policies into the FL6.1 PR.