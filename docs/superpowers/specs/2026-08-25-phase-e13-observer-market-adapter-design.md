# Phase E13 — Observer Market Replay Adapter Design

## Purpose

Phase E13 creates the first read-only bridge from the real Rust observer database into the sealed Python market-feature stack.

The observer already runs continuously and persists normalized candidate and market history in SQLite. The Python B2 feature engine already accepts deterministic `MarketFeaturePoint` values, but there is no production adapter between those two layers. E13 closes only that gap.

E13 does **not** create a second observer, a scheduler, a safety evaluator, a paper runner, a promotion path, or any live-trading authority.

## Source-of-truth boundary

The project progression remains:

`OBSERVE -> UNDERSTAND -> PAPER TRADE -> EVALUATE -> LEARN -> PROVE -> LIVE TRADE`

Phase F stays disabled. E13 exists to make later paper/proof campaigns consume real observer history instead of fixtures while preserving the existing fail-closed evidence rules.

No profitability, promotion, or live-money claim follows from successful E13 operation.

## Existing facts E13 composes

The Rust observer executable writes into the operational SQLite database in WAL mode. The storage schema contains:

- `token_candidates` with durable candidate identity;
- `market_snapshots` with timestamped normalized market observations, source, venue, pair identity, price, liquidity, volume, transaction counts, price-change fields, and pair creation time;
- `provider_health`, raw observations, and later operational tables.

The sealed Python B2 feature stack accepts:

- one current `MarketFeaturePoint`;
- optional 1-minute, 5-minute, and 15-minute anchors with exact B2 age windows;
- pair creation time;
- local high / local low;
- an independently supplied `SafetyAssessment` and exit-price-impact value.

E13 will not fabricate the safety fields that the observer database cannot currently prove, such as holder concentration or an executable exit quote.

## Selected design

Create a new isolated package:

`python/src/shreks_brain/observer_market/`

with schema/version identifier:

`e13-observer-market-v1`

The package contains immutable policy/result models plus a read-only SQLite reader.

### Public models

`ObserverMarketReadPolicy`

- `version: str`
- `source_priority: tuple[str, ...]`
- `max_current_age_ms: int`
- `local_range_lookback_ms: int`

All thresholds and provider preference are caller-supplied. E13 does not invent economic or staleness thresholds.

`ObserverCandidateIdentity`

- `candidate_id: int`
- `mint: str`
- `pair_address: str`
- `discovery_source: str`
- `discovered_at_unix_ms: int`
- `venue: str | None`

`ObserverMarketSnapshot`

A strict immutable representation of one persisted `market_snapshots` row required by E13, including source/pair identity, observation times, price/liquidity/volume/count fields, and pair creation time.

`ObservedMarketWindow`

- schema version and policy version;
- exact candidate identity;
- `as_of_unix_ms`;
- exact selected source and pair address;
- current snapshot;
- optional 1m / 5m / 15m snapshots;
- optional local high / local low;
- deterministic source observation metadata.

The model exposes no execution or promotion methods.

### Reader

`ObserverMarketStore(database_path)` opens SQLite in read-only URI mode. It never creates, migrates, alters, checkpoints, vacuums, or writes the observer database.

Public methods:

- `resolve_candidate(mint, *, pair_address=None, discovery_source=None) -> ObserverCandidateIdentity`
- `load_window(candidate_id, as_of_unix_ms, policy) -> ObservedMarketWindow`
- `build_market_feature_points(window) -> tuple[current, one_minute_ago, five_minutes_ago, fifteen_minutes_ago]`

`resolve_candidate` fails closed if the requested mint is absent or remains ambiguous after caller-supplied filters. It never guesses which duplicate candidate row represents the intended market path.

`load_window` validates the required observer schema before reading evidence.

## Deterministic market-path selection

For one exact candidate ID and `as_of_unix_ms`:

1. Ignore every row with `observed_at_unix_ms > as_of_unix_ms`.
2. Walk `source_priority` in caller-supplied order.
3. For each source, choose the newest row at or before `as_of_unix_ms` whose age is at most `max_current_age_ms`.
4. The first source with such a row becomes the selected source.
5. The current row's `pair_address` becomes the selected pair path.
6. All historical anchors and local-range statistics must use the **same source and same pair address** as the current row. E13 never mixes providers or pairs inside one B2 feature window.

If no preferred source has a sufficiently fresh row, the reader fails closed.

## Anchor selection and no-future-leakage rule

B2 already defines valid anchor age windows:

- 1m: 60,000–90,000 ms old;
- 5m: 300,000–360,000 ms old;
- 15m: 900,000–1,020,000 ms old.

Within each valid age window, E13 selects the row closest to the nominal target age (60s, 300s, 900s). Ties choose the newer observation, then lower row ID for deterministic replay.

If no row exists inside an anchor window, that anchor is `None`. Missing anchors are evidence, not an error and not a reason to synthesize data.

Rows after `as_of_unix_ms` are never eligible for current, anchor, pair metadata, high/low, or any other output.

## Local range

`local_range_lookback_ms` is caller supplied and must be positive.

For the selected source/pair path, E13 considers only rows in:

`[as_of_unix_ms - local_range_lookback_ms, as_of_unix_ms]`

Positive, finite prices contribute to local range. If no valid prices exist, high and low are `None`. E13 does not substitute zero or an external price.

## Pair creation time

The current row's `pair_created_at_unix_ms` wins when present. Otherwise E13 may use the newest non-null value from the selected source/pair at or before `as_of_unix_ms`.

A future pair-creation timestamp, negative timestamp, or other malformed persisted value fails closed.

## Strict database validation

E13 validates that SQLite contains the required tables and columns before reading.

Required tables:

- `token_candidates`
- `market_snapshots`

Required candidate columns:

- `id`, `mint`, `pair_address`, `discovery_source`, `discovered_at_unix_ms`, `venue`

Required market columns:

- `id`, `candidate_id`, `observed_at_unix_ms`, `source`, `source_observed_at_unix_ms`, `venue`, `pair_address`, `price_usd`, `liquidity_usd`, `volume_m5_usd`, `volume_h1_usd`, `buys_m5`, `sells_m5`, `buys_h1`, `sells_h1`, `pair_created_at_unix_ms`

Future additive columns are allowed. Missing required columns fail closed.

SQLite values are validated strictly before becoming E13 models or B2 `MarketFeaturePoint` values. Non-finite numbers, negative non-negative fields, malformed identities, and invalid timestamps fail closed.

## Read-only authority firewall

E13 must have no API capable of:

- inserting or updating observer rows;
- changing provider configuration;
- running discovery;
- creating trade intents;
- invoking paper execution;
- mutating E6 registry state;
- applying E8 promotion;
- enabling runtime `LIVE`;
- signing or submitting transactions.

The package may import B2 market feature model types only for deterministic conversion. It must not import execution, promotion, registry mutation, signing, or provider-network modules.

## TDD verification

Tests will prove:

1. exact immutable model validation;
2. read-only open behavior, including no database creation for a missing path;
3. exact candidate resolution and ambiguity rejection;
4. caller-priority current-source selection;
5. same-source/same-pair anchor construction;
6. exact B2 anchor windows and deterministic tie-breaking;
7. strict exclusion of future rows;
8. caller-supplied current-staleness rejection;
9. caller-supplied local-range computation;
10. missing anchors remain `None`;
11. malformed/missing schema fails closed;
12. public API and import firewall expose no execution/live authority.

Every production behavior is introduced only after a failing test demonstrates the missing behavior.

## Deferred work

E13 intentionally does not build:

- safety reconstruction from mint/holder/quote evidence;
- wallet-feature reconstruction;
- regime construction;
- `PaperCycleInput` construction;
- unattended Python campaign orchestration;
- E10/E11/E12 evidence advancement;
- live execution.

Those become subsequent phases only after this real observer-market seam is sealed and verified.