# FL9 Tradable Universe Policy — Design

**Date:** 2026-09-07  
**Base:** `c28eb704073c53b22f299b9617f40608abaf6c34`

## Status

Design slice before first genuine FL9 champion training.

The fresh FL4 cohort is physically complete at:

- 146,432 decisions;
- 1,757,184 FL4 labels;
- fresh lower bound `1788687602234`;
- target values not inspected;
- model performance not inspected.

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

The raw fresh FL4 cohort intentionally includes every canonical decision opportunity in the
authenticated coverage windows. That population contains both Pump.fun bonding-curve decisions and
post-graduation PumpSwap decisions.

Raw evidence population is not the same thing as BUY eligibility.

The first-champion evidence planner currently preselects by chronology only. Without a separate
tradable-universe contract, bonding-curve decisions or inactive/illiquid PumpSwap markets can
participate in first-champion BUY learning even though those markets are not intended production
entry targets.

## Production BUY universe

A decision is BUY-eligible only when all conditions below are proven from point-in-time evidence:

1. the decision venue is exactly `pump_swap`;
2. a verified `pump_graduation` lifecycle event exists for the exact mint/quote market;
3. that lifecycle transition is exactly
   `pump_fun_bonding_curve -> pump_swap`;
4. the graduation was detected no later than the decision timestamp;
5. the liquidity/volume market snapshot is the fresh canonical PumpSwap pair for the exact mint/quote market under the established current-pair selection semantics;
6. snapshot source is exactly `dexscreener`;
7. snapshot observation is no later than the decision/evaluation timestamp;
8. snapshot age is at most **60,000 ms**;
9. snapshot pair chronology is valid;
10. `liquidity_usd >= 3000.0`;
11. `volume_h24_usd >= 1000.0`.

Missing, ambiguous, stale, or contradictory evidence is ineligible and must fail closed to SKIP.

No bonding-curve decision is BUY-eligible, regardless of activity, forecast, return, or later
graduation.


## Exact graduation-pool join audit correction

The first production audit using an exact equality join between
`token_lifecycle_events.pool_address` and `market_snapshots.pair_address` produced only 770
eligible decisions across 3 mints, with 104,782 PumpSwap decisions classified as
`missing_exact_pool_snapshot`.

That result does **not** prove those markets lacked liquidity/volume evidence.

Repository PR #69 (`fix: align Fresh Launch selection with canonical market pair`) already sealed
the market-selection rule: current tradability is based on the canonical fresh market pair selected
from point-in-time snapshots. A secondary/older pair must not override that current canonical pair,
but canonical market identity is not defined as equality with the lifecycle graduation pool address.

Therefore v1 requires:

- verified Pump graduation before the decision;
- current point-in-time canonical snapshot venue exactly `pump_swap`;
- exact mint/quote attribution;
- canonical pair chronology/freshness;
- liquidity/volume thresholds on that canonical pair.

The exact graduation pool address remains immutable lifecycle provenance but is **not** an equality
join requirement for market-quality eligibility.

## Historical versus runtime chronology

For champion training/validation/TEST/final fit, liquidity and trailing 24h volume are taken from the
latest eligible persisted market snapshot **at or before that historical decision timestamp**.

Current market state must never be used to decide whether a historical row enters training.

For PAPER/shadow/LIVE entry authority, the exact same policy is evaluated against the current
point-in-time snapshot.

Therefore:

- a token that is dead today may still remain valid historical evidence if it satisfied the policy
  when the decision occurred;
- a token that was historically active but is dead now must be rejected by current BUY authority;
- a token still on the bonding curve is always rejected.

## Evidence source

The existing normalized observer schema already persists:

- `market_snapshots.liquidity_usd`;
- `market_snapshots.volume_h24_usd`;
- snapshot source/venue/pair/base/quote identity;
- snapshot and pair-created timestamps;
- `token_lifecycle_events` with verified Pump graduation pool identity.

The current Python observer market read model does not expose `volume_h24_usd`; implementation must
extend the authenticated point-in-time read surface rather than add ad-hoc production SQL inside the
champion planner.

## First-champion preselection

Tradable-universe eligibility is applied **before** chronological 60/20/20 partitioning.

The exact same eligible identity population must feed:

- training;
- validation;
- TEST;
- final runtime-artifact fit.

The evidence plan fingerprints:

- policy version;
- minimum liquidity USD;
- minimum trailing-24h volume USD;
- required venue;
- required lifecycle transition;
- required snapshot source;
- maximum snapshot age;
- eligible decision identity population/fingerprint;
- explicit exclusion counts/reasons.

No target value or model-performance result may influence eligibility.

## Runtime authority

The learned action policy may only consider BUY when the current caller-supplied tradable-universe
assessment is eligible.

An attractive forecast cannot override an ineligible market.

Conceptually:

`model BUY + tradable-universe ineligible = SKIP`.

Open-position HOLD/REDUCE/SELL safety behavior remains separate; this policy controls new BUY
authority and does not forbid defensive exits from a market that later falls below the thresholds.

## Raw evidence preservation

The complete 146,432-decision FL4 population remains immutable research evidence.

Bonding-curve, low-liquidity, low-volume, stale, and missing-market-evidence rows are not deleted,
mutated, or relabeled. They are simply not admitted to first-champion BUY learning.

## Initial production policy

- version: `fl9-tradable-universe-v1`
- required venue: `pump_swap`
- required graduation: verified Pump.fun bonding curve -> PumpSwap
- required market source: `dexscreener`
- maximum market snapshot age: `60000 ms`
- minimum liquidity: `3000.0 USD`
- minimum trailing 24h volume: `1000.0 USD`

Threshold changes require a new policy version and a new evidence campaign. They are not
self-tuning parameters.


## Input-only activity/concentration audit

Before any target, future-return, or model-performance inspection, the completed fresh PumpSwap
population was audited using only 10-second point-in-time participation inputs.

Observed structural PumpSwap population:

- 106,799 decisions;
- 84 unique mints;
- top-1 mint share: 12.010%;
- top-3 mint share: 31.141%;
- top-5 mint share: 45.617%;
- top-10 mint share: 68.852%;
- maximum decisions contributed by one mint: 12,827.

Stricter short-window activity cuts did **not** solve concentration. They reduced mint diversity while
raising top-10 decision concentration:

- trades>=10, actors>=5, quote-flow>=1 SOL: 46 mints, top-10 share 71.848%;
- trades>=20, actors>=10, quote-flow>=5 SOL: 39 mints, top-10 share 76.533%;
- trades>=50, actors>=20, quote-flow>=25 SOL: 23 mints, top-10 share 78.797%.

Therefore `fl9-tradable-universe-v1` does **not** add an arbitrary 10-second trade/actor/flow
threshold. Market-quality eligibility remains the independently frozen migration/liquidity/24h-volume
contract.

After the v1 market-quality gate is audited, mint concentration must be measured again before model
training. If the final eligible population remains materially dominated by a small number of mints,
the solution must be an explicit versioned training-balance policy or additional fresh evidence—not
an outcome-driven activity filter and not silent row deletion.

## Pre-implementation production audit

Before champion training, run a read-only audit over the fresh 146,432 decisions using only the
fields above.

Required output:

- PumpSwap decision count;
- verified-graduation count;
- canonical fresh PumpSwap-pair snapshot coverage;
- fresh DexScreener snapshot coverage;
- missing/stale snapshot counts;
- liquidity-threshold exclusion count;
- 24h-volume-threshold exclusion count;
- final eligible decision count;
- final eligible unique-mint count;
- per-mint concentration summary.

The audit must report:

- database mutation = NO;
- target values inspected = no;
- future returns inspected = no;
- model performance inspected = no;
- champion training performed = no.

If the resulting population is too small or overly concentrated, collect more fresh PumpSwap
evidence. Do not relax thresholds after inspecting outcomes.


## Production canonical-pair audit result

The corrected canonical-pair production audit still produced:

- 146,432 raw fresh decisions;
- 39,633 bonding-curve decisions excluded;
- 106,799 verified migrated PumpSwap decisions;
- 106,029 PumpSwap decisions with no fresh canonical DexScreener snapshot within 60 seconds;
- 770 eligible decisions;
- 3 eligible mints;
- top-1 eligible mint share: 99.610%.

The surviving snapshots all greatly exceeded the frozen market-quality thresholds:

- minimum observed eligible liquidity: $18,254.97;
- minimum observed eligible trailing 24h volume: $247,241.04.

Therefore the limiting factor is **not** the $3,000 liquidity or $1,000 trailing-24h volume threshold.
It is contemporaneous market-snapshot coverage.

This population is insufficient for first-champion training under v1. It remains immutable raw FL4
research evidence only.


## Migration-to-sampler linkage audit

A read-only production linkage audit over the 84 fresh migrated PumpSwap mints proved:

- 84/84 have verified Pump graduation lifecycle evidence;
- only 2/84 have exactly one verified Pump launch-linked `candidate_id`;
- 82/84 have no verified Pump launch-linked candidate;
- 0/84 have ambiguous verified launch linkage;
- Observer V2 registry contains 304 total mints;
- only 3/84 fresh migrated mints are currently in that registry;
- 81/84 are absent;
- only 8/84 have any historical DexScreener PumpSwap snapshot in the fresh interval;
- 76/84 have none.

Therefore verified Pump launch linkage is not a valid prerequisite for migrated-market sampling.

The migration lifecycle event itself is the complete authoritative trigger for all 84 markets.

Before implementing migration-driven sampler registration, production must classify existing
`token_candidates` identities for those mints. The implementation must reuse an existing canonical
candidate identity when possible and must not blindly create a second candidate row that could
introduce duplicate-mint ambiguity into campaign selection.

## Capture-path root cause

Repository inspection shows the two evidence lanes are currently driven by different target
populations:

- broad Pump/PumpSwap FastEvent capture is driven by verified Pump migration pools through the
  bounded realtime target publisher;
- Observer V2 high-resolution DexScreener sampling is driven by its own discovery registry.

Observer V2 does not currently import verified PumpSwap migrations into that registry. Therefore a
migrated mint can generate dense canonical PumpSwap FastEvents without ever receiving contemporaneous
DexScreener liquidity/volume snapshots unless independent discovery happens to register it.

The next implementation slice must explicitly bridge verified Pump migrations into the
high-resolution market sampler without creating duplicate candidate identities.

After the bridged sampler is sealed and deployed, the first champion cohort lower bound must be
captured **after deployment**. Historical rows missing contemporaneous market evidence may not be
backfilled from present-day snapshots.

## Authority boundary

This policy adds no:

- provider/network call inside training;
- historical DB mutation;
- future-label/outcome input to eligibility;
- strategy edge threshold;
- model self-promotion;
- signer/submission;
- LIVE enablement.

LIVE remains disabled.
