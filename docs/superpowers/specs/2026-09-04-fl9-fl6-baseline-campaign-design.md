# FL9 FL6 Same-Population Baseline Campaign — Design

**Date:** 2026-09-04

## Status

Design for the next FL9 evidence slice after same-population snapshot hydration was merged as `dc198ef2d0b22367f9eb49c7d77d9c2ef2a9b6fe` (PR #167).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Compose the two already-sealed seams:

`exact FL8.1 row -> canonical snapshot hydration -> posture-aware FL6 replay`

while keeping every baseline-specific evidence class explicit.

The campaign composer must guarantee that the current snapshot used by an FL6 baseline is reconstructed from the **same immutable FL8.1 row** used by the learned-policy campaign. A caller must not be able to substitute a separately reconstructed current snapshot.

## Ownership boundary

Add:

`crates/shreks-storage/src/fast_baseline_campaign.rs`

This module is pure composition logic inside `shreks-storage` because:

- FL8.1 `FastTrainingFeatureRecord` is storage-owned;
- the sealed hydration function is storage-owned;
- FL6 replay/types are core-owned and already dependencies of storage;
- no database/network/runtime authority is required.

## Public contract

### Version

`FAST_BASELINE_CAMPAIGN_VERSION = 1`

### Input

`FastBaselineCampaignInput<'a>` is an enum containing **only** baseline-specific evidence and policy.

The current snapshot is never supplied by the caller.

Variants:

- `ImpulseScalp { execution, policy }`
- `MicroPullback { execution, policy }`
- `PreGraduation { execution, policy }`
- `GraduationFlow { pre_snapshot, boost_context, execution, policy }`
- `WalletCohort { evidence, position, policy }`
- `LongerRunner { protective, continuation, policy }`

The function also receives explicit `FastBaselinePosture`.

### Graduation companion snapshot

FL6.4 is special: the sealed evaluator requires Pump bonding-curve **pre** state and PumpSwap **post** state at the same decision timestamp.

The campaign's exact FL8.1 row supplies the authoritative **post/current** snapshot. The companion `pre_snapshot` remains explicit caller-supplied point-in-time evidence.

The composer must never invent a pre-migration snapshot from lifecycle metadata, reserve data, or future labels.

The sealed FL6.4 evaluator remains responsible for enforcing:

- same mint/quote identity;
- same decision timestamp;
- Pump curve -> PumpSwap venue transition;
- lifecycle consistency.

### Output

`FastBaselineCampaignAssessment` records:

- campaign version;
- hydration version;
- replay version;
- source event ID;
- market key;
- source sequence;
- as-of timestamp;
- posture;
- baseline kind;
- baseline version;
- exact `FastBaselineReplayAssessment`.

Identity must equal the learned-policy campaign identity:

- `source_event_id = "{decision_signature}:{decision_ordinal}"`
- `market_key = "{venue}:{mint}:{quote_mint}"`
- `source_sequence = decision_sequence`
- `as_of_unix_ms = decision_observed_at_unix_ms`

### Function

```rust
pub fn evaluate_fast_baseline_campaign(
    record: &FastTrainingFeatureRecord,
    posture: FastBaselinePosture,
    input: FastBaselineCampaignInput<'_>,
) -> Result<FastBaselineCampaignAssessment, FastBaselineCampaignError>;
```

Algorithm:

1. call sealed `hydrate_fast_baseline_snapshot(record)`;
2. construct exactly one `FastBaselineReplayInput`;
3. use the hydrated snapshot as the current snapshot:
   - FL6.1/2/3/5/6: `snapshot = &hydration.snapshot`;
   - FL6.4: `post_snapshot = &hydration.snapshot`, caller provides only `pre_snapshot`;
4. call sealed `replay_fast_baseline(posture, input)`;
5. assert returned replay market/time still equal the hydrated snapshot;
6. return identity + exact typed replay assessment.

## Error contract

`FastBaselineCampaignError` wraps:

- hydration/storage failure;
- replay failure;
- invariant failure if a replay result ever disagrees with the hydrated current market/time.

No baseline error is converted to a weaker action.

## Evidence separation

### Entry-only FL6.1-6.4

Execution economics remain explicit through the existing optional FL6 execution inputs.

They may contain forecast economics needed for baseline eligibility:

- base quantity;
- executable entry price;
- forecast exit price;
- future exit capacity;
- cost model;
- required edge/risk margin.

The composer derives none of these fields.

### Open-position FL6.5

Wallet/cohort evidence and authoritative position input remain explicit.

No wallet evidence is inferred from FL8.1 market windows.

### Open-position FL6.6

Protective state and continuation evidence remain explicit.

The composer does not turn learned FL9 predictions into FL6.6 continuation evidence automatically. Any shared forecast-source mapping must be a separately specified evidence-hydration slice with explicit provenance.

## PAPER boundary

This module does not:

- create FL7 assessments;
- choose executable PAPER quotes;
- create fills;
- mutate the ledger;
- calculate realized PnL;
- normalize E11/E5 runs;
- compare superiority.

Forecast exit price/capacity used by FL6 eligibility must never be reused as actual PAPER fills.

## No aggregate strategy

The output is one baseline assessment for one baseline at one population row/posture.

This module does not combine FL6.1-6.4 entry rules with FL6.5/6.6 open-position rules into a new strategy.

A lifecycle strategy would be a new named candidate and needs its own design/evidence.

## TDD requirements

RED before production code:

1. exact learned-campaign identity survives `FL8.1 -> hydration -> ImpulseScalp replay`;
2. exact typed ImpulseScalp BUY assessment matches direct sealed replay;
3. wrong posture remains explicit `NotApplicable`;
4. execution-evidence market/time mismatch fails closed through the wrapped replay error;
5. LongerRunner OPEN + missing continuation preserves sealed REDUCE behavior;
6. GraduationFlow uses hydrated row as post snapshot and explicit caller pre snapshot;
7. repeated identical input is deterministic;
8. source firewall forbids database/network/PAPER/risk/promotion/LIVE authority and future-label imports.

## Exit of this slice

This slice is sealed only after exact-head four-gate GREEN and guarded merge.

It does **not** satisfy FL9 economic superiority.

## Next slice

Build the evidence adapters that source the explicit baseline-specific economics/context from authoritative chronological evidence, then produce ordered baseline decision streams over the same FL8.1 population.

After that:

`learned decision stream + FL6 decision streams -> same contemporaneous PAPER quote evidence -> FL7 executor -> E11 -> E5 -> FL9 superiority proof`

No synthetic fills. No fixture profitability claims. LIVE remains disabled.
