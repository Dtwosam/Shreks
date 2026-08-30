# Bounded PumpSwap Realtime Ingestion Design

## Status

FL1/FL1.5 production-safety follow-up stacked on the exact GREEN provider-budget guardrail head `02cc83dee43f7a6a2a01c307db359a90e4be2140`.

**LIVE TRADING: DISABLED.**

Production observer and paper-evidence services remain intentionally stopped. FL1.5 remains HOLD until the combined HTTP-budget and bounded-realtime changes are sealed, deployed, and accepted on the physical host.

## Problem

The current production Pump realtime stream creates one standard-Solana websocket per active provider and installs two program-wide `logsSubscribe` subscriptions:

1. Pump bonding-curve program (`PUMP_PROGRAM_ID`), and
2. PumpSwap AMM program (`PUMP_AMM_PROGRAM_ID`).

The Pump-wide lane is necessary for launch/lifecycle discovery and pre-graduation trade evidence. The PumpSwap-wide lane is not bounded by Shreks' active opportunity set: it receives every transaction mentioning the PumpSwap AMM program, including pools Shreks is not tracking. On a metered provider this creates provider consumption proportional to global PumpSwap activity rather than Shreks' bounded working set.

A process-local HTTP/RPC request ceiling cannot bound websocket push billing. Therefore the global PumpSwap subscription must be replaced before production restarts.

## Protocol facts

Standard Solana `logsSubscribe` supports an object filter `mentions: [<pubkey>]` and currently permits one pubkey per method call. Multiple websocket subscriptions may coexist on one connection. A successful subscription returns an integer subscription ID, and `logsUnsubscribe` removes that subscription by ID.

This makes verified PumpSwap pool addresses usable as narrow subscription filters without provider-specific streaming APIs.

## Existing durable evidence

No database migration is required.

Verified Pump graduation evidence already persists in `token_lifecycle_events` with:

- `event_type = 'pump_graduation'`,
- `mint`,
- `pool_address`,
- `signature`,
- `detected_at_unix_ms`,
- immutable/restart-safe lifecycle semantics.

Only these verified durable pool identities may become PumpSwap realtime subscription targets. Public market-data pair addresses, unverified websocket payloads, guessed PDAs, or provider-returned strings that have not passed existing migration verification are not sufficient authority.

## Goals

1. Preserve continuous Pump-wide launch/lifecycle and pre-graduation trade coverage.
2. Eliminate the program-wide PumpSwap AMM websocket subscription.
3. Track PumpSwap activity only for a deterministic bounded set of verified recent migration pools.
4. Update pool subscriptions dynamically on the existing websocket rather than reconnecting for normal target-set changes.
5. Preserve provider order and truthful provenance: Helius -> Chainstack -> Alchemy.
6. Preserve restart safety, duplicate/conflict quarantine, canonical event identity, and fail-closed behavior.
7. Make realtime scope visible and auditable without exposing provider endpoints/keys.
8. Add no trading, strategy, risk, signing, wallet, PAPER, LIVE, or FL2 authority.

## Non-goals

- no paid provider plan;
- no provider-specific premium streaming API;
- no attempt to capture every global PumpSwap trade;
- no database schema migration;
- no change to Pump/PumpSwap parsing or canonical economic semantics;
- no strategy ranking of pools;
- no capital/execution behavior;
- no automatic production restart after CI.

## Tracking policy

Pump-wide ingestion remains always active whenever a realtime provider is configured.

PumpSwap tracking is controlled by two required positive host values whenever realtime ingestion is enabled:

- `SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS`
- `SHREKS_PUMPSWAP_MAX_TRACKED_POOLS`

There are deliberately no permissive production defaults.

At each refresh point, Shreks queries verified `pump_graduation` lifecycle rows in the half-open point-in-time window ending at `as_of_unix_ms` and selects unique nonblank pool addresses deterministically:

1. newest `detected_at_unix_ms` first;
2. stable tie break by lifecycle identity (`signature`, then `pool_address`);
3. deduplicate pool address;
4. stop at `SHREKS_PUMPSWAP_MAX_TRACKED_POOLS`.

The age window is operational collection scope, not trading strategy. It must be measured during FL1.5 and may only be changed deliberately with evidence that provider capacity and Fast Lane coverage remain adequate.

A verified pool aging out or falling outside the count cap is unsubscribed; the durable history already collected for that pool remains immutable.

## Runtime architecture

### Target reader

Add a read-only/restart-safe storage query that returns bounded verified PumpSwap pool targets for a caller-supplied `as_of_unix_ms`, maximum age, and maximum count. It must reject invalid/negative time values and zero bounds rather than silently widening scope.

No write or migration occurs during target selection.

### Target publisher

The production observer owns a small periodic target-refresh task using its own SQLite connection. The task publishes the canonical target set through a Tokio `watch` channel. The refresh cadence is operational and must be slower than event handling; it does not control trading decisions.

The initial implementation may use a small fixed internal refresh cadence because the expensive resource is provider subscription scope, not this local SQLite query. If measurements later justify externalizing the cadence, that is a separate operational change.

### Realtime stream

`PumpRealtimeLogStream` receives a cloneable target-set watch receiver in addition to provider endpoint configuration.

On initial connection:

1. subscribe once to `PUMP_PROGRAM_ID` using the existing confirmed `logsSubscribe` lane;
2. read the current bounded target set;
3. subscribe once per tracked PumpSwap `pool_address` using `mentions: [pool_address]`;
4. store `pool_address -> provider subscription ID` for this socket.

There is **no** `mentions: [PUMP_AMM_PROGRAM_ID]` subscription.

While connected, the event loop selects between websocket frames and target-set changes:

- target additions issue `logsSubscribe` for the new verified pool and record its returned subscription ID;
- target removals issue `logsUnsubscribe` for the recorded subscription ID and require a successful boolean acknowledgement;
- unchanged pools remain subscribed without duplicate method calls;
- a malformed/rejected subscribe/unsubscribe acknowledgement is a provider error and must not be treated as success.

If connection/failover occurs, provider-local subscription IDs are discarded. The new provider connection reconstructs Pump + current pool subscriptions from the shared canonical target set.

Normal target-set changes must not force websocket reconnects, avoiding avoidable gaps/replay amplification.

## Bounds and validation

The target set is canonicalized before publication/subscription:

- no blank pool address;
- no duplicate pool address;
- length never exceeds configured maximum;
- only verified durable lifecycle rows in the configured age window;
- deterministic ordering independent of SQLite incidental row order.

A target query or publisher failure is fatal to the realtime evidence lane while bounded PumpSwap tracking is required. The observer must not continue nominally healthy with a stale/unknown target set.

An empty valid target set is allowed: it means there are currently no verified recent PumpSwap pools to track. Pump-wide lifecycle ingestion continues so new migrations can enter the target set on the next refresh. Empty targets must not cause a fallback to the global PumpSwap program subscription.

## Provider failover

The current provider order remains unchanged:

`Helius -> Chainstack -> Alchemy`

All provider streams observe the same target-set state. A failover reconstructs the bounded subscription set on the newly active provider and emits that provider's truthful provenance on subsequent notifications.

Provider endpoint/key material remains redacted from Debug/log/evidence output.

## Acceptance semantics

FL1.5 PumpSwap acceptance changes from accidental global coverage to deliberate bounded Fast Lane coverage.

A representative physical interval must prove:

- Pump-wide creation/pre-graduation progress;
- at least one verified tracked PumpSwap pool when natural migration/traffic is available in the interval;
- PumpSwap raw/canonical events for tracked pools when those pools trade naturally;
- zero sequence-integrity and canonical-conflict violations;
- deterministic target count never above configured maximum;
- no program-wide `PUMP_AMM_PROGRAM_ID` subscription in the deployed release;
- stable add/remove/failover behavior without restart churn;
- provider consumption compatible with the intended free-tier duty cycle.

If there is no natural verified migrated pool/traffic in a candidate interval, extend the interval. Do not manufacture migration/trades or re-enable the global AMM firehose merely to satisfy acceptance.

## TDD requirements

RED before GREEN must prove at minimum:

1. subscription request construction supports one explicit mentioned pubkey and cannot silently build a multi-address request;
2. production initial subscription plan contains `PUMP_PROGRAM_ID` plus tracked pool addresses, never `PUMP_AMM_PROGRAM_ID`;
3. verified lifecycle target selection is deterministic, bounded, point-in-time-safe, deduplicated, and rejects invalid bounds;
4. an empty target set remains Pump-only and never falls back to global PumpSwap;
5. target additions create exactly one new pool subscription;
6. target removals use the exact provider subscription ID returned for that pool;
7. unchanged targets create no duplicate subscribe/unsubscribe traffic;
8. failover rebuilds the current target set on the next provider;
9. malformed or rejected unsubscribe acknowledgement fails closed;
10. provider provenance and Pump/PumpSwap parsing remain unchanged;
11. observer/runtime source contains no trading/signing/LIVE authority;
12. exact-head repository safety, Rust, Python, and ARM64 release-build CI all pass.

## Merge/deploy order

1. Merge provider-budget guardrail PR #105 first.
2. Retarget/rebase this bounded-realtime PR onto the resulting `main` without changing its tested tree unexpectedly.
3. Require fresh exact-head four-gate CI.
4. Merge through the normal immutable seal/release/deploy path.
5. Configure explicit host HTTP and PumpSwap tracking bounds.
6. Run a short read-only sanity interval followed by representative FL1.5 physical acceptance.
7. Only after FL1.5 passes may the build order advance to FL2.

**LIVE TRADING remains disabled throughout.**
