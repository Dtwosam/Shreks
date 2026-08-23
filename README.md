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

## Fresh Launch Continuation setup

Phase B3 introduces the first explicit setup family under `shreks_brain.setups`: `fresh_launch_continuation`.

Fresh Launch Continuation is designed for newly launched Solana memecoins and intentionally avoids first-second blind sniping. It waits for point-in-time evidence that the token has survived long enough to evaluate, still has fresh source data, remains executable, and shows continuation characteristics across participation, volume velocity, buy pressure, short-term momentum, liquidity improvement, and local price structure.

Every numerical setup threshold belongs to an explicit, versioned `FreshLaunchPolicy`. B3 ships **no production default trading thresholds**. Thresholds are research hypotheses that must be calibrated against Shreks' own unseen, post-cost outcome data before they can be treated as useful trading rules.

A setup assessment is one of:

- `BLOCKED` — a hard condition currently prevents entry consideration, including safety not passing, stale data, expired setup window, inadequate liquidity, excessive exit impact, or an already-overextended 5-minute move;
- `WATCH` — no hard blocker is proven, but the setup is too young, evidence is missing, or one or more continuation confirmations have not passed;
- `READY` — safety/executability/age gates pass and all nine continuation confirmations are satisfied.

`READY` is **not** an order or trade instruction. It only means the setup is eligible for later decision, risk, and paper-trading layers. B1 safety `PASS` is mandatory and cannot be overridden by setup strength.

The 5-minute return ceiling is an explicit anti-chase guard: a token can have strong confirmation evidence and still be `BLOCKED` if the move is already too extended under the active policy.

B3's `confirmation_score` is only checklist completeness: `confirmations_passed / 9 * 100`. It is not expected return, win probability, confidence, or a final trade score. Hard-blocked candidates still retain confirmation counts for research so Shreks can later measure the opportunity cost and value of its filters instead of hiding rejected opportunities from the dataset.

B3 adds no `TradeIntent`, position size, paper fill, wallet, signer, transaction construction, submission, or live execution path.

## Pump graduation lifecycle evidence

Phase B4a adds the protocol-evidence prerequisite for a later Graduation/Breakout setup. It does **not** decide whether a graduation is tradable.

The existing single Pump websocket now carries both creation and migration log signals. Realtime delivery remains durable-write-only: a migration wake-up records its signature, full-width Solana slot, and local detection time, but does not fetch the transaction or trigger a setup decision between normal observer cycles.

During a full observer cycle, creation and migration verification share the same hard budget of at most 32 Pump transaction fetches. When migration backlog exists, up to eight slots are serviced first, creation verification can use the remaining capacity, and any unused creation capacity returns to older migration work. This is one shared budget, not separate 32-call budgets.

A normalized `pump_graduation` event is created only from a fetched transaction containing a verified Pump `migrate` or `migrate_v2` instruction with the pinned protocol identities/account layout. A PumpSwap market pair by itself is never graduation evidence, and `MigrateBondingCurveCreator` is intentionally not classified as a token graduation.

The durable lifecycle event preserves the token mint, quote mint, Pump.fun bonding-curve -> PumpSwap venue transition, PumpSwap pool, transaction provider, signature, full `u64` slot, decision-safe `detected_at_unix_ms`, and optional chain `occurred_at_unix_ms`. Legacy migrations normalize the quote asset to wrapped SOL; v2 migrations preserve the instruction's explicit quote mint.

Migration inbox replay is restart-safe and deterministic. Verified lifecycle persistence and terminal inbox completion are atomic, and an already-verified signature cannot silently mutate its normalized lifecycle truth on replay.

B4a adds no Graduation/Breakout threshold, setup score, `TradeIntent`, paper fill, wallet, signer, transaction construction, submission, or live execution path.

## Graduation/Breakout setup

Phase B4b introduces the second explicit setup family under `shreks_brain.setups`: `graduation_breakout`.

Graduation/Breakout requires normalized, protocol-verified B4a `pump_graduation` evidence with the exact Pump.fun bonding-curve -> PumpSwap transition. A PumpSwap pair or generic momentum alone is not enough. The setup consumes that immutable `GraduationContext` beside the unchanged B2 `b2-v1` `FeatureVector`; B4b does not widen the shared B2 schema or read SQLite/provider payloads inside strategy logic.

The first locally observed B4a `detected_at_unix_ms` is the sole graduation decision clock. Optional on-chain `occurred_at_unix_ms` remains audit/research metadata and cannot make a historical setup eligible before Shreks actually observed the migration.

Every numerical threshold belongs to an explicit, versioned `GraduationBreakoutPolicy`. B4b ships **no production default trading thresholds**. The policy values are research hypotheses that must later be calibrated against unseen, point-in-time outcomes after realistic fees, slippage, and exitability constraints.

The setup remains `BLOCKED / WATCH / READY`. Hard blockers include B1 safety not passing, missing or invalid verified graduation evidence, future-dated local detection, an expired post-graduation window, stale market data, inadequate known liquidity, excessive known exit price impact, or an already-overextended one-minute move. A graduation that is still too recent, missing executability evidence, or incomplete confirmation evidence remains `WATCH` when no hard blocker exists.

B4b-v1 uses exactly eight equal-weight confirmations: five-minute transaction participation, volume velocity, five-minute buy fraction, buy-pressure acceleration, one-minute return, five-minute liquidity growth, distance from the local high, and local-range position. Positive five-minute return and 1m-vs-5m momentum acceleration are deliberately excluded because their anchors can straddle the pre/post-graduation regime boundary immediately after migration.

`confirmation_score` is checklist completeness: `confirmations_passed / 8 * 100`. It is not expected return, win probability, confidence, position size, or a final trade score. Blocked candidates still retain computable confirmation evidence so later research can measure the opportunity cost and value of filters rather than hiding rejected opportunities.

`READY` is **not** an order or trading instruction. B4b creates no `TradeIntent`, position size, paper fill, wallet, signer, Jupiter execution request, transaction construction, submission, or live-money path.

## First Pullback setup

Phase B5 introduces the third explicit setup family under `shreks_brain.setups`: `first_pullback`.

First Pullback is not inferred from a single momentum snapshot. It requires explicit point-in-time chronology for `impulse start -> peak -> trough`, then evaluates the current B2 `b2-v1` market observation as the recovery state. Structural evidence later than the current market source observation is rejected so a historical decision cannot borrow a newer trough.

The evaluator derives the initial impulse return, peak-to-trough pullback depth, recovery from the trough, current position versus the prior peak, liquidity retention through the retracement, and the improvement in five-minute buy fraction versus the trough. A current price below the recorded trough invalidates that pullback context instead of being relabeled as a bargain or recovery.

Every numerical threshold belongs to an explicit, versioned `FirstPullbackPolicy`; B5 ships **no production default trading thresholds**. Policy values remain research hypotheses for later unseen, point-in-time, post-cost calibration.

B5-v1 uses exactly nine equal-weight confirmations: recovery from the trough, current price versus the prior impulse peak, liquidity retention, five-minute transaction participation, volume velocity, current five-minute buy fraction, buy-fraction improvement versus the trough, buy-pressure acceleration, and one-minute return. Missing evidence never becomes zero and never passes a confirmation.

Seller absorption is represented only by the auditable proxy `current 5m buy fraction - trough 5m buy fraction`; B5 does not claim to observe hidden order-book absorption. If either side of that comparison is unavailable, the absorption evidence remains unknown.

`confirmation_score` is checklist completeness: `confirmations_passed / 9 * 100`. It is not win probability, confidence, expected return, position size, or a final trade score. Hard-blocked candidates keep all computable structural metrics and confirmation evidence so later research can measure the opportunity cost and value of filters rather than hiding rejected recoveries.

`READY` is **not** an order or trading instruction. B5 adds no `TradeIntent`, sizing, paper fill, wallet, signer, swap request, transaction construction/submission, or live-money path.

## Explainable market regime

Phase B6 repairs an ordering gap in the repository by adding the explainable market-regime layer required by the source-of-truth build sequence before deterministic scoring. The branch is called B6 only to preserve repository chronology; functionally this is the planned regime-engine capability.

The regime engine lives under `shreks_brain.regime` and leaves the shared feature schema exactly at `b2-v1`. It produces one timestamped, versioned global market assessment with the labels `HOT`, `NORMAL`, `WEAK`, or `DEAD`; it does not widen individual token features or call setup evaluators.

The base regime is intentionally transparent rather than a weighted black-box score. It uses four aggregate market dimensions: candidate opportunity rate, executable-candidate breadth, median liquidity, and median five-minute volume. A candidate rate or executable fraction at the configured DEAD ceiling makes the base regime `DEAD`; otherwise any dimension below its WEAK minimum makes the base regime `WEAK`; all four at or above HOT minima make it `HOT`; a healthy mixed market is `NORMAL`.

Critical evidence quality fails closed. Future-dated or stale market source data, an undersized/too-short market window, no candidates, or missing critical liquidity/volume medians classify the base regime as `DEAD` with stable reason codes. This means Shreks pauses entry eligibility rather than guessing that incomplete global evidence is healthy.

Optional recent strategy performance is deliberately asymmetric. Once there is a configured minimum sample of closed trades, poor **after-cost** expectancy may downgrade the market regime to `WEAK` or `DEAD`; strong recent performance can never upgrade a weaker base market into `HOT`. This prevents a recent winning streak from creating a self-reinforcing pro-risk label. Future-dated performance is also rejected fail-closed.

Every numerical threshold belongs to an explicit, versioned `RegimePolicy`; B6 ships **no production default regime thresholds**. Those values remain research hypotheses to be calibrated on unseen point-in-time data and later paper results after realistic costs.

A regime label is **not** a trade instruction, expected-return forecast, confidence score, or sizing command. B6 adds no wallet intelligence, deterministic trade score, `TradeDecision`, `TradeIntent`, position sizing, paper fill, signer, swap request, transaction submission, or live-money path.

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
