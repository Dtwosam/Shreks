# FL9 FL6 Same-Population Snapshot Hydration — Implementation Plan

**Date:** 2026-09-04  
**Base:** `0daa71ecd488671f5208c839491d5bcaafae1df4`

## Goal

Add one fail-closed storage-side hydration seam that reconstructs the exact canonical `FastMarketSnapshot` and exact learned-campaign population identity from one immutable FL8.1 `FastTrainingFeatureRecord`.

## Scope

Production:

- new `crates/shreks-storage/src/fast_baseline_hydration.rs`;
- tiny crate-internal visibility-only reuse in `crates/shreks-storage/src/training_features.rs`;
- `crates/shreks-storage/src/lib.rs` module/export wiring.

Tests:

- `crates/shreks-storage/tests/fl9_fast_baseline_snapshot_hydration.rs`.

Docs:

- design;
- this plan.

No provider, observer, database schema/migration, PAPER, risk authority, promotion, runtime, signer, deployment, or LIVE files.

## TDD sequence

### 1. RED — missing hydration contract

Commit the contract test before production code exists.

The test imports:

- `FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION`;
- `FastBaselineSnapshotHydration`;
- `hydrate_fast_baseline_snapshot`.

Required RED coverage:

- valid Pump curve row -> exact population identity + exact canonical snapshot;
- exact seven rolling windows including ordered path fields;
- exact reserve context;
- exact lifecycle evidence;
- PumpSwap reserve context;
- deterministic repeat;
- contradiction/future-evidence failures;
- source-authority firewall.

Open a draft PR at the missing-contract head and record the exact Rust collection/compiler failure.

### 2. GREEN — reuse FL8.1 validation

In `training_features.rs`, make only these existing helpers crate-visible:

- `validate_record`;
- `parse_training_venue`.

Do not change their logic.

The hydration module must call `validate_record(record)?` first.

### 3. GREEN — hydration implementation

Implement:

```rust
pub const FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct FastBaselineSnapshotHydration { ... }

pub fn hydrate_fast_baseline_snapshot(
    record: &FastTrainingFeatureRecord,
) -> Result<FastBaselineSnapshotHydration, StorageError>;
```

Internal helpers:

- exact window mapping;
- exact reserve-context mapping + venue check;
- strict known provider parsing;
- strict lifecycle event mapping + identity checks.

No floating-point arithmetic is needed. Numeric values are copied unchanged.

### 4. Public export

Wire the new module through `shreks-storage/src/lib.rs`.

Do not alter existing FL8.1 public names.

### 5. Candidate verification

Require canonical CI:

1. Repository safety;
2. Python tests;
3. Rust workspace tests;
4. native ARM64 release build.

Freeze the exact candidate tree while the run executes.

### 6. Audit

Read-only audit must confirm:

- same source_event_id formula as Python learned campaign;
- same market_key formula;
- same sequence/time;
- no future label/counterfactual import;
- no provider/network/db/PAPER/risk/LIVE authority;
- exact six-file scope or smaller.

### 7. Seal

After exact final head 4/4 GREEN:

- update PR with RED/GREEN provenance;
- mark ready;
- guarded squash merge with expected head SHA;
- do not claim merged-main CI if the connected workflow reader still cannot surface push-triggered runs;
- the next branch must root at the exact merge commit and re-run the full suite.

## Next slice

Build strict baseline campaign request/evidence wiring over:

`FL8.1 row -> hydrated snapshot -> explicit posture/evidence/policy -> sealed FL6 replay dispatcher`.

Execution economics remain explicit. Forecast prices never become PAPER fills. Wallet and continuation evidence remain separate. No aggregate strategy is invented.
