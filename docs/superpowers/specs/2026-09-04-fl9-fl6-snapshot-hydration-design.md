# FL9 FL6 Same-Population Snapshot Hydration — Design

**Date:** 2026-09-04

## Status

Design for the next FL9 evidence slice after the FL6 baseline replay dispatcher was merged.

Base merge: `0daa71ecd488671f5208c839491d5bcaafae1df4` (PR #166).  
Exact pre-merge candidate: `97699334859245b4008ec96cf4ef91096226f283`, CI `33821297095` four-gate GREEN.

The connected GitHub workflow reader does not surface push-triggered `main` runs, so this document does **not** claim a merged-main run ID that has not been observed. This branch is rooted at the exact merge commit and its own full CI must therefore re-prove the merged tree plus this slice before merge.

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Reconstruct one canonical Rust `FastMarketSnapshot` from the **exact immutable FL8.1 `FastTrainingFeatureRecord` row** used by the learned-policy campaign, while preserving the exact campaign population identity.

This closes the point-in-time population seam required before FL6 deterministic baseline decisions can be compared to the learned FL9 policy.

The hydration layer must answer:

> Given this exact FL8.1 feature row, what exact canonical Fast Lane snapshot did the exporter preserve, and what exact campaign population key identifies it?

It does **not** attach future economics, wallet evidence, continuation forecasts, PAPER fills, or a baseline policy.

## Why this slice exists

The learned-policy campaign already consumes FL8.1 rows in Python and preserves:

- `source_event_id = "{decision_signature}:{decision_ordinal}"`;
- `market_key = "{venue}:{mint}:{quote_mint}"`;
- `source_sequence = decision_sequence`;
- `as_of_unix_ms = decision_observed_at_unix_ms`.

FL6 evaluators consume Rust `FastMarketSnapshot` values.

The FL8.1 exporter was produced directly from the sealed canonical `FastMarketState` snapshot and stores the complete snapshot fields required by FL6:

- market identity;
- as-of timestamp;
- last sequence;
- last price;
- reserve context;
- lifecycle event;
- all seven sealed rolling window summaries including ordered high/low/trough identity.

Therefore baseline replay should reconstruct from the same row rather than replaying raw events a second time or independently recomputing features.

## Ownership boundary

Add a focused storage-side module:

`crates/shreks-storage/src/fast_baseline_hydration.rs`

This is the correct dependency direction:

- `shreks-storage` already owns `FastTrainingFeatureRecord`;
- `shreks-storage` already depends on `shreks-core`;
- `shreks-core` must not depend on storage;
- the output is a canonical `FastMarketSnapshot` consumed by the already-merged pure FL6 replay dispatcher.

No network/provider call, database read, filesystem read, PAPER execution, risk mutation, registry mutation, signer, transaction submission, deployment, or LIVE authority belongs in this module.

## Reuse the sealed FL8.1 validator

The hydration path must not create a second weaker validation definition.

Change the existing private helpers in `training_features.rs` only as needed for crate-internal reuse:

- `validate_record` -> crate-visible;
- `parse_training_venue` -> crate-visible.

Their behavior does not change.

The new hydration module calls the exact FL8.1 record validator before reconstructing anything.

## Public contract

### Version

```rust
pub const FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION: u16 = 1;
```

### Output

```rust
pub struct FastBaselineSnapshotHydration {
    pub version: u16,
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub decision_executable_entry_price_quote: f64,
    pub decision_entry_total_quote: Option<f64>,
    pub snapshot: FastMarketSnapshot,
}
```

The decision price/total are copied unchanged from the point-in-time FL8.1 row for later explicit execution-economics construction. The hydration layer does not derive quantity, forecast exit price, exit capacity, cost model, edge, or risk margin from them.

### Function

```rust
pub fn hydrate_fast_baseline_snapshot(
    record: &FastTrainingFeatureRecord,
) -> Result<FastBaselineSnapshotHydration, StorageError>;
```

## Exact population identity

For every hydrated row:

```text
source_event_id = "{decision_signature}:{decision_ordinal}"
market_key      = "{venue}:{mint}:{quote_mint}"
source_sequence = decision_sequence
as_of_unix_ms   = decision_observed_at_unix_ms
```

These strings and values must exactly equal the already-sealed Python `build_fast_campaign_decision_request(...)` identity.

The hydration result also requires:

- `snapshot.market` equals the identity market;
- `snapshot.as_of_unix_ms == as_of_unix_ms`;
- `snapshot.last_sequence == Some(source_sequence)`.

No alternate identity is introduced.

## Snapshot reconstruction

### Market

Parse the existing FL8.1 venue string with the same crate-internal venue parser used by the exporter and construct `FastMarketKey` from:

- `mint`;
- `quote_mint`;
- parsed venue.

V1 remains limited to Fast Lane training venues already accepted by FL8.1:

- `pump_fun_bonding_curve`;
- `pump_swap`.

### Top-level snapshot fields

Copy unchanged:

- `snapshot_as_of_unix_ms`;
- `snapshot_last_sequence`;
- `snapshot_last_price_quote`.

The sealed validator already requires the snapshot clock and sequence to equal the decision clock and sequence.

### Rolling windows

Map every `FastTrainingWindowSummary` field 1:1 back to `FastWindowSummary`.

No recomputation is permitted.

The exact seven-window order and identities remain the sealed `DEFAULT_FAST_WINDOWS_MS` set.

This includes:

- buy/sell counts;
- unique actors;
- arrival rates;
- count imbalance;
- base/quote quantities;
- net quote flow;
- quote-flow imbalance;
- velocity/acceleration;
- local high price/sequence/time;
- local low price/sequence/time;
- post-high trough price/sequence/time;
- last price;
- drawdown;
- recovery.

### Reserve context

Map FL8.1 reserve context 1:1:

- `PumpCurve` -> `FastReserveContext::PumpCurve`;
- `PumpSwapPool` -> `FastReserveContext::PumpSwapPool`.

Fail closed if the reserve-context variant contradicts the hydrated market venue.

No reserve values are estimated or normalized.

### Lifecycle event

When present, reconstruct `TokenLifecycleEvent` exactly from the stored FL8.1 event.

Only the sealed lifecycle vocabulary is accepted:

- kind: `pump_graduation`;
- transition: Pump.fun bonding curve -> PumpSwap;
- known `ProviderId`;
- non-empty market/pool/signature identity;
- non-negative clocks;
- lifecycle mint/quote must equal the hydrated row.

The existing FL8.1 future-evidence guard still applies: lifecycle evidence detected after the decision time is rejected before hydration.

## Fail-closed semantics

Hydration returns `StorageError::InvalidData` on at least:

- unsupported schema/version;
- malformed point-in-time clocks/sequences;
- future window sequence/timestamp;
- future lifecycle evidence;
- unsupported venue;
- invalid/empty market identity;
- reserve-context/venue contradiction;
- unsupported lifecycle kind/provider/venue;
- malformed lifecycle identity;
- lifecycle market mismatch.

Missing optional reserve/lifecycle evidence stays `None`; it is not fabricated.

## Explicitly excluded evidence

This slice must not consume or derive:

- FL4 future path endpoint labels;
- FL5 counterfactual labels;
- future exit prices;
- future exit capacity;
- cost models;
- wallet/cohort evidence;
- continuation forecast evidence;
- PAPER quote evidence;
- RiskContext;
- position state;
- baseline policy;
- learned forecast predictions.

Those belong to later explicit evidence layers.

## Source-authority firewall

The new hydration module may import only:

- FL8.1 training feature record types/validator;
- canonical `shreks_core` data types;
- `StorageError`.

Tests should source-scan the module and reject authority/dependency strings for:

- `rusqlite` / database access;
- provider crates;
- HTTP/network clients;
- filesystem;
- PAPER execution;
- RiskContext/risk mutation;
- registry/promotion;
- signer/submission;
- LIVE mode.

## TDD requirements

RED tests before production hydration code must prove:

1. exact campaign population identity from a valid FL8.1 row;
2. full window reconstruction is exact, including ordered path identity;
3. Pump curve reserve context is preserved exactly;
4. Pump graduation lifecycle evidence is preserved exactly;
5. PumpSwap pool reserve context is preserved exactly;
6. reserve-context/venue contradiction fails closed;
7. lifecycle market/provider/kind/transition defects fail closed;
8. a future path timestamp/sequence rejected by the existing FL8.1 validator remains rejected;
9. repeated identical hydration is deterministic;
10. source-authority firewall.

## Next slice

After this hydration seam is sealed, build a strict baseline campaign request/evidence layer that combines:

- this exact same-population hydrated snapshot;
- explicit caller-supplied FL6 policy;
- explicit execution-economics inputs where an entry baseline requires them;
- explicit wallet/continuation/protective evidence where an open-position baseline requires them;
- explicit current posture.

That layer may then use the already-merged FL6 replay dispatcher.

Actual PAPER comparison still comes later and must use the same contemporaneous quote evidence as the learned candidate.

No synthetic fills. No profitability claim. FL9 remains **EVIDENCE PENDING** until real evidence passes the sealed superiority proof.
