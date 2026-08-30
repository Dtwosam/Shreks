# SHREKS — MASTER SOURCE OF TRUTH

**Project:** Shreks  
**Repository:** `Dtwosam/Shreks`  
**Primary chain:** Solana  
**System type:** Autonomous memecoin trading system  
**Architecture:** Rust Fast Lane + Python research/learning/control plane  
**Status:** Fast Lane trading-core rebuild authorized; LIVE trading remains disabled  
**Last updated:** 2026-08-30

---

## 1. Purpose

Shreks is an autonomous Solana memecoin trading system designed to exploit **tradable price movement**, not to judge whether a memecoin is fundamentally good, legitimate, or likely to survive long term.

Its job is to:

1. discover and continuously observe memecoins and their onchain market activity,
2. reconstruct event-level order flow, bonding-curve/pool state, wallet/cohort behavior, and execution conditions,
3. estimate likely future price/executability paths across several horizons,
4. continuously choose between `BUY`, `SKIP`, `HOLD`, `REDUCE`, and `SELL`,
5. calculate expected profit **after all realistic round-trip costs**,
6. determine the maximum price worth paying for an entry,
7. size risk and execute automatically,
8. reevaluate whenever meaningful new information arrives rather than waiting for a fixed timer,
9. record actual and counterfactual outcomes,
10. learn from traded, skipped, held, reduced, and exited opportunities,
11. improve through controlled champion/challenger promotion.

A trade may last fractions of a second, seconds, minutes, or longer. There is no fixed holding period and no five-minute ceiling.

The objective is **positive long-run net expectancy/account growth after fees, slippage, latency, failed fills, and drawdown**, not win rate, token quality, or prediction accuracy by itself.

Profit is never assumed or guaranteed.

---

## 2. Non-Negotiable Requirements

### 2.1 Autonomous execution
The final live system buys, holds, reduces, and sells without per-trade human approval.

### 2.2 Solana only for V1
Do not add other chains until the Solana system is proven.

### 2.3 Free external data sources for V1
V1 must not require paid market-data subscriptions or premium RPC/data plans.

Allowed inputs include:

- free API/RPC tiers,
- public Solana data,
- self-derived data,
- open-source software.

Real trading costs are allowed and must be measured, including:

- platform/swap fees,
- network fees,
- priority fees/tips,
- slippage,
- price impact,
- failed/partial execution costs where applicable.

If a free source is exhausted or unavailable, Shreks degrades or pauses the affected strategy safely rather than silently requiring paid data.

Provider consumption itself is an operational cost/health invariant. Enabled metered HTTP/RPC paths must have explicit bounded request budgets appropriate to their process, expose non-secret usage evidence where implemented, and fail closed at exhaustion rather than silently consuming beyond the configured ceiling. A per-process budget resets on restart and is **not** a substitute for cross-process or monthly provider accounting; service restarts must never be used to bypass a provider budget.

Metered realtime/WebSocket consumption must be measured and bounded separately from HTTP/RPC request budgets. A full-program realtime firehose may not be assumed safe for continuous production merely because transport remains connected. If its consumption is incompatible with free-tier operation, the runtime must narrow collection, rotate/degrade to an allowed source, or pause the affected lane safely. Buying a larger provider plan is not the default architectural fix.

### 2.4 LIVE stays disabled until proof
Real-money trading remains disabled until the promoted strategy family passes explicit PAPER/shadow, execution, accounting, recovery, and risk gates.

### 2.5 Paper/live strategy parity
Paper and live modes must use the same approved semantics for:

- event/state construction,
- feature calculation,
- forecasting,
- action selection,
- expected-value calculation,
- risk logic,
- position management,
- exit logic.

Only the actual signing/submission/fill boundary changes.

### 2.6 Fail closed on execution uncertainty, not merely on token suspicion
A new trade is blocked when critical information needed to execute or exit within the active risk policy is missing, stale, contradictory, or unreliable.

Examples:

- no usable execution path,
- no credible exit capacity for intended size,
- unknown executable price,
- slippage/impact beyond risk policy,
- accounting/reconciliation uncertainty,
- duplicate-intent uncertainty,
- active health/risk/kill-switch halt.

However, the following are **not automatic token-level vetoes** merely because they look suspicious:

- coordinated wallet activity,
- creator/deployer participation,
- concentrated holders,
- unusual transfers,
- rapid pumps/dumps,
- high volatility,
- suspected manipulation,
- historical rug association.

Those are normally **features** that may imply ride, fade, smaller size, shorter hold, faster exit, or skip.

### 2.7 Risk authority cannot be bypassed
No score, forecast, model, wallet signal, or Fast Lane strategy can bypass hard capital/risk invariants.

### 2.8 Learning cannot silently self-promote
The live runtime may continuously update market state and predictions from incoming events, but it may not rewrite its own approved model weights/strategy parameters and silently deploy them.

New models/policies are challengers. They must pass chronological evaluation, replay, and PAPER/shadow proof before explicit promotion.

### 2.9 Secrets never enter source control or ChatGPT
Never commit or paste wallet private keys, seed phrases, or unrestricted production secrets.

### 2.10 Everything important is auditable
For every material opportunity/action, preserve enough information to reconstruct:

- events/state Shreks saw,
- feature/model/schema versions,
- wallet/cohort/manipulation descriptors,
- multi-horizon forecasts,
- expected gross move,
- expected round-trip costs,
- expected net value,
- maximum acceptable entry price when buying,
- why Shreks chose `BUY`, `SKIP`, `HOLD`, `REDUCE`, or `SELL`,
- risk decision,
- requested and actual execution price,
- latency/fees/slippage,
- PnL,
- counterfactual outcomes where measurable.

---

## 3. Core Trading Philosophy

Shreks trades **moments**, not reputations.

A token that later rugs may still contain a profitable 1–10 second opportunity. A token that looks healthy can still be a terrible buy at the current executable price.

The primary event-driven loop is:

`EVENT -> UPDATE STATE -> FORECAST FUTURE PATHS -> PRICE EXECUTION -> ESTIMATE NET EV -> CHOOSE ACTION -> RISK CHECK -> EXECUTE/WAIT -> RECORD -> LEARN`

The action set is:

- `BUY`
- `SKIP`
- `HOLD`
- `REDUCE`
- `SELL`

Prediction horizons are **future checkpoints, not decision timers**. Example horizons include:

`250ms -> 500ms -> 1s -> 3s -> 5s -> 10s -> 30s -> 1m -> 5m -> 15m -> 30m -> 1h+`

If material information changes at 2.4 seconds, Shreks reevaluates at 2.4 seconds. It does not wait for the next named horizon.

The core question is:

> Given everything observable now, which available action maximizes expected net account growth after costs and risk?

---

## 4. Architecture

### 4.1 Rust = Fast Lane + Eyes + Hands

Rust owns latency-sensitive responsibilities:

- direct Solana/RPC/WebSocket ingestion,
- Pump/PumpSwap launch/lifecycle/swap-event ingestion,
- event ordering/deduplication,
- bonding-curve/pool-state reconstruction,
- live per-token rolling state,
- microstructure windows,
- approved champion inference when latency requires it,
- event-driven Fast Lane action evaluation,
- risk-request generation,
- execution integration,
- transaction construction/signing/submission,
- confirmation and reconciliation,
- live execution guardrails.

The previous rule **"Rust does not decide which memecoin to trade" is superseded**. For sub-second/seconds strategies, the approved strategy runtime must be able to evaluate inside Rust so a Python round trip does not become the latency bottleneck.

Rust still cannot bypass the approved champion artifact, risk authority, live-mode gate, or promotion system.

### 4.2 Python = Research + Training + Evaluation + Control Brain

Python owns non-latency-critical intelligence:

- feature research,
- dataset construction,
- wallet/cohort research,
- manipulation-pattern research,
- counterfactual labeling,
- strategy experiments,
- model training,
- backtesting/replay,
- chronological validation,
- champion/challenger comparison,
- promotion evidence,
- slower-horizon decision logic where latency is not material,
- research/dashboard explanations where appropriate.

Python may produce the approved champion artifact/configuration loaded by Rust.

### 4.3 Shared state

Keep infrastructure simple until measurements prove otherwise:

- SQLite WAL for durable operational/evidence/decision/trade/checkpoint state,
- Parquet for large research datasets,
- in-memory Rust rolling state for latency-critical windows, with restart-safe reconstruction/checkpointing.

Do not add Redis, Kafka, Kubernetes, or a hosted database merely because the strategy is fast.

---

## 5. Data Sources and Provider Rule

Initial V1 sources remain adapter-based:

### Direct Solana / Helius free tier
Use for:

- launch/lifecycle events,
- transactions/swaps,
- account/token state,
- wallet activity,
- authority/supply state,
- chain timestamps.

Direct public Solana data is preferred whenever it can provide a reliable signal without paid dependencies.

### DEX Screener
Use primarily for slower enrichment/reference market data such as:

- pair discovery/enrichment,
- price/liquidity/volume snapshots,
- pair age,
- reference/cross-check data.

DEX Screener must **not be the only source driving a 1–10 second Fast Lane**.

### Jupiter / executable quote sources
Use where appropriate for:

- executable route/quote information,
- price impact,
- slippage context,
- eventual execution paths.

Pre-graduation Pump trades may use direct curve math/state when that is the authoritative executable mechanism.

### Provider rule
External responses are inputs, not Shreks domain objects. Adapters normalize them into versioned Shreks-owned structures.

---

## 6. Core Domain Objects

### TokenCandidate
Observation identity for a discovered mint/curve/pair/pool and lifecycle state. It does not imply the token is safe or worth buying.

### MarketEvent
Timestamped/ordered event such as:

- buy/sell/swap,
- reserve/curve change,
- liquidity change,
- creator/deployer action,
- wallet/cohort action,
- migration/graduation/BOOST-related event,
- route/executability change.

### FastMarketState
Current event-derived state used by Fast Lane, including where available:

- curve/pool reserves and derived price,
- executable/reference price,
- rolling buy/sell notional and counts,
- flow imbalance/velocity/acceleration,
- buyer/seller arrival rates,
- wallet/cohort actions,
- creator activity,
- local high/low/reversal state,
- liquidity/exit capacity,
- graduation/migration state,
- expected round-trip costs and latency.

### FeatureVector
Versioned point-in-time-safe features for strategy/model use.

### HorizonForecast
Forecast distribution for one or more future horizons, potentially including:

- expected return,
- upside/downside probabilities,
- expected MFE/MAE,
- reversal probability,
- expected executable exit quality,
- confidence/uncertainty.

### TradeabilityAssessment
Describes whether a **specific trade at a specific size/time** can be executed and exited within active risk limits.

### ActionAssessment
Decision record for `BUY`, `SKIP`, `HOLD`, `REDUCE`, or `SELL`, including forecasts, costs, expected net value, price boundary, strategy/model version, and reasons.

### TradeIntent
Risk-validated capital-changing execution request with side, size, price/slippage constraints, model/strategy version, idempotency key, and execution mode.

### Position
Authoritative open/closed position state with quantity, weighted entry, costs, PnL, high-water state, and latest action/forecast context.

### CounterfactualOutcome
Research-only record of what would have happened under alternative available actions, such as:

- buy vs skip,
- enter now vs delay,
- sell now vs hold another 250ms/1s/3s/10s/30s,
- reduce vs full exit.

Future data may label counterfactuals but must never leak into the original decision features.

---

## 7. Observation and Labeling

Shreks should observe as much of the memecoin market as free-source and host capacity reasonably permit.

### 7.1 Event-driven capture
Prioritize event-level or near-event-level data where available:

- buys/sells/swaps,
- curve reserve changes,
- liquidity changes,
- wallet/cohort actions,
- creator/deployer actions,
- graduation/migration events,
- route/execution changes.

### 7.2 Rolling micro-windows
Maintain strategy-relevant rolling windows such as:

- 100ms,
- 250ms,
- 500ms,
- 1s,
- 2s,
- 5s,
- 10s,

where source timing supports them.

Exact windows are configuration/model inputs, not immutable strategy law.

### 7.3 Longer labels still matter
Persist future labels at longer horizons too, such as 30s, 1m, 5m, 15m, 30m, 1h, 4h, and 24h when practical.

### 7.4 Preserve the path
Do not reduce a token to endpoint returns. Event sequence, time-to-peak, drawdown, recovery, liquidity survival, and executable exit quality matter.

### 7.5 SKIP is first-class data
Shreks must learn from opportunities it did not trade. A skipped token that later moved strongly is important evidence, as is a correctly avoided loss.

---

## 8. Feature Families

All features must be point-in-time safe and versioned.

### Microstructure / flow
- buy/sell notional/count imbalance,
- net flow,
- flow velocity/acceleration,
- buyer/seller arrival rate,
- burst intensity,
- changing trade-size distribution,
- seller exhaustion,
- continuation/reversal signatures.

### Curve / pool
- reserves,
- derived price,
- reserve change rate,
- graduation progress/state,
- pool liquidity,
- exit capacity.

### Wallet / cohort
- entries/exits,
- repeat-wallet activity,
- coordinated timing,
- cohort historical post-action path by horizon,
- creator/deployer behavior,
- large-holder distribution behavior,
- linkage/independence confidence.

### Manipulation descriptors
- concentration,
- coordinated-flow intensity,
- abnormal transfers,
- pump/distribution patterns,
- related-wallet behavior where inferable,
- historical behavior of involved wallets/cohorts.

These are normally predictive features, not automatic vetoes.

### Momentum / path
- returns across micro/short/long windows,
- acceleration,
- local high/low,
- drawdown/recovery,
- volatility/velocity,
- breakout/pullback/reclaim structure,
- point-in-time-safe MFE/MAE-so-far features.

### Execution economics
- reference/executable price,
- expected entry/exit price,
- maximum acceptable entry price,
- route/capacity,
- slippage/impact,
- platform/swap fee,
- network/priority/tip cost,
- expected landing latency,
- round-trip break-even move.

### Market regime/context
Use broad activity, volatility, launch/graduation rates, congestion, and other evidence to determine whether specific strategy families currently have edge.

---

## 9. Strategy Families

Multiple independently measurable strategies should coexist. Capital should eventually favor strategies with proven net expectancy/capacity, not one permanently hard-coded setup.

### 9.1 Impulse Scalp
Potentially fractions of a second to roughly 1–10 seconds. Target explosive order-flow/curve movement when predicted movement comfortably exceeds round-trip costs.

### 9.2 Micro Pullback / Reclaim
Enter after an impulse retraces and sellers weaken while demand reappears. Entry is based on favorable price structure/executability, not merely a token score.

### 9.3 Pre-Graduation Acceleration
Trade accelerating flow as a curve approaches graduation when cost-adjusted expected value supports it.

### 9.4 Graduation / Migration / BOOST Flow
Treat graduation as an event regime. Learn whether to enter before/during/after, fade, hold, or skip based on live flow and executable economics.

### 9.5 Wallet/Cohort Ride or Fade
Learn what typically happens after specific wallets/cohorts act. Coordinated/manipulated activity may imply continuation, reversal, fast exit, or skip.

### 9.6 Longer Runner
Continue holding while the expected value of holding remains superior to reducing/selling and risk limits remain satisfied. No fixed five-minute stop.

### 9.7 Legacy setups
Fresh Launch Continuation, First Pullback, Graduation/Breakout, deterministic scores, and current setup engines remain useful as baselines/features/challengers. They are **no longer the sole gateway to entry**.

---

## 10. Forecast, Decision, and Entry-Price Engine

The existing deterministic score is retained as an interpretable baseline/feature. **A high score alone must not trigger a buy.**

The target decision sequence is:

1. build current point-in-time state,
2. forecast price/path/executability across several horizons,
3. estimate realistic entry and exit economics,
4. subtract all expected costs,
5. compare available actions,
6. choose `BUY`, `SKIP`, `HOLD`, `REDUCE`, or `SELL`,
7. pass capital-changing actions through risk.

For `BUY`, calculate a **maximum acceptable entry price** or equivalent constraint. If price moves beyond the level where expected net value remains acceptable before landing, abort rather than chase.

For open positions, continuously compare the expected value of holding with reducing/selling.

---

## 11. Risk Engine

Risk remains a hard independent capital-preservation authority.

It must enforce/configure:

- max notional per position,
- max capital % per position,
- max simultaneous positions,
- max aggregate exposure/risk,
- daily realized-loss limit,
- rolling drawdown limit,
- abnormal-loss/execution cooldowns,
- slippage/impact limits,
- minimum credible exit capacity for intended size,
- duplicate-intent prevention,
- health-based entry halts,
- global kill switch.

Sizing may use volatility, liquidity/capacity, forecast confidence, strategy family, holding horizon, and manipulation descriptors.

Suspicious conditions can require smaller size or higher required edge without automatically deleting the opportunity.

---

## 12. Paper and Shadow Trading

Paper mode must exercise the same approved strategy semantics intended for live.

At the resolution relevant to a strategy, simulate:

- contemporaneous curve/quote/executable price,
- platform/swap fees,
- network/priority/tip costs,
- decision-to-landing latency,
- slippage/impact,
- partial/failed fills where meaningful,
- finite exit capacity,
- adverse movement during execution.

For sub-second/seconds strategies, minute candles and perfect midpoint fills are invalid proof.

PAPER must record `BUY`, `SKIP`, `HOLD`, `REDUCE`, and `SELL` decisions and enough future path to learn from them.

---

## 13. Continuous Hold / Reduce / Sell

Exits do not wait for fixed checkpoints.

On material new information, ask:

> Is the expected net value of continuing to hold greater than reducing or selling now?

Relevant information may include:

- reversal probability,
- continuing buy-flow expectancy,
- wallet/cohort distribution,
- creator selling,
- curve/pool changes,
- liquidity/exit-capacity deterioration,
- momentum/flow deterioration,
- high-water drawdown,
- current executable sell price and costs.

Hard stop-loss, take-profit, trailing stop, maximum holding time, and emergency exits remain protective backstops/baselines.

Every `HOLD`, `REDUCE`, and `SELL` decision should later be counterfactually evaluated where data permits.

---

## 14. Learning System

Shreks learns **which action was best**, not merely which token predicted profit.

It learns from:

- all observed opportunities,
- every `SKIP`,
- entry timing/price after every `BUY`,
- every `HOLD`,
- every `REDUCE`,
- every `SELL`,
- wallet/cohort/creator sequences,
- full price/liquidity/execution paths,
- PAPER trades,
- later LIVE trades.

The loop is:

`EVENTS -> STATE -> ACTION -> FUTURE PATH -> MULTI-HORIZON LABELS -> COUNTERFACTUALS -> DATASET -> TRAIN CHALLENGER -> VALIDATE -> REPLAY -> PAPER/SHADOW -> COMPARE -> PROMOTE OR REJECT`

### 14.1 Multi-horizon learning
Models may estimate outcomes over `250ms, 500ms, 1s, 3s, 5s, 10s, 30s, 1m, 5m, 15m, 30m, 1h+` or other evidence-supported horizons.

Those horizons characterize opportunity duration; they do not constrain action time.

### 14.2 Counterfactual learning
Evaluate alternatives such as:

- skip vs buy,
- immediate vs delayed entry,
- looser vs stricter maximum entry price,
- sell now vs hold longer,
- reduce vs full exit.

This is required to learn **when not to buy, when to hold, and when to sell**.

### 14.3 Objective
Primary objective:

> maximize long-run net account growth/expectancy after realistic costs and drawdown constraints.

Measure at least:

- net expectancy,
- profit factor,
- max drawdown,
- average winner/loser,
- win rate,
- calibration by horizon,
- expected-value calibration,
- entry-price efficiency,
- exit-timing efficiency,
- missed-opportunity cost,
- cost burden,
- capacity/turnover,
- performance by strategy and regime.

### 14.4 Champion / Challenger
A challenger must use point-in-time-safe data, chronological unseen evaluation, realistic replay costs/latency, PAPER/shadow proof, and explicit promotion. It never silently promotes itself.

---

## 15. Wallet and Manipulation Intelligence

Do not reduce wallet intelligence to "smart wallet bought = bullish."

Learn histories such as:

- immediate path after wallet/cohort entries/exits,
- typical impulse magnitude/duration,
- distribution timing,
- behavior around graduation,
- interaction with creator/deployer actions,
- performance by market regime,
- likely independence/linkage.

The useful question is:

> Given this wallet/cohort behavior now, what does it imply about the next executable path, and should Shreks ride, fade, hold, reduce, sell, or skip?

Attribution/linkage that cannot be proven must remain probabilistic.

---

## 16. Live Fast Lane and Execution

LIVE remains disabled until promotion gates pass.

The live path is:

1. **Fast Lane strategy runtime** updates state and runs the approved champion logic/inference.
2. **Risk authority** validates capital/execution constraints and creates a `TradeIntent` for capital-changing actions.
3. **Rust executor** executes the validated intent.

Immediately before submission:

- confirm live mode,
- verify idempotency,
- recheck risk/notional,
- reprice with freshest executable state,
- ensure price remains inside the decision's maximum acceptable price/slippage/EV boundary,
- abort materially changed trades,
- construct/sign/submit,
- confirm,
- reconcile actual balances/fills.

Low-latency Solana submission/priority mechanisms may be used when appropriate and when they do not create a forbidden paid-data dependency. Their real costs must be included in expected value.

---

## 17. Health, Recovery, and Operations

Shreks must survive provider limits/outages, malformed/stale data, network failures, process/host restarts, duplicate events/intents, partial execution failures, and confirmation uncertainty.

Critical health degradation pauses new entries.

Provider health includes consumption health, not only transport connectivity. Production evidence must distinguish HTTP/RPC request usage from realtime/WebSocket push consumption, retain truthful provider provenance, and show that configured ceilings and free-tier capacity are compatible with the intended operating interval. An exhausted required request budget is a fail-closed provider condition, not a reason to silently raise the limit or restart the process to reset it.

A realtime source that is technically connected but consuming provider quota at an unsustainable rate is not production-healthy. Full-program metered ingestion must be narrowed, bounded, or otherwise proven sustainable before 24/7 runtime acceptance.

### Production location
GitHub is the source-control/CI/release/deployment control plane. It does **not** run Shreks continuously.

The actual system runs continuously on the dedicated Linux VPS.

The existing VPS release/deploy, service supervision, dashboard, PAPER runtime, and evidence foundations should be reused rather than discarded. The Fast Lane rebuild must earn new physical acceptance evidence for changed runtime behavior.

Initial runtime shape:

```text
Solana/Pump events
       |
       v
+---------------------------+
|        SHREKS VPS         |
| Rust Fast Lane / Observer |
| Rolling live state        |
| PAPER / later LIVE path   |
| Risk authority            |
| SQLite evidence/state     |
| Python research services  |
| Dashboard / telemetry     |
+---------------------------+
```

Use systemd/current release-manager architecture unless measurements justify a deliberate change.

### Dashboard
The operator surface should expose:

- service/provider/event freshness,
- decisions by `BUY/SKIP/HOLD/REDUCE/SELL`,
- current forecasts/EV for open positions where stored,
- entry price boundary vs actual fill,
- latency/fees/slippage,
- PnL/drawdown/exposure,
- model/strategy version,
- proof/promotion state,
- LIVE disabled/enabled state,
- risk halt and kill switch.

Trade drill-down must show stored evidence, not invented explanations.

---

## 18. Testing and Proof

Before LIVE money, require tests/evidence for:

- event ingestion/order/deduplication,
- curve/pool-state reconstruction,
- rolling micro-windows,
- wallet/cohort features,
- manipulation descriptors,
- multi-horizon labels,
- counterfactual leakage prevention,
- Fast Lane inference/decision parity,
- maximum-entry-price abort behavior,
- realistic cost/EV accounting,
- event-resolution PAPER fills,
- continuous hold/reduce/sell,
- risk authority,
- restart/recovery,
- idempotency,
- paper/live artifact parity,
- chronological evaluation,
- latency/throughput/capacity benchmarks,
- provider-consumption/budget evidence under representative physical-host load,
- live dry runs.

LIVE promotion additionally requires:

- sufficient independent PAPER/shadow sample,
- positive net expectancy after realistic costs,
- acceptable drawdown/tail losses,
- enough execution capacity for intended size/frequency,
- measured latency compatible with claimed edge,
- stable recovery/provider behavior,
- reconciled accounting,
- reliable halts/kill switch,
- reproducible evaluation without look-ahead leakage.

Initial LIVE capital, when eventually authorized, must be deliberately small and strictly capped.

---

## 19. Scope Explicitly Deferred

Do not add prematurely:

- other chains,
- leverage/perpetuals,
- paid data feeds/RPC as a requirement,
- social/X dependency,
- Telegram trading-control bot,
- Kafka/Kubernetes/microservice sprawl,
- reinforcement learning merely for sophistication,
- self-modifying live strategies,
- custom Solana onchain program.

---

## 20. Source of Truth Hierarchy

When project documents conflict:

1. `SHREKS_MASTER_SOURCE_OF_TRUTH.md`
2. `SHREKS_BUILD_ORDER.md`
3. current approved repo spec/plan
4. repository code/tests
5. chat messages

Durable architecture changes must update this document deliberately.

---

## 21. Rebuild Directive — 2026-08-28

The existing Shreks infrastructure is **not being thrown away**. Preserve and reuse the proven pieces:

- Solana/Pump observation foundations,
- SQLite/WAL evidence state,
- wallet reconstruction/research foundations,
- PAPER ledger/accounting,
- risk controls,
- dashboard/telemetry,
- release/deploy/VPS supervision,
- backup/recovery work,
- learning/champion-challenger foundations.

The **trading core is being rebuilt**.

The old default philosophy:

`discover -> slow snapshots -> setup/score -> buy available quote -> rule-based exit`

is superseded by:

`event stream -> Fast Lane state -> multi-horizon forecast -> cost-adjusted action -> price boundary -> risk -> event-driven hold/reduce/sell -> counterfactual learning`

Implementation must now prioritize the Fast Lane and learning requirements in the updated `SHREKS_BUILD_ORDER.md` before further strategy promotion or LIVE work.

LIVE TRADING REMAINS DISABLED.

### Current repository/runtime position

- `main` contains the previously built observer/PAPER/risk/learning/ops foundations.
- the canonical-pair selection correction is merged and previously deployed/physically accepted on the VPS at release `330ace280067905b6502ba3846f73b2b461be125`.
- the verified-Pump-market-evidence fix is merged and sealed in GitHub at `29f6dd9b747e053569d14d54a2f346b46ed103ac`; physical VPS deployment/acceptance of that newer seal must not be assumed until separately proven.
- the Fast Lane architecture described here is the next major build direction.
- FL1.5 physical-host work exposed unsustainable provider consumption in the metered realtime/evidence paths; provider-consuming production services remain stopped until bounded HTTP guardrails, a bounded realtime topology, exact release verification, and fresh physical-host acceptance are all complete.

---

## 22. Definition of Success

Shreks succeeds when it can:

- observe Solana memecoin markets at the event resolution required by its strategies,
- reconstruct order flow, curve/pool movement, wallet/cohort behavior, and execution state,
- treat manipulation/suspicious activity as learnable market information rather than blindly discarding opportunities,
- estimate cost-adjusted future paths across multiple horizons,
- choose `BUY`, `SKIP`, `HOLD`, `REDUCE`, or `SELL` whenever material information changes,
- determine a maximum acceptable entry price instead of chasing any available quote,
- PAPER trade sub-second, seconds, minutes, and longer opportunities under realistic costs/latency/capacity,
- learn from actual actions and counterfactual alternatives,
- demonstrate repeatable net expectancy and acceptable drawdown,
- improve through controlled champion/challenger promotion,
- execute LIVE automatically only after proof,
- preserve capital through hard risk/execution invariants,
- explain every action from stored evidence.

The goal is not a high score, a pretty dashboard, or correctly predicting which meme survives.

The goal is a trading machine with a measurable, repeatable **net execution edge**.
