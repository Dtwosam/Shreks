# Shreks Master Design

**Status:** Approved architecture, written for implementation review  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`

## 1. Purpose

Shreks is an autonomous Solana memecoin trading system. Its final operating mode will discover opportunities, reject unsafe tokens, decide whether to enter, size positions, execute buys, monitor open positions, execute exits, and learn from outcomes without requiring approval for each trade.

The system is not designed to predict the next 100x token. Its objective is to develop positive trading expectancy by repeatedly making better decisions about:

1. whether to trade,
2. when to enter,
3. how much to risk,
4. when to exit,
5. when not to trade.

Profit is not guaranteed. Memecoin markets are highly adversarial, illiquid, volatile, and vulnerable to manipulation. Shreks must therefore optimize for survival and measured expectancy before live-money deployment.

## 2. Non-Negotiable Requirements

1. **Autonomous execution:** live mode must be able to buy and sell without per-trade human approval.
2. **Solana only for V1:** no multi-chain scope until the Solana system is proven.
3. **Free market/data sources only:** Shreks may use free API/RPC tiers and direct public Solana data. It must not require a paid data subscription to operate V1.
4. **Trading costs are allowed:** network fees, swap fees, priority fees/tips if enabled, and slippage are real trading costs and must be included in performance calculations.
5. **No live trading before proof:** live execution remains disabled until the paper-trading system has passed explicit promotion criteria.
6. **No private key in source control or chat:** secrets are injected at runtime through environment/secret storage.
7. **One decision path:** paper and live modes use the same strategy, scoring, risk, and exit logic. Only the execution adapter changes.
8. **Learning cannot directly rewrite live behavior:** new models are challengers and must pass evaluation before promotion.
9. **Every decision is auditable:** Shreks records the data, features, strategy version, score, risk decision, execution result, and exit reason for every candidate and every trade.
10. **No hidden paid fallback:** if a free provider becomes unavailable or exceeds its free allowance, Shreks degrades or pauses that adapter rather than silently switching to paid usage.

## 3. Core Trading Loop

The simplest description of Shreks is:

`Watch -> Filter -> Score -> Decide -> Size -> Buy -> Monitor -> Sell -> Record -> Learn -> Repeat`

Shreks watches far more tokens than it trades. Rejection is a first-class outcome.

## 4. Technology Choice

### Rust: eyes and hands

Rust owns the latency-sensitive and Solana-facing parts of the system:

- Solana/RPC ingestion,
- provider adapters that benefit from persistent connections,
- normalized market event generation,
- transaction construction/signing/submission,
- live execution guardrails,
- execution receipts and confirmations.

Rust is used because Solana has strong Rust support and because execution reliability and latency matter once Shreks is live.

### Python: brain

Python owns the research, decision, and learning layers:

- feature engineering,
- token safety analysis,
- wallet intelligence,
- setup detection,
- trade scoring,
- position sizing,
- paper trading,
- exit logic,
- backtesting,
- model training and evaluation,
- champion/challenger promotion.

Python is used because its data-analysis and machine-learning ecosystem is better suited to rapid trading research.

### Shared state

V1 runs as a small number of local processes on one host and uses **SQLite in WAL mode** as the operational database. This avoids introducing Redis, Kafka, or a hosted database before the strategy has demonstrated value.

Historical analytical datasets are exported to **Parquet** so Python can train and evaluate models efficiently without turning the operational database into an analytics warehouse.

Rust is the schema owner for raw/normalized ingestion tables and execution records. Python owns feature, decision, paper-trade, evaluation, and model tables. Schema migrations remain explicit and versioned in the repository.

## 5. High-Level Architecture

```text
                    FREE PUBLIC DATA
       Solana RPC / Helius / DEX Screener / Jupiter
                         |
                         v
                +------------------+
                | Rust Data Layer  |
                | discovery + feed |
                +------------------+
                         |
                         v
                Normalized snapshots/events
                         |
                         v
                +------------------+
                |  SQLite Event DB |
                +------------------+
                         |
                         v
                +------------------+
                |   Python Brain   |
                | safety           |
                | features         |
                | wallet intel     |
                | strategy         |
                | score            |
                | risk             |
                +------------------+
                         |
                    TradeIntent
                         |
              +----------+----------+
              |                     |
              v                     v
      +---------------+      +---------------+
      | Paper Adapter |      | Rust Executor |
      | default mode  |      | live only     |
      +---------------+      +---------------+
              |                     |
              +----------+----------+
                         v
                Position Monitor
                         |
                         v
                    Exit Engine
                         |
                         v
              Outcomes + training data
                         |
                         v
              Champion/Challenger Lab
```

## 6. Provider Strategy

Provider integrations are adapters behind internal interfaces so Shreks is not coupled to one company.

Initial free-source roles:

- **Solana RPC / Helius free tier:** chain state, transactions, account activity, token metadata/authority data where available, and wallet history inputs.
- **DEX Screener:** pair discovery/enrichment and market snapshots such as liquidity, price, volume, and transaction counts.
- **Jupiter:** route/quote information and eventual swap execution integration.
- **Direct Solana data:** preferred whenever Shreks can derive a signal reliably itself without paying a third party.

Provider responses are never trusted as the domain model. Each adapter converts external responses into Shreks-owned types.

If a provider is rate-limited, unavailable, malformed, or stale, the adapter reports degraded health. Missing critical inputs cause a candidate to be rejected or a new entry to be paused rather than guessed.

## 7. Domain Objects

The system revolves around a small set of stable domain objects.

### TokenCandidate

Represents a mint/pair discovered by Shreks and contains identity, discovery time, source, pair/pool references, and lifecycle status.

### MarketSnapshot

A timestamped view of observable market state, including:

- price,
- market cap/FDV where available,
- liquidity,
- volume windows,
- buy/sell transaction counts,
- price changes,
- token/pair age,
- holder observations when available,
- source timestamps and freshness.

### SafetyAssessment

Contains hard-fail flags and scored safety features such as:

- mint authority,
- freeze authority,
- holder concentration,
- creator/deployer exposure,
- suspicious supply concentration,
- liquidity adequacy,
- abnormal transfers,
- known execution hazards.

Safety has veto power. A high momentum score cannot override a hard safety rejection.

### WalletObservation

Represents a wallet action relevant to a candidate: buy, sell, transfer, liquidity action, creator action, or other tracked behavior.

### WalletProfile

An evolving record of historical wallet behavior including:

- number of observed trades,
- realized/estimated outcomes,
- typical entry timing,
- median outcome,
- drawdown behavior,
- rug exposure,
- confidence/sample size.

Wallet scores must be confidence-weighted. A wallet with two lucky trades cannot be treated like one with hundreds of observations.

### FeatureVector

The reproducible input to a strategy/model at a specific timestamp. It includes market, safety, flow, wallet, momentum, liquidity, and regime features plus a feature-schema version.

### TradeDecision

One of:

- `REJECT`,
- `WATCH`,
- `ENTER`,
- `HOLD`,
- `REDUCE`,
- `EXIT`.

Every decision includes reasons and strategy/model version.

### TradeIntent

A validated request to an execution adapter. It includes token, side, requested notional/quantity, slippage ceiling, strategy version, reason, idempotency key, and current mode.

### Position

The authoritative representation of an open or closed position, including weighted entry, quantity, realized/unrealized PnL, costs, stop/trailing state, and lifecycle status.

## 8. Discovery and Observation

Shreks does not need to trade a token to learn from it.

Every discovered candidate that passes minimum data-quality requirements is observed and sampled over time. The system records what the candidate looked like at discovery and what happened afterward.

Initial outcome checkpoints are:

- 1 minute,
- 5 minutes,
- 15 minutes,
- 30 minutes,
- 1 hour,
- 4 hours,
- 24 hours.

For each window Shreks records, where data permits:

- return,
- maximum favorable excursion,
- maximum adverse excursion,
- liquidity change,
- volume change,
- buyer/seller change,
- rug/dead-pool condition,
- whether a hypothetical trade could realistically have exited.

This observation dataset is the basis of later learning and must include rejected tokens to reduce selection bias.

## 9. Safety Layer

The safety layer runs before strategy scoring.

### Hard rejection examples

A candidate can be rejected immediately for conditions such as:

- critical token authority risk that violates the active policy,
- liquidity below the configured executable minimum,
- concentration above a configured hard ceiling,
- inability to obtain a reliable exit quote,
- stale or contradictory critical data,
- explicitly detected execution trap,
- active global risk halt.

Threshold values are configuration, not magic constants buried in code.

### Soft safety features

Other risks reduce score instead of causing immediate rejection. These include creator concentration, suspicious holder clustering, rapid liquidity deterioration, unusual transfers, or weak confidence in available wallet data.

The safety engine returns structured reasons so later research can determine whether a rule is useful or overly conservative.

## 10. Feature Engine

V0 uses deterministic, explainable features before machine learning is introduced.

Feature families:

### Market quality

- liquidity level and change,
- token/pair age,
- spread/quote quality where observable,
- estimated price impact,
- executable route availability.

### Flow

- buy/sell count ratio,
- buy/sell volume imbalance where derivable,
- unique buyer/seller growth,
- net flow trend,
- acceleration/deceleration.

### Momentum

- short-window return,
- return acceleration,
- volume acceleration,
- breakout/pullback structure,
- distance from recent local extremes.

### Wallet quality

- count of independently strong wallets entering,
- weighted historical wallet quality,
- smart-wallet clustering,
- high-quality wallet exits,
- creator/deployer behavior.

### Distribution/safety

- top-holder concentration,
- creator exposure,
- authority status,
- concentration change,
- liquidity concentration.

### Market regime

Shreks maintains a basic Solana memecoin regime classification such as `HOT`, `NORMAL`, `WEAK`, or `DEAD` using aggregate opportunity frequency, liquidity/volume conditions, and recent strategy performance. Strategies can be disabled by regime.

All features are timestamped and versioned to prevent training on information that was not available at decision time.

## 11. Strategy Layer

V0 begins with a small set of explicit setups rather than one generic score.

Initial setup families:

1. **Fresh Launch Continuation** — avoids first-second blind sniping and looks for sustained genuine demand after enough evidence exists.
2. **Graduation/Breakout** — looks for a token transitioning from random launch behavior into sustained liquidity and participation.
3. **First Pullback** — looks for a strong initial move, controlled retracement, seller absorption, and renewed demand.
4. **Smart Wallet Cluster** — looks for multiple independent historically strong wallets entering within a defined time window.

Each setup produces:

- eligibility,
- setup-specific features,
- deterministic score,
- reasons,
- invalidation conditions.

Strategies are independently measurable. A losing setup can be disabled without changing the others.

## 12. V0 Trade Score

The first scoring system is deterministic and configurable. It combines separate subscores rather than one opaque formula.

Initial score families:

- safety,
- money flow,
- wallet quality,
- momentum/setup quality,
- liquidity/executability.

The initial numeric weights and entry threshold are hypotheses, not claims of profitability. They must be calibrated using observation and paper-trade results.

A score never bypasses hard risk controls.

## 13. Risk Engine

Risk control is independent of strategy confidence.

The risk engine enforces at least:

- maximum notional per position,
- maximum percentage of available trading capital per position,
- maximum simultaneous positions,
- maximum aggregate open risk,
- maximum daily realized loss,
- maximum rolling drawdown,
- cooldown after consecutive losses,
- minimum liquidity,
- maximum expected price impact,
- maximum allowed slippage,
- no duplicate active intent for the same idempotency key,
- no new entries while data/execution health is degraded.

A global kill switch prevents new entries and can request liquidation of open positions according to policy.

Live execution is fail-closed: uncertainty about a critical guardrail means no entry.

## 14. Paper Trading

Paper mode is the default and is fully autonomous.

It consumes the same `TradeIntent` objects that live execution will consume. The paper adapter simulates fills using contemporaneous quotes/market state and includes:

- estimated slippage,
- swap/network cost assumptions,
- latency assumptions,
- partial/failed fill representation where appropriate,
- exit liquidity constraints.

Paper results that ignore slippage or impossible exits are invalid for promotion decisions.

The paper engine manages complete position lifecycle: entry, partial reductions, stop exits, trailing exits, emergency exits, and final close.

## 15. Exit Engine

Exits are first-class strategy decisions, not an afterthought.

V0 supports configurable combinations of:

- hard stop loss,
- initial take-profit levels,
- partial profit taking,
- trailing stop,
- maximum holding time,
- momentum/flow deterioration exit,
- strong-wallet distribution exit,
- liquidity deterioration emergency exit,
- global risk halt exit.

Every exit records a single primary reason plus supporting signals.

The research layer later compares exit policies by realized expectancy rather than assuming that a fixed take-profit is best.

## 16. Live Execution Layer

Live execution is a separate Rust adapter that accepts only validated `TradeIntent` messages.

The executor:

1. rechecks runtime trading mode,
2. verifies the intent has not already been executed,
3. rechecks hard notional/slippage constraints,
4. requests/validates a current Jupiter route/quote,
5. rejects stale or materially changed execution conditions,
6. constructs/signs/submits the transaction,
7. records transaction signature and submission metadata,
8. confirms result,
9. reconciles actual balances/fill against the intended trade.

The executor cannot invent trade ideas. It only executes intents already approved by the Python decision and risk layers.

### Secret handling

- wallet secrets are never committed,
- `.env` files containing secrets are ignored,
- production secrets are injected through the deployment environment,
- logs redact secrets and raw key material,
- the trading wallet is intended to hold only the capital allocated to Shreks.

## 17. Learning System

Shreks learns from both observed candidates and completed trades.

The first learning stage is **analysis, not autonomous self-modification**.

### Training data

Rows are built from point-in-time feature vectors and future outcomes. Dataset generation must prevent look-ahead leakage.

### Objectives

Models are evaluated on trading outcomes, not raw classification accuracy. Primary measures include:

- expectancy after costs,
- profit factor,
- maximum drawdown,
- average winner,
- average loser,
- win rate,
- calibration,
- performance by setup,
- performance by market regime,
- turnover and cost burden.

### Champion/challenger

The currently approved strategy/model is the **champion**.

A newly trained candidate is a **challenger**.

A challenger must:

1. be trained only on its permitted training window,
2. pass schema/data-quality checks,
3. beat required baselines on unseen validation/test periods,
4. avoid unacceptable drawdown or concentration of returns,
5. run in shadow or paper mode,
6. meet promotion criteria before replacing the champion.

A challenger never promotes itself. Promotion is an explicit system operation governed by evaluation rules and recorded in the model registry.

## 18. Evaluation and Promotion to Live Trading

Live trading remains disabled until the paper system demonstrates that it can operate reliably and has evidence of positive expectancy.

Minimum categories that must pass before live activation:

- sufficient sample size across independent trades,
- positive net expectancy after realistic costs,
- acceptable maximum drawdown,
- no unresolved execution/accounting defects,
- paper/live execution-path parity tests,
- stable operation through provider degradation/restart tests,
- no evidence that profit comes from one anomalous trade,
- strategy performance broken down by setup and regime,
- wallet secret and kill-switch controls verified.

The exact statistical/live-capital thresholds will be established from the collected distribution rather than chosen to create a desired result.

Initial live deployment, once eligible, starts with deliberately small allocated capital and hard limits. Scaling happens only from measured live performance.

## 19. Reliability Model

Shreks assumes external APIs fail.

Required behavior includes:

- bounded retries with backoff,
- provider rate-limit awareness,
- timestamps/freshness checks,
- persistent idempotency keys,
- restart-safe positions and decisions,
- reconciliation after restart,
- no duplicate execution after ambiguous network responses,
- structured health state per provider,
- global degraded state,
- fail-closed entry behavior.

An open position is never forgotten because a process restarts.

## 20. Logging and Auditability

Structured logs and database records must make every trade reconstructable.

For each entry or exit Shreks records:

- timestamp,
- candidate/token,
- input snapshot references,
- feature-schema version,
- strategy/model version,
- setup,
- score/subscores,
- safety result,
- risk result,
- requested trade,
- simulated or real execution result,
- estimated and realized costs,
- exit reason,
- final PnL.

Logs must never contain private keys.

## 21. Testing Strategy

Development follows test-driven boundaries.

### Rust tests

- provider response normalization,
- stale/malformed response handling,
- execution idempotency,
- guardrail rejection,
- quote-change rejection,
- transaction result reconciliation.

### Python tests

- safety hard/soft rules,
- deterministic feature calculations,
- setup detection,
- score reproducibility,
- position sizing,
- stop/take-profit/trailing behavior,
- paper fill accounting,
- dataset leakage prevention,
- champion/challenger evaluation.

### Integration tests

Use recorded provider fixtures and deterministic simulated market sequences so tests do not depend on live APIs.

### Live-source smoke tests

A small opt-in suite verifies current provider connectivity but is not required for deterministic unit-test success.

## 22. Repository Shape

The target repository shape is:

```text
Shreks/
  README.md
  AGENTS.md
  .gitignore
  .env.example
  Cargo.toml
  pyproject.toml

  crates/
    shreks-domain/        # shared Rust domain types and validation
    shreks-data/          # provider adapters + normalized ingestion
    shreks-executor/      # live execution adapter and hard guardrails
    shreks-service/       # Rust process/API coordination

  python/
    shreks/
      config/             # Python configuration
      safety/             # safety assessment
      features/           # feature engineering
      wallets/            # wallet intelligence
      strategies/         # setup definitions
      scoring/            # deterministic/model scoring
      risk/               # position sizing and portfolio risk
      paper/              # paper execution
      positions/          # lifecycle + exits
      learning/           # datasets/models/evaluation
      persistence/        # Python DB repositories

  migrations/             # SQLite schema migrations
  data/                   # gitignored runtime data
  tests/                  # cross-component fixtures/integration tests
  docs/
    superpowers/
      specs/
      plans/
```

Files within these directories should remain focused. Large generic `utils` modules are discouraged; functionality belongs with the domain that owns it.

## 23. Build Decomposition

The project is intentionally split into independently testable subprojects.

### Subproject A — Foundation and Observation

Deliverable: Shreks can run continuously, discover/enrich Solana memecoin candidates from free sources, normalize market data, persist snapshots, and expose health/freshness state.

No trading decisions yet.

### Subproject B — Deterministic Brain

Deliverable: persisted candidates receive reproducible safety assessments, feature vectors, setup detection, scores, and `REJECT/WATCH/ENTER` decisions.

No money or simulated positions yet.

### Subproject C — Autonomous Paper Trader

Deliverable: Shreks autonomously converts approved entries into realistic simulated positions, monitors them, exits according to risk/strategy rules, and records complete PnL after estimated costs.

This is the first end-to-end trading milestone.

### Subproject D — Historical Evaluation and Wallet Intelligence

Deliverable: Shreks builds outcome datasets for traded and untraded candidates, profiles wallets, evaluates setups, and produces leakage-safe performance reports.

### Subproject E — Learning and Champion/Challenger

Deliverable: Shreks trains challenger models, evaluates them on unseen periods and paper/shadow operation, and maintains an auditable model registry.

### Subproject F — Live Solana/Jupiter Executor

Deliverable: the Rust executor can safely execute the same validated intents used by paper mode, reconcile results, recover after failures, and remain disabled until promotion gates pass.

### Subproject G — Operations and Dashboard

Deliverable: operator visibility into system health, candidates, decisions, positions, performance, model versions, provider state, and kill switch without making the dashboard part of the critical trading path.

## 24. First Implementation Target

Implementation begins with **Subproject A — Foundation and Observation**.

Its success criterion is concrete:

> Running Shreks on a development machine continuously discovers and enriches Solana memecoin candidates from free sources, stores normalized timestamped snapshots in SQLite, survives recoverable provider failures, and can restart without corrupting or duplicating candidate identity.

Subproject A does not include trading logic. This keeps the first build small enough to test deeply and gives later strategy work a trustworthy dataset.

## 25. Explicitly Deferred

The following are not part of the first implementation target:

- multi-chain support,
- copy trading,
- social/X sentiment,
- LLM-based trade decisions,
- mobile app,
- paid providers,
- custom Solana onchain program,
- live-wallet execution,
- reinforcement learning,
- autonomous model promotion,
- complex distributed infrastructure.

These may be revisited only when measured results justify the complexity.

## 26. Definition of Success for Shreks

Shreks is successful only if it becomes a reliable trading system, not merely a technically impressive bot.

The final system must be able to demonstrate, with recorded evidence:

- what it observed,
- why it traded or rejected,
- what it expected,
- what actually happened,
- how much the trade made or lost after costs,
- whether the strategy remains profitable across enough independent samples,
- whether new learning genuinely improves out-of-sample results.

The project optimizes for measured edge, capital preservation, and repeatable autonomous execution.