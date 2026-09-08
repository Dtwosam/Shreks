# FL9 Priority Response Observability — Seal

**Date:** 2026-09-08  
**Behavior merge:** `ac33c0ca0d970248aacdf92e43cdfd287f73eff4`  
**Merged-main CI:** `34235655041`

## Status

Production evidence slice before accepting any first-champion FL9 cohort floor.

The currently deployed production release remains
`f2d88b7757e270868e67ed6919cf1e3ba9569cd0` until this observability seal is released and
deployed.

FL9 superiority remains **EVIDENCE PENDING**.  
LIVE remains disabled.

## Production evidence that forced this slice

The authenticated immutable FL9 replay at provisional floor `1788858050000` proved:

- exact release identity: PASS;
- 3 immutable realtime sessions;
- 1,565 PumpSwap decisions;
- 12 unique PumpSwap mints;
- 385 decisions with an authenticated exact DexScreener/PumpSwap snapshot within 60 seconds;
- 1,180 decisions without an authenticated fresh exact snapshot;
- 0 eligible FL9 decisions;
- cohort floor accepted: NO;
- champion training: BLOCKED;
- LIVE trading: DISABLED.

The authenticated coverage root-cause audit split the 1,180 exact-market misses into:

- 397 decisions with no prior exact snapshot;
- 783 decisions with only a stale prior exact snapshot.

Fresh authenticated evidence was highly concentrated:

- 385 fresh decisions;
- 2 fresh unique mints;
- 11 unique fresh snapshot rows.

The fresh rows were not market-quality eligible:

- liquidity range: $2,134.67 to $2,147.04;
- trailing-24h volume range: $0.00 to $0.44;
- fresh rows meeting liquidity >= $3,000: 0;
- fresh rows meeting volume_h24 >= $1,000: 0.

No target values, future returns, or model-performance evidence were inspected.

## Falsified hypotheses

### Priority/admission identity mismatch did not cause the misses

A read-only point-in-time comparison between the active priority selector and the authenticated FL9
exact-market read found:

- priority false-fresh total: 0;
- wrong-quote false-fresh: 0;
- wrong-candidate false-fresh: 0;
- wrong-candidate-and-quote false-fresh: 0.

The priority selector therefore was not suppressing these historical refreshes because of a broader
mint-only snapshot match.

### DexScreener-wide outage did not explain most misses

During the 1,180 exact-market misses, the latest global DexScreener snapshot was:

- <=5 seconds old for 477 decisions;
- 15-45 seconds old for 457 decisions;
- >60 seconds old for 246 decisions.

Therefore 934 / 1,180 misses occurred while DexScreener was still persisting other market snapshots
within 45 seconds.

For every exact miss, the affected mint itself had either:

- only a stale same-mint DexScreener snapshot; or
- no prior same-mint DexScreener snapshot.

No fresh same-mint non-exact pair was found.

### Top-32 priority starvation did not cause the misses

A point-in-time reconstruction of the active priority queue for all 1,180 exact misses found:

- target rank <=32: 1,180;
- target rank >32: 0;
- target rank minimum: 1;
- target rank median: 1;
- target rank p90: 3;
- target rank p95: 4;
- target rank p99: 5;
- target rank maximum: 6;
- priority queue depth minimum: 2;
- priority queue depth median: 4;
- priority queue depth maximum: 6.

The fixed 32-mint priority cap was therefore not binding for this audited population.

## Remaining evidence gap

The deployed sampler invokes the priority DexScreener provider through
`sample_candidate_from_provider(...)`.

Before this slice, three operational outcomes were not separately observable:

1. a provider response persisted one or more snapshots;
2. the provider returned `Ok(Vec::new())`;
3. the provider call failed.

The empty-response case was treated as provider-health success and persisted no market snapshot.
The cycle report exposed only priority candidate count, persisted snapshot count, and the aggregate
market-provider failure count.

Because the frozen production database stores successful market snapshots but does not persist
historical zero-row provider responses or priority-call failures, retrospective SQL cannot determine
whether a missing target snapshot came from:

- a successful DexScreener request that returned no base-mint pairs;
- a failed DexScreener request;
- or a sampler cycle that did not reach the target soon enough.

That is the root evidence gap addressed here.

## Sealed observability behavior

Observer V2 now exposes two additional cycle-report counters:

- `priority_empty_response_count`;
- `priority_provider_failure_count`.

For priority market calls only:

- `Ok(provider_snapshots)` with an empty vector increments
  `priority_empty_response_count`;
- provider errors increment `priority_provider_failure_count` in addition to the existing aggregate
  `market_provider_failure_count`;
- persisted priority snapshots continue incrementing
  `priority_persisted_snapshot_count`.

The sampler also emits structured journal diagnostics:

- `Observer V2 priority market response empty: provider=... mint=... candidate_id=...`
- `Observer V2 priority market request failed: provider=... mint=... candidate_id=... error_kind=...`

This slice intentionally does not change:

- active-priority selection;
- priority ordering;
- the 32-mint priority limit;
- provider request pacing;
- retry semantics;
- broad A10 sampling;
- provider-health semantics;
- market normalization;
- FL9 tradable-universe thresholds;
- model behavior;
- cohort admission;
- execution authority.

## TDD and regression evidence

PR #248 added regression coverage proving:

- an empty priority provider response is counted separately from a persisted-snapshot response;
- an empty priority response is not counted as a provider failure;
- a priority provider error is counted separately;
- the existing aggregate provider-failure counter is preserved;
- existing priority sampling behavior remains unchanged.

TDD RED evidence:

- commit: `c4a6a55259d149d4eb9497b0fd945c7110f623ae`;
- CI: `34234753924`;
- Rust compilation failed exactly because
  `priority_empty_response_count` and `priority_provider_failure_count` did not yet exist.

GREEN PR evidence:

- commit: `37bbdafa64f5c13e76ad5bb653dde59ea1bf4ccd`;
- CI: `34234973377`;
- new priority observability tests: PASS;
- Repository safety: PASS;
- Python tests: PASS;
- ARM64 release build: PASS;
- Rust tests: PASS after one unrelated transient SQLite BUSY test passed on rerun.

Merged-main evidence on behavior merge `ac33c0ca0d970248aacdf92e43cdfd287f73eff4`:

- CI: `34235655041`;
- Repository safety: PASS;
- Rust tests: PASS;
- Python tests: PASS;
- ARM64 release build: PASS.

## Post-deploy evidence gate

After a release containing this seal is deployed, the next production step is not model training.

Collect input-only evidence from active PumpSwap priority sampling and classify misses by:

1. persisted priority snapshot;
2. empty priority response;
3. priority provider failure;
4. no priority response diagnostic before the freshness deadline.

Interpretation:

- empty responses dominating -> investigate DexScreener PumpSwap pair availability / response shape;
- provider failures dominating -> investigate provider reliability, rate limiting, and request bounds;
- exact misses with neither empty nor failure diagnostics -> investigate sampler-cycle timing / blocking;
- successful priority snapshots but continued authenticated FL9 misses -> re-open exact market attribution
  with fresh physical evidence.

Only after the collector sustains decision-time exact-market coverage should a new immutable
post-repair population be replayed through `Fl9TradableUniverseStore`.

The frozen `60,000 ms / $3,000 liquidity / $1,000 volume_h24` FL9 v1 policy remains unchanged.
No outcome/model evidence may be used to relax those thresholds.

## Authority boundary

This seal adds no:

- database mutation for FL9 admission;
- FL4 label mutation;
- target/future-return inspection;
- model training;
- model selection or promotion;
- BUY authority;
- transaction construction;
- signing/submission;
- wallet authority;
- LIVE enablement.

**Cohort floor accepted: NO.**  
**Champion training: BLOCKED.**  
**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
