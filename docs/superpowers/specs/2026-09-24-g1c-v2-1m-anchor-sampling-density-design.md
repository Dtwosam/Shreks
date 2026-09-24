# G1C V2 1m Anchor Sampling Density Design

**Date:** 2026-09-24  
**Branch:** `fix/g1c-v2-1m-anchor-sampling-density`  
**Base:** `403c99a488d193b59db8e360937123f73a561e07`

## Problem

Post-bootstrap physical PAPER evidence proved that exact-WSOL market history is now
being collected reliably, but the sealed 45-second fresh-pair freshness target is
too sparse for the versioned B2 one-minute anchor band.

The production B2 feature contract remains:

- 1m anchor: 60,000..90,000 ms old;
- 5m anchor: 300,000..360,000 ms old;
- 15m anchor: 900,000..1,020,000 ms old.

Physical audit after the discovery-bootstrap fix observed:

- 67 selected candidate evaluations mature enough for a 1m anchor;
- 17 had a 1m anchor;
- 50 lacked a 1m anchor;
- all 50 misses were proven cadence straddles, with exact-pair observations on
  both sides of the legal 60..90 second band;
- 1m anchor coverage was 25.37%;
- 5m anchor coverage was 51/51 (100%);
- 15m anchor coverage was 17/17 (100%).

The same physical run showed fresh exact-pair follow-up cadence around 45..48
seconds. This is sufficient for the wider 5m and 15m bands, but can naturally
jump from a row younger than 60 seconds to the prior row older than 90 seconds.

This missingness suppresses the sealed Fresh Launch `return_1m_pct`
confirmation even when market sampling is otherwise healthy.

## Capacity evidence

A read-only post-deploy census observed:

- average simultaneous fresh exact-WSOL population: 7.43;
- p95 population: 9;
- maximum population: 10;
- configured DexScreener market pacing: 4 requests/second.

Theoretical fresh-lane demand at the observed peak population:

- 45s target: 0.222 RPS;
- 30s target: 0.333 RPS;
- 25s target: 0.400 RPS;
- 20s target: 0.500 RPS.

A conservative combined envelope including:

- observed fresh-pair peak population;
- the full 32-mint active-PumpSwap lane at its existing 45s target;
- the existing one-per-cycle broad lane;

remained below the configured 4 RPS limit for 30s, 25s, and 20s targets.

A separate one-second physical census of the active-PumpSwap selector observed:

- average due count: 0;
- p95: 0;
- p99: 0;
- maximum: 0.

With one second of runtime-loop allowance, the resulting observed envelope is:

- 30s target -> approximately 31s upper gap, too large for a 30s-wide anchor band;
- 25s target -> approximately 26s upper gap;
- 20s target -> approximately 21s upper gap.

## Chosen change

Change only:

`FRESH_PAIR_FRESHNESS_TARGET_MS: 45_000 -> 25_000`

The active-PumpSwap priority freshness target remains 45,000 ms.

25 seconds is chosen because it is the least aggressive observed-capacity-safe
target that leaves meaningful scheduling margin inside the 30-second-wide B2 1m
anchor band. 30 seconds has insufficient margin; 20 seconds is unnecessary based
on current evidence.

## Invariants

This slice does **not** change:

- `FEATURE_SCHEMA_VERSION = "b2-v1"`;
- B2 anchor timing bands;
- `return_1m_pct` semantics;
- any Fresh Launch confirmation threshold;
- liquidity threshold;
- safety policy;
- quote identity or WSOL authority;
- entry sizing;
- Jupiter execution semantics;
- scoring;
- model fitting;
- PAPER promotion;
- protected campaign manifest bytes;
- LIVE state.

The provider pacing implementation and configured 4-RPS DexScreener market
budget are unchanged.

## Tests

Add an observer-level regression that proves a freshly persisted recent pair:

1. is not refreshed while its newest DexScreener observation is exactly 25,000
   ms old;
2. becomes due immediately after the 25,000 ms freshness boundary;
3. uses the existing fresh-pair priority path;
4. does not invoke the broad sampler for that priority refresh.

Existing fresh-pair priority, discovery-bootstrap, broad-bounding, storage,
Python, repository-safety, and ARM64 release tests must remain green.

## Physical acceptance

After immutable seal/release/deploy:

- deployed release SHA equals the seal;
- protected V2 manifest SHA remains unchanged;
- observer/PAPER services remain healthy;
- fresh exact-WSOL follow-up cadence reflects the denser target without provider
  failure growth;
- repeat the exact PAPER checkpoint anchor audit;
- 1m anchor coverage materially improves from the pre-fix 25.37% baseline;
- cadence-straddle misses materially decline;
- 5m/15m coverage remains healthy;
- no feature-schema or trading-threshold change occurs.

No PAPER promotion or LIVE authority is implied by successful acceptance.
