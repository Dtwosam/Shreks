# FL6.5 Wallet/Cohort Ride/Fade Baseline Design

**Date:** 2026-09-03

## Goal

Implement FL6.5 as an independently measurable deterministic Fast Lane baseline that uses known wallet/cohort behavior as **directional and holding-horizon evidence**, not as an automatic entry approval/rejection switch.

The build-order requirement is explicit: wallet/cohort behavior should inform whether an already-open position is worth riding, trimming, or fading. FL6.5 therefore evaluates **open positions only** and emits only:

- `HOLD`,
- `REDUCE`,
- `SELL`.

It deliberately never emits `BUY` or `SKIP`.

## Source-of-truth alignment

The sealed wallet research stack already established important semantics that FL6.5 must preserve:

- D1 records normalized wallet observations and distinguishes direct from inferred evidence.
- D2 reconstructs candidate-specific wallet trade chronology without turning unresolved state into fake closed trades.
- D3 computes evidence-weighted wallet history, including sample confidence and historical median holding time.
- D4 keeps wallet relationships tri-state/uncertain rather than inventing independence.
- D5 exposes strong-wallet entry/exit evidence, weighted support, and independence uncertainty without reducing it to `whale bought = bullish`.

Rust owns latency-sensitive Fast Lane evaluation, while Python remains the research/training/evaluation plane. FL6.5 therefore consumes a compact caller-supplied point-in-time wallet/cohort evidence contract. It performs no synchronous Python call and does not reimplement the D2-D5 research engines inside Rust.

A later runtime/hydration phase may cache or translate approved D5-derived evidence into this contract. That adapter is outside FL6.5.

## Base and scope

Base: sealed FL6.4 merged-main commit `9bd1f04d2493d252d151a984e184b67d9c598d4a`, proven by fresh merged-main CI run `33737558661`.

Production scope is intentionally narrow:

```text
crates/shreks-core/src/fast_lane/wallet_cohort.rs
crates/shreks-core/src/fast_lane/mod.rs
crates/shreks-core/src/lib.rs
```

Tests:

```text
crates/shreks-core/tests/fl6_wallet_cohort.rs
```

No provider, storage, observer/runtime, strategy wiring, PAPER execution, risk authority, signer, submission, deployment, secret, or LIVE-authority change belongs in this phase.

## Key design choice: open-position-only

Wallet history can be useful without becoming a universal entry gate.

FL6.5 intentionally does **not** answer “should Shreks buy this token?” Other independent FL6 entry baselines already produce auditable `BUY/SKIP` evidence from market state and execution economics.

FL6.5 instead answers:

> Given an existing position, does current historically credible wallet/cohort behavior support riding it, trimming exposure, or fading it?

This makes wallet evidence directional and horizon-aware while avoiding a monolithic smart-wallet approval switch.

## Public contract

### Version constants

```rust
pub const WALLET_COHORT_EVIDENCE_VERSION: u16 = 1;
pub const WALLET_COHORT_BASELINE_VERSION: u16 = 1;
```

### `WalletCohortSideSummary`

One directional cohort summary:

```rust
pub struct WalletCohortSideSummary {
    pub strong_wallet_count: u64,
    pub confidence_weighted_strong_count: f64,
    pub independently_strong_wallet_count: Option<u64>,
    pub all_pairs_independent_under_evidence: Option<bool>,
}
```

The two sides are:

- **support** — historically strong wallets currently supporting/accumulating the candidate under the upstream point-in-time wallet policy,
- **exit** — historically strong wallets currently exiting/fading the candidate under the upstream point-in-time wallet policy.

A wallet may legitimately contribute to both sides when the upstream chronology classifies churn inside both active windows. FL6.5 does not silently force overlapping chronology into one direction.

Validation mirrors D5/D4 uncertainty semantics:

- weighted count is finite, non-negative, and cannot exceed raw strong-wallet count;
- zero-wallet side => independently strong count is exactly `Some(0)` and all-pairs flag is `None`;
- one-wallet side => independently strong count is exactly `Some(1)` and all-pairs flag is `Some(true)`;
- two-or-more wallets:
  - all-pairs `Some(true)` requires exact independent count equal to raw strong-wallet count;
  - all-pairs `Some(false)` or `None` requires independent count `None`;
- unknown/linked/conflicting evidence is never rewritten into proven independence.

### `WalletCohortEvidence`

```rust
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
```

The provenance strings identify the upstream policy family that produced the evidence. FL6.5 does not interpret those version strings as quality scores.

Holding-horizon fields describe historically strong support wallets only:

- `support_hold_horizon_wallet_weight` is the sum of upstream evidence-confidence weights for support wallets contributing a known historical median holding time;
- it is finite, non-negative, and bounded by `support.strong_wallet_count`;
- positive weight requires a finite non-negative `confidence_weighted_support_median_hold_ms`;
- zero weight requires the median hold field to be `None`.

If either directional side contains historically strong wallets, `profile_policy_version` must be present. Empty wallet evidence may leave it absent.

### `WalletCohortPositionInput`

```rust
pub struct WalletCohortPositionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub opened_at_unix_ms: i64,
}
```

The position market and decision timestamp must exactly match the current `FastMarketSnapshot`. Opening time must be non-negative and not later than the decision clock.

### `WalletCohortPolicy`

```rust
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

No production default policy instance is introduced. Every threshold is an explicit replay/research hypothesis.

Validation:

- version must equal `WALLET_COHORT_BASELINE_VERSION`;
- support/independent minimum counts are positive;
- all weighted thresholds are finite and positive;
- exit pressure ratios are finite in `[0, 1]`;
- sell exit-weight threshold must be at least the reduce threshold;
- sell exit-pressure threshold must be at least the reduce threshold;
- `reduce_after_median_hold_ratio` must be finite and strictly positive.

## Derived evidence

### Position age

```text
position_age_ms = as_of_unix_ms - opened_at_unix_ms
```

### Exit pressure ratio

When support + exit confidence weight is positive:

```text
exit_pressure_ratio = exit_weight / (support_weight + exit_weight)
```

Otherwise the ratio is `0.0`.

This is a directional evidence ratio, not a probability that price will fall.

### Historical support horizon

The historical horizon is usable only when:

- `support_hold_horizon_wallet_weight >= min_hold_horizon_wallet_weight_for_ride`, and
- `confidence_weighted_support_median_hold_ms` is known.

The configured ride horizon is:

```text
ride_horizon_ms = confidence_weighted_support_median_hold_ms
                  * reduce_after_median_hold_ratio
```

The horizon is exhausted when `position_age_ms > ride_horizon_ms`.

Insufficient/missing hold-horizon evidence is **unknown**, not a zero-length holding period.

## Deterministic action precedence

### 1. Strong independent exit pressure => `SELL`

`SELL` requires all of:

- exit confidence weight >= sell threshold,
- exit pressure ratio >= sell threshold,
- exact independently strong exit count is known,
- exact independently strong exit count >= configured sell minimum,
- exit all-pairs independence is `Some(true)`.

Therefore a linked, conflicting, or unknown exit cohort cannot trigger `SELL` solely by being numerically large.

### 2. Moderate or unresolved exit pressure => `REDUCE`

`REDUCE` applies when `SELL` is not proven and either:

- exit confidence weight **and** exit pressure ratio meet the reduce thresholds, or
- reliable historical support-horizon evidence is exhausted.

This means high exit pressure with unresolved independence can trim exposure but cannot escalate to a full wallet-driven sell.

### 3. Otherwise => `HOLD`

`HOLD` is the neutral/default open-position action for this baseline.

Missing wallet evidence, unknown support independence, or missing historical hold horizon does not fabricate a sell and does not become a bullish approval signal.

## Ride posture

Add a separate audit posture:

```rust
pub enum WalletCohortPosture {
    Ride,
    Neutral,
    Fade,
}
```

- `Fade` accompanies `REDUCE` or `SELL`.
- `Ride` requires `HOLD` plus all positive support conditions:
  - support wallet count threshold,
  - weighted support threshold,
  - exact independently strong support threshold,
  - all-pairs support independence `Some(true)`,
  - reliable historical support-horizon evidence,
  - horizon not exhausted,
  - exit pressure below the reduce threshold.
- otherwise `HOLD` is `Neutral`.

The posture preserves wallet direction without turning it into entry authority.

## Stable reasons

`WalletCohortReason` will expose fixed audit reasons covering:

- evidence unavailable,
- support count/weight below ride minimum,
- support independence unknown/below minimum,
- hold-horizon evidence unavailable/below minimum,
- historical hold horizon exhausted,
- exit weight/pressure reaching reduce thresholds,
- exit weight/pressure reaching sell thresholds,
- exit independence unknown/below sell minimum,
- ride conditions met,
- neutral hold,
- reduce conditions met,
- sell conditions met.

Reasons are emitted in one canonical order so identical inputs produce byte-for-byte stable reason sequences.

## Assessment output

`WalletCohortAssessment` retains the evidence needed to audit the decision:

- baseline and policy versions,
- market and as-of time,
- `FastLaneAction`,
- `WalletCohortPosture`,
- ordered reasons,
- position age,
- support/exit raw and confidence-weighted counts,
- exact independence fields,
- exit pressure ratio,
- historical-horizon evidence weight,
- median support hold milliseconds,
- configured ride horizon milliseconds,
- remaining horizon milliseconds when known.

No hidden score is produced.

## Error handling

Contradictory structure fails closed with `WalletCohortError`:

- invalid policy,
- invalid snapshot timestamp,
- invalid evidence structure/numeric values,
- evidence mint mismatch,
- evidence timestamp mismatch,
- position market mismatch,
- position timestamp mismatch,
- position opened after decision time.

Genuinely missing wallet evidence is not contradictory; `None` evidence yields neutral `HOLD` with an explicit reason.

## Execution economics boundary

FL6.5 intentionally does **not** consume `ExecutionEconomics`.

This module provides wallet/cohort **continuation evidence**, not transaction authority. A wallet-driven `REDUCE` or `SELL` assessment is an advisory deterministic baseline output. Later decision/risk/execution layers still decide whether and how much to transact, and FL6.6 separately handles cost/risk-adjusted continuation.

This separation prevents wallet evidence from bypassing protective exits or execution economics.

## Determinism and leakage rules

The evaluator must not read:

- wall clock,
- providers,
- databases,
- Python process state,
- future-path labels,
- counterfactual labels,
- randomness,
- mutable global state.

All inputs are point-in-time caller-supplied values. Future-dated evidence and position state fail closed.

## TDD proof requirements

The intentional RED test must require the FL6.5 public API before implementation exists.

GREEN tests must prove at minimum:

1. strong independent support + reliable remaining historical horizon => `HOLD / Ride`;
2. moderate exit pressure => `REDUCE / Fade`;
3. strong independently supported exit pressure => `SELL / Fade`;
4. unresolved exit independence caps the action at `REDUCE`, never `SELL`;
5. reliable historical hold-horizon expiry causes `REDUCE`, never `SELL` by itself;
6. missing/insufficient hold-horizon evidence does not fabricate expiry;
7. missing wallet evidence => neutral `HOLD`;
8. unknown support independence prevents `Ride` but does not force an exit;
9. candidate-mint, market, timestamp, and future-position contradictions fail closed;
10. invalid/NaN policy or evidence numeric state fails closed;
11. overlapping support/exit churn is valid when each side summary is internally valid;
12. no tested scenario emits `BUY` or `SKIP`;
13. identical input produces identical output and reason ordering.

## Exit criterion

FL6.5 is complete when the pure Rust baseline can reproducibly classify an open position as `HOLD`, `REDUCE`, or `SELL` from explicit point-in-time wallet/cohort evidence, while preserving uncertainty and never granting wallet intelligence entry or execution authority.

LIVE remains disabled.