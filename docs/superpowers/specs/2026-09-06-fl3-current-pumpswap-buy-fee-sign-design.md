# FL3 Training Economics Current PumpSwap BUY Fee Sign — Design

**Date:** 2026-09-06  
**Base:** `4d33fef8224dd3babf40c97c5fc0d6ce59efbe18`

## Status

Follow-on to the fresh FL9 rich-cohort deployment and physical target-coverage audit.

Fresh batch 001 proved:

- 512 fresh decisions / 6,144 FL4 labels;
- 373 PumpSwap decisions;
- route-target evidence is now available on 150–244 mature rows depending on horizon;
- only 8 fresh economics overlay rows were `available`;
- 1,378 fresh overlay rows were `entry_fee_rate_unknown`.

A read-only source audit reduced those 1,378 rows to 239 unique causal BUY fee sources. Every one had:

- canonical raw PumpSwap source evidence;
- migration-15 PumpSwap execution-economics sidecar;
- complete current economics suffix;
- negative raw `user_quote_amount_raw - quote_amount_raw`.

A second physical proof established, for all 239/239 sources with zero mismatch:

`quote_amount_raw - user_quote_amount_raw = lp_fee_raw + protocol_fee_raw + coin_creator_fee_raw`

and also:

`quote_amount_with_or_without_lp_fee_raw - user_quote_amount_raw = lp_fee_raw`

`quote_amount_raw - quote_amount_with_or_without_lp_fee_raw = protocol_fee_raw + coin_creator_fee_raw`

PAPER remained healthy and LIVE remained disabled.

## Problem

The lower-level PumpSwap effective-fee normalizer intentionally treats the stable raw
`user_quote_amount_raw` vs `quote_amount_raw` delta without assigning combined semantics to
migration-15 component fields.

For legacy BUY evidence, that contract is retained.

For current PumpSwap BUY events carrying the complete migration-15 sidecar, production evidence
shows a distinct field orientation: the user quote is below the market quote by exactly the source
fee stack. The v2 training overlay currently sees the negative raw delta and classifies it as
`entry_fee_rate_unknown`, discarding valid source-backed cost evidence.

## Goal

Add training-economics overlay schema v3 that resolves this current BUY orientation only when the
migration-15 sidecar proves the exact source identity.

Do not change the lower-level raw normalizer or historical FL4 rows.

## Source contract

When an entry fee context is `RateUnknown` solely because the raw BUY delta is negative, overlay
v3 may recover a non-negative fee only if all of the following hold for the exact causal source:

1. the source is BUY;
2. the migration-15 PumpSwap sidecar exists;
3. the current suffix is complete;
4. `quote_amount_raw >= user_quote_amount_raw`;
5. `quote_amount_raw - user_quote_amount_raw == lp_fee_raw + protocol_fee_raw + coin_creator_fee_raw`;
6. `quote_amount_with_or_without_lp_fee_raw - user_quote_amount_raw == lp_fee_raw`;
7. `quote_amount_raw - quote_amount_with_or_without_lp_fee_raw == protocol_fee_raw + coin_creator_fee_raw`.

If any condition is not proven, preserve `entry_fee_rate_unknown`. No fallback, rounding, current
protocol constant, or inferred fee schedule is allowed.

The recovered signed user cost is exactly:

`quote_amount_raw - user_quote_amount_raw`.

Its optional integer-bps representation is computed exactly using the same no-rounding rule as the
existing normalizer. Non-integral ratios remain `effective_fee_bps = null` and are still usable by
overlay v3 through exact-rational raw integers.

## Compatibility

- lower-level PumpSwap effective-fee API remains unchanged;
- legacy raw BUY/SELL semantics remain unchanged;
- historical overlay v1/v2 artifacts remain immutable;
- current Rust/Python overlay schema increments to v3;
- current readers reject v1/v2 rather than silently reinterpret them;
- FL4 rows are not mutated;
- old 512-decision population remains champion-ineligible through the sealed cohort floor.

## Required tests

1. current BUY with exact three-part sidecar identity becomes source-backed `available`;
2. recovered signed cost is positive and exact;
3. non-integral corrected fee remains valid with `effective_fee_bps = null`;
4. mismatched current sidecar remains `entry_fee_rate_unknown`, not guessed;
5. legacy negative BUY delta remains rate-unknown;
6. SELL behavior is unchanged;
7. overlay manifest reports schema v3;
8. Python reader requires schema v3 and exact-rational fee validation still passes;
9. full Rust/Python/repository-safety/native ARM64 gates pass.

LIVE remains disabled.

## Implementation seal

Implementation PR #227 merged as `034d8e564f5d6496b5f12e388a3fe24e2016aeb9` after CI run `34027827399` passed all required gates:

- Rust workspace: GREEN;
- Python suite: GREEN;
- repository safety: GREEN;
- native ARM64 release verification: GREEN.

The implementation preserves the lower-level raw fee normalizer, adds sidecar-proven current BUY fee recovery only in training-economics overlay v3, keeps mismatches unknown, and changes no FL4/PAPER/LIVE authority.

This follow-up commit exists only to create the repository-standard `seal:` main commit required by the automatic immutable ARM64 release workflow.
