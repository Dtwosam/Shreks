# FL9 FL6 Baseline Replay Dispatcher — Implementation Plan

**Date:** 2026-09-04  
**Base:** `870477e71c98339856788896b26a3b7107cf56ea`

## Goal

Add one pure Rust dispatcher that can replay each sealed FL6 baseline against an explicit current posture without combining baseline families or granting execution authority.

## Scope

Production:

- `crates/shreks-core/src/fast_lane/baseline_replay.rs`
- `crates/shreks-core/src/fast_lane/mod.rs`
- `crates/shreks-core/src/lib.rs`

Tests:

- `crates/shreks-core/tests/fl9_fl6_baseline_replay.rs`

Docs:

- design
- this plan

No provider/storage/runtime/PAPER/risk/signer/deployment/LIVE files.

## TDD sequence

### 1. RED — public replay contract

Add the integration test before the production module exists.

The test must import:

- `FAST_BASELINE_REPLAY_VERSION`;
- `FastBaselineKind`;
- `FastBaselinePosture`;
- `FastBaselineReplayInput`;
- `FastBaselineReplayAssessment`;
- `replay_fast_baseline`.

Required RED cases:

- flat Impulse Scalp strong fixture -> exact typed BUY assessment;
- same entry baseline under OPEN posture -> `NotApplicable`;
- Longer Runner under FLAT posture -> `NotApplicable`;
- Longer Runner under OPEN posture with missing continuation -> exact typed REDUCE assessment;
- repeated replay -> equal output;
- authority/source firewall.

Open a draft PR on the intentional missing-contract head and record the exact CI failure.

### 2. GREEN — dispatcher implementation

Implement:

```rust
pub const FAST_BASELINE_REPLAY_VERSION: u16 = 1;

pub enum FastBaselineKind { ... }
pub enum FastBaselinePosture { Flat, Open }
pub struct FastBaselineNotApplicable { ... }
pub enum FastBaselineReplayInput<'a> { ... }
pub enum FastBaselineReplayAssessment { ... }
pub enum FastBaselineReplayError { ... }

pub fn replay_fast_baseline(
    posture: FastBaselinePosture,
    input: FastBaselineReplayInput<'_>,
) -> Result<FastBaselineReplayAssessment, FastBaselineReplayError>;
```

Rules:

- FL6.1-6.4 require `Flat`;
- FL6.5-6.6 require `Open`;
- mismatch returns typed `NotApplicable`;
- applicable dispatch calls exactly one sealed evaluator;
- evaluator errors are wrapped, not rewritten;
- output keeps the exact typed FL6 assessment;
- no dynamic provider/storage/PAPER authority.

### 3. Public exports

Expose the dispatcher through:

- `shreks_core::fast_lane` internal re-export;
- root `shreks_core` public re-export.

Do not change existing FL6 exports.

### 4. Verification

Require canonical CI:

1. Repository safety;
2. Python tests;
3. Rust workspace tests;
4. native ARM64 release build.

Any production edit after a GREEN candidate invalidates that candidate and requires a fresh run.

### 5. Clean-history seal

After final candidate 4/4 GREEN:

- reconstruct clean history as:
  1. design;
  2. plan;
  3. consolidated RED;
  4. implementation;
- verify final tree is byte-identical to the verified candidate;
- move only the feature branch;
- require fresh exact-head 4/4 GREEN;
- guarded merge using expected head SHA;
- require push-triggered merged-main 4/4 GREEN.

## Next slice

After this dispatcher is SEALED, build the evidence hydration/decision-stream layer that maps the exact FL8.1 campaign population into baseline-specific point-in-time inputs.

That layer must keep entry-only and open-position-only baselines separate. If a full lifecycle candidate is needed, it must be explicitly named and specified rather than created implicitly inside replay.

FL9 economic exit remains **EVIDENCE PENDING**.
