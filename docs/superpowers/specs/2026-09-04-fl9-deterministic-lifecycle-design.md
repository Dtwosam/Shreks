# FL9 Explicit Deterministic Lifecycle Baselines — Design

**Date:** 2026-09-04

## Status

Design after learned-vs-baseline population parity was merged as `2bd91693fbac62c79fbd012cfc019a35a894926a` (PR #170).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The six sealed FL6 strategy families are intentionally posture-specific:

- FL6.1–6.4: flat-position entry evaluators producing `BUY/SKIP`;
- FL6.5–6.6: open-position management evaluators producing `HOLD/REDUCE/SELL`.

FL9 superiority requires comparable closed-trade PAPER expectancy.

A single posture-specific FL6 family cannot create a complete closed-trade run. Silently treating wrong-posture rows as HOLD, inventing an exit rule, or assigning a default REDUCE fraction would create hidden strategy authority and invalidate the comparison.

## Decision

Create an explicit, separately versioned **deterministic lifecycle candidate** that pairs:

1. exactly one sealed entry family from FL6.1–6.4; and
2. exactly one sealed open-position manager from FL6.5–6.6.

This is a new named comparison candidate, not a reinterpretation of an existing FL6 baseline.

The policy also explicitly supplies sizing semantics that the underlying directional evaluators do not own:

- `entry_target_exposure_fraction` in `(0, 1]`;
- `reduce_remaining_fraction` in `(0, 1)`.

No production defaults are embedded.

Four entry families × two managers yields eight possible lifecycle family combinations. Evidence campaigns may evaluate any or all explicitly configured candidates.

## Ownership

Add:

`crates/shreks-storage/src/fast_deterministic_lifecycle.rs`

The module composes the already-sealed same-population FL6 campaign evaluator. It has no provider/database/PAPER/risk/promotion/LIVE authority.

## Public policy

```rust
pub const FAST_DETERMINISTIC_LIFECYCLE_VERSION: u16 = 1;

pub struct FastDeterministicLifecyclePolicy {
    pub version: u16,
    pub entry_baseline_kind: FastBaselineKind,
    pub manager_baseline_kind: FastBaselineKind,
    pub entry_target_exposure_fraction: f64,
    pub reduce_remaining_fraction: f64,
}
```

Validation:

- `version > 0`;
- entry kind must be one of ImpulseScalp, MicroPullback, PreGraduation, GraduationFlow;
- manager kind must be WalletCohort or LongerRunner;
- entry target finite and `0 < target <= 1`;
- reduction remainder finite and `0 < fraction < 1`.

The policy does not hide baseline-specific thresholds. Those remain in the explicit FL6 component inputs.

## Per-row request

```rust
pub struct FastDeterministicLifecycleRequest<'a> {
    pub record: &'a FastTrainingFeatureRecord,
    pub posture: FastDeterministicLifecyclePostureInput<'a>,
}

pub enum FastDeterministicLifecyclePostureInput<'a> {
    Flat {
        input: FastBaselineCampaignInput<'a>,
    },
    Open {
        current_exposure_fraction: f64,
        input: FastBaselineCampaignInput<'a>,
    },
}
```

The request supplies only the component relevant to the current posture.

There are no placeholder manager inputs for flat rows and no placeholder entry economics for open rows.

## Component selection

### FLAT

- request component kind must equal `policy.entry_baseline_kind`;
- evaluate exact FL8.1 row through `evaluate_fast_baseline_campaign(..., Flat, ...)`;
- valid directional outcomes:
  - `BUY`
  - `SKIP`
- `NotApplicable`, HOLD, REDUCE, SELL are invariant failures.

Target exposure:

- BUY -> `entry_target_exposure_fraction`;
- SKIP -> `0.0`.

Current exposure is `None`.

### OPEN

- `current_exposure_fraction` must be finite and `0 < current <= 1`;
- request component kind must equal `policy.manager_baseline_kind`;
- evaluate through `evaluate_fast_baseline_campaign(..., Open, ...)`;
- valid outcomes:
  - `HOLD`
  - `REDUCE`
  - `SELL`
- `NotApplicable`, BUY, SKIP are invariant failures.

Target exposure:

- HOLD -> current exposure;
- SELL -> `0.0`;
- REDUCE -> `current_exposure_fraction * reduce_remaining_fraction`.

This makes reduction sizing deterministic and always strictly below the current exposure without embedding an arbitrary default.

## Output

Each decision records:

- lifecycle version;
- source event ID;
- market key;
- source sequence;
- as-of timestamp;
- selected component kind/version;
- action;
- current exposure fraction when OPEN;
- target exposure fraction;
- exact underlying `FastBaselineCampaignAssessment`.

Batch output records:

- lifecycle policy;
- ordered decisions.

## Batch population invariants

A batch must be non-empty and preserve caller order.

Fail closed on:

- duplicate source event ID;
- per-market source-sequence non-increase;
- per-market timestamp regression;
- wrong component family for current posture;
- component evaluation failure.

Every row produces exactly one lifecycle decision.

## Exposure-state boundary

This layer does **not** infer current exposure from previous decisions.

The caller supplies authoritative current exposure for each OPEN row. The later PAPER executor remains the authority that verifies the decision posture/exposure against its actual ledger state.

This separation prevents research replay from pretending it owns portfolio state.

## Execution-evidence boundary

This layer does not construct:

- entry execution economics;
- wallet/cohort evidence;
- continuation evidence;
- protective state;
- PAPER quote evidence;
- risk context.

Those remain explicit component/evidence inputs.

Forecast exit prices/capacity used for entry eligibility remain forecast economics and must never be reused as PAPER fills.

## Candidate identity

This slice does not invent a human version string or SHA fingerprint.

A following canonical wire/codec slice will fingerprint:

- this lifecycle policy;
- exact component baseline versions/policies/evidence provenance;
- ordered decision output.

That fingerprint becomes the deterministic baseline candidate identity supplied to the existing PAPER/proof chain.

## TDD

RED before production implementation must prove:

1. valid ImpulseScalp + LongerRunner policy;
2. invalid entry/manager family pair fails closed;
3. FLAT BUY maps to explicit entry target;
4. FLAT SKIP maps to zero target;
5. OPEN HOLD preserves current exposure;
6. OPEN REDUCE applies explicit remaining fraction exactly;
7. OPEN SELL targets zero;
8. wrong component family for posture fails closed;
9. duplicate/order regressions fail;
10. repeated identical batch is deterministic;
11. source firewall forbids external/PAPER/risk/promotion/LIVE authority.

## Economic status

This makes complete deterministic action lifecycles **representable**. It does not prove any lifecycle candidate profitable.

Candidates that never close enough trades will correctly fail the later FL9 minimum-evidence gates.

No fixture result may be called economic superiority.

LIVE remains disabled.
