# FL9 Migration Sampler Candidate Bootstrap — Design

**Date:** 2026-09-07
**Base release:** `f0e03c8cd04fc43262e6babb9399763fa3f2a888`

## Production regression

The first deployment of the migration-driven Observer V2 market-snapshot bridge activated the exact
sealed release successfully, but `shreks-observe.service` then failed five consecutive restarts.

Journal root cause:

`verified PumpSwap migration mint '2QvCZ9JKxxqtcsAhmkuibuouvcTdwe54usW6vErDpump' has no existing candidate identity`.

A read-only 24h10m migration-sampler preflight found:

- 532 recent verified migrated mints;
- 55 already active in Observer V2 registry state;
- 471 resolvable by a sole candidate;
- 1 resolvable by a unique snapshot-owning candidate;
- 4 with zero existing candidate identities;
- 1 with two candidates and zero snapshot owners;
- zero contradictory migration quote/pool identities.

The one two-candidate/no-snapshot mint had exactly:

- one `solana_public` bonding-curve candidate;
- one `dexscreener` candidate;
- zero snapshots on either identity.

No target values, future returns, model performance, or champion training were inspected.

The previously proposed post-deployment champion cohort floor is rejected because the observer did
not remain healthy.

## Root cause

The first bridge treated `token_candidates` as a prerequisite for market sampling.

That assumption is false for verified migrations. Migration lifecycle truth can exist before
DexScreener discovery creates a candidate row. Requiring an existing candidate converts missing
reconstructible sampler metadata into a process-fatal condition and can stop the entire evidence
observer.

## Correct candidate resolution

Verified migration remains the authoritative trigger. Candidate identity is reconstructible
sampling metadata.

Resolution order:

1. if the mint is already active in Observer V2 registry state, preserve that active identity;
2. if exactly one candidate exists, reuse it;
3. if multiple candidates exist and exactly one owns historical market snapshots, reuse it;
4. if no snapshot owner exists and exactly one candidate has
   `discovery_source='dexscreener'`, reuse that DexScreener identity;
5. if no candidate exists, idempotently create the same canonical candidate ordinary DexScreener
   discovery would create:
   - exact mint;
   - empty pair identity;
   - `discovery_source='dexscreener'`;
   - venue `pump_swap`;
   - migration detection timestamp as discovery/sampling anchor;
6. if ambiguity remains (including multiple snapshot owners or multiple DexScreener identities),
   fail closed.

Candidate bootstrap uses the existing `upsert_candidate` uniqueness contract
`(mint, pair_address, discovery_source)`; it does not introduce a new identity namespace.

A newly bootstrapped candidate also receives the ordinary outcome-checkpoint rows that discovery
would create.

## Authority boundary

This fix changes reconstructible observer metadata only.

It does not:

- alter verified migration lifecycle truth;
- alter Pump/PumpSwap FastEvents;
- mutate FL4 labels;
- inspect future targets or model performance;
- loosen the FL9 tradable-universe thresholds;
- grant BUY authority;
- train or promote a champion;
- enable signing, submission, or LIVE trading.

The frozen tradable-universe policy remains:

- migrated PumpSwap only;
- fresh canonical DexScreener evidence <= 60s old;
- liquidity >= $3,000;
- trailing 24h volume >= $1,000;
- missing/stale evidence = SKIP.

A new champion cohort floor may be accepted only after a repaired sealed release is deployed and
`shreks-observe.service` remains healthy.
