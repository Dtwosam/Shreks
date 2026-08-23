# Shreks

Shreks is an autonomous Solana memecoin trading system under active development.

The target system will watch the market, reject unsafe or untradeable tokens, identify explicit setups, size risk, execute entries and exits automatically, record outcomes, and learn from a growing point-in-time dataset.

**Current phase:** Phase A — Foundation + Observation  
**Current live-money status:** Disabled

## Architecture

- **Rust — eyes + hands:** Solana-facing ingestion, normalized events, operational storage, and eventual transaction execution.
- **Python — brain:** safety analysis, feature engineering, strategies, risk, paper trading, research, and model evaluation.
- **SQLite WAL — operational state:** active from Phase A2.
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
  shreks-storage/    SQLite WAL database + migrations
python/
  src/shreks_brain/  Python trading/research brain
  tests/             Python tests
docs/
  superpowers/       Design and implementation plans
.github/workflows/   CI
```

## Operational database

`shreks-storage` owns the Phase A operational SQLite schema. Opening a database automatically:

1. creates missing parent directories,
2. enables WAL journal mode,
3. enables foreign keys,
4. configures normal synchronous behavior and a 5-second busy timeout,
5. applies unapplied migrations transactionally.

Migration 1 creates:

- `schema_migrations`
- `provider_health`
- `token_candidates`
- `market_snapshots`
- `raw_observations`
- `ingestion_checkpoints`

The default runtime path in `.env.example` is `data/shreks.db`. Runtime databases, WAL/SHM files, and Parquet datasets are ignored by Git.

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

See `docs/superpowers/specs/2026-08-23-shreks-master-design.md` for the approved architecture. Phase A1 and A2 implementation plans are under `docs/superpowers/plans/`.
