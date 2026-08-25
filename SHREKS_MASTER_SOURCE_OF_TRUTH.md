# SHREKS — MASTER SOURCE OF TRUTH

**Project:** Shreks  
**Repository:** `Dtwosam/Shreks`  
**Primary chain:** Solana  
**System type:** Autonomous memecoin trading system  
**Architecture:** Rust + Python  
**Status:** Implementation in progress; architecture controlled by this source of truth  
**Last updated:** 2026-08-25

---

## 1. Purpose

Shreks is an autonomous Solana memecoin trading system.

Its final job is to:

1. discover memecoins,
2. reject unsafe or untradeable tokens,
3. analyze market and wallet behavior,
4. identify valid trading setups,
5. decide whether to enter,
6. size the position,
7. execute the buy automatically,
8. monitor the open position,
9. execute partial or full exits automatically,
10. record the result,
11. learn from observed markets and completed trades,
12. improve future decisions through controlled model evaluation.

The final product is **not a signal bot**. In live mode, Shreks will be authorized to buy and sell without requiring human approval for each trade.

Shreks is not designed around finding the next 100x token. Its objective is to develop **positive trading expectancy after real costs** by repeatedly making better decisions about:

- whether to trade,
- when to enter,
- how much to risk,
- when to exit,
- when to do nothing.

Profit is never assumed or guaranteed.

---

## 2. Non-Negotiable Requirements

These requirements must not be changed casually.

### 2.1 Autonomous execution
The final live system buys and sells by itself. Manual confirmation per trade is not part of the target architecture.

### 2.2 Solana only for V1
Do not add Ethereum, Base, BNB Chain, or other chains until the Solana system is proven.

### 2.3 Free external sources only
V1 must not require paid APIs, paid data subscriptions, or premium market-data plans.

Allowed:

- free API tiers,
- free RPC tiers,
- public blockchain data,
- self-derived data,
- open-source software.

Actual trading costs are allowed and must be measured:

- network fees,
- swap fees,
- priority fees/tips if enabled,
- slippage,
- price impact.

If a free source reaches its allowance or becomes unavailable, Shreks must degrade or pause safely rather than silently switch to paid usage.

### 2.4 No live trading before proof
Real-money trading stays disabled until the paper-trading system meets explicit promotion criteria.

### 2.5 One decision path
Paper and live modes use the same:

- feature calculations,
- strategy logic,
- scoring,
- risk logic,
- position management,
- exit logic.

Only the execution adapter changes.

### 2.6 Fail closed
If critical market, safety, risk, quote, or execution information is stale, missing, contradictory, or unreliable, Shreks does not open a new trade.

### 2.7 Secrets never enter source control
Private keys, seed phrases, API secrets, and wallet secrets must never be committed to GitHub or pasted into ChatGPT.

### 2.8 Learning cannot directly control live money
A newly trained model cannot silently replace the live strategy.

New models are challengers. They must be evaluated, tested on unseen data, and paper/shadow traded before promotion.

### 2.9 Everything important is auditable
Every candidate and every trade must preserve enough information to reconstruct:

- what data Shreks saw,
- what features it calculated,
- what safety rules fired,
- which strategy/setup was considered,
- the score,
- the risk decision,
- execution/fill information,
- the exit reason,
- final PnL and costs,
- strategy/model versions.

---

## 3. Core Trading Loop

The high-level trading loop is:

`WATCH -> FILTER -> SCORE -> DECIDE -> SIZE -> BUY -> MONITOR -> SELL -> RECORD -> LEARN -> REPEAT`

A separate continuous observation loop runs whether or not a token is traded:

`DISCOVER -> STREAM EVENTS -> SNAPSHOT -> TRACK PATH -> LABEL OUTCOMES -> DATASET`

Shreks must watch far more tokens than it trades.

**Rejection is a valid and important outcome.**

Observation must not stop when a candidate is rejected. Where data quality and provider limits permit, rejected, watched, entered, dead, rugged, and otherwise untraded candidates remain observable long enough to create useful future-outcome labels.

---

## 4. Technology Architecture

### 4.1 Rust = Eyes + Hands

Rust owns Solana-facing and latency-sensitive responsibilities:

- Solana/RPC ingestion,
- persistent market/event connections,
- fast provider adapters where appropriate,
- normalized market event creation,
- execution integration,
- transaction construction,
- transaction signing,
- submission,
- confirmation,
- balance/fill reconciliation,
- live execution guardrails.

Rust does **not** decide which memecoin to trade.

### 4.2 Python = Brain

Python owns research and decision intelligence:

- feature engineering,
- token safety analysis,
- wallet intelligence,
- setup detection,
- deterministic scoring,
- strategy logic,
- risk and position sizing,
- paper execution,
- exit logic,
- backtesting,
- dataset generation,
- model training,
- model evaluation,
- champion/challenger comparison.

### 4.3 Shared state and durable storage

V1 starts simple:

- **SQLite in WAL mode** is the authoritative operational recovery store for state that the running system must survive across process or host restarts. This includes provider health, observer/event-ingestion checkpoints, candidate lifecycle state, normalized observations, safety/quote evidence needed by active flows, paper/live positions and ledgers, processed intent/idempotency state, risk/mode/kill-switch state, campaign/evaluation evidence references, and durable checkpoint metadata.
- **Parquet** is the durable historical/research format for larger point-in-time datasets, feature/training exports, wallet research, outcome labels, and reproducible evaluation inputs. Research exports must retain schema/version information and must include rejected and untraded candidates where data quality permits.
- Evidence/checkpoint files may be used where an approved phase requires immutable artifacts, but they must be written atomically, versioned or content-addressed where appropriate, and either referenced by authoritative operational state or reproducibly derivable from it.
- Logs and dashboards are observability surfaces, **not authoritative state**. A restart must not depend on reconstructing trading or risk state from logs.

Operational data may later be compacted or archived only after the information required for recovery, audit, labels, accounting, and reproducible research has been preserved. Do not silently discard or rewrite history that an evaluation or proof record depends on.

Do not introduce Redis, Kafka, Kubernetes, or a hosted database unless real operating evidence shows they are necessary.

### 4.4 Production runtime and GitHub boundary

GitHub is the source-control, review, CI, release, and deployment control plane. It is **not** the machine that continuously observes markets or trades.

The initial production architecture should run Shreks 24/7 on **one dedicated Linux host/VPS** with persistent storage. Rust observer/execution services, Python brain/paper-or-live runner, operational SQLite, checkpoints/evidence, and monitoring agents may coexist on that host for V1. Process supervision may use `systemd` or Docker Compose; the exact supervisor/provider is an operational choice, not a strategy dependency.

The host must restart services after reboot/crash and remount the same durable state before autonomous operation resumes. Splitting into multiple hosts or managed data services is deferred until measured load, reliability, or security evidence requires it.

Runtime wallet/signing secrets are injected only on the execution host through protected runtime secret handling. They never belong in GitHub source, repository history, ChatGPT, research exports, logs, or dashboard payloads.

---

## 5. Initial Free Data / Execution Sources

The initial provider strategy is adapter-based so external sources can be replaced later.

### Helius / Solana RPC
Primary uses:

- Solana chain data,
- transactions,
- account activity,
- token/account state,
- authority data,
- wallet observations,
- persistent Solana event access where available within free limits.

### DEX Screener
Primary uses:

- token/pair discovery and enrichment,
- price,
- liquidity,
- volume,
- buy/sell transaction counts,
- pair age,
- market snapshots.

### Jupiter
Primary uses:

- executable route/quote information,
- price-impact checks,
- eventual automatic swap execution.

### Direct Solana data
Whenever a reliable signal can be derived directly from public chain data without paying a third party, prefer the direct calculation.

### Provider rule
Provider responses are inputs, not Shreks' internal domain model.

Every provider adapter converts external responses into Shreks-owned normalized types.

---

## 6. Primary Domain Objects

### TokenCandidate
A discovered mint/pair Shreks may observe.

Contains at minimum:

- token mint,
- discovery timestamp,
- discovery source,
- relevant pair/pool identifiers,
- lifecycle status.

### MarketEvent
A timestamped market/onchain event relevant to an observed candidate.

Examples include:

- swap/buy/sell,
- liquidity add/remove,
- creator/deployer action,
- large-wallet action,
- authority/supply change,
- pool/account state change,
- route/executability change.

Where available, preserve enough event-level information to reconstruct important intra-window behavior instead of relying only on sparse periodic snapshots.

### MarketSnapshot
Point-in-time market state and rolling-path summary.

Possible fields include:

- timestamp,
- price,
- market cap/FDV when reliable,
- liquidity,
- volume by time window,
- buys/sells,
- buy/sell volume imbalance,
- unique buyer/seller counts or growth,
- price change windows,
- rolling/local high and low,
- maximum favorable/adverse excursion so far,
- pair/token age,
- holder observations,
- wallet-entry/exit summaries,
- creator/deployer activity,
- quote/route quality,
- estimated price impact where available,
- data source,
- freshness.

### SafetyAssessment
Structured result of safety checks.

Includes:

- hard-reject flags,
- authority risks,
- concentration data,
- creator/deployer exposure,
- suspicious supply behavior,
- liquidity adequacy,
- abnormal transfers,
- execution hazards,
- confidence,
- reasons.

Safety has veto power.

### WalletObservation
An observed wallet action relevant to a candidate:

- buy,
- sell,
- transfer,
- liquidity event,
- creator/deployer action,
- other classified behavior.

### WalletProfile
An evolving history of a wallet's observed trading behavior.

Examples:

- observations/trades,
- entry timing,
- median outcome,
- estimated expectancy,
- drawdown behavior,
- rug exposure,
- sample size,
- confidence.

Scores must be confidence-weighted. A wallet with two lucky trades cannot rank like one with hundreds of useful observations.

### FeatureVector
The reproducible point-in-time features used by a strategy/model.

Must include:

- timestamp,
- feature schema version,
- market features,
- safety features,
- flow features,
- wallet features,
- momentum features,
- liquidity/execution features,
- regime features.

### TradeDecision
Possible actions:

- `REJECT`
- `WATCH`
- `ENTER`
- `HOLD`
- `REDUCE`
- `EXIT`

Every decision has structured reasons and strategy/model version.

### TradeIntent
A validated execution request.

Contains:

- token,
- side,
- requested size,
- slippage ceiling,
- strategy/model version,
- reason,
- idempotency key,
- execution mode.

### Position
Authoritative state of a position.

Contains:

- token,
- quantity,
- weighted entry,
- current state,
- realized PnL,
- unrealized PnL,
- accumulated costs,
- stop state,
- trailing state,
- lifecycle state.

---

## 7. Token Discovery and Continuous Observation

Shreks must not blindly buy brand-new launches in the first seconds.

V1 is not a pure sniper.

The first goal is to **watch broadly, preserve the path, and reject aggressively**.

Every useful discovered token should be observed even when it is never traded. Pumps are only one outcome class. The research system must also preserve dumps, rugs, failed pumps, dead/flat tokens, recoveries, slow grinders, pump-consolidation-second-leg behavior, and pump-distribution behavior.

### 7.1 Outcome checkpoints are labels, not the observation cadence

For observed candidates, standard future outcomes are recorded at:

- 1 minute,
- 5 minutes,
- 15 minutes,
- 30 minutes,
- 1 hour,
- 4 hours,
- 24 hours.

These checkpoints are standardized research labels. They must **not** be the only times Shreks observes a token. Sparse checkpoint-only storage can miss a pump, dump, liquidity disappearance, wallet exit, or other critical path event that happens between two checkpoints.

### 7.2 Three-layer observation model

The observer should combine three layers:

1. **Event-level or near-event-level capture**
   - swaps/buys/sells where available,
   - meaningful liquidity changes,
   - large-wallet activity,
   - creator/deployer activity,
   - important account/supply/authority changes,
   - route/executability changes.

2. **Short-interval rolling snapshots**
   - price, liquidity, market cap/FDV when reliable,
   - rolling volume and transaction counts,
   - buy/sell imbalance and net flow,
   - unique buyer/seller behavior,
   - high/low and path statistics,
   - wallet-entry/exit summaries,
   - execution quality and price impact,
   - data freshness/confidence.

3. **Standard future-outcome labels**
   - checkpoint return,
   - maximum favorable excursion (MFE),
   - maximum adverse excursion (MAE),
   - time to peak,
   - time to worst drawdown where measurable,
   - liquidity and volume change,
   - buyer/seller change,
   - rug/dead-pool condition,
   - whether a realistic exit was available,
   - other path summaries required by approved research schemas.

### 7.3 Adaptive sampling

Snapshot frequency should be adaptive rather than identical for every token.

A newly launched, volatile, or rapidly changing token should be observed at high resolution. A quiet or dead token can be sampled less frequently while still preserving required labels and critical events.

Initial operational targets may resemble:

- first ~15 minutes: seconds-level snapshots where provider limits permit,
- ~15 minutes to 1 hour: tens-of-seconds resolution,
- ~1 to 4 hours: roughly minute-level resolution,
- later observation: progressively lower frequency.

These are operating targets, **not hard-coded strategy constants**. Provider limits, measured information value, and storage cost may change the exact cadence.

Sampling should automatically increase when meaningful activity accelerates, including sharp price movement, volume acceleration, liquidity change, wallet clustering, creator activity, or execution-quality deterioration.

### 7.4 Preserve the path, not only the endpoint

A token that moves from `$100k -> $400k -> $60k` between two checkpoints is materially different from a token that simply moves `$100k -> $60k`. The dataset must preserve enough high-frequency/event-derived information to distinguish those paths.

Research labels must therefore capture path-dependent facts such as MFE, MAE, time-to-peak, time-to-drawdown, liquidity survival, and realistic exit quality whenever the underlying observations support them.

### 7.5 Rejected and untraded tokens are first-class data

Rejected tokens must remain in the research dataset where data quality permits. WATCH candidates and tokens that never become trades must also remain represented.

This reduces selection bias and lets Shreks learn both:

- which apparent opportunities should have been avoided, and
- which filters repeatedly reject genuinely tradable opportunities.

The learning problem is not simply **"will this token pump?"**

The intended question is closer to:

> Given everything observable at this timestamp, what future path is likely, what is the upside/downside distribution, how does liquidity/executability evolve, and is there a realistic positive-expectancy trade after costs?

### 7.6 Collection durability, identity, and retention

Continuous collection is valuable only if later research can prove what was known at each timestamp. Persisted observation records therefore need stable candidate/event identity, source timestamp where available, Shreks ingestion/observation timestamp, normalized schema/version context, and freshness/confidence or provider-health context when it affects interpretation.

Restart-safe collection must resume from durable checkpoints and deduplicate replayed provider events or already-processed observation work. A restart must not create duplicate trades, duplicate labels, or materially different history merely because the same provider data was seen twice.

Point-in-time history should be treated as append-oriented evidence. Corrections, backfills, normalization upgrades, or research re-exports must be explicit and versioned rather than silently rewriting the data that earlier decisions or evaluations consumed.

As volume grows, hot operational records may be compacted or archived, but only after required recovery state and research/audit fields are durably preserved in approved historical storage. Provider limits and storage pressure may reduce sampling frequency; they must not silently convert continuous/path-aware collection back into sparse checkpoint-only collection.

---

## 8. Safety Layer

Safety runs before strategy scoring.

### Potential hard rejects

Exact thresholds are configuration and will be calibrated later.

Examples:

- dangerous token authority state under active policy,
- liquidity below executable minimum,
- holder/supply concentration above a hard ceiling,
- inability to obtain a reliable exit route/quote,
- stale critical data,
- contradictory critical data,
- detected execution trap,
- active global risk halt.

A high momentum score can never override a hard safety rejection.

### Soft safety factors

Examples:

- creator concentration,
- suspicious holder clustering,
- weak holder distribution,
- liquidity deterioration,
- unusual transfers,
- uncertain wallet data,
- questionable route quality.

Soft risks reduce score or confidence instead of automatically rejecting the token.

Every rule returns structured reasons for later evaluation.

---

## 9. Feature Families

V0 begins with deterministic and explainable features.

### Market quality
- liquidity level,
- liquidity change,
- pair/token age,
- quote quality,
- estimated price impact,
- route availability.

### Flow
- buy/sell count ratio,
- buy/sell volume imbalance when derivable,
- unique buyer growth,
- unique seller growth,
- net flow,
- flow acceleration/deceleration.

### Momentum / path dynamics
- short-window return,
- return acceleration,
- volume acceleration,
- breakout behavior,
- pullback structure,
- distance from recent local extremes,
- recent high/low path,
- volatility/velocity where useful,
- time since local peak/trough,
- MFE/MAE-so-far features when point-in-time safe.

### Wallet quality
- number of independently strong wallets entering,
- weighted wallet quality,
- smart-wallet clustering,
- strong-wallet exits,
- creator/deployer activity.

### Distribution/safety
- top-holder concentration,
- creator exposure,
- authority state,
- concentration change,
- liquidity concentration.

### Market regime
Initial labels:

- `HOT`
- `NORMAL`
- `WEAK`
- `DEAD`

Regime can affect which strategies are allowed to trade.

All features must be point-in-time safe. Never train on information that did not exist at the decision timestamp.

---

## 10. Initial Trading Setups

V0 starts with a small number of explicit setups.

### 10.1 Fresh Launch Continuation
Avoid blind first-second sniping.

Look for evidence that real demand persists after initial launch noise.

### 10.2 Graduation / Breakout
Look for a token moving from random launch behavior into stronger liquidity, participation, and price structure.

### 10.3 First Pullback
Look for:

- strong initial move,
- controlled retracement,
- seller absorption,
- renewed demand.

### 10.4 Smart Wallet Cluster
Look for several independent historically strong wallets entering within a meaningful time window.

Each setup must produce:

- eligibility,
- features,
- score,
- reasons,
- invalidation conditions.

Each strategy must be independently measurable and independently disableable.

---

## 11. V0 Scoring

The first scorer is deterministic.

Possible score families:

- safety,
- money flow,
- wallet quality,
- momentum/setup quality,
- liquidity/executability.

Initial weights and entry thresholds are **hypotheses**, not claims of profitability.

They must be calibrated from observation and paper trading.

No score bypasses hard safety or risk controls.

---

## 12. Risk Engine

Risk logic is independent of strategy confidence.

The risk engine must support:

- max notional per position,
- max % of trading capital per position,
- max simultaneous positions,
- max aggregate open risk,
- max daily realized loss,
- max rolling drawdown,
- cooldown after consecutive losses,
- minimum liquidity,
- max expected price impact,
- max slippage,
- duplicate-intent protection,
- health-based new-entry pause,
- global kill switch.

Uncertainty about a critical guardrail means **no new entry**.

---

## 13. Paper Trading

Paper mode is fully autonomous.

It receives the same `TradeIntent` that live execution will later receive.

The paper adapter must simulate realistic costs and constraints:

- slippage,
- swap/network costs,
- latency,
- route/quote conditions,
- partial or failed fills where appropriate,
- limited exit liquidity.

Paper performance that assumes perfect fills or impossible exits is invalid.

Paper mode must support the full position lifecycle:

- entry,
- partial reduction,
- take profit,
- stop loss,
- trailing stop,
- emergency exit,
- final close.

---

## 14. Exit Engine

Exits are first-class decisions.

V0 can combine:

- hard stop loss,
- take-profit levels,
- partial profit taking,
- trailing stop,
- maximum holding time,
- flow deterioration exit,
- momentum deterioration exit,
- strong-wallet distribution exit,
- liquidity deterioration exit,
- global-risk exit.

Every exit records one primary reason plus supporting signals.

Exit policies must later be compared by realized expectancy rather than assumed to be optimal.

---

## 15. Live Execution

Live execution is a Rust adapter.

It executes approved `TradeIntent` objects. It does not invent trades.

Before sending a transaction it must:

1. confirm live mode is allowed,
2. verify idempotency,
3. recheck notional/risk constraints,
4. obtain a fresh executable quote/route,
5. recheck slippage and price impact,
6. reject materially changed conditions,
7. construct and sign,
8. submit,
9. record the signature,
10. confirm,
11. reconcile actual balances/fills.

The live trading wallet should hold only capital deliberately allocated to Shreks.

---

## 16. Learning System

The system learns from:

1. all sufficiently observed candidates,
2. rejected and never-traded candidates,
3. full observed token paths including pumps, dumps, rugs, dead tokens, failed breakouts, recoveries, and slow trends,
4. wallet/creator activity sequences where attribution and data quality permit,
5. paper trades,
6. later, live trades.

The learning loop is:

`DISCOVER -> CONTINUOUS OBSERVE -> FEATURE SNAPSHOT -> DECISION -> PATH/FUTURE OUTCOME -> DATASET -> TRAIN -> VALIDATE -> PAPER/SHADOW -> COMPARE -> PROMOTE OR REJECT`

Continuous data collection should begin as soon as the read-only observer is operational and may run in parallel with later research/promotion implementation phases. Every day of correctly timestamped observation adds proprietary history that is difficult to reconstruct perfectly after the fact.

### What the system optimizes
Do not optimize for win rate alone.

Primary evaluation metrics:

- expectancy after costs,
- profit factor,
- maximum drawdown,
- average winner,
- average loser,
- win rate,
- calibration,
- performance by setup,
- performance by market regime,
- turnover,
- cost burden.

### Champion / Challenger

**Champion:** currently approved strategy/model.

**Challenger:** new candidate strategy/model.

A challenger must:

- use valid point-in-time data,
- pass schema/data-quality checks,
- be evaluated on unseen data,
- beat required baselines,
- remain within drawdown/risk limits,
- avoid relying on one tiny period or a few extreme winners,
- run in paper/shadow mode,
- satisfy promotion rules.

A challenger never promotes itself automatically.

---

## 17. Wallet Intelligence

Wallet intelligence becomes more valuable over time.

The system should learn behavioral histories such as:

- how early a wallet tends to enter,
- how often its entries precede profitable moves,
- whether entries cluster before pumps, failed pumps, or rugs,
- when the wallet begins reducing/exiting relative to local peaks and drawdowns,
- typical hold time,
- median trade outcome,
- average/median drawdown,
- rug exposure,
- behavior during different regimes,
- whether its activity is independent or linked to other wallets.

Avoid simplistic "whale bought = bullish" logic.

The intended future signal is closer to:

> Several independent wallets with meaningful, statistically credible histories are accumulating the same token under favorable market conditions.

Wallet identity heuristics must be treated as uncertain, not factual, when attribution is not provable.

---

## 18. System Health and Recovery

Shreks must be able to survive:

- provider rate limits,
- provider downtime,
- malformed responses,
- stale responses,
- process restarts,
- temporary network failures,
- duplicate events,
- duplicate intents,
- partial execution failures,
- transaction confirmation uncertainty.

Critical health degradation pauses new entries.

State must be recoverable after restart from the operational database and onchain truth where necessary. At minimum, recovery must preserve or reconstruct consistently:

- last durable observer/event-ingestion checkpoints,
- active candidate/observation scheduling state where needed to continue labels,
- open paper/live positions and the authoritative position ledger,
- realized/unrealized accounting state and accumulated costs,
- processed intent/idempotency identifiers,
- current risk, mode, halt, and kill-switch state,
- paper-campaign/evaluation evidence required by the active proof phase,
- latest durable checkpoint/evidence references.

A restarted process must reconcile this state before new entries are allowed. In live mode, local execution/accounting state must be reconciled against onchain balances, signatures, and confirmed fills where necessary. Monitoring may report the problem, but it must never substitute for the recovery/reconciliation path itself.

---

## 19. Testing Philosophy

Testing is mandatory before live money.

Required categories eventually include:

- Rust unit tests,
- Python unit tests,
- provider adapter tests,
- continuous-observer/event-ingestion tests,
- adaptive-sampling tests,
- path/MFE/MAE outcome-label tests,
- normalization tests,
- schema/migration tests,
- point-in-time feature tests,
- safety rule tests,
- strategy tests,
- risk tests,
- paper fill simulation tests,
- exit tests,
- restart/recovery tests,
- idempotency tests,
- paper/live parity tests,
- model data-leakage tests,
- backtest/evaluation tests,
- live execution dry-run tests.

Use test-driven development for implementation tasks.

---

## 20. Live Promotion Gate

Live trading remains disabled until Shreks demonstrates:

- sufficient independent paper-trade sample size,
- positive expectancy after realistic costs,
- acceptable drawdown,
- stable provider/restart behavior,
- no unresolved accounting defects,
- no unresolved execution defects,
- paper/live decision-path parity,
- reliable risk halts,
- realistic fill simulation,
- reproducible evaluation.

The exact numeric thresholds will be defined using data rather than invented prematurely.

Initial real-money deployment, when reached, must use deliberately limited capital and strict risk caps.

---

## 21. Production Operations and Monitoring Architecture

This layer is required for the finished autonomous system, but implementation remains sequenced **after the trading/proof path is sealed enough to justify operating infrastructure**. Monitoring must make Shreks understandable and controllable without becoming a second trading brain or an authoritative state store.

### 21.1 GitHub is the control plane, not the runtime

GitHub remains responsible for:

- source code,
- pull requests and review,
- automated tests and CI history,
- release history,
- sealed proof phases and immutable verification points,
- deployment workflows,
- rollback points.

The intended delivery path is:

`code change -> PR -> tests GREEN -> approved/sealed release -> deploy to Shreks host -> host runs 24/7`

GitHub must not be treated as the continuously running trading machine.

### 21.2 Initial production host

For the first production deployment, Shreks should run on **one dedicated Linux VPS/host with persistent storage**, preferably in Europe unless measured network/provider behavior gives a reason to choose another region. An Ubuntu-class Linux host is a suitable baseline.

The initial host may contain:

- `shreks-observer` / Rust observer,
- safety-evidence collection,
- Python paper/live runner and decision brain,
- risk engine runtime,
- SQLite operational database,
- Parquet/research storage and exports,
- evidence/checkpoint files,
- monitoring/telemetry agent,
- backup/recovery jobs.

Services should be supervised by `systemd` or Docker Compose and automatically restart after process failure or host reboot. The exact supervisor, VPS vendor, and dashboard technology are operational choices, not trading-strategy dependencies.

### 21.3 Operator dashboard

The operator must not need to SSH into the host and manually inspect logs to understand normal operation. A private authenticated dashboard should be provided, for example at a private domain such as `https://shreks.<operator-domain>` once deployment exists.

The top-level dashboard should expose at least four classes of information.

**System**

- running/halted state,
- uptime,
- observer health,
- provider health including Helius/Jupiter and other active providers,
- market-data age/freshness,
- last durable checkpoint,
- restart count/recent recovery state,
- CPU/RAM/disk where useful,
- accounting reconciliation state.

**Trading**

- operating mode: observe / paper / shadow / live / halted,
- candidates observed/discovered,
- candidates passing safety,
- decisions generated,
- trades entered,
- open positions,
- recent entries/exits.

**Performance / Money**

- realized PnL,
- unrealized PnL,
- net expectancy after costs,
- profit factor,
- max drawdown,
- fees, slippage and other execution costs,
- capital deployed / exposure,
- daily realized loss.

**Proof / Risk**

- independent paper-trade count,
- distinct tokens/mints represented,
- time-span/evidence coverage,
- proof-gate state such as `INSUFFICIENT` / `SUFFICIENT`,
- promotion state,
- live-trading enabled/disabled state,
- kill-switch state,
- risk-halt state,
- E11/E12 evaluation/gate summaries and reproducibility status.

The dashboard may be implemented as a small Shreks UI, Grafana-backed view, or another lightweight authenticated operator surface. A large or sophisticated dashboard remains deferred until core performance evidence warrants it.

### 21.4 Per-trade explainability

The operator must be able to drill into an individual paper/live trade and reconstruct both **what Shreks did** and **why it did it**. The trade view should expose, where applicable:

- token/mint,
- observation/decision timestamp,
- why the setup became eligible,
- safety assessment and reasons,
- point-in-time feature vector/schema version,
- regime,
- setup,
- score,
- decision and structured reasons,
- risk sizing,
- entry quote and quote purpose,
- simulated or actual fill,
- position-management decisions,
- exit reason,
- fees,
- slippage/price impact,
- realized PnL,
- strategy/model version,
- relevant evidence/checkpoint references.

A monitoring UI must not invent explanations that are absent from durable decision evidence.

### 21.5 Alerts and phone notifications

The dashboard is for inspection; important operational or trading events should be pushed automatically. Alert conditions should include at least:

- Shreks process/service stopped unexpectedly,
- market data became materially stale,
- Helius/Jupiter/other required provider failure persists,
- database/checkpoint/evidence-store failure,
- accounting no longer reconciles,
- risk kill switch activates,
- daily-loss or drawdown halt activates,
- a paper/live position opens,
- a paper/live position closes with its PnL and costs,
- unusually bad fill/slippage/price-impact behavior,
- paper proof becomes sufficient under the active gate,
- a challenger fails or is rejected by proof/evaluation,
- eventually, any live-money transaction or execution/reconciliation anomaly.

Telegram is a practical first alert transport. Email, Discord, or Slack may be added or substituted. This is **alerting only**; a Telegram trading UI or command surface remains out of scope unless separately approved.

### 21.6 Emergency operator controls

When live mode is eventually allowed, the dashboard must make live state unmistakable. Before promotion it should visibly show that live trading is disabled. Once live is legitimately enabled, operator controls should include at least:

- `HALT NEW ENTRIES`,
- `EMERGENCY KILL SWITCH`.

These controls must write through the controlled runtime/risk authority path. The dashboard must never bypass the risk engine, construct trades independently, or mutate authoritative accounting directly.

### 21.7 Four monitoring layers

Operational monitoring should remain conceptually separated into:

1. **System** — uptime, CPU/RAM/disk, provider health, freshness, restarts, checkpoints.
2. **Trading** — observations, scores, decisions, entries, position management, exits.
3. **Money** — PnL, fees, slippage, drawdown, exposure, reconciliation.
4. **Proof/Risk** — sample size, expectancy, E12 gates, halts, accounting integrity, promotion/live state.

This separation is intended to answer both: **"is Shreks technically healthy?"** and **"is it making money safely and with enough proof?"**

### 21.8 Crash/restart recovery contract

If the runtime host dies and restarts, the recovery path must restore or reconcile, at minimum:

- last observer/event-ingestion state,
- open paper/live positions,
- authoritative ledger/accounting,
- processed intent/idempotency IDs,
- risk state and active halts,
- mode / live-enable state,
- E11/evaluation evidence needed by the active campaign,
- latest durable checkpoint,
- provider-health/freshness context where needed,
- onchain truth for live positions/balances where applicable.

The required invariant is that a normal crash/restart does **not** erase Shreks' memory, duplicate its actions, silently change accounting, or corrupt proof/research history. Autonomous new entries must remain paused whenever recovery or reconciliation is uncertain.

### 21.9 Backups and recovery

The operations layer must eventually include durable backups for operational SQLite state, evidence/checkpoint artifacts, configuration required for recovery, and historical/research datasets that cannot be reconstructed safely from providers. Backup restoration must be tested before live money is enabled. Secrets must follow separate protected-runtime handling and must not be copied into normal research or telemetry archives.

### 21.10 Operational build sequence

The current trading/proof path remains:

`observer -> evidence -> strategy decision -> paper execution -> restart -> evaluation -> proof`

After that path is sealed and a real paper campaign can run, the next major operational layer is:

`deployment -> 24/7 supervisor -> telemetry -> dashboard -> alerts -> backup/recovery`

This operations work must support the proof campaign and eventual live execution without changing the proven strategy/risk decision path.

---

## 22. Current Verified Implementation and Proof Position

**Status date:** 2026-08-25

Shreks is near the point where the engineering bottleneck changes from building proof machinery to collecting and evaluating real paper performance. It has **not** yet demonstrated that it makes money. Live money remains disabled.

### 22.1 E15 status

The active workstream is **Phase E15 — Observer Paper Campaign**, stacked on sealed E14. At the point Task 7 completed, the E15 code head was `45e454cd7aa21a23d4f7ff52f21752b2fa8b07d3`. CI run `32879194087` was fully GREEN with **2220 Python tests passing in 8.63s**, Rust/workspace GREEN, and repository safety GREEN. Tasks 1–7 were therefore effectively complete at that verified checkpoint.

A later documentation-only commit `f43550b3c0609b75d263ccce0c1421cdf39e0c4f` added the runtime/data-persistence architecture to this source of truth and also passed CI (`32880782381`). Documentation commits after the Task-7 code checkpoint do not themselves complete E15 Task 8 or change the proven trading behavior.

### 22.2 What remains to seal E15

E15 Task 8 remains the immediate engineering task. It includes:

1. add the restricted `observer_campaign` public API,
2. test the authority firewall,
3. freeze the behavior SHA,
4. audit every changed file from sealed E14 through E15,
5. write the final verification record,
6. make the one-document seal commit,
7. run fresh exact-seal CI,
8. update draft PR #39.

This is primarily verification, authority-boundary checking, auditing, and sealing rather than new strategy/trading logic.

### 22.3 Real paper campaign after E15

Once E15 is sealed, Shreks should begin accumulating **real independent paper trades from actual point-in-time observer data**, not synthetic fixtures. E15 is intended to turn real observer market+safety history into purpose-correct paper cycles while surviving restarts, preserving exact accounting, and producing E11 evaluation evidence.

The campaign must collect enough real evidence to evaluate the system honestly. It must not manufacture trades, reuse synthetic fixture performance as proof, or reduce thresholds merely to make a gate pass.

### 22.4 Evaluation of real evidence

Real paper evidence should flow through the already-built E10/E11/E12 evaluation/proof stack. Required evaluation includes, at minimum:

- positive or negative expectancy after realistic costs,
- profit factor,
- maximum drawdown,
- independent trade count,
- distinct token/mint count,
- evidence time span,
- cost burden,
- winner concentration / dependence on a few extreme winners,
- reproducible accounting,
- reproducible evaluation,
- setup/regime breakdowns where supported.

The exact numeric promotion thresholds must be evidence-based. They must not be invented or weakened merely to pass the live gate.

### 22.5 Remaining live-proof requirements before Phase F

Before Phase F live-money activation can be legitimate, Shreks still needs real evidence demonstrating:

- stable provider behavior and safe degradation,
- restart/recovery stability,
- realistic paper fill behavior,
- reliable risk halts and kill-switch behavior,
- execution/accounting integrity,
- no unresolved reconciliation defects,
- paper/live decision-path parity,
- reproducible evaluation and proof.

Only after those requirements are demonstrated should deliberately limited-capital live trading be considered.

### 22.6 Plain-English project position

The infrastructure is nearly ready to prove whether Shreks can develop a real edge, but profitability has **not** been proven. After the E15 seal, the main bottleneck becomes collecting and evaluating independent real paper performance rather than adding more speculative strategy complexity.

---

## 23. Scope Explicitly Deferred

Do not add these until core performance requires them:

- multi-chain trading,
- copy trading as the primary strategy,
- paid data feeds,
- paid RPC requirement,
- social/X sentiment dependency,
- Telegram trading UI,
- complex web dashboard,
- microservice sprawl,
- Kafka,
- Kubernetes,
- reinforcement learning,
- self-modifying live strategies,
- custom Solana onchain program,
- leverage,
- perpetual futures.

---

## 24. Source of Truth Hierarchy

When project documents conflict, use this order:

1. `SHREKS_MASTER_SOURCE_OF_TRUTH.md`
2. `SHREKS_BUILD_ORDER.md`
3. current approved implementation spec/plan in the repo
4. repository code and tests
5. chat messages

If implementation discoveries require changing architecture, update the source of truth deliberately instead of silently drifting.

---

## 25. Definition of Success

Shreks is successful when it can:

- continuously observe Solana memecoin markets at sufficient resolution to reconstruct important intra-window pumps, dumps, liquidity changes, and wallet behavior,
- adapt observation frequency to information value without losing required outcome labels,
- reject unsafe/untradeable situations,
- generate reproducible trading decisions,
- paper trade autonomously under realistic costs,
- measure its true expectancy and drawdown,
- learn from a growing proprietary dataset,
- safely evaluate improved challengers,
- execute live trades automatically only after proof,
- preserve capital through hard risk controls,
- explain why every trade was entered and exited,
- run continuously on a supervised production host rather than GitHub,
- recover durable observer/trading/risk/evidence state after crashes without duplicate actions,
- expose an authenticated operator view covering system, trading, money, and proof/risk state,
- push meaningful operational/trading alerts to the operator,
- provide controlled halt/kill-switch actions that cannot bypass the risk engine,
- preserve rollback/audit linkage between deployed behavior, GitHub release history, and evaluation evidence.

The goal is not an impressive dashboard.

The goal is a trading machine that can demonstrate a real, measurable edge before meaningful capital is exposed.
