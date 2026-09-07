# FL9 Migrated PumpSwap Market-Snapshot Coverage — Production Seal

**Date:** 2026-09-07  
**Behavior implementation merge:** `9927274491d418949f0603ea825668c3f2b912e0`  
**Tradable-universe design merge:** `656722192eb70ccfea3072c47f728ee8a8babef4`  
**Implementation PR:** #237  
**Design PR:** #236

## Production evidence that triggered this seal

The immutable fresh FL4 population completed at:

- 146,432 decisions;
- 1,757,184 FL4 labels;
- 12 horizons per decision;
- target values not inspected;
- model performance not inspected.

A decision-time venue audit then proved:

- 39,633 decisions were still on `pump_fun_bonding_curve`;
- 106,799 decisions were on `pump_swap`;
- the PumpSwap population covered 84 unique mints;
- all 106,799 PumpSwap decisions had verified Pump graduation evidence;
- all 106,799 had source-backed PumpSwap reserve evidence.

The first-champion BUY universe is therefore explicitly post-graduation PumpSwap only. Bonding-curve
rows remain immutable research evidence but are not BUY-learning authority.

## Frozen market-quality policy

`fl9-tradable-universe-v1` requires, from point-in-time evidence:

- venue exactly `pump_swap`;
- verified `pump_fun_bonding_curve -> pump_swap` graduation before the decision;
- canonical PumpSwap market snapshot from DexScreener;
- snapshot observed no later than the decision/evaluation time;
- maximum snapshot age 60,000 ms;
- liquidity at least $3,000 USD;
- trailing 24-hour volume at least $1,000 USD.

Missing, stale, ambiguous, or contradictory evidence fails closed to SKIP.

Historical champion eligibility must use only evidence available at the historical decision time.
Current market state cannot be used to backfill old training rows.

## Production coverage blocker

The canonical-pair tradable-universe audit over the 106,799 verified PumpSwap decisions produced:

- no fresh canonical DexScreener snapshot: 106,029;
- eligible decisions: 770;
- eligible unique mints: 3;
- top-1 eligible mint share: 99.610%.

The 770 surviving rows were not near the market-quality thresholds:

- minimum eligible liquidity: $18,254.97;
- minimum eligible trailing 24-hour volume: $247,241.04.

Therefore the blocker was contemporaneous market-snapshot coverage, not the $3,000/$1,000
market-quality thresholds.

The 146,432-decision historical fresh population remains valid immutable FL4 research evidence, but
it is not admitted as the first-champion population under v1.

## Linkage root cause

The production observer had two different target populations:

- bounded Pump/PumpSwap FastEvent capture follows verified Pump graduation pools;
- Observer V2 high-resolution DexScreener sampling followed its independent discovery registry.

A migrated PumpSwap market could therefore generate dense canonical FastEvents without ever entering
the market-snapshot sampler.

Read-only production linkage evidence over the 84 migrated mints proved:

- 84/84 had verified graduation;
- only 3/84 were in the Observer V2 registry;
- 81/84 were absent;
- only 8/84 had any historical DexScreener PumpSwap snapshot in the audited interval;
- 76/84 had none.

Verified Pump launch linkage could not bridge the gap:

- exactly one verified launch-linked candidate: 2 mints;
- no verified launch-linked candidate: 82 mints;
- ambiguous verified launch linkage: 0.

## Candidate identity proof

A final read-only identity audit proved:

- zero-candidate mints: 0;
- exactly-one-candidate mints: 61;
- multiple-candidate mints: 23;
- current registry candidate available: 3;
- exactly one snapshot-owning candidate: all 23 multi-candidate mints;
- multiple snapshot-owning candidates: 0;
- candidate creation required for the audited population: 0.

This allowed a deterministic outcome-neutral identity rule without creating duplicate candidates.

## Sealed sampler behavior

Observer V2 now synchronizes verified recent PumpSwap migrations before ordinary DexScreener
discovery.

For a verified migrated mint:

1. an already-active Observer V2 registry identity wins;
2. otherwise, when multiple candidate rows exist and exactly one owns persisted market snapshots,
   that snapshot-owning identity wins;
3. otherwise, when exactly one candidate row exists, it wins;
4. missing or unresolved multi-candidate identity fails closed.

The implementation does not create a new candidate identity.

Migration detection time becomes the sampler's tracking anchor. An already-tracked mint is
re-anchored to migration time so an old pre-migration discovery timestamp cannot prematurely expire
the post-graduation market path.

Ordinary DexScreener discovery may persist its own candidate evidence but cannot replace a mint
already active in the sampler registry.

The established Observer V2 24-hour research retention plus grace remains unchanged.

## Test/CI evidence

Initial PR head exposed one implementation bug in tests: signed `i64::saturating_sub` can saturate
below zero for synthetic clocks near the Unix epoch. The migration query lower bound was corrected
to clamp at zero. This was an implementation correction, not a policy change.

Corrected implementation head:

`b9975aa23bbcdacd3dc7e6267e63edf70eff7011`

PR CI run:

`34131424258`

All four gates GREEN:

- repository safety;
- Rust workspace;
- Python;
- native ARM64 release build.

Behavior merge:

`9927274491d418949f0603ea825668c3f2b912e0`

Merged-main CI run:

`34131710852`

All four gates GREEN.

Tradable-universe design merge:

`656722192eb70ccfea3072c47f728ee8a8babef4`

Combined-main CI run:

`34131995583`

All four gates GREEN.

## Authority boundary

No:

- FL4/raw/canonical evidence mutation;
- historical market-data backfill;
- target-value or future-return inspection;
- model-performance inspection;
- champion training;
- outcome-driven threshold tuning;
- bonding-curve BUY authority;
- risk/sizing change;
- signing/submission;
- LIVE enablement.

LIVE remains disabled.

## Production next gate

Build and deploy the exact immutable sealed release.

After deployment:

1. verify exact release identity and all core PAPER services;
2. establish a new first-champion cohort lower bound after the migration-sampler release is active;
3. collect new immutable FastEvent/FL4 evidence while Observer V2 simultaneously captures
   point-in-time DexScreener market snapshots for verified migrated PumpSwap mints;
4. run the v1 input-only tradable-universe audit on that new cohort;
5. require meaningful fresh-snapshot coverage under the 60-second rule;
6. require enough eligible unique mints and acceptable per-mint concentration;
7. if 60-second coverage is not operationally achievable, fail closed and change sampler cadence in
   a new versioned evidence slice rather than weakening the $3,000 liquidity or $1,000 24-hour
   volume standards;
8. implement/fingerprint the v1 tradable-universe gate in first-champion preselection before the
   60/20/20 partition;
9. only then perform first-champion training/validation/TEST/final fit.

The old 146,432-decision cohort stays immutable audit/research evidence and must not be retroactively
qualified with present-day market snapshots.

**LIVE TRADING: DISABLED**
