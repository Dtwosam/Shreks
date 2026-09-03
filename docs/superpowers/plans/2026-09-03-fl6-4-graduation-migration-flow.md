# FL6.4 Graduation / Migration Flow Implementation Plan

> Execute autonomously with TDD. Preserve the sealed FL6.3 base and do not grant capital authority.

**Base:** `cac03c19577942f6049cd504a65a05b059699a7b`  
**Branch:** `build/fl6-4-graduation-migration-flow`

## Task 1 — Freeze cross-venue contract

- Same mint/quote across Pump curve and PumpSwap snapshots.
- Same point-in-time decision timestamp.
- Verified PumpGraduation lifecycle transition from Pump curve to PumpSwap.
- One explicit flow window in both venue snapshots.
- Optional provider-neutral `can_boost` context only; do not claim a BOOST action occurred.
- Reuse existing execution economics for current PumpSwap entry tradeability.
- No production default thresholds.
- No provider/storage/PAPER/risk/signer/deployment/LIVE changes.

## Task 2 — RED tests

Create `crates/shreks-core/tests/fl6_graduation_flow.rs` before production implementation.

Tests cover:

- strong recent migration flow + economics => BUY,
- missing lifecycle => SKIP,
- stale graduation => SKIP,
- pre/post venue and mint/quote contradictions => error,
- snapshot timestamp mismatch => error,
- conflicting lifecycle evidence => error,
- weak pre-flow => SKIP,
- weak post-flow / excessive sells => canonical SKIP reasons,
- low post/pre velocity retention => SKIP,
- optional boost context true and false retained without being a stand-alone decision gate,
- boost identity mismatch => error,
- missing execution => SKIP with absent economics,
- insufficient capacity => SKIP,
- negative post-cost forecast => SKIP,
- entry above max acceptable => SKIP,
- invalid policy => error,
- deterministic repeated output.

Run canonical CI. Require Rust RED exactly because the FL6.4 API does not exist yet while repository safety, Python, and ARM64 remain green.

## Task 3 — Pure evaluator

Add `crates/shreks-core/src/fast_lane/graduation_flow.rs` implementing:

- `GRADUATION_FLOW_BASELINE_VERSION = 1`,
- `GraduationFlowPolicy`,
- `GraduationBoostContext`,
- `GraduationFlowExecutionInput`,
- stable `GraduationFlowReason`,
- auditable `GraduationFlowAssessment`,
- fail-closed `GraduationFlowError`,
- `assess_graduation_flow`.

Validation/evaluation order:

1. Validate policy.
2. Validate both snapshots and exact identity/timestamp contract.
3. Resolve lifecycle truth from both snapshots; missing => SKIP, conflicting => error.
4. Validate Pump curve -> PumpSwap lifecycle transition and age.
5. Read exact configured flow window from both snapshots.
6. Evaluate pre-flow activity.
7. Evaluate post-flow participation, seller ceiling, imbalance, velocity, acceleration.
8. Compute post/pre velocity retention ratio only when pre velocity is positive; never invent one otherwise.
9. Validate optional boost context identity and retain `can_boost` only as context.
10. Apply existing execution economics bound to post PumpSwap market.
11. Canonicalize reasons; BUY only when no reasons remain.

## Task 4 — Public exports

Update only:

- `crates/shreks-core/src/fast_lane/mod.rs`,
- the Fast Lane export block in `crates/shreks-core/src/lib.rs`.

## Task 5 — Exact-head verification

- Run all four canonical gates.
- Audit exact changed-file set from sealed FL6.3 main.
- Review `lib.rs` patch for export-only changes.
- Preserve intentional RED proof; clean only post-RED authoring history if useful.
- After any history rewrite, require fresh four-gate exact-head CI.

## Task 6 — Guarded merge and seal

- Update PR with proof chain and scope audit.
- Mark ready after exact-head all-green.
- Guarded merge expected exact head.
- Require fresh merged-main four-gate CI.
- Mark FL6.4 SEALED only after merged-main success.

LIVE remains disabled throughout.
