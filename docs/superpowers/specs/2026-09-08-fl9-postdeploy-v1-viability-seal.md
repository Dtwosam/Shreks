# FL9 Post-Deploy V1 Viability — Production Evidence Seal

**Date:** 2026-09-08  
**Base release:** `5b1b8b8df66f8fbea26b84fdf2e92f36f06db292`  
**Policy:** `fl9-tradable-universe-v1`  
**Policy fingerprint:** `abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4`

## Status

Input-only production evidence checkpoint after deploying FL9 priority-response observability.

This seal does **not** accept a first-champion cohort.

- cohort floor accepted: **NO**
- eligible identity fingerprint created: **NO**
- chronological 60/20/20 split: **BLOCKED**
- champion training: **BLOCKED**
- FL9 superiority: **EVIDENCE PENDING**
- LIVE trading: **DISABLED**

No target values, future returns, model-performance evidence, or training outputs were inspected.

## Physical release evidence

The VPS physically reported:

- current release: `/opt/shreks/releases/5b1b8b8df66f8fbea26b84fdf2e92f36f06db292`
- current SHA: `5b1b8b8df66f8fbea26b84fdf2e92f36f06db292`
- expected SHA: exact match
- release identity: PASS
- `shreks-observe.service`: active
- `shreks-paper-evidence.service`: active
- `shreks-paper-campaign.service`: active
- `shreks.target`: active
- observer PID: 372277
- observer restarts: 0
- observer main status: 0
- observer active-enter timestamp: 2026-09-08 14:38:41 UTC
- post-deploy lower bound: `1788878321000`

## Priority-response root cause

Post-deploy priority-response observability showed:

- successful empty priority responses: 195 lines across 7 unique mints in the first audit;
- priority provider failures: 0;
- no provider failure kinds;
- exact fresh decisions: 6,270 / 10,248;
- missing fresh exact decisions: 3,978;
- candidate identity unavailable: 0;
- exact fresh unique mints: 8;
- fresh exact snapshot age p50: 10,376 ms;
- p95: 22,855 ms;
- maximum: 48,081 ms.

Once an exact snapshot existed, the sampler was comfortably within the frozen 60-second freshness contract.

### Raw DexScreener response audit

A later raw-response audit over the then-current empty-response mint set found 4/4:

- HTTP 200;
- raw JSON array length 0;
- no Solana pair rows;
- no base-mint pair rows;
- no quote-side pair rows;
- no PumpSwap pair rows;
- no verified-pool rows;
- verified Pump.fun -> PumpSwap lifecycle/pool evidence present locally.

Classification totals:

- `TRUE_UPSTREAM_EMPTY=4`
- all Shreks base/quote filtering classifications: 0
- HTTP errors: 0
- transport errors: 0
- invalid JSON: 0

Therefore the empty-response condition is genuine DexScreener pair unavailability at request time, not a Shreks base/quote parser bug.

## DexScreener indexing-lag evidence

The post-deploy verified-migration population contained:

- 6 verified PumpSwap migrations;
- 5 later indexed by the exact DexScreener PumpSwap pool;
- 1 not indexed in the audited interval.

For the 5 indexed pools, migration-detection -> first exact DexScreener snapshot lag was:

- <=15s: 0
- 15–30s: 0
- 30–60s: 0
- 60–120s: 2
- 2–5m: 3
- >5m: 0

Lag distribution:

- minimum: 79,545 ms
- p50: 144,878 ms
- p90/p95/p99/max: 236,405 ms

All 5 active indexed mints produced PumpSwap decisions before DexScreener exposed the exact pool.

However, the first observed PumpSwap decision occurred only shortly before first DexScreener indexing:

- 5,849 ms
- 6,125 ms
- 7,690 ms
- 8,233 ms
- 9,607 ms

Thus the direct production evidence supports a narrow conclusion:

> `fl9-tradable-universe-v1` is not able to authenticate the first roughly 6–10 seconds of captured PumpSwap decision activity for these newly indexed markets, because DexScreener had not exposed the pair yet.

This does not justify changing the frozen v1 snapshot source or 60-second freshness limit.

The repository build order already states that DexScreener polling is not sufficient for 1–10 second Fast Lane trading. That architectural limitation remains separate from the v1 first-champion admission policy.

## Post-deploy v1 viability

A read-only `Fl9TradableUniverseStore` assessment over all provisional post-deploy PumpSwap decisions reported:

- assessed PumpSwap decisions: 15,831
- eligible decisions: 5,718
- eligible unique mints: 4
- missing fresh exact market snapshot: 7,461
- below minimum liquidity: 2,106
- below minimum trailing-24h volume: 546
- missing verified migration: 0
- contradictory migration: 0
- candidate identity unavailable: 0
- missing liquidity: 0
- missing volume: 0

Eligible snapshot freshness:

- minimum age: 247 ms
- p50: 10,871 ms
- p90: 21,805 ms
- p95: 22,855 ms
- p99: 24,194 ms
- maximum: 32,710 ms

Eligible market quality:

- minimum liquidity: $9,090.00
- median liquidity: $110,223.63
- maximum liquidity: $1,045,080.04
- minimum trailing-24h volume: $4,409.09
- median trailing-24h volume: $46,428.14
- maximum trailing-24h volume: $514,606.04

The surviving rows therefore exceed the frozen `$3,000 / $1,000` market-quality thresholds by meaningful margins. Market-quality thresholds are not the dominant blocker in this provisional population.

## Concentration blocker

Eligible decisions were distributed:

- `mqKcfLa9NvF2Qsw4UdqjnLu1QebenJX4uxiASL6pump`: 5,072
- `8CjwoD9z664yQR12ZYSSYPV98UQ8ijrHe1MD5eeupump`: 404
- `76cJTCcyZ6zVXUM4TkAWoCJ953MDnEzs3mpaAkbypump`: 214
- `EuYX7zYuLTMNSF2o1Kj6Vzd8qbevGWoLVBV9VhWVpump`: 28

Top-1 eligible mint share:

`5072 / 5718 = 88.7023%`

The canonical FL9 tradable-universe design explicitly requires concentration to be re-audited after the market-quality gate. If the final eligible population remains materially dominated by a small number of mints, the permitted remedies are:

1. collect additional fresh evidence; or
2. design an explicit versioned training-balance policy.

It explicitly rejects:

- outcome-driven activity filters;
- silent row deletion;
- post-hoc threshold relaxation.

An 88.7% top-mint share across only 4 eligible mints is materially concentrated relative to the broader pre-market-gate PumpSwap population and is not accepted here for first-champion training.

No arbitrary new numeric concentration threshold is introduced by this seal.

## Immutability blocker

At audit time:

- latest coverage session: 115
- post-deploy session 114: immutable, but ends essentially at the deployment boundary
- post-deploy session 115: current/mutable

The useful 15,831-decision provisional population therefore cannot yet become the immutable first-champion population.

A current coverage session cannot be fingerprinted as final champion evidence because its coverage boundary may still extend.

## Decision

The post-deploy collector repair is operationally meaningful:

- priority requests reach active PumpSwap mints;
- provider failures are not the dominant problem;
- exact snapshots, once available, are sampled within the frozen 60-second contract;
- v1 now yields thousands of genuinely eligible rows;
- eligible market-quality values exceed the frozen thresholds.

But first-champion training remains blocked because:

1. the useful population is still in a mutable coverage session; and
2. the eligible population is materially mint-concentrated.

The next evidence action is **additional fresh collection under the unchanged v1 policy**, followed by an immutable-session input-only viability/concentration audit.

Only after a final immutable eligible population is accepted may Shreks:

1. freeze exact eligible decision identities;
2. create the eligible-population fingerprint;
3. perform chronological 60/20/20 partitioning;
4. train the first genuine FL9 champion;
5. inspect validation/TEST/model evidence.

## Authority boundary

This seal adds no:

- database mutation;
- historical backfill;
- target/future-return inspection;
- model-performance inspection;
- training;
- model selection/promotion;
- BUY authority;
- risk/sizing change;
- transaction construction;
- signing/submission;
- LIVE enablement.

**Cohort floor accepted: NO.**  
**Champion training: BLOCKED.**  
**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
