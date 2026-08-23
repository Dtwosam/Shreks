# Shreks

Shreks is an autonomous Solana memecoin trading system under active development.

The target system will watch the market, reject unsafe or untradeable tokens, identify explicit setups, size risk, execute entries and exits automatically, record outcomes, and learn from a growing point-in-time dataset.

**Current phase:** Phase B — UNDERSTAND  
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

## Future outcome checkpoints

Phase A9 schedules future learning checkpoints for every durable observed candidate at:

- 1 minute,
- 5 minutes,
- 15 minutes,
- 30 minutes,
- 1 hour,
- 4 hours,
- 24 hours.

Checkpoint rows are durable and idempotent. Pending checkpoints survive SQLite/process restart, repeated scheduling does not duplicate them, and a completed checkpoint keeps references to the actual baseline and checkpoint market snapshots used for its metrics.

Outcome sampling runs only as part of normal full observer cycles. Realtime Pump wake-ups between cycles remain durable-write-only. Multiple overdue horizons for one candidate share one market-observation pass, and due work is bounded to at most 16 candidates per cycle while reusing the existing provider pacing. A candidate revisited only for an outcome checkpoint does not trigger mint-state/chain enrichment solely because the checkpoint is due.

When sufficient point-in-time evidence exists, Shreks records return, MFE, MAE, liquidity change, 5-minute volume change, and signed 5-minute buy/sell-count changes. Metrics stay `NULL` when required values are missing or a percentage denominator is not positive. If there is no usable price-bearing snapshot at or after a due horizon, the checkpoint stays pending for a later cycle rather than being falsely completed. `rug_or_dead_pool` and `exitability` also stay `NULL` until an explicit detector or quote provides evidence; absence of a provider pair is not treated as proof.

Phase A9 is observation and dataset infrastructure only. It does not enable transaction signing, transaction submission, paper execution, or live trading.

## Deterministic safety assessment

Phase B1 introduces a dependency-free, point-in-time Python safety core under `shreks_brain.safety`. It consumes already-proven candidate facts and a versioned `SafetyPolicy`; it does not read SQLite or provider payloads directly.

The safety decision is one of:

- `PASS` — no hard blocker exists and all policy-required critical facts are usable;
- `REJECT` — at least one proven hard blocker exists;
- `INCOMPLETE` — no hard blocker is proven, but required critical evidence is missing, stale, future-dated, or contradictory.

Decision precedence is `REJECT > INCOMPLETE > PASS`. Only `PASS` is eligible for later entry consideration. Later strategy scoring is not allowed to reinterpret a hard rejection as a soft penalty, and incomplete critical evidence fails closed rather than being guessed.

Hard/soft thresholds live in explicit `SafetyPolicy` configuration. Findings use stable reason codes and deterministic ordering so later research can measure which rules help or hurt. Soft findings are recorded for later scoring/research but never independently turn a result into `REJECT` or `INCOMPLETE`.

B1 accepts no future outcome checkpoints, realized PnL, future returns, MFE, or MAE. A critical-data timestamp after the assessment time is treated as contradictory evidence rather than fresh data. B1 adds no wallet secrets, signer, swap execution, paper-fill engine, or live-trading path.

## Deterministic feature engine

Phase B2 adds a dependency-light, point-in-time feature engine under `shreks_brain.features`. It converts normalized market observations plus the same-timestamp B1 `SafetyAssessment` into a versioned `FeatureVector`.

B2 is deliberately **not** a trade score. It exposes reproducible raw/derived evidence so later setup logic can be calibrated against Shreks' own post-cost outcome dataset instead of baking assumptions into one opaque formula.

The first schema, `b2-v1`, includes:

- market quality: token age, price, liquidity, 5-minute liquidity change, exit price impact;
- participation: 5-minute/hourly volume, volume velocity, transaction counts;
- flow: buy fractions, buy/sell ratios, buy-pressure acceleration;
- momentum: 1m/5m/15m returns and short-vs-medium momentum acceleration;
- structure: distance from local high and position inside the observed local range;
- safety research flags copied from B1 soft findings.

Named return horizons use versioned timing bands, so a feature called `return_1m_pct` cannot silently use a much newer or older observation. The feature vector also records current source age.

Missing market evidence remains `None`; it is never converted to zero. Zero denominators also produce `None` rather than infinity or artificial extreme signals. Every vector carries a deterministic `missing_features` list so later strategies can require the evidence they actually need.

B1 remains the hard safety gate. B2 computes feature vectors for `PASS`, `REJECT`, and `INCOMPLETE` candidates because rejected candidates are still valuable research data and reduce selection bias; later entry logic must independently require safety `PASS`.

B2 accepts no future outcome checkpoint or realized trade-result fields and does not read SQLite or call providers directly. It adds no setup score, trade intent, paper fill, signer, swap submission, or live-trading path.

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

The repository intentionally does not contain a live-wallet secret variable during the current pre-live phases.

## Build discipline

The required progression is:

```text
OBSERVE -> UNDERSTAND -> PAPER TRADE -> EVALUATE -> LEARN -> PROVE -> LIVE TRADE
```

Live execution is not an early demo milestone. Paper and live modes will share the same decision and risk path; only the execution adapter changes.

See `docs/superpowers/specs/2026-08-23-shreks-master-design.md` for the approved architecture. Design and implementation plans are under `docs/superpowers/`.
