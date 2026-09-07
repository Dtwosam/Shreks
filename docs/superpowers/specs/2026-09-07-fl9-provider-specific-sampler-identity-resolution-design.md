# FL9 Provider-Specific Sampler Identity Resolution — Design

**Date:** 2026-09-07  
**Base release:** `bec413b8716f3451d87ae220ca497addd73c454c`

## Production regression

The sealed active-PumpSwap priority scheduler deployed successfully, but
`shreks-observe.service` later failed after six restart attempts.

The fatal storage error was:

`migration sampling mint 'MukLDtJ8Cx9DxLbeyLRSWPSposTMWuwHANbuaudpump' is ambiguous across 2 candidate identities with 2 snapshot owners and 1 DexScreener candidates`.

A read-only reconstruction of the active priority batch showed that exact mint was among the eight
priority candidates and had two normalized identities:

- candidate 60094:
  - discovery source `helius`;
  - venue `pump_fun_bonding_curve`;
  - 2 market snapshots;
- candidate 60203:
  - discovery source `dexscreener`;
  - 1,266 market snapshots.

Provider health at failure was healthy for both DexScreener and Meteora.

No database mutation, future-return inspection, target inspection, model-performance inspection, or
champion training was used to localize the failure.

The candidate cohort floor remains unaccepted.

## Root cause

The shared migration/market-sampler candidate resolver treats all market-snapshot ownership as
equivalent provenance.

That is too coarse for DexScreener-directed market sampling.

When multiple candidate identities own snapshots, a unique DexScreener identity can be operationally
unambiguous even though unrelated identities also own historical market snapshots.

The priority lane requests DexScreener market data. Failing the entire observer because a Helius or
other chain-discovery candidate also owns snapshots is therefore a false ambiguity.

## Narrow resolution rule

Preserve the existing deterministic resolution order with one additional provider-specific case.

1. If exactly one candidate exists, reuse it.
2. If exactly one snapshot-owning candidate exists, reuse it.
3. If multiple snapshot owners exist, and:
   - exactly one candidate has `discovery_source='dexscreener'`; and
   - that DexScreener candidate itself owns at least one market snapshot;
   then reuse that DexScreener candidate.
4. If no snapshot owners exist and exactly one DexScreener candidate exists, reuse it.
5. Otherwise fail closed.

This is deliberately narrower than a blanket "DexScreener always wins" policy.

It does not override a unique non-Dex snapshot owner when the DexScreener identity has no evidence,
and it still rejects:

- multiple snapshot owners with no DexScreener candidate;
- multiple DexScreener candidates;
- multiple DexScreener snapshot owners.

The active Observer V2 registry remains authoritative before this resolver is consulted.

## Why this is safe for the production failure

For `MukLDtJ8Cx9DxLbeyLRSWPSposTMWuwHANbuaudpump`:

- there is exactly one DexScreener candidate;
- it is itself a snapshot owner;
- it owns 1,266 snapshots;
- the competing identity is Helius/bonding-curve provenance.

The provider-specific market-sampler identity is therefore deterministic without using outcomes or
model evidence.

## Regression coverage

Tests must prove:

- sole candidate reuse remains unchanged;
- unique snapshot-owner reuse remains unchanged;
- unique DexScreener owner is selected when multiple candidates own snapshots;
- multiple non-Dex snapshot owners remain rejected;
- multiple DexScreener snapshot owners remain rejected;
- multiple ownerless DexScreener candidates remain rejected.

## Authority boundary

This change only resolves reconstructible sampler metadata.

It does not:

- alter lifecycle truth;
- alter FastEvents;
- mutate FL4 labels;
- inspect future targets or model performance;
- change the 60-second FL9 market-freshness ceiling;
- change the $3,000 liquidity threshold;
- change the $1,000 trailing-24h volume threshold;
- grant BUY authority;
- train or promote a champion;
- enable signing/submission;
- enable LIVE trading.

**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
