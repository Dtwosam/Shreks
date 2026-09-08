# FL9 Authenticated Tradable-Universe Read — Design

**Date:** 2026-09-08  
**Base release:** `05a92931f01e87c517783a07dd77c4e98ffe0976`

## Status

Input-only evidence infrastructure before first genuine FL9 champion selection.

**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**

## Production evidence

The provider-specific DexScreener candidate resolver release was deployed and subsequently proved
runtime-stable:

- exact release identity: PASS;
- observer process active;
- PID stable;
- restart count zero;
- no post-deploy fatal journal lines;
- registry checkpoint advanced;
- DexScreener provider health remained healthy;
- post-floor DexScreener PumpSwap snapshot count increased during the progress probe;
- previously observed SQLite deferrals did not increase during the two-minute progress window.

A read-only immutable-session audit from provisional floor `1788858050000` then reported:

- 3 immutable sessions;
- 1,565 PumpSwap FastEvents;
- 12 unique PumpSwap mints;
- 100% of those events had verified migration evidence;
- 385 events had an apparent DexScreener snapshot within 60 seconds;
- 24.601% apparent <=60s coverage;
- 2 apparent fresh mints;
- 0 apparent market-quality-eligible events;
- all 385 apparent fresh events were classified below $3,000 liquidity;
- no fresh row failed the $1,000 trailing-24h volume threshold.

The same host had already persisted 796 post-floor DexScreener PumpSwap snapshots across 372 mints.

No database mutation, target-value inspection, future-return inspection, model-performance inspection,
or champion training occurred.

## Why the 0-eligible audit is not yet authoritative

The frozen FL9 design already requires market-quality eligibility to use the authenticated
point-in-time market read surface.

The diagnostic audit instead queried normalized market rows directly across candidate identities.

That is insufficient for final admission because the repository's sealed current-market semantics
are candidate-specific and deterministic:

1. resolve one candidate identity;
2. restrict evidence to the point-in-time boundary;
3. require the intended market source;
4. select the newest observation;
5. use stable row-id ordering as the tie break;
6. lock downstream evidence to that exact selected market path.

Additionally, the Python E13 market snapshot model currently omits three persisted fields required by
the frozen FL9 contract:

- `base_mint`;
- `quote_mint`;
- `volume_h24_usd`.

Therefore the direct-SQL audit remains useful as a capacity diagnostic, but it must not be used as
the final first-champion tradable-universe population.

In particular, its zero eligible rows do **not** justify lowering the independently frozen
`$3,000 liquidity / $1,000 volume_h24` thresholds.

## Additive authenticated market read

The existing E13 observer-market schema version remains unchanged because the Rust database already
persists the required columns; the Python adapter was omitting them.

`ObserverMarketSnapshot` is extended additively with:

- `base_mint`;
- `quote_mint`;
- `volume_h24_usd`.

Existing callers remain compatible; authenticated SQLite reads populate all three values.

### Point-in-time candidate resolution

A new read-only `resolve_candidate_at(...)` method mirrors the sealed production resolver while
bounding snapshot ownership at or before the supplied timestamp.

Resolution is:

1. sole candidate;
2. unique snapshot owner at/before the timestamp;
3. when multiple snapshot owners exist, a unique preferred-source candidate may win only when it
   itself owns point-in-time snapshots;
4. when no snapshot owners exist, a unique preferred-source candidate may be reused;
5. otherwise fail closed.

This prevents snapshot ownership created after a historical decision from changing the identity used
for that earlier decision.

### Exact current-market read

A new read-only `load_current_exact_market(...)` method selects one exact point-in-time market using:

- candidate id;
- source;
- venue;
- base mint;
- quote mint;
- caller-supplied maximum age;
- observation timestamp <= as-of;
- valid pair chronology;
- newest `observed_at_unix_ms`;
- lowest row id as the stable tie break.

A fresher wrong-quote or wrong-venue pair cannot rescue the requested market.

## FL9 v1 assessor

A dedicated read-only `Fl9TradableUniverseStore` implements
`fl9-tradable-universe-v1`.

The v1 constants are immutable in code:

- decision venue: `pump_swap`;
- lifecycle event: `pump_graduation`;
- lifecycle transition: `pump_fun_bonding_curve -> pump_swap`;
- market source: `dexscreener`;
- maximum snapshot age: 60,000 ms;
- minimum liquidity: $3,000;
- minimum trailing-24h volume: $1,000.

Changing any v1 constant raises an error. Threshold changes require a new policy version.

For each decision, the assessor:

1. rejects non-PumpSwap decisions;
2. requires exact mint/quote verified migration evidence detected by decision time;
3. rejects contradictory verified migration pool evidence;
4. resolves candidate identity using point-in-time snapshot ownership;
5. reads the exact DexScreener/PumpSwap mint/quote current snapshot within 60 seconds;
6. enforces source and pair chronology at the market-reader boundary;
7. requires liquidity and trailing-24h volume;
8. applies the frozen $3,000/$1,000 thresholds;
9. returns an explicit eligible/ineligible reason plus the exact evidence row ids and values.

The assessor opens SQLite read-only and has no network, target, model, execution, promotion, signing,
submission, or LIVE dependency.

## Leakage boundary

Historical assessment may use only evidence timestamped at or before the decision.

Candidate identity resolution is also bounded by the decision timestamp. Later snapshot ownership
cannot retroactively disambiguate an earlier decision.

Current market state cannot qualify historical rows.

## Regression proof required

Tests cover:

- additive base/quote/24h-volume market fields;
- point-in-time candidate resolution;
- future snapshot ownership not affecting past identity;
- genuine multi-preferred-source ambiguity remaining fail-closed;
- exact source/venue/mint/quote current-market selection;
- wrong quote/venue not rescuing exact-market eligibility;
- stale evidence failing closed;
- verified migration chronology;
- contradictory migration pools failing closed;
- missing liquidity/volume;
- exact $3,000/$1,000 thresholds;
- read-only behavior;
- no network/model/target/execution authority.

## First-champion boundary

This slice does **not** yet train or promote a champion.

The next evidence step after this read contract is sealed and deployed is to reproduce the
post-repair immutable-session audit through the authenticated assessor.

Only after that population is adequate may the exact eligible decision identities be fingerprinted
and applied before chronological 60/20/20 partitioning.

The provisional floor `1788858050000` remains unaccepted.

**Champion training: BLOCKED.**  
**LIVE TRADING: DISABLED.**
