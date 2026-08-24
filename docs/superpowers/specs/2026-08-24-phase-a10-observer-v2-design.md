# Phase A10 Observer V2 — High-Resolution Lifecycle Capture Design

**Status:** Approved by current project direction  
**Base:** sealed E5 head `8f8454a982d41a7f5710c66f27690ef8c080bf41`  
**Scope:** read-only observation/data collection only

## Goal

Upgrade Shreks' existing Rust observer so standardized 1m/5m/15m/30m/1h/4h/24h outcome labels are backed by sufficiently dense token-path observations rather than sparse checkpoint-only sampling.

The immediate business reason is simple: a token can pump and dump between two labels. Shreks must preserve enough of the path to learn from that event later, including candidates it rejects or never trades.

A10 does not create trade intents, sign transactions, promote a model, or enable live money.

## Existing foundation we keep

The current observer already provides valuable invariants that must remain intact:

- Rust owns observation/provider orchestration.
- SQLite WAL storage is restart-safe and auditable.
- provider failures are isolated and provider health is persisted.
- DEX Screener and Meteora provide normalized pair snapshots.
- Helius provides chain/transaction observation when configured.
- Pump realtime creation/migration signals are durably queued and verified through the existing observer path.
- discovered candidates receive the seven standardized A9 outcome checkpoints.
- A9 already computes MFE and MAE from **all market snapshots between baseline and checkpoint**.
- snapshot writes are deduplicated by candidate/source/pair/timestamp.
- rejected/untraded observations remain useful research evidence.

A10 therefore improves observation density and path preservation rather than rewriting the outcome system.

## Architecture choice

### Chosen approach: companion high-resolution sampler inside the existing `shreks-observer` process

Keep the existing `Observer` library as the authoritative discovery/lifecycle/checkpoint engine. Upgrade the default `shreks-observe` binary so it also runs a second, focused high-resolution market sampler against the same SQLite WAL database.

The companion sampler:

1. independently discovers DEX Screener candidates,
2. idempotently upserts them through `ShreksDb`,
3. registers all candidates regardless of future trading decision,
4. samples market providers on an adaptive per-candidate cadence,
5. persists every normalized `PairMarketData` snapshot through existing storage,
6. updates durable path state used for scheduling and diagnostics,
7. finalizes any now-due A9 checkpoints after fresh snapshots arrive,
8. backs off safely under provider failures/rate limits,
9. expires tracking only after the 24h research horizon plus grace.

The existing observer continues to own Pump realtime lifecycle verification, chain mint state, provider-health behavior, and its existing due-checkpoint path. Both SQLite connections use the already-configured WAL/busy-timeout behavior.

### Why not rewrite `Observer`

The existing observer's `lib.rs` contains mature Pump inbox/verification/restart logic. Replacing that orchestration to add sampling would unnecessarily widen risk. A companion loop isolates A10 behavior and can later be folded inward only if measured operating evidence justifies it.

### Why not add a new service/database

A10 stays in the existing Rust process and existing SQLite database. No Redis, Kafka, hosted database, microservice, paid feed, or new operational dependency is introduced.

## Durable candidate registry

The sampler needs to remember tracked candidates across restart without adding a new database migration solely for scheduler state.

Use the existing `ingestion_checkpoints` table with a versioned stream name:

`observer_v2_registry_v1`

The cursor contains a deterministic line-based encoding of active candidate state. It is operational scheduler state, not research truth. Market snapshots remain the research evidence.

Each tracked candidate stores at least:

- `candidate_id`
- mint
- discovery timestamp
- last sample timestamp
- next due timestamp
- consecutive failed sample count
- first usable price
- latest usable price
- path high and timestamp
- path low and timestamp
- latest liquidity
- latest 5m volume
- latest 5m buy/sell counts

Registry serialization is deterministic by `(discovered_at_unix_ms, candidate_id, mint)` and validates every field on restore. Corrupt registry state fails closed instead of silently inventing candidate history.

A registry flush occurs after discovery changes and periodically during sampling. A crash can lose a small amount of scheduling state but cannot lose already committed market snapshots.

## Candidate retention

A candidate is tracked regardless of REJECT/WATCH/ENTER outcome because the sampler does not consume strategy decisions.

Retention ends only after:

`discovery + 24h + grace`

The grace period protects the 24h checkpoint from ordinary provider delay. Expiration is an observation-storage concern, not a claim that the token is dead.

## Adaptive sampling policy

Sampling cadence is operational policy, not a trading signal and not a model feature by itself.

Default age bands:

- age <= 15m: 10s
- age <= 1h: 30s
- age <= 4h: 60s
- age <= 24h: 300s

Activity can temporarily increase resolution. Initial evidence triggers include:

- absolute price move between representative samples,
- material liquidity change,
- material 5m volume change,
- material change in 5m buy/sell transaction activity.

Activity classes:

- `CALM`: base age cadence
- `ACTIVE`: approximately half the base cadence
- `HOT`: approximately one quarter of the base cadence

All intervals are bounded by a minimum of 5 seconds. Provider pacing remains authoritative: the sampler may want a 5-second token cadence while provider request budgets still serialize actual calls below configured free-tier RPS.

The exact thresholds are explicit constants inside a versioned `SamplingPolicy`; they are hypotheses about information density, not profitability thresholds.

## Provider failure/backpressure behavior

Per-provider request pacing uses the existing free-tier budgets from `ProviderConfig`.

For one candidate sample:

- if at least one market provider succeeds, preserve those snapshots and reset the candidate failure streak;
- if every enabled market provider fails, increase candidate backoff exponentially up to the ordinary slow cadence;
- rate-limit/provider errors are recorded to provider health using existing `ShreksDb` APIs;
- the sampler never compensates by switching to a paid endpoint.

A provider failure never deletes the candidate or converts missing evidence into zero.

## Representative sample and path state

All provider/pair snapshots are stored. For adaptive activity/path state only, choose one representative snapshot deterministically:

1. usable finite positive USD price required;
2. highest known liquidity wins;
3. lexical `(provider, pair_address)` breaks ties.

Path state uses representative prices:

- first usable price is immutable,
- high updates only on a strictly higher price,
- low updates only on a strictly lower price,
- high/low timestamps come from the selected snapshot,
- MFE-so-far and MAE-so-far are derived from first/high/low prices.

This path state helps scheduling/diagnostics. The authoritative A9 MFE/MAE labels continue to be computed from persisted snapshots by `shreks-storage`, preserving one outcome implementation.

Dense snapshots also make later time-to-peak/time-to-trough research derivable without inventing an endpoint-only proxy.

## Event-aware coverage

A10 must not pretend an event stream exists where the current provider boundary does not expose one.

Current normalized event-aware evidence already available in the repository remains active:

- Pump realtime creation/migration signals,
- verified Pump graduation lifecycle events,
- D1 wallet observations where supplied by the wallet-observation path,
- chain mint-state observations.

A10-v1 adds dense market-path snapshots around those events. Generic per-swap normalization is deferred until a free provider adapter exposes a stable normalized swap/event boundary; it must not be fabricated from DEX Screener rolling counters.

This satisfies the source-of-truth requirement to persist market/onchain events **where available** while preserving data-quality honesty.

## Outcome checkpoints

A10 does not change the approved horizons or duplicate A9 outcome formulas.

After each successful high-resolution sample, call existing checkpoint finalization. Because `shreks-storage` calculates MFE/MAE from all persisted snapshots between baseline and checkpoint, denser observations improve those labels automatically.

The 1m/5m/15m/30m/1h/4h/24h checkpoints remain standardized labels, never the observation cadence.

## Runtime behavior

`shreks-observe` becomes the operator entrypoint for both loops:

- existing observer task: lifecycle, chain, legacy provider cycle, A9 completion
- V2 sampler loop: discovery registry + adaptive high-resolution market sampling
- existing Pump forwarder when Helius is configured

Shutdown stops the sampler cleanly and flushes registry state; observer/stream tasks are then terminated. No trade path is present.

## Testing

A10 tests must cover at minimum:

- age-band cadence boundaries,
- ACTIVE/HOT cadence boosts and 5-second floor,
- exponential failure backoff,
- deterministic due ordering,
- rejected/untraded neutrality (scheduler has no decision field),
- registry encode/decode round trip,
- corrupt registry fails closed,
- registry input order canonicalization,
- retention through 24h + grace,
- path sequence `100 -> 400 -> 60` preserves the pump and dump (`MFE=300%`, `MAE=-40%`) and peak/trough times,
- representative-pair selection is deterministic,
- no price/activity calculation accepts NaN/infinity/non-positive price,
- sampler source contains no trade-intent, signing, transaction submission, or live-mode authority.

Existing workspace tests remain mandatory.

## Exit criterion

A10-v1 is complete when:

- the default observe process continuously retains discovered tokens through the research horizon,
- active candidates receive adaptive high-resolution snapshots under free-provider pacing,
- restart restores the active registry,
- high/low/path timing survives registry round trips,
- A9 checkpoint finalization consumes the denser stored path automatically,
- existing Pump lifecycle observation remains unchanged,
- the full Rust/Python/repository-safety suite is green,
- no trading authority is introduced.

Once verified, the read-only collector should be started operationally as soon as runtime credentials/free provider access are available, while E6-E8 continue separately.