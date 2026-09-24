# G1C V2 1m Anchor Sampling Density Seal

**Date:** 2026-09-24  
**Integration SHA:** `9311811c66b1d4f1ec9cffc883f2c5d3d982a7aa`  
**PR:** #485  
**Merged-main CI:** `36040350360`

## Proven production defect

Post-bootstrap physical PAPER evidence established that the versioned B2
one-minute anchor contract was frequently unpopulated despite healthy exact-WSOL
market sampling.

Observed after deployment of the discovery-bootstrap fix:

- 67 selected candidate evaluations were mature enough for a 1m anchor;
- 17 had a legal 1m anchor;
- 50 lacked a legal 1m anchor;
- all 50 misses were proven cadence straddles;
- 1m anchor coverage was 25.37%;
- 5m anchor coverage was 51/51 (100%);
- 15m anchor coverage was 17/17 (100%).

The physical exact-pair follow-up cadence was approximately 45..48 seconds. With
the B2 one-minute band fixed at 60,000..90,000 ms, a healthy cadence near 46
seconds can place one row younger than 60 seconds and the prior row older than 90
seconds, producing `return_1m_pct=None` without any provider failure or general
history gap.

## Capacity evidence

Physical post-deploy census:

- average simultaneous fresh exact-WSOL population: 7.43;
- p95 population: 9;
- maximum population: 10;
- configured DexScreener market pacing: 4 requests/second.

At the observed population maximum:

- 45s fresh target: 0.222 RPS;
- 30s fresh target: 0.333 RPS;
- 25s fresh target: 0.400 RPS;
- 20s fresh target: 0.500 RPS.

The conservative combined envelope, including the full active-PumpSwap upper
bound and the one-per-cycle broad lane, was 2.111 RPS for the selected 25-second
target, below the configured 4 RPS limit.

A separate one-second census of the active-PumpSwap priority selector observed:

- average due count: 0;
- p95 due count: 0;
- p99 due count: 0;
- maximum due count: 0.

With one second of runtime-loop allowance:

- 30s target implies approximately 31s effective upper gap and lacks margin for
  the 30-second-wide one-minute anchor band;
- 25s target implies approximately 26s effective upper gap;
- 20s target implies approximately 21s but is more aggressive than required by
  current evidence.

## Sealed behavior

Change exactly:

```
FRESH_PAIR_FRESHNESS_TARGET_MS: 45_000 -> 25_000
```

The active-PumpSwap priority freshness target remains 45,000 ms.

The fresh-pair selector semantics, recent-pair 30-minute lookback, priority limit,
provider pacing, persistence, discovery bootstrap behavior, broad-sampler bound,
and market identity rules remain unchanged.

## RED / GREEN evidence

RED head: `bc62fec3893287f0ee7e1d8178c047ca4ffe7244`

CI run `36039468187`:

- Rust tests: FAIL
- ARM64 release build: PASS
- Repository safety: PASS

The new regression
`fresh_pair_priority_refreshes_immediately_after_25_second_boundary` failed
against the prior 45-second runtime, proving the old sampler did not refresh once
a recent pair crossed the new 25-second boundary.

GREEN head: `887f1691f471a3aaca21b66315458af773f087e2`

CI run `36039529036`:

- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS
- Repository safety: PASS

Canonical non-draft PR-attached CI run `36040058751`:

- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS
- Repository safety: PASS

Merged integration SHA: `9311811c66b1d4f1ec9cffc883f2c5d3d982a7aa`

Merged-main CI run `36040350360`:

- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS
- Repository safety: PASS

## Physical acceptance required

After immutable release and production deployment:

- deployed release SHA must equal this seal commit;
- protected campaign manifest SHA must remain
  `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`;
- observer, PAPER evidence, and PAPER campaign services must remain healthy;
- exact fresh-WSOL follow-up cadence should materially tighten from the prior
  45..48 second baseline;
- repeat the actual PAPER checkpoint anchor-coverage audit;
- one-minute anchor coverage must materially improve from the 25.37% pre-fix
  baseline;
- cadence-straddle misses must materially decline;
- 5m and 15m anchor coverage must remain healthy;
- provider failures must not materially increase.

Physical acceptance is not complete until VPS evidence is collected.

## Explicit non-authority

```
FRESH_PAIR_FRESHNESS_TARGET=25_SECONDS
ACTIVE_PUMPSWAP_FRESHNESS_TARGET=45_SECONDS_UNCHANGED
FEATURE_SCHEMA_VERSION=B2_V1_UNCHANGED
ANCHOR_1M_BAND=60000_90000_UNCHANGED
ANCHOR_5M_BAND=300000_360000_UNCHANGED
ANCHOR_15M_BAND=900000_1020000_UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
PAPER_EVIDENCE_QUOTE_AUTHORITY=AUTHENTICATED_CAMPAIGN_MANIFEST
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

No change to feature-schema semantics, strategy thresholds, scoring, model fitting,
promotion authority, signing, wallet behavior, or LIVE operation is authorized by
this seal.
