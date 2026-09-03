# FL6.5 Wallet/Cohort Ride/Fade Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure deterministic Rust baseline that converts point-in-time wallet/cohort support, exit, independence, and historical holding-horizon evidence into open-position `HOLD`, `REDUCE`, or `SELL` assessments without creating wallet-driven entry authority.

**Architecture:** Add one focused `shreks-core::fast_lane::wallet_cohort` module. The evaluator consumes a current `FastMarketSnapshot`, optional caller-supplied versioned `WalletCohortEvidence`, an exact-clock `WalletCohortPositionInput`, and an explicit `WalletCohortPolicy`. It never calls Python, providers, storage, future labels, or execution authority.

**Tech Stack:** Rust 2024 workspace, `shreks-core`, existing `FastMarketKey`, `FastMarketSnapshot`, and `FastLaneAction` contracts; GitHub Actions four-gate CI.

**Spec:** `docs/superpowers/specs/2026-09-03-fl6-5-wallet-cohort-ride-fade-design.md`

## Global Constraints

- Base exactly sealed FL6.4 merged-main commit `9bd1f04d2493d252d151a984e184b67d9c598d4a`.
- FL6.5 is open-position-only and emits only `HOLD`, `REDUCE`, or `SELL`; never `BUY` or `SKIP`.
- Missing wallet evidence is neutral `HOLD`, not a fabricated bullish/bearish signal.
- Unknown/linked/conflicting wallet relationships are never rewritten into proven independence.
- Historical hold-horizon evidence alone may cause `REDUCE`; it may never cause `SELL` by itself.
- `SELL` requires strong exit pressure plus exact proven independent exit support.
- No production default policy thresholds.
- No provider/storage/observer/runtime/PAPER/risk/signer/submission/deployment/secret/LIVE-authority changes.
- TDD requires intentional RED before production implementation, then fresh exact-head four-gate GREEN.
- LIVE remains disabled.

---

### Task 1: Freeze the FL6.5 public behavior at RED

**Files:**
- Create: `crates/shreks-core/tests/fl6_wallet_cohort.rs`

**Interfaces:**
- Consumes: existing `FastLaneAction`, `FastMarketKey`, `FastMarketSnapshot`, `VenueId`.
- Produces requirement for:

```rust
pub const WALLET_COHORT_EVIDENCE_VERSION: u16 = 1;
pub const WALLET_COHORT_BASELINE_VERSION: u16 = 1;

pub struct WalletCohortSideSummary { /* spec fields */ }
pub struct WalletCohortEvidence { /* spec fields */ }
pub struct WalletCohortPositionInput { /* spec fields */ }
pub struct WalletCohortPolicy { /* spec fields */ }
pub enum WalletCohortPosture { Ride, Neutral, Fade }
pub enum WalletCohortReason { /* stable spec reasons */ }
pub struct WalletCohortAssessment { /* audit fields */ }
pub enum WalletCohortError { /* fail-closed structural errors */ }

pub fn assess_wallet_cohort_ride_fade(
    snapshot: &FastMarketSnapshot,
    evidence: Option<&WalletCohortEvidence>,
    position: &WalletCohortPositionInput,
    policy: &WalletCohortPolicy,
) -> Result<WalletCohortAssessment, WalletCohortError>;
```

- [ ] **Step 1: Write the failing contract tests**

Create tests with explicit fixtures and these exact behavioral assertions:

```rust
#[test]
fn strong_independent_support_with_remaining_horizon_rides() {
    let result = assess_wallet_cohort_ride_fade(...).unwrap();
    assert_eq!(result.action, FastLaneAction::Hold);
    assert_eq!(result.posture, WalletCohortPosture::Ride);
    assert!(result.reasons.contains(&WalletCohortReason::RideConditionsMet));
}

#[test]
fn moderate_exit_pressure_reduces() {
    let result = assess_wallet_cohort_ride_fade(...).unwrap();
    assert_eq!(result.action, FastLaneAction::Reduce);
    assert_eq!(result.posture, WalletCohortPosture::Fade);
}

#[test]
fn strong_independent_exit_pressure_sells() {
    let result = assess_wallet_cohort_ride_fade(...).unwrap();
    assert_eq!(result.action, FastLaneAction::Sell);
    assert_eq!(result.posture, WalletCohortPosture::Fade);
}

#[test]
fn unknown_exit_independence_caps_at_reduce() {
    let result = assess_wallet_cohort_ride_fade(...).unwrap();
    assert_eq!(result.action, FastLaneAction::Reduce);
    assert_ne!(result.action, FastLaneAction::Sell);
}

#[test]
fn exhausted_reliable_hold_horizon_reduces_but_never_sells_by_itself() { /* REDUCE */ }
#[test]
fn missing_hold_horizon_does_not_fabricate_expiry() { /* HOLD */ }
#[test]
fn missing_wallet_evidence_is_neutral_hold() { /* HOLD / Neutral */ }
#[test]
fn unknown_support_independence_prevents_ride_without_forcing_exit() { /* HOLD / Neutral */ }
#[test]
fn overlapping_support_and_exit_churn_is_valid() { /* deterministic action */ }
#[test]
fn candidate_mint_mismatch_fails_closed() { /* WalletCohortError::EvidenceMintMismatch */ }
#[test]
fn position_market_or_timestamp_mismatch_fails_closed() { /* exact errors */ }
#[test]
fn future_position_open_time_fails_closed() { /* PositionOpenedAfterDecision */ }
#[test]
fn invalid_nan_policy_or_evidence_fails_closed() { /* InvalidPolicy / InvalidEvidence */ }
#[test]
fn identical_inputs_are_identical_and_reason_order_is_stable() { /* full equality */ }
#[test]
fn wallet_baseline_never_emits_buy_or_skip() { /* enumerate representative HOLD/REDUCE/SELL cases */ }
```

Use a valid default test policy only inside tests; production must not expose a default.

- [ ] **Step 2: Commit intentional RED**

Commit only the test:

```text
test: define FL6.5 wallet cohort baseline contract
```

- [ ] **Step 3: Run full canonical CI and verify the RED reason**

Expected Rust failure is unresolved FL6.5 public imports only. Repository safety, Python, and native ARM64 must stay green.

Do not implement production code until this exact failure is observed.

---

### Task 2: Implement the pure wallet/cohort evaluator

**Files:**
- Create: `crates/shreks-core/src/fast_lane/wallet_cohort.rs`
- Test: `crates/shreks-core/tests/fl6_wallet_cohort.rs`

**Interfaces:**
- Consumes: `FastLaneAction`, `FastMarketKey`, `FastMarketSnapshot`.
- Produces: all FL6.5 types and `assess_wallet_cohort_ride_fade` from Task 1.

- [ ] **Step 1: Implement the versioned evidence and policy types**

Use exactly:

```rust
pub const WALLET_COHORT_EVIDENCE_VERSION: u16 = 1;
pub const WALLET_COHORT_BASELINE_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortSideSummary {
    pub strong_wallet_count: u64,
    pub confidence_weighted_strong_count: f64,
    pub independently_strong_wallet_count: Option<u64>,
    pub all_pairs_independent_under_evidence: Option<bool>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortEvidence {
    pub version: u16,
    pub as_of_unix_ms: i64,
    pub candidate_mint: String,
    pub wallet_feature_policy_version: String,
    pub profile_policy_version: Option<String>,
    pub relationship_policy_version: String,
    pub support: WalletCohortSideSummary,
    pub exits: WalletCohortSideSummary,
    pub support_hold_horizon_wallet_weight: f64,
    pub confidence_weighted_support_median_hold_ms: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WalletCohortPositionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub opened_at_unix_ms: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortPolicy {
    pub version: u16,
    pub min_support_wallet_count_for_ride: u64,
    pub min_confidence_weighted_support_for_ride: f64,
    pub min_independent_support_wallet_count_for_ride: u64,
    pub min_hold_horizon_wallet_weight_for_ride: f64,
    pub reduce_after_median_hold_ratio: f64,
    pub min_confidence_weighted_exit_for_reduce: f64,
    pub min_exit_pressure_ratio_for_reduce: f64,
    pub min_confidence_weighted_exit_for_sell: f64,
    pub min_exit_pressure_ratio_for_sell: f64,
    pub min_independent_exit_wallet_count_for_sell: u64,
}
```

- [ ] **Step 2: Implement fail-closed validation**

Validation must enforce:

```text
policy.version == 1
positive count/weight thresholds
finite ratios in [0,1]
sell thresholds >= reduce thresholds
finite positive reduce_after_median_hold_ratio
snapshot as_of >= 0
position exact market/time match and opened_at <= as_of
evidence version == 1
evidence exact mint/time match
non-empty provenance versions when required
finite weighted counts in [0, raw_count]
D4/D5 independence tri-state invariants
hold-horizon weight in [0, support raw count]
zero horizon weight <=> median hold is None
positive horizon weight => finite non-negative median hold
```

Return stable enum errors; do not panic or coerce malformed evidence.

- [ ] **Step 3: Implement derived values**

```rust
let position_age_ms = snapshot
    .as_of_unix_ms
    .checked_sub(position.opened_at_unix_ms)
    .and_then(|value| u64::try_from(value).ok())
    .ok_or(...)?;

let support_weight = evidence.support.confidence_weighted_strong_count;
let exit_weight = evidence.exits.confidence_weighted_strong_count;
let exit_pressure_ratio = if support_weight + exit_weight > 0.0 {
    exit_weight / (support_weight + exit_weight)
} else {
    0.0
};
```

When reliable horizon evidence exists:

```rust
ride_horizon_ms = median_hold_ms * policy.reduce_after_median_hold_ratio;
horizon_exhausted = position_age_ms as f64 > ride_horizon_ms;
remaining_horizon_ms = (ride_horizon_ms - position_age_ms as f64).max(0.0);
```

Keep derived numbers finite; invalid arithmetic fails closed.

- [ ] **Step 4: Implement action precedence**

Implement in this exact order:

```text
sell_proven =
    exit_weight >= sell_weight_threshold
    AND exit_pressure >= sell_pressure_threshold
    AND exits.all_pairs_independent_under_evidence == Some(true)
    AND exact independent exit count is known and >= sell independent minimum

if sell_proven:
    SELL / Fade
else if moderate_exit_pressure OR reliable_horizon_exhausted:
    REDUCE / Fade
else:
    HOLD
```

For `HOLD`, classify posture as `Ride` only when every positive ride condition is proven; otherwise posture is `Neutral`.

Missing evidence skips all sell/reduce evidence and yields `HOLD / Neutral` with `WalletEvidenceUnavailable`.

- [ ] **Step 5: Implement canonical reasons and audit assessment**

Reason order is fixed by a private canonical ranking function. Assessment echoes all raw/derived fields listed in the spec; no hidden score.

- [ ] **Step 6: Run the focused Rust test file**

Run conceptually equivalent to:

```text
cargo test -p shreks-core --test fl6_wallet_cohort
```

Expected: all FL6.5 tests pass.

- [ ] **Step 7: Commit evaluator implementation**

```text
feat: add FL6.5 wallet cohort evaluator
```

---

### Task 3: Export the FL6.5 public contract without widening authority

**Files:**
- Modify: `crates/shreks-core/src/fast_lane/mod.rs`
- Modify: `crates/shreks-core/src/lib.rs`

**Interfaces:**
- Consumes: Task 2 module.
- Produces: root-level public imports used by `fl6_wallet_cohort.rs`.

- [ ] **Step 1: Add the module and focused re-exports**

`fast_lane/mod.rs` adds:

```rust
mod wallet_cohort;

pub use wallet_cohort::{
    assess_wallet_cohort_ride_fade, WalletCohortAssessment, WalletCohortError,
    WalletCohortEvidence, WalletCohortPolicy, WalletCohortPositionInput,
    WalletCohortPosture, WalletCohortReason, WalletCohortSideSummary,
    WALLET_COHORT_BASELINE_VERSION, WALLET_COHORT_EVIDENCE_VERSION,
};
```

`lib.rs` adds those names only to the existing Fast Lane `pub use` block.

- [ ] **Step 2: Audit `lib.rs` patch before trusting CI**

The patch must contain only Fast Lane re-export changes. Any unrelated domain deletion or rewrite is a blocker and must be reverted before continuing.

- [ ] **Step 3: Commit export surface**

```text
feat: re-export FL6.5 wallet cohort contract
```

---

### Task 4: Prove, clean, guarded-merge, and seal FL6.5

**Files:**
- No new production files.
- Update PR metadata/body only after evidence exists.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: one sealed merged-main FL6.5 phase.

- [ ] **Step 1: Run fresh exact-head four-gate CI**

Require on the exact implementation head:

```text
Repository safety: GREEN
Rust workspace: GREEN
Python suite: GREEN
Native ARM64 release build + bundle verification: GREEN
```

- [ ] **Step 2: Audit scope**

Expected phase diff is exactly six files:

```text
crates/shreks-core/src/fast_lane/wallet_cohort.rs
crates/shreks-core/src/fast_lane/mod.rs
crates/shreks-core/src/lib.rs
crates/shreks-core/tests/fl6_wallet_cohort.rs
docs/superpowers/plans/2026-09-03-fl6-5-wallet-cohort-ride-fade.md
docs/superpowers/specs/2026-09-03-fl6-5-wallet-cohort-ride-fade-design.md
```

- [ ] **Step 3: Clean post-RED authoring history if needed**

Preserve design -> plan -> RED. Collapse implementation/export authoring commits into one clean implementation commit when that produces a clearer branch history. Force-move only the feature branch, never main.

- [ ] **Step 4: Re-run fresh exact-head four-gate CI after any history rewrite**

The exact SHA that will be merged must independently pass all four gates.

- [ ] **Step 5: Guarded-merge only the proven exact head**

Use GitHub merge with `expected_head_sha=<proven SHA>`.

- [ ] **Step 6: Require fresh merged-main four-gate CI**

Do not call FL6.5 sealed until the merge commit itself passes all four canonical gates.

- [ ] **Step 7: Update PR body to `SEALED` with RED, exact-head, merge, merged-main, behavior, and scope proof**

LIVE remains disabled.

## Plan self-review

- Spec coverage: every design requirement maps to Tasks 1-4.
- Placeholder scan: no TBD/TODO/implicit implementation steps remain.
- Type consistency: public names and fields match the design spec.
- Scope: one pure evaluator plus exports/tests/docs; no runtime or authority wiring.
