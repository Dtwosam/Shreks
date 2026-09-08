# FL9 Authenticated Tradable-Universe Read — Seal

**Date:** 2026-09-08  
**Behavior merge:** `67252d209482524aff2aa7b651dc55a68cdeb100`  
**Merged-main CI:** `34216777904`

## Production evidence before this seal

The provider-specific DexScreener candidate resolver release
`05a92931f01e87c517783a07dd77c4e98ffe0976` was deployed and proved runtime-stable:

- exact release identity PASS;
- `shreks-observe.service` active;
- observer PID stable;
- restart count zero;
- no post-deploy fatal lines;
- registry checkpoint advancing;
- DexScreener healthy with zero consecutive failures;
- post-floor DexScreener PumpSwap snapshots increasing;
- previously observed SQLite writer-contention deferrals did not increase during the measured
  progress probe.

A read-only immutable-session diagnostic from provisional floor `1788858050000` reported:

- 3 immutable sessions;
- 1,565 PumpSwap FastEvents;
- 12 unique PumpSwap mints;
- 100% verified migration coverage;
- 385 events with an apparent <=60s DexScreener snapshot;
- apparent <=60s coverage of 24.601%;
- 2 apparent fresh mints;
- 0 apparent market-quality-eligible events;
- all 385 apparent fresh events classified below $3,000 liquidity;
- no apparent fresh event failed the $1,000 trailing-24h volume threshold;
- 796 post-floor DexScreener PumpSwap snapshots persisted across 372 mints.

No database mutation, future-return inspection, target-value inspection, model-performance inspection,
or champion training occurred.

## Why the direct-SQL zero-eligible result is not admission authority

The frozen `fl9-tradable-universe-v1` design requires historical market-quality admission through
the authenticated point-in-time market read surface.

The diagnostic SQL aggregated market rows across candidate identities directly. That is useful for
capacity diagnosis, but it does not reproduce the sealed candidate-specific current-market semantics.

Therefore:

- the diagnostic `eligible=0` result is not final first-champion admission evidence;
- it does not justify reducing the $3,000 liquidity threshold;
- it does not justify reducing the $1,000 trailing-24h volume threshold;
- it does not justify increasing the 60,000 ms freshness ceiling.

## Sealed authenticated market read

The existing E13 market read surface is extended additively without changing legacy read semantics.

Authenticated snapshots now expose the persisted FL9-required fields:

- exact `base_mint`;
- exact `quote_mint`;
- `volume_h24_usd`.

Legacy E13 databases/callers remain supported for general reads. The additive FL9 columns are
required only when the exact-market FL9 method is invoked.

### Historical candidate identity

`ObserverMarketStore.resolve_candidate_at(...)` resolves one candidate identity using only evidence
known at or before the caller's `as_of_unix_ms`.

Candidate rows discovered after the as-of boundary are invisible.

Resolution is deterministic:

1. sole candidate identity available by as-of;
2. unique point-in-time snapshot owner;
3. if multiple point-in-time snapshot owners exist, a unique preferred-source candidate may win
   only when it itself owns point-in-time snapshots;
4. if no point-in-time snapshot owners exist, a unique preferred-source candidate may be reused;
5. remaining ambiguity fails closed.

This prevents future candidate discovery or future snapshot ownership from retroactively changing a
historical decision's market identity.

### Exact current-market read

`ObserverMarketStore.load_current_exact_market(...)` requires:

- candidate id;
- source;
- venue;
- exact base mint;
- exact quote mint;
- maximum snapshot age;
- observation timestamp at or before as-of;
- valid pair chronology.

Selection is:

1. newest `observed_at_unix_ms`;
2. lowest row id as stable tie break.

A newer wrong-quote or wrong-venue pair cannot rescue the requested market.

## Sealed FL9 v1 assessor

`Fl9TradableUniverseStore` is the authenticated, read-only implementation of
`fl9-tradable-universe-v1`.

The v1 constants are immutable in code:

- decision venue: `pump_swap`;
- lifecycle transition: `pump_fun_bonding_curve -> pump_swap`;
- lifecycle event: `pump_graduation`;
- migration signal status: verified;
- required market source: `dexscreener`;
- maximum snapshot age: 60,000 ms;
- minimum liquidity: $3,000;
- minimum trailing-24h volume: $1,000.

Changing those values under v1 is rejected. A threshold change requires a new policy version.

For each decision the assessor:

1. rejects non-PumpSwap decisions;
2. requires exact mint/quote verified migration detected no later than the decision;
3. rejects contradictory verified migration pool evidence;
4. resolves candidate identity point-in-time;
5. loads one exact DexScreener/PumpSwap mint/quote current snapshot within 60 seconds;
6. preserves source and pair chronology;
7. requires liquidity and trailing-24h volume;
8. applies the frozen $3,000/$1,000 thresholds;
9. returns an explicit eligibility reason and exact candidate/snapshot evidence identity.

The assessor opens SQLite read-only and contains no provider network call, future target read, model
performance read, strategy action, execution authority, promotion authority, signer, submission, or
LIVE authority.

## Regression proof

Behavior PR #246 and merged-main CI prove:

- additive exact market identity and h24-volume fields;
- legacy E13 read compatibility;
- exact-market columns required only by the FL9 exact read;
- point-in-time candidate resolution;
- future candidate discovery excluded from historical identity;
- future snapshot ownership excluded from historical identity;
- genuine multiple preferred-source ambiguity remains fail-closed;
- unique preferred-source point-in-time ownership is deterministic;
- exact source/venue/base/quote market selection;
- wrong quote and wrong venue cannot rescue a decision;
- stale exact-market evidence fails closed;
- verified migration chronology;
- contradictory migration pool evidence fails closed;
- missing liquidity and missing volume fail closed;
- exact $3,000 and $1,000 threshold behavior;
- read-only operation;
- no network/model/target/execution authority.

PR #246 CI completed 4/4 GREEN.

Merged-main CI run `34216777904` on
`67252d209482524aff2aa7b651dc55a68cdeb100` completed:

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

## Next evidence step

This seal still does not accept provisional floor `1788858050000`.

After this sealed read API is released and deployed, the next production step is a read-only replay
of the immutable post-repair decision population through `Fl9TradableUniverseStore`.

Required outputs include:

- total assessed PumpSwap decisions;
- exclusion counts by authenticated reason;
- eligible decision count;
- eligible unique-mint count;
- eligible per-mint concentration;
- snapshot-age distribution for eligible/fresh authenticated rows;
- exact policy fingerprint.

Only after an adequate authenticated eligible population exists may its exact decision identities be
fingerprinted and wired before the first-champion chronological 60/20/20 split.

The same eligible identity population must later feed training, validation, TEST, and final runtime
artifact fit.

## Authority boundary

This seal adds no:

- database mutation;
- FL4 label mutation;
- target/future-return inspection;
- model training;
- model selection or promotion;
- BUY authority;
- transaction construction;
- signing/submission;
- wallet authority;
- LIVE enablement.

**Cohort floor accepted: NO.**  
**Champion training: BLOCKED.**  
**FL9 superiority: EVIDENCE PENDING.**  
**LIVE TRADING: DISABLED.**
