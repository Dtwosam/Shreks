# FL9 Active PumpSwap Priority Sampling — Design

**Date:** 2026-09-07  
**Base:** `94c784352b26a82107af2b51f0cdae89f4895ef8`

## Status

Production evidence slice before accepting a new first-champion cohort floor.

FL9 superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Production evidence

The repaired migration-sampler candidate bootstrap release was deployed successfully and remained
process-stable:

- exact release identity: PASS;
- `shreks-observe.service`: active;
- observer PID unchanged across a 75-second probe;
- observer restart count: 0;
- post-deploy fatal journal lines: 0;
- migration candidate ambiguity after one complete cycle: 0 fatal mints.

The first complete repaired Observer V2 sampler cycle exposed a separate capacity problem:

- registry after the cycle: 784 mints;
- recent verified migrated mints: 524;
- first post-deploy registry flush occurred about 24.8 minutes after deployment;
- 597 post-floor mints had DexScreener PumpSwap snapshots;
- only 22 were fresh within 60 seconds;
- only 4 of those 22 met the independently frozen
  `liquidity >= $3,000 && volume_h24 >= $1,000` market-quality thresholds;
- 67 were fresh within 5 minutes, 34 of them meeting the market-quality thresholds;
- 152 were fresh within 10 minutes, 60 of them meeting the thresholds;
- latest-snapshot age distribution:
  - minimum: 188 ms;
  - median: 878,698 ms;
  - p90: 1,426,601 ms;
  - maximum: 1,487,861 ms.

No future returns, target values, or model-performance evidence were inspected.

The candidate-identity problem is therefore closed, but the current provider scheduler cannot support
the FL9 v1 60-second point-in-time market-freshness contract.

## Root cause

Observer V2 currently performs one unbounded due-candidate pass per cycle.

For every due candidate it calls all configured market providers serially.

Production provider budgets are:

- DexScreener market: 4 requests/second;
- Meteora market: 1 request/second.

The full broad registry therefore creates a long cycle. Migration synchronization, current
DexScreener discovery, and durable registry flush happen only at cycle boundaries.

A newly migrated mint can consequently appear in lifecycle/FastEvent evidence while the sampler is
still inside an older long cycle.

More importantly, FL9 decision-time market evidence is blocked behind unrelated broad research
sampling, including Meteora requests that are not required by the FL9 tradable-universe contract.

## Chosen architecture

Preserve the approved A10 broad research sampler and all-provider persistence, but make each outer
sampler cycle bounded.

Before ordinary broad work, add an operational priority pass driven only by recent canonical
PumpSwap FastEvent activity.

Priority selection uses only:

- venue = `pump_swap`;
- recent FastEvent timestamp;
- current DexScreener PumpSwap snapshot timestamp.

It consumes no strategy decision, target, future return, model output, profitability metric, or
liquidity/volume threshold.

### Priority policy

Initial operational constants:

- recent PumpSwap activity lookback: 60,000 ms;
- DexScreener priority freshness target: 45,000 ms;
- maximum priority mints per bounded cycle: 32;
- ordinary broad A10 candidates processed per bounded cycle: 1.

The 45-second priority target is scheduler headroom under the unchanged FL9 eligibility ceiling of
60,000 ms. It is not a replacement eligibility threshold.

A priority mint is selected when:

1. a canonical PumpSwap FastEvent exists inside the last 60 seconds;
2. no DexScreener PumpSwap snapshot for that mint exists at or after
   `as_of - 45,000 ms`.

Priority ordering is newest FastEvent first, then mint lexical order.

The priority pass calls only DexScreener because the FL9 market-quality contract requires
DexScreener liquidity and trailing-24h volume. Returned normalized snapshots continue through the
existing market-snapshot storage path.

The priority pass does not alter the broad A10 representative-path scheduler state. A priority mint
is excluded from the ordinary broad candidate slot in the same bounded cycle to avoid an immediate
duplicate call; it remains eligible for later broad DexScreener/Meteora research sampling.

## Broad A10 preservation

The ordinary A10 due-candidate queue remains deterministic and adaptive.

Instead of draining the whole due queue before the next migration sync/registry flush, each bounded
outer cycle processes at most one ordinary due candidate through all configured providers.

This preserves:

- candidate neutrality;
- 24h + 10m broad research retention;
- DexScreener and Meteora research evidence;
- A9 checkpoint finalization;
- deterministic due ordering;
- existing provider-health and backoff behavior.

It also ensures migration synchronization and registry durability occur continuously rather than
only after a many-minute backlog drains.

## Storage selector

A new bounded point-in-time storage selector returns active PumpSwap mints needing a fresh
DexScreener snapshot.

It reads the indexed recent FastEvent time interval and compares against persisted market snapshot
timestamps. It never writes, inspects labels, or looks beyond the supplied as-of timestamp.

## Exit evidence

After seal and deployment, do not accept the new champion cohort floor until production proves:

- observer process stability;
- no migration candidate-resolution fatal;
- registry checkpoint advancing continuously;
- post-floor active PumpSwap mints receive DexScreener snapshots;
- decision-time 60-second DexScreener coverage is materially improved;
- the final `$3k liquidity / $1k volume_h24` eligible population has adequate mint diversity.

If the 60-second contract still cannot be sustained for the active PumpSwap decision population,
the next change must be an explicit versioned operational-policy decision supported by input-only
capacity evidence. The liquidity/volume thresholds must not be weakened based on outcomes.

## Authority boundary

This slice adds no:

- FL4 mutation;
- future-label or outcome input;
- model training;
- model promotion;
- BUY authority;
- signer/submission;
- wallet authority;
- LIVE enablement.

**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
