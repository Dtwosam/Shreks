# FL6.3 Pre-Graduation Acceleration Implementation Plan

> Execute autonomously with TDD. Preserve the verified FL6.2 base and do not grant capital authority.

**Base:** `be8a2404051903e2b4ec6abf47a902e577d165d4`  
**Branch:** `build/fl6-3-pre-graduation-acceleration`

## Task 1 — Freeze the contract

- Keep FL6.3 independent from FL6.1/FL6.2.
- Use existing `FastMarketSnapshot.last_reserve_context` for authoritative Pump curve state.
- Use existing rolling summaries for participation and acceleration.
- Require explicit policy-supplied graduation target and near-graduation reserve ceiling.
- Do not add production default thresholds.
- Do not change provider/storage/PAPER/risk/signer/deployment/LIVE authority.

## Task 2 — RED evaluator tests

Create `crates/shreks-core/tests/fl6_pre_graduation.rs` before production implementation.

Tests must cover:

- strong near-graduation acceleration + positive economics => BUY,
- wrong venue => SKIP,
- missing/wrong reserve context => SKIP,
- graduation target reached => SKIP,
- too far from configured graduation boundary => SKIP,
- weak signal participation and acceleration => SKIP with stable reason order,
- already-graduated lifecycle evidence => SKIP,
- missing execution evidence => SKIP with economic fields absent,
- insufficient exit capacity => SKIP,
- non-positive post-cost value => SKIP,
- entry above maximum acceptable entry => SKIP,
- execution market/time mismatch => error,
- invalid policy => error,
- deterministic identical output.

Run canonical CI and require Rust to fail exactly because the FL6.3 public API is absent while repository safety, Python, and ARM64 remain green.

## Task 3 — Implement the pure evaluator

Add `crates/shreks-core/src/fast_lane/pre_graduation.rs`.

Implement:

- `PRE_GRADUATION_BASELINE_VERSION = 1`,
- versioned `PreGraduationPolicy`,
- `PreGraduationExecutionInput`,
- stable `PreGraduationReason`,
- auditable `PreGraduationAssessment`,
- fail-closed `PreGraduationError`,
- `assess_pre_graduation_acceleration`.

Signal requirements:

1. Market is Pump.fun bonding curve.
2. No already-observed Pump graduation lifecycle transition.
3. Pump curve reserve context is present.
4. Current real base reserve is above the configured graduation target and at/below the configured near-graduation ceiling.
5. Signal-window buy participation and actor count pass.
6. Signal-window buy arrival, count imbalance, quote-flow imbalance, velocity, and acceleration pass.
7. Signal/context quote-flow velocity expansion passes.
8. Signal buy base quantity as a fraction of normalized distance-to-graduation passes.
9. Explicit execution economics pass capacity, positive post-cost value, and maximum-entry boundary.

Do not read DB/provider/future labels or wall clock.

## Task 4 — Public exports

Update only:

- `crates/shreks-core/src/fast_lane/mod.rs`,
- `crates/shreks-core/src/lib.rs` Fast Lane re-export block.

No unrelated public API edits.

## Task 5 — Exact-head proof and scope audit

- Run fresh exact-head four-gate CI.
- Audit changed files against sealed FL6.2 main.
- Require only design/plan + FL6.3 evaluator/test + export surfaces.
- Clean authoring history only if it can preserve intentional RED proof.
- Run another fresh exact-head four-gate CI after any history rewrite.

## Task 6 — Guarded merge and seal

- Update PR with RED/GREEN evidence and exact scope.
- Mark ready only after exact-head all-green CI.
- Guarded merge with expected head SHA.
- Require fresh merged-main four-gate CI.
- Mark FL6.3 SEALED only after merged-main all-green proof.

LIVE remains disabled throughout.
