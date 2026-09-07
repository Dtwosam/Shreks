# FL9 Migration Sampler Candidate Bootstrap — Seal

**Date:** 2026-09-07  
**Behavior merge:** `c5d8eb674d4fa58937b168efdd177f8dd0b902c7`  
**Behavior CI:** `34136531179`

## Production failure

The first sealed migration-driven sampler release
`f0e03c8cd04fc43262e6babb9399763fa3f2a888` deployed successfully, but
`shreks-observe.service` failed five restart attempts immediately after activation.

The journal failure was:

`verified PumpSwap migration mint '2QvCZ9JKxxqtcsAhmkuibuouvcTdwe54usW6vErDpump' has no existing candidate identity`.

A read-only production preflight over the sealed 24h10m migration retention window found:

- 650 verified migration lifecycle rows;
- 532 unique migrated mints;
- 55 active-registry identities;
- 471 sole-candidate identities;
- 1 unique snapshot-owner identity;
- 4 zero-candidate mints;
- 1 two-candidate mint with zero snapshot owners;
- 5 fatal mints total;
- zero contradictory migration quote/pool identities.

The exact fatal population was:

- `2QvCZ9JKxxqtcsAhmkuibuouvcTdwe54usW6vErDpump`: no candidate;
- `7ztCuHnPgoSw8J5LcutXNMjBSZCAMTi9g7hKGsbhpump`: no candidate;
- `MdrfW5U68jMBhoWjR1KsMMHxHe5qvDccD3fUTcRpump`: no candidate;
- `ym3tr6ghm1h2n5N514FEP5uqDFpF1VB8oBCzVtJpump`: no candidate;
- `7FixfVqcsm1p7yUPhMyB379JAgdBfA5Sj9BrzcsSpump`: two candidates, zero snapshot owners.

For the ambiguous mint, the two candidates were exactly:

- one `solana_public` Pump.fun bonding-curve candidate;
- one `dexscreener` candidate;
- neither owned a market snapshot.

No database mutation, future-return inspection, target inspection, model-performance inspection, or
champion training occurred during localization.

The previously proposed post-deployment champion cohort floor is rejected because the observer did
not remain healthy.

## Sealed fix

Verified migration remains authoritative lifecycle truth. Candidate identity is reconstructible
observer metadata.

Migration-driven market-sampler candidate resolution is:

1. active Observer V2 registry identity wins;
2. otherwise, a sole existing candidate is reused;
3. otherwise, a unique snapshot-owning candidate is reused;
4. otherwise, if there are zero snapshot owners and exactly one
   `discovery_source='dexscreener'` candidate, that DexScreener identity is reused;
5. otherwise, if no candidate exists, Observer V2 idempotently bootstraps the canonical ordinary
   DexScreener discovery identity:
   - exact migration mint;
   - empty pair identity;
   - source `dexscreener`;
   - venue `pump_swap`;
   - migration detection timestamp as discovery/sampling anchor;
6. remaining ambiguity still fails closed.

Bootstrapping uses the pre-existing uniqueness contract
`UNIQUE(mint, pair_address, discovery_source)`.
It therefore does not create a new candidate namespace and is restart-idempotent.

A bootstrapped candidate also receives the ordinary outcome-checkpoint rows created by public
discovery.

## Regression proof

Behavior PR #240 added focused regression coverage proving:

- a verified migration with zero candidates bootstraps one canonical DexScreener/PumpSwap candidate
  and is sampled;
- the bootstrapped identity is registered and owns ordinary outcome checkpoints;
- the production-shaped two-candidate/no-snapshot case reuses the unique DexScreener identity;
- a multi-candidate mint with multiple DexScreener identities and no snapshot owner remains rejected;
- multiple snapshot owners remain rejected;
- sole-candidate and unique-snapshot-owner behavior remains unchanged.

Behavior PR CI completed 4/4 GREEN.

Merged-main CI run `34136531179` on
`c5d8eb674d4fa58937b168efdd177f8dd0b902c7` completed:

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

## Evidence and champion boundary

The frozen FL9 tradable universe remains unchanged:

- PumpSwap only;
- verified Pump.fun -> PumpSwap migration;
- canonical fresh DexScreener snapshot no more than 60 seconds old;
- liquidity >= $3,000;
- trailing 24h volume >= $1,000;
- missing/stale evidence = SKIP.

The old 146,432-decision FL4 cohort remains immutable research evidence only for first-champion
purposes.

No champion cohort floor is accepted from the failed
`f0e03c8cd04fc43262e6babb9399763fa3f2a888` deployment.

After this sealed fix is deployed, a new lower bound may be established only after:

- exact release identity passes;
- `shreks-observe.service` remains active;
- recent verified migrations no longer contain sampler-fatal candidate identities;
- migrated PumpSwap DexScreener snapshots are being persisted.

## Authority boundary

This seal adds no:

- FL4 label mutation;
- future-target or model-performance input;
- strategy threshold change;
- champion training or promotion;
- BUY authority;
- signing/submission;
- wallet authority;
- LIVE enablement.

**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
