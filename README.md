# Shreks

Shreks is an autonomous Solana memecoin trading system under active development.

The target system will watch the market, reject unsafe or untradeable tokens, identify explicit setups, size risk, execute entries and exits automatically, record outcomes, and learn from a growing point-in-time dataset.

**Current phase:** Phase A — Foundation + Observation  
**Current live-money status:** Disabled

## Architecture

- **Rust — eyes + hands:** Solana-facing ingestion, provider normalization, operational storage, realtime observation, and eventual transaction execution.
- **Python — brain:** safety analysis, feature engineering, strategies, risk, paper trading, research, and model evaluation.
- **SQLite WAL — operational state:** restart-safe local state and normalized observations.
- **Parquet — research datasets:** introduced after enough observation data exists.

Shreks is Solana-only for V1 and must not require paid market-data subscriptions or paid RPC plans.

## Runtime modes

The shared runtime vocabulary is:

- `observe` — collect and persist data; no trades.
- `paper` — autonomous simulated trading.
- `shadow` — challenger decisions run without controlling capital.
- `live` — autonomous real execution; unavailable until promotion gates are proven.
- `halted` — no new trading activity.

The default is `observe`.

## Repository layout

```text
crates/
  shreks-core/       Shared Rust domain primitives
  shreks-providers/  Free-source provider adapters + Pump realtime ingestion
  shreks-storage/    SQLite WAL database + versioned migrations
  shreks-observer/   Restart-safe observe-only orchestration
python/
  src/shreks_brain/  Python trading/research brain
  tests/             Python tests
docs/
  superpowers/       Design, amendments, and implementation plans
.github/workflows/   CI
```

## Phase A data sources

The observe path currently uses free/public data only:

- **DEX Screener** for public Solana discovery/enrichment and pair market data.
- **Meteora** directly for DLMM and DAMM v2 pool data.
- **Helius / standard Solana RPC** for parsed mint state, confirmed transaction verification, and standard `logsSubscribe` realtime Pump launch signals when a Helius key is configured.
- **Jupiter Swap V2** has a read-only quote/build adapter for future executability work, but Jupiter is deliberately excluded from the normal observe-only runtime.

Provider identity and economic venue are separate. For example, DEX Screener may supply an observation whose venue is PumpSwap. Pump.fun bonding-curve, PumpSwap, Meteora DLMM, and Meteora DAMM v2 are preserved as first-class venue identities.

There is no hidden paid fallback. If a required free provider is unavailable, Shreks records degraded/rate-limited/unavailable health and fails safely rather than purchasing or silently switching to paid data.

## Pump.fun realtime observation

With `HELIUS_API_KEY` configured locally, the observe runtime can use Helius' standard Solana WebSocket path to watch the official Pump program.

The path is:

```text
Pump logsSubscribe
    -> reconnecting/heartbeat WebSocket source
    -> bounded in-memory channel
    -> observer-owned durable Pump inbox
    -> confirmed getTransaction verification
    -> verified Create/CreateV2 candidate
    -> normal market + chain observation
```

The WebSocket producer never writes SQLite directly. The observer remains the single database writer. Duplicate signatures are idempotent; RPC lag keeps a signal pending for retry; confirmed non-creation transactions are rejected audibly. Realtime arrivals can wake a sleeping observer for a durable inbox write without forcing another expensive full provider cycle.

## Operational database

`shreks-storage` owns the Phase A operational SQLite schema. Opening a database automatically:

1. creates missing parent directories,
2. enables WAL journal mode,
3. enables foreign keys,
4. configures normal synchronous behavior and a 5-second busy timeout,
5. applies unapplied migrations transactionally.

Current migrations are additive and restart-safe:

- **Migration 1 — operational:** provider health, token candidates, market snapshots, raw observations, ingestion checkpoints.
- **Migration 2 — observer normalization:** venue-aware candidate/snapshot identity and full-width Solana mint-state history.
- **Migration 3 — Pump launch inbox:** durable pending/verified/rejected realtime Pump signatures and verification audit state.
- **Migration 4 — candidate outcome checkpoints:** standardized future-outcome labels for every durable candidate.

The default runtime path in `.env.example` is `data/shreks.db`. Runtime databases, WAL/SHM files, and Parquet datasets are ignored by Git.

## Future-outcome tracking

Every durable candidate is scheduled idempotently for these official outcome horizons after its first discovery time:

```text
1m -> 5m -> 15m -> 30m -> 1h -> 4h -> 24h
```

These checkpoints are research labels, not separate trading strategies. Due candidates are revisited in bounded batches through the normal paced market-provider path. A candidate is sampled only once per full cycle even when several horizons are overdue, and outcome-only sampling does not request mint state just because a checkpoint is due.

A completed checkpoint references the actual baseline and checkpoint `market_snapshots`, preserving provider and venue identity. From data actually observed by that time Shreks can deterministically calculate:

- return,
- maximum favorable excursion (MFE),
- maximum adverse excursion (MAE),
- liquidity change,
- 5-minute volume change,
- signed buy-count change,
- signed sell-count change.

Unsupported or unproven values stay `NULL`. In particular, absence of a pair does not by itself prove a rug/dead pool, and exitability remains unknown until an explicit detector or quote path proves it.

Outcome schedules survive restart. A pending checkpoint can be completed after reopening the same database, and a completed checkpoint is terminal: later observations/restarts do not rewrite its result.

The official checkpoints do not prevent Shreks from storing additional market observations between them. A separate budget-aware adaptive path-observation layer is being added so future research can study the sequence that led to each checkpoint outcome without querying every token every few seconds for 24 hours.

## Running observe mode

After local configuration, the Rust observe binary is the long-running Phase A process. It opens the configured SQLite database, assembles only the enabled free providers, runs observation cycles, persists provider health/checkpoints, and stops cleanly on shutdown.

No wallet, signer, swap submission, buy, or sell path is enabled by Phase A.

## Local setup

### Rust

Install a stable Rust toolchain, then run:

```bash
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

### Python

Python 3.12 or newer is required.

```bash
python -m venv .venv
```

Activate the environment using the command appropriate for your shell, then:

```bash
python -m pip install -e './python[dev]'
python -m pytest python/tests -q
```

## Configuration

Copy `.env.example` to a local `.env` when runtime configuration is needed.

Never commit:

- private keys,
- seed phrases,
- wallet secrets,
- real `.env` files,
- production API secrets.

The repository intentionally does not contain a live-wallet secret variable during Phase A.

## Build discipline

The required progression is:

```text
OBSERVE -> UNDERSTAND -> PAPER TRADE -> EVALUATE -> LEARN -> PROVE -> LIVE TRADE
```

Live execution is not an early demo milestone. Paper and live modes will share the same decision and risk path; only the execution adapter changes.

See `docs/superpowers/specs/2026-08-23-shreks-master-design.md` for the approved architecture, `docs/superpowers/specs/2026-08-23-venue-priority-amendment.md` for Pump/Meteora venue treatment, and `docs/superpowers/plans/` for the implementation plans.
