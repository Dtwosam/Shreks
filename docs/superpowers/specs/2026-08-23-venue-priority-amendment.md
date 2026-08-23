# Shreks Venue Priority Amendment

**Status:** Approved durable design amendment  
**Date:** 2026-08-23  
**Applies to:** Shreks Master Design and Phase A build order

## Why this amendment exists

Shreks is a Solana memecoin trader, so venue identity is not incidental metadata. Pump.fun/PumpSwap and Meteora represent important parts of the memecoin launch, graduation, liquidity, and trading lifecycle. Shreks must preserve those distinctions rather than flattening every market into a generic DEX pair.

This amendment does not replace the master design. It clarifies and extends the existing provider/discovery architecture without changing the Rust + Python split, free-source-only rule, paper-before-live rule, or Jupiter execution direction.

## First-class venues

Shreks V1 treats these as first-class venue/lifecycle identities:

- `PUMP_FUN_BONDING_CURVE`
- `PUMP_SWAP`
- `METEORA_DLMM`
- `METEORA_DAMM_V2`
- `OTHER_SOLANA`

Venue identity must survive normalization and be available to later feature, strategy, risk, execution, and research layers.

## Pump.fun

Pump.fun is treated primarily as a **launch/lifecycle source**, not as a website to scrape.

Shreks should eventually observe public Solana program/account activity to detect and classify:

- token creation,
- active bonding-curve state,
- buys/sells on the curve where derivable,
- reserve/liquidity progression,
- graduation readiness/state,
- actual graduation/migration.

The Pump web application must not become a required data dependency. Direct public Solana data is preferred so the system remains free, reproducible, and independent of undocumented frontend behavior.

No program ID should be hardcoded from memory or an unofficial source. Program/account identifiers must be verified before the A8 direct observer is enabled.

## PumpSwap

PumpSwap is treated as the canonical post-graduation venue for Pump-launched coins when that lifecycle applies.

Shreks should preserve signals such as:

- pool/canonical-pool identity,
- graduation timestamp,
- time since graduation,
- liquidity immediately before/after graduation,
- post-graduation volume acceleration,
- unique buyer/seller changes where derivable,
- liquidity additions/removals,
- executable depth/price impact,
- PumpSwap-specific fee/cost assumptions when relevant.

DEX Screener can enrich PumpSwap pair data when available, but broad discovery and lifecycle truth should ultimately come from direct Solana observation.

## Meteora

Meteora is both a first-class venue and an additional approved **free direct data provider**.

Initial official public data endpoints can cover at least:

- DLMM pool lists and individual pools,
- DAMM v2 pool lists and individual pools,
- pool creation time,
- TVL,
- 5m/30m/1h/2h/4h/12h/24h volume windows where exposed,
- current price,
- token identity/metadata fields,
- blacklist flags supplied by Meteora,
- fee information,
- launchpad tag where exposed,
- OHLCV/history where useful for later research.

Meteora responses remain provider inputs, not Shreks domain objects. They must be normalized through the provider boundary.

Meteora-provided blacklisting or token metadata is evidence, not unquestionable truth. The Shreks safety layer will corroborate critical safety decisions with direct chain data where practical.

## Provider versus venue

These concepts must remain separate.

**Provider** answers: "Where did Shreks obtain this observation?"

Examples:
- DEX Screener
- Helius
- Jupiter
- Meteora Data API
- direct Solana RPC

**Venue** answers: "Where is the token/pool/trade economically occurring?"

Examples:
- Pump.fun bonding curve
- PumpSwap
- Meteora DLMM
- Meteora DAMM v2

A DEX Screener observation may therefore have:

- provider = `DEX_SCREENER`
- venue = `PUMP_SWAP`

This distinction is mandatory for reproducible research.

## Venue-aware features

Later feature vectors should be able to include:

- venue,
- lifecycle stage,
- time since launch,
- time since graduation,
- venue-specific liquidity,
- venue-specific volume acceleration,
- cross-venue liquidity fragmentation,
- best executable venue/route,
- venue concentration,
- migration/graduation events.

Do not assume one venue is inherently bullish. Venue identity is a feature whose usefulness must be measured.

## Execution

Jupiter remains the default execution router when it provides a valid route under Shreks' risk controls.

The execution record should preserve route/venue labels so later evaluation can answer questions such as:

- Did PumpSwap fills outperform Meteora fills?
- Was slippage materially different by venue?
- Did post-graduation PumpSwap setups behave differently from Meteora launches?
- Did fragmented liquidity make exits worse than paper assumptions?

Direct venue-specific execution may be considered later only if evidence shows Jupiter routing is materially inadequate. It is not added prematurely.

## Build-order impact

Phase A provider/discovery work is amended as follows:

1. A3 provider-neutral contracts also add provider/venue separation.
2. A4 DEX Screener remains a generic enrichment adapter.
3. **A4b Meteora official public-data adapter** is added for DLMM/DAMM v2 liquidity/volume/pool observations.
4. A5 Helius/Solana chain data remains the chain-truth adapter.
5. A6 Jupiter remains read-only quote/build first, live execution later.
6. A8 continuous observer will add targeted direct Solana lifecycle watchers for Pump.fun/PumpSwap and eventually Meteora program events where useful.

## Free-source rule

This amendment does not permit any paid source.

- Meteora official public data endpoints are acceptable while available without paid access.
- Pump.fun/PumpSwap lifecycle observation should use public Solana data and existing approved free providers.
- If a venue requires a paid source for a noncritical feature, that feature is degraded/deferred rather than creating a paid dependency.
