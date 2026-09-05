# FL3/FL8.1 Exact-Rational PumpSwap Training Fees — Implementation Plan

**Date:** 2026-09-05
**Design:** `docs/superpowers/specs/2026-09-05-fl3-exact-rational-training-fees-design.md`

## Task 1 — RED Rust overlay semantics

Modify only training-economics tests first.

Add a PumpSwap fixture where:

- BUY fee raw delta is positive but not integer-bps representable;
- SELL fee evidence is exact and non-negative;
- reserve projections are valid.

Assert overlay v2 should produce `available`, preserve the exact raw BUY delta/market quote, and keep `effective_fee_bps = None`.

Add a negative/rebate-like fixture proving it still produces `entry_fee_rate_unknown`.

Run CI and require the new positive non-integral test to fail for the intended reason before production changes.

## Task 2 — GREEN Rust overlay v2

In `training_economics_overlay.rs`:

- bump schema version to 2;
- allow fee provenance `effective_fee_bps: Option<u32>`;
- preserve existing exact-bps provenance;
- for `RateUnknown(value)`, accept only non-negative signed raw cost as exact-rational evidence;
- leave negative signed raw cost unavailable;
- keep causal selection unchanged.

Do not modify the sealed PumpSwap fee normalizer/context contract.

Run focused Rust tests, then full CI.

## Task 3 — RED Python reader/application

Update tests first to require:

- schema v2;
- attached fee provenance with non-negative exact non-integral ratio and null bps decodes;
- contradictory bps/raw ratio fails closed;
- negative attached fee provenance fails closed;
- exact-rational fee application produces the expected BUY/SELL quote evidence without integer-bps rounding.

Prove RED before Python implementation.

## Task 4 — GREEN Python overlay v2

Update `fast_training_economics.py`:

- bump schema version to 2;
- make fee bps optional;
- validate raw ratio/bps consistency;
- apply source fee as exact rational raw delta / market quote;
- combine with policy bps and fixed costs deterministically;
- preserve positive finite output checks;
- preserve exit variable rate <100%.

No first-champion compatibility fallback.

## Task 5 — Cross-language and runtime propagation

Run/adjust:

- mixed Rust->Python overlay fixture;
- runtime FL8.1 bundle tests;
- first-champion file/preparation/host tests;
- request-writer tests.

Only update expectations caused by overlay v2/fingerprints. Do not bump unrelated schemas unless an actual serialized contract changes.

## Task 6 — Review, merge, seal, release

Require:

- Rust GREEN;
- Python GREEN;
- repository safety GREEN;
- native ARM64 GREEN;
- exact-head PR review;
- fresh merged-main GREEN;
- zero-diff seal;
- seal-head GREEN;
- immutable release.

## Task 7 — Physical acceptance

Deploy the sealed release through the existing verified deploy workflow.

Create a fresh SHA-keyed acceptance directory.

Re-export:

- 512 features;
- 6,144 overlay rows;
- runtime FL8.1 bundle.

Capture exact status counts and prove FL4 fingerprint unchanged.

Interpret the resulting `available` population as evidence only. Do not promote LIVE or claim economic superiority.
