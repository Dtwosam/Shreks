# SHREKS — BUILD ORDER

**Project:** Shreks  
**Repository:** `Dtwosam/Shreks`  
**Architecture:** Rust + Python  
**Purpose of this file:** Defines the order in which Shreks must be built so later components do not depend on unproven or missing foundations.

---

## Rule

Do not skip directly to live trading.

The required progression is:

`OBSERVE -> UNDERSTAND -> PAPER TRADE -> EVALUATE -> LEARN -> PROVE -> LIVE TRADE`

Each phase must leave behind working, tested software.

---

# PHASE A — FOUNDATION + OBSERVATION

## A1. Repository foundation
Create the basic Rust/Python workspace, shared configuration, test structure, logging conventions, environment templates, and development commands.

Requirements:

- Rust workspace
- Python package/environment
- `.env.example`
- `.gitignore`
- no secrets committed
- unified local run instructions
- basic CI/tests where practical

## A2. Operational database
Create SQLite WAL-mode storage and explicit migrations.

Initial storage areas:

- provider health
- token candidates
- normalized market snapshots
- raw observation metadata
- event ingestion checkpoints

## A3. Provider interfaces
Define Shreks-owned interfaces before wiring individual providers.

Providers must not leak arbitrary external JSON through the entire system.

## A4. DEX Screener adapter
Implement free market/pair discovery and enrichment.

Capture relevant:

- mint/pair identity
- price
- liquidity
- volume
- buys/sells
- market cap/FDV when available
- price-change windows
- pair creation/age
- source timestamps

## A5. Solana / Helius adapter
Implement free onchain observation.

Initial goals:

- account/token state
- authority data
- transaction/account activity
- wallet observations
- chain timestamps
- provider health/rate handling

## A6. Jupiter quote adapter
Use free Jupiter access to obtain executable route/quote information.

Initially this is read-only.

Capture:

- route availability
- expected output
- price impact
- slippage context
- quote timestamp/freshness

## A7. Normalized market model
Convert provider outputs into stable Shreks domain objects.

No strategy logic yet.

## A8. Continuous observer
Create the autonomous observation loop.

It must:

- discover candidates
- sample them over time
- persist snapshots
- deduplicate inputs
- survive provider errors
- survive process restarts
- record provider health

## A9. Outcome checkpoints
For observed candidates, record future outcomes around:

- 1m
- 5m
- 15m
- 30m
- 1h
- 4h
- 24h

These are standardized research labels, not the only observation times.

## A10. Observer V2 — high-resolution lifecycle capture

Upgrade the read-only observer so important intra-window behavior is preserved rather than inferred from sparse checkpoints.

Requirements:

- persist normalized market/onchain events where available, including swaps/buys/sells, meaningful liquidity changes, large/strong-wallet actions, creator/deployer actions, authority/supply changes, and route/executability changes
- keep short-interval rolling market snapshots in addition to event records
- make snapshot cadence adaptive: newly launched, volatile, rapidly changing, or execution-deteriorating tokens receive higher-resolution observation; quiet/dead tokens back off
- preserve path summaries such as rolling/local high/low, MFE/MAE-so-far, time of peak/trough, liquidity survival, flow acceleration/deceleration, and execution-quality deterioration where supported
- continue observing REJECT, WATCH, ENTER, dead, rugged, and otherwise untraded candidates long enough to produce useful labels, subject to data quality and free-provider limits
- deduplicate events and snapshots and preserve restart-safe ingestion checkpoints
- apply free-tier pacing/backpressure; provider exhaustion must degrade cadence or pause safely rather than silently require paid access
- keep the observer strictly read-only; it must not create or execute trade intents
- add tests for event ingestion, adaptive sampling, restart recovery, deduplication, and path/MFE/MAE label construction

Initial cadence targets may be seconds-level for the earliest/hottest period, tens-of-seconds later, then minute-level or slower as information value falls. Exact cadence values remain configuration/operational policy rather than trading-strategy constants.

**Exit criterion for Phase A:**  
Shreks can run unattended, observe Solana memecoins using only free sources, persist clean normalized event and snapshot data at sufficient resolution to reconstruct important intra-window pumps/dumps/liquidity and wallet behavior, produce standardized future labels, and recover after restart.

---

# PHASE B — SAFETY + TRADING BRAIN V0

## B1. Safety engine
Build deterministic safety checks with structured reasons.

Initial categories:

- authority risk
- liquidity
- concentration
- creator/deployer exposure
- stale/missing data
- route/exit availability
- execution hazards

## B2. Feature engine
Produce point-in-time versioned features.

Initial families:

- market quality
- flow
- momentum
- distribution/safety
- wallet features where available
- regime
- executability

## B3. Regime engine
Classify the overall memecoin environment into:

- HOT
- NORMAL
- WEAK
- DEAD

Keep V0 explainable.

## B4. Setup engine
Implement initial explicit setups:

1. Fresh Launch Continuation
2. Graduation / Breakout
3. First Pullback
4. Smart Wallet Cluster when sufficient wallet data exists

## B5. Deterministic score
Combine interpretable subscores.

Weights and thresholds remain configuration.

## B6. Decision engine
Produce:

- REJECT
- WATCH
- ENTER
- HOLD
- REDUCE
- EXIT

Each with structured reasons and version information.

## B7. Risk engine
Enforce:

- max size
- max capital %
- max concurrent positions
- max aggregate risk
- daily loss limit
- rolling drawdown limit
- cooldowns
- min liquidity
- max price impact
- max slippage
- health halts
- idempotency
- kill switch

**Exit criterion for Phase B:**  
Given historical/live snapshots, Shreks can reproducibly decide whether a candidate is safe, identify a setup, score it, and create or reject a trade intent without touching money.

---

# PHASE C — AUTONOMOUS PAPER TRADING

## C1. Paper execution adapter
Consume the exact `TradeIntent` interface intended for live execution.

## C2. Realistic fill simulator
Model:

- contemporaneous quote
- slippage
- network/swap cost assumptions
- latency
- failed fill
- partial fill where meaningful
- exit liquidity constraints

## C3. Position ledger
Maintain authoritative positions.

Support:

- weighted entry
- quantity
- realized PnL
- unrealized PnL
- accumulated costs
- lifecycle state

## C4. Exit engine
Implement configurable:

- hard stop
- take profit
- partial take profit
- trailing stop
- max hold time
- flow deterioration
- momentum deterioration
- wallet-distribution exit
- liquidity emergency exit
- global halt exit

## C5. Autonomous loop
Shreks now operates unattended:

`observe -> filter -> score -> decide -> size -> paper buy -> monitor -> paper sell -> record`

## C6. Accounting validation
Ensure portfolio values reconcile after:

- partial exits
- multiple positions
- losses
- wins
- failed fills
- restarts

**Exit criterion for Phase C:**  
Shreks can paper trade autonomously for extended periods using realistic market conditions, while preserving a complete and reconcilable trade history.

---

# PHASE D — WALLET INTELLIGENCE + RESEARCH DATA

## D1. Wallet observation store
Record relevant wallet actions around candidates.

## D2. Wallet trade reconstruction
Estimate entries/exits/outcomes where possible without pretending uncertain reconstruction is exact.

## D3. Wallet profiles
Build confidence-weighted histories:

- sample size
- entry quality
- median outcome
- rug exposure
- timing
- drawdown
- regime behavior

## D4. Independence / clustering heuristics
Avoid counting clearly linked wallet behavior as many independent confirmations where evidence suggests coordination.

Treat this probabilistically.

## D5. Smart-wallet features
Expose wallet intelligence to the feature engine.

## D6. Research dataset export
Generate point-in-time-safe Parquet datasets containing both traded and rejected/observed candidates.

**Exit criterion for Phase D:**  
Shreks has a proprietary wallet/market research dataset suitable for evaluating whether wallet behavior actually improves trading results.

---

# PHASE E — EVALUATION + LEARNING

## E1. Backtest/replay engine
Replay decisions using only data available at each historical timestamp.

## E2. Baselines
Create simple baselines so a complex model has something meaningful to beat.

Examples:

- deterministic V0
- random/naive setup baselines where useful
- simple threshold variants

## E3. Model training pipeline
Begin with practical tabular models rather than exotic AI.

Candidate families can include:

- logistic regression baselines
- tree-based models
- gradient boosting

Do not begin with reinforcement learning.

## E4. Time-aware validation
Split data chronologically to prevent leakage.

## E5. Trading evaluation
Measure:

- net expectancy
- profit factor
- drawdown
- average win/loss
- win rate
- turnover
- costs
- calibration
- setup performance
- regime performance

## Mandatory observation upgrade before E6

Before beginning E6, complete **A10 Observer V2 — high-resolution lifecycle capture**.

Reason: continuous real-market observation should begin accumulating proprietary token-path history as early as practical. Once A10 is verified, its read-only collector may run continuously while E6-E8 and later paper/shadow work continue.

A10 does not relax any live-money gate. It is observation/data collection only.

## E6. Champion / Challenger registry
Persist:

- model/strategy version
- training window
- feature schema
- evaluation results
- promotion status

## E7. Shadow/paper challenger
A challenger observes current conditions and generates decisions without controlling real money.

## E8. Promotion rules
Promotion must be an explicit recorded operation based on evaluation gates.

**Exit criterion for Phase E:**  
Shreks can scientifically compare strategy/model versions and reject false improvements caused by overfitting or leakage.

---

# PHASE F — LIVE AUTONOMOUS EXECUTION

This phase remains disabled until prior proof exists.

## F1. Rust live executor
Consume validated `TradeIntent`.

## F2. Jupiter transaction path
Implement:

- fresh quote
- route validation
- transaction construction
- signing
- submission
- confirmation
- reconciliation

## F3. Secret management
Private key only through runtime secret storage/environment.

Never GitHub. Never ChatGPT.

## F4. Idempotency
Prevent duplicate execution.

## F5. Fail-closed execution checks
Recheck immediately before execution:

- mode
- health
- notional
- quote freshness
- price impact
- slippage
- duplicate state
- kill switch

## F6. Paper/live parity tests
Confirm live and paper execution use the same decision/risk intent path.

## F7. Tiny-capital live stage
When all promotion gates pass, begin with deliberately limited capital.

## F8. Live reconciliation
Compare intended execution against actual onchain balances/fills.

**Exit criterion for Phase F:**  
Shreks can autonomously buy and sell on Solana with strict limits, complete reconciliation, and no manual per-trade approval.

---

# PHASE G — OPERATIONS + DASHBOARD

Only after the trading machine works.

## G1. Operator dashboard
Useful views:

- system health
- current regime
- observed candidates
- rejected candidates
- open positions
- recent trades
- PnL
- drawdown
- strategy performance
- provider health
- model version

## G2. Kill switch / mode control
Modes:

- observe
- paper
- shadow
- live
- halted

## G3. Alerts
Alert only on meaningful operational/trading conditions.

## G4. Deployment hardening
Make the system restart-safe and suitable for continuous operation.

Do not choose paid infrastructure as a hidden requirement.

---

# DEFERRED UNTIL EVIDENCE REQUIRES IT

Do not build these early:

- multi-chain support
- leverage
- perps
- social/X dependency
- Telegram bot
- paid data sources
- expensive RPC
- custom onchain Solana program
- microservice sprawl
- Kafka
- Kubernetes
- reinforcement learning
- autonomous self-modification
- complex dashboards before strategy proof

---

# BUILD DISCIPLINE

For every implementation task:

1. read `SHREKS_MASTER_SOURCE_OF_TRUTH.md`,
2. identify the active phase,
3. inspect current repository state,
4. write or update tests first where practical,
5. implement the smallest correct unit,
6. run relevant tests,
7. verify no architecture drift,
8. commit coherent changes,
9. update docs if a durable decision changed.

Never claim a phase is complete without verification evidence.

---

# CURRENT POSITION

As of 2026-08-24:

- repository exists: `Dtwosam/Shreks`
- Rust + Python architecture is implemented
- Solana V1 and free-source-only constraints remain active
- Phases A-D and E1-E4 have verified implementations
- E5 Trading Evaluation behavior is implemented and verified; documentation sealing is in progress
- the master source of truth now requires high-resolution continuous token-path observation
- **next mandatory implementation after the E5 seal: A10 Observer V2 — high-resolution lifecycle capture**
- after A10 is verified and the collector can accumulate data continuously, continue with E6 Champion / Challenger registry

Do not skip A10 and go directly from E5 to E6.
