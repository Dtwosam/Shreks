# FL9 Provider-Specific Sampler Identity Resolution — Seal

**Date:** 2026-09-07  
**Behavior merge:** `9a1e021ec3284546787481586dee7c7baefbf3ba`  
**Behavior main CI:** `34156764915`

## Production failure

The sealed active-PumpSwap priority scheduler release
`bec413b8716f3451d87ae220ca497addd73c454c` deployed successfully, but
`shreks-observe.service` later failed and exhausted systemd restart attempts.

The journal root cause was:

`migration sampling mint 'MukLDtJ8Cx9DxLbeyLRSWPSposTMWuwHANbuaudpump' is ambiguous across 2 candidate identities with 2 snapshot owners and 1 DexScreener candidates`.

A read-only reconstruction of the priority batch at failure found:

- priority candidate mints: 8;
- exactly one fatal priority mint:
  `MukLDtJ8Cx9DxLbeyLRSWPSposTMWuwHANbuaudpump`;
- candidate 60094:
  - source `helius`;
  - venue `pump_fun_bonding_curve`;
  - 2 market snapshots;
- candidate 60203:
  - source `dexscreener`;
  - 1,266 market snapshots;
- DexScreener provider health: healthy, failures=0;
- Meteora provider health: healthy, failures=0.

The observer failed because the shared market-sampler candidate resolver treated two snapshot-owning
identities as inherently ambiguous even when exactly one of them was the evidence-owning
DexScreener identity required by the priority lane.

No database mutation, target inspection, future-return inspection, model-performance inspection,
or champion training was used to select the fix.

No champion cohort floor from this failed release is accepted.

## Sealed resolution rule

The active Observer V2 registry remains authoritative before storage resolution is consulted.

For a mint not already represented by the active registry:

1. exactly one candidate -> reuse it;
2. exactly one snapshot-owning candidate -> reuse it;
3. if multiple snapshot owners exist:
   - exactly one candidate must have `discovery_source='dexscreener'`; and
   - that same DexScreener candidate must own at least one market snapshot;
   - then reuse that DexScreener candidate;
4. if no snapshot owners exist and exactly one DexScreener candidate exists -> reuse it;
5. otherwise fail closed.

This rule is intentionally narrower than "DexScreener always wins".

It still rejects:

- multiple snapshot owners when no DexScreener candidate exists;
- multiple DexScreener candidates;
- multiple DexScreener snapshot owners;
- any remaining unresolved identity ambiguity.

The rule changes only reconstructible sampler candidate selection. Existing candidate rows and
historical snapshots are not rewritten or deleted.

## Production case under the sealed rule

For `MukLDtJ8Cx9DxLbeyLRSWPSposTMWuwHANbuaudpump`:

- candidate identities = 2;
- snapshot owners = 2;
- DexScreener candidates = 1;
- DexScreener snapshot owners = 1.

The selected sampler identity is therefore deterministically candidate 60203, the existing
DexScreener identity with 1,266 historical market snapshots.

The competing Helius/bonding-curve identity remains persisted as audit provenance.

## Regression proof

Behavior PR #244 added explicit tests proving:

- sole candidate reuse remains unchanged;
- unique snapshot-owner reuse remains unchanged;
- a unique evidence-owning DexScreener candidate is selected among multiple snapshot owners;
- multiple non-Dex snapshot owners remain rejected;
- multiple DexScreener snapshot owners remain rejected;
- multiple ownerless DexScreener identities remain rejected.

PR CI completed successfully.

Merged-main CI run `34156764915` on
`9a1e021ec3284546787481586dee7c7baefbf3ba` completed:

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

## Freshness scheduler remains unchanged

The active-PumpSwap priority scheduler from the prior seal is preserved:

- PumpSwap activity lookback: 60 seconds;
- operational DexScreener freshness target: 45 seconds;
- maximum priority mints per bounded outer cycle: 32;
- ordinary broad A10 candidates per outer cycle: 1;
- broad DexScreener + Meteora research sampling remains enabled.

The 45-second target remains collection headroom beneath the FL9 eligibility ceiling, not a BUY
threshold.

## Tradable-universe contract remains unchanged

First-champion BUY eligibility remains:

- venue exactly `pump_swap`;
- verified Pump.fun bonding-curve -> PumpSwap migration known by decision time;
- canonical DexScreener PumpSwap snapshot at or before the decision;
- snapshot age <= 60,000 ms;
- liquidity >= $3,000;
- trailing 24h volume >= $1,000;
- missing/stale/ambiguous evidence = SKIP.

Bonding-curve decisions remain never BUY-eligible.

## Post-deploy evidence gate

No champion cohort floor is accepted yet.

After deployment of this seal, production must prove:

- exact release identity;
- observer remains active with stable PID/restart count;
- no provider-specific candidate-resolution fatal;
- registry checkpoint continues advancing;
- active PumpSwap decision-time DexScreener <=60s coverage materially improves;
- final market-quality eligible population has adequate mint diversity/concentration.

Only then may a new post-release champion cohort lower bound be accepted.

## Authority boundary

This seal adds no:

- FL4 label mutation;
- future-target/outcome input;
- model training;
- champion promotion;
- strategy threshold change;
- transaction construction;
- signing/submission;
- wallet authority;
- LIVE enablement.

**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
