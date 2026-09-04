# FL9 FL6 Ordered Baseline Campaign Batch — Design

**Date:** 2026-09-04

## Status

Design for the next FL9 evidence slice after the same-population single-row campaign composer was merged as `3cbc494aa2ceb7be5f641113ed2045ca7d596b2d` (PR #168).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Evaluate one deterministic FL6 baseline across an ordered set of exact FL8.1 rows while preserving the same point-in-time population identity/order used by the learned-policy campaign.

This slice creates a deterministic **decision stream**, not a strategy aggregator and not PAPER execution.

## Core invariant

One batch represents exactly one FL6 baseline kind/version.

Mixed baseline kinds in one batch are rejected.

Each row keeps its own explicit posture and baseline-specific evidence.

Wrong-posture rows remain explicit `NotApplicable` assessments. They are never dropped because dropping them would silently change the evaluated population.

## Public contract

Add:

`crates/shreks-storage/src/fast_baseline_batch.rs`

### Version

`FAST_BASELINE_CAMPAIGN_BATCH_VERSION = 1`

### Request

```rust
pub struct FastBaselineCampaignRequest<'a> {
    pub record: &'a FastTrainingFeatureRecord,
    pub posture: FastBaselinePosture,
    pub input: FastBaselineCampaignInput<'a>,
}
```

The request contains the exact immutable FL8.1 row plus explicit posture/evidence.

### Output

```rust
pub struct FastBaselineCampaignBatchAssessment {
    pub version: u16,
    pub baseline_kind: FastBaselineKind,
    pub baseline_version: u16,
    pub decisions: Vec<FastBaselineCampaignAssessment>,
}
```

Output order equals input order exactly.

No sorting is performed.

### Function

```rust
pub fn evaluate_fast_baseline_campaign_batch(
    requests: &[FastBaselineCampaignRequest<'_>],
) -> Result<FastBaselineCampaignBatchAssessment, FastBaselineCampaignBatchError>;
```

## Validation

Fail closed on:

- empty batch;
- mixed baseline kinds;
- duplicate `source_event_id`;
- per-market source sequence not strictly increasing;
- per-market timestamp regression;
- any single-row campaign failure.

The batch uses the same market key as the learned campaign:

`"{venue}:{mint}:{quote_mint}"`

Order validation mirrors the learned campaign batch contract:

- source sequence strictly increases per market;
- timestamp cannot move backward per market.

This lets later comparison assert that learned and baseline streams describe the same population without reinterpreting order.

## Population semantics

A valid batch may contain:

- actionable baseline decisions;
- SKIP/HOLD/REDUCE/SELL;
- explicit `NotApplicable` rows.

Every input row produces exactly one output row unless the whole batch fails closed.

No row is silently filtered.

## No aggregate strategy

A batch is homogeneous by `FastBaselineKind`.

Running six baselines means six separate batches over the same population, not one combined policy.

## No execution authority

This module does not:

- build execution economics;
- source future forecasts;
- source wallet evidence;
- source continuation evidence;
- create FL7 PAPER assessments;
- pick quotes;
- create fills;
- mutate positions;
- calculate PnL;
- compare superiority;
- promote;
- enable LIVE.

## TDD

RED before production:

1. ordered two-row Impulse Scalp batch preserves exact input order and typed decisions;
2. wrong-posture row remains present as `NotApplicable`;
3. duplicate source identity is rejected;
4. per-market sequence regression is rejected;
5. timestamp regression is rejected;
6. mixed baseline kinds are rejected;
7. identical batch evaluation is deterministic;
8. source firewall forbids I/O/PAPER/risk/promotion/LIVE authority.

## Next slice

Attach authoritative explicit evidence adapters to produce these requests from chronological evidence, then compare the resulting homogeneous FL6 streams with the learned stream using identical PAPER quote evidence.

No synthetic fills. FL9 remains **EVIDENCE PENDING**.
