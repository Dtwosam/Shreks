# SHREKS — BUILD ORDER

**Project:** Shreks  
**Repository:** `Dtwosam/Shreks`  
**Architecture:** Rust Fast Lane + Python research/learning/control plane  
**Purpose:** Defines the required implementation order for the Fast Lane rebuild while preserving already-proven Shreks infrastructure.  
**Last updated:** 2026-08-28

---

## 1. Governing Rule

The canonical architecture is defined by `SHREKS_MASTER_SOURCE_OF_TRUTH.md`.

The required progression for the new trading core is:

`CAPTURE EVENTS -> RECONSTRUCT STATE -> PRICE EXECUTION -> LABEL FUTURE PATHS -> LEARN ACTIONS -> PAPER TRADE -> PROVE EDGE -> INTEGRATE FAST RUNTIME -> SHADOW -> LIVE`

Do not skip directly to learned models or live execution.

Every phase must leave behind independently testable, auditable software. LIVE remains disabled until all required proof and operations gates pass.

---

# 2. PRESERVED FOUNDATION — DO NOT REBUILD WITHOUT EVIDENCE

The previous A–G program produced substantial infrastructure that remains useful. The Fast Lane rebuild must reuse it unless a measured limitation proves replacement is necessary.

Preserve:

- Rust/Python workspace and CI,
- SQLite WAL storage and migrations,
- provider-health and normalized-data foundations,
- Solana/Helius/Pump observation foundations,
- DEX Screener and Jupiter adapters,
- token-candidate and market-snapshot storage,
- Pump launch verification,
- wallet reconstruction/research foundations,
- PAPER execution and authoritative ledger/accounting,
- risk engine, idempotency, halts, and kill switch,
- existing exit-engine protections,
- backtest/evaluation/learning foundations,
- champion/challenger concepts,
- release/deploy manager and immutable releases,
- dedicated Linux VPS/systemd runtime,
- dashboard/telemetry/operator controls,
- restart/recovery and backup work.

Legacy Fresh Launch, Graduation/Breakout, First Pullback, deterministic scoring, and the existing PAPER campaign remain useful as **baselines, research signals, and compatibility tests**. They no longer define the sole trading path.

The following old assumptions are superseded:

- token suspicion/manipulation is not an automatic strategy-level veto,
- a high deterministic score is not sufficient to trigger a buy,
- entry is not “take any acceptable quote after score approval,”
- action decisions are not tied to fixed checkpoint timers,
- Python is not required to sit in the latency-critical decision loop,
- DEX Screener snapshots are not sufficient for 1–10 second trading.

---

# 3. FAST LANE REBUILD PHASES

## FL0 — Contract, compatibility, and measurement baseline

Before changing trading behavior, establish the exact boundary between preserved infrastructure and the Fast Lane.

### FL0.1 Repository/runtime map
Document the current paths for:

- Pump create/verification events,
- any existing Pump/PumpSwap swap-event parsing,
- observer event normalization,
- SQLite persistence/checkpoints,
- risk intent creation,
- PAPER execution/ledger,
- model/learning artifacts,
- dashboard telemetry,
- systemd production services.

### FL0.2 Versioned Fast Lane interfaces
Define the initial versioned domain contracts without granting trading authority yet:

- `FastEvent`,
- `FastEventId`,
- `FastMarketState`,
- rolling-window summaries,
- `HorizonForecast`,
- `ExecutionEconomics`,
- `ActionAssessment`,
- `CounterfactualOutcome`.

Exact Rust names may differ if existing repository conventions strongly favor another name, but the responsibilities must remain separate and versioned.

### FL0.3 Compatibility invariants
Prove:

- existing observer/PAPER/risk code still compiles and tests,
- LIVE remains disabled,
- Fast Lane cannot create a live transaction,
- no existing database evidence is silently reinterpreted,
- legacy strategy remains available as a comparison baseline.

### FL0.4 Production measurement baseline
Record current event throughput, storage growth, CPU/RAM, provider limits, and relevant source latency before optimization.

**Exit criterion:** Fast Lane contracts and preserved boundaries are explicit, tested, and do not alter capital behavior.

---

## FL1 — Direct event stream and canonical FastEvent

Build the event source required for sub-second/seconds strategies.

### FL1.1 Pump/PumpSwap event coverage
Capture or derive, where available from free/direct Solana data:

- token creation,
- pre-graduation buys,
- pre-graduation sells,
- bonding-curve reserve/state changes,
- graduation/migration,
- PumpSwap/post-graduation swaps where supported,
- meaningful liquidity changes,
- creator/deployer actions,
- wallet identity/signature/slot/timestamp attribution.

Do not use DEX Screener polling as the authoritative source for Fast Lane order flow.

### FL1.2 Canonical event identity
Every Fast Lane event must have deterministic identity sufficient for:

- deduplication,
- replay,
- restart recovery,
- chronological ordering,
- attribution to mint/curve/pool,
- source-quality auditing.

### FL1.3 Event ordering and late-arrival policy
Define and test behavior for:

- duplicate events,
- same-slot events,
- out-of-order delivery,
- delayed observations,
- reconnect/replay overlap,
- invalid/malformed events.

### FL1.4 Durable checkpoints
Persist enough ingestion/checkpoint evidence to restart without creating gaps or duplicate economic events.

### FL1.5 Read-only runtime acceptance
Deploy only after tests prove the stream is observation-only. Measure real production event rate and latency before proceeding.

**Exit criterion:** Shreks continuously captures a replayable, deduplicated, ordered stream of economically relevant Pump/PumpSwap events from free/direct sources.

---

## FL2 — FastMarketState and rolling microstructure windows

This is the first trading-intelligence foundation. Keep it deterministic and pure before introducing learned forecasts.

### FL2.1 Per-token live state
Maintain current state for active mints including, where available:

- curve/pool reserves,
- derived/reference price,
- latest executable context,
- buy/sell counts and notionals,
- buyer/seller arrival rates,
- flow imbalance,
- flow velocity and acceleration,
- local high/low,
- drawdown/recovery,
- wallet/cohort activity,
- creator/deployer activity,
- graduation/migration state,
- liquidity/exit capacity.

### FL2.2 Rolling windows
Support deterministic rolling summaries initially around:

- 100ms,
- 250ms,
- 500ms,
- 1s,
- 2s,
- 5s,
- 10s.

These are configurable feature windows, not action timers.

### FL2.3 Boundary correctness
Test exact inclusion/exclusion at window boundaries, event ordering, clock behavior, and absence of future leakage.

### FL2.4 Deterministic reconstruction
Replaying the same ordered event stream must reproduce the same `FastMarketState` and rolling summaries.

### FL2.5 Capacity/latency benchmark
Measure:

- events/sec handled,
- p50/p95/p99 event-to-state-update latency,
- memory per active token,
- behavior during burst load.

**Exit criterion:** Rust can reconstruct and maintain deterministic event-level market state fast enough for the intended strategies, with measured capacity headroom.

---

## FL3 — Execution economics and maximum acceptable entry price

Before predicting price, make the economics exact enough to know whether a predicted move is worth trading.

### FL3.1 Cost model
Model all applicable expected round-trip costs:

- Pump/PumpSwap/platform fees,
- swap fees,
- expected buy slippage/impact,
- expected sell slippage/impact,
- network fee,
- priority fee/tip when used,
- partial/failed fill cost where meaningful,
- decision-to-landing latency impact.

Fee values must be versioned/configurable and verified from current provider/protocol evidence before production use.

### FL3.2 Exit-capacity model
Estimate whether intended size can be exited under active route/curve/pool conditions.

### FL3.3 Break-even move
Calculate the minimum future executable price movement required to produce non-negative net PnL for the intended size.

### FL3.4 Maximum acceptable entry price
Given a forecast distribution and required edge/risk margin, calculate the highest executable entry price at which the trade remains worthwhile.

### FL3.5 Reprice/abort invariant
Immediately before execution, if current executable conditions exceed the approved price/EV boundary, abort instead of chasing.

**Exit criterion:** Shreks can answer “is this specific trade at this specific price/size economically worthwhile?” without using a token-quality shortcut.

---

## FL4 — Multi-horizon future-path labels

Build reliable targets before training anything.

### FL4.1 Horizon labels
From each valid decision timestamp, create future labels over evidence-supported horizons such as:

- 250ms,
- 500ms,
- 1s,
- 3s,
- 5s,
- 10s,
- 30s,
- 1m,
- 5m,
- 15m,
- 30m,
- 1h+.

Exact available horizons depend on source timestamp resolution and observation completeness.

### FL4.2 Path labels
Where supported, label:

- executable return,
- MFE,
- MAE,
- time to local peak/trough,
- reversal occurrence/timing,
- liquidity/exit-capacity evolution,
- route availability,
- cost-adjusted achievable return.

### FL4.3 Leakage prevention
Future labels must never enter point-in-time decision features.

### FL4.4 Completeness/confidence
A label must carry enough quality/completeness metadata to distinguish “observed no move” from “future path was not captured.”

**Exit criterion:** Shreks can create trustworthy point-in-time-safe future-path datasets at micro and longer horizons.

---

## FL5 — Counterfactual action labels

Teach Shreks more than “did price go up?”

### FL5.1 BUY vs SKIP
For an observation where a buy was technically possible, estimate the realistic outcome of:

- buying now,
- delaying entry where evidence permits,
- skipping.

### FL5.2 Entry-price efficiency
Record how alternative acceptable entry prices/timing would have affected net outcome without pretending an impossible fill was available.

### FL5.3 HOLD vs REDUCE vs SELL
For open-position states, label realistic outcomes for:

- sell now,
- reduce now,
- hold through later horizons.

### FL5.4 Counterfactual executability
Counterfactuals must respect real contemporaneous liquidity, latency, fees, slippage, and capacity. “Could have sold at the candle high” is invalid unless an executable path supports it.

### FL5.5 Dataset export
Export versioned Parquet/research records for action learning.

**Exit criterion:** The dataset can teach when to buy, when not to buy, when to keep holding, and when to reduce/sell.

---

## FL6 — Deterministic Fast Lane baselines

Before ML, build simple interpretable strategies that can be replayed and beaten.

### FL6.1 Impulse scalp baseline
Use event-derived flow/curve acceleration plus execution economics to identify very short continuation opportunities.

### FL6.2 Micro pullback/reclaim baseline
Detect impulse -> controlled retracement -> seller exhaustion -> demand return, with an explicit entry-price boundary.

### FL6.3 Pre-graduation acceleration baseline
Model accelerating curve participation toward graduation without assuming graduation itself guarantees profit.

### FL6.4 Graduation/migration flow baseline
Measure before/during/after-graduation behavior and BOOST-related flow where observable.

### FL6.5 Wallet/cohort ride/fade baseline
Use known wallet/cohort behavior as directional/holding-horizon information rather than automatic approval/rejection.

### FL6.6 Longer-runner baseline
Continue holding only while cost/risk-adjusted expected continuation remains favorable; protective exits remain backstops.

**Exit criterion:** Shreks has several independently measurable Fast Lane baselines that generate `BUY/SKIP/HOLD/REDUCE/SELL` decisions without machine learning.

---

## FL7 — Event-resolution PAPER action engine

Reuse the existing PAPER ledger/risk foundations, but make the decision/execution cadence compatible with Fast Lane strategies.

### FL7.1 Event-driven PAPER loop
A material event/state update may trigger a new action assessment immediately.

### FL7.2 BUY
A PAPER buy must respect:

- decision timestamp,
- assumed/observed landing latency,
- maximum acceptable entry price,
- intended notional,
- executable capacity,
- fees/slippage/impact.

### FL7.3 SKIP
Record why a valid observed opportunity was skipped and preserve its future labels.

### FL7.4 HOLD/REDUCE/SELL
Continuously reevaluate open positions. Named horizons never force the system to wait.

### FL7.5 Realistic fill and accounting
Reuse/extend existing PAPER fill and ledger logic so event-resolution actions still reconcile after partial fills, multiple reductions, failures, restarts, fees, and slippage.

### FL7.6 Protective risk exits
Existing hard stops, trailing stops, max hold, liquidity emergency, and global halt remain available as independent protective backstops.

**Exit criterion:** Shreks can PAPER trade event-driven strategies with realistic costs/latency/capacity and reconciled accounting.

---

## FL8 — Learned multi-horizon forecasting

Only begin after FL1–FL7 produce trustworthy events, state, labels, costs, and baselines.

### FL8.1 Training dataset/versioning
Use point-in-time-safe features plus multi-horizon and counterfactual labels.

### FL8.2 Practical model baselines
Begin with models appropriate for tabular/sequence summaries and measured latency requirements. Do not jump to reinforcement learning.

### FL8.3 Chronological validation
Training/validation/test splits must be time-aware and resistant to wallet/token/event leakage.

### FL8.4 Forecast calibration
Measure prediction quality by horizon, regime, strategy family, and liquidity/cost bucket.

### FL8.5 Champion artifact
Produce a versioned immutable champion artifact/configuration that can be loaded by the Fast Lane runtime.

### FL8.6 Rust inference parity
If champion inference runs in Rust, prove numerical/decision parity with the reference evaluator within explicit tolerances.

**Exit criterion:** A challenger forecast system demonstrably beats deterministic baselines on unseen chronological data after realistic costs, without violating latency requirements.

---

## FL9 — Learned continuous action policy

Use forecasts to choose the action with best expected net value subject to hard risk constraints.

### FL9.1 Action comparison
Evaluate `BUY`, `SKIP`, `HOLD`, `REDUCE`, and `SELL` as applicable to current state.

### FL9.2 Dynamic holding horizon
Do not choose a fixed holding period at entry. Update expected continuation/reversal and execution value whenever material information changes.

### FL9.3 Uncertainty-aware behavior
Low-confidence forecasts may require:

- higher edge threshold,
- smaller size,
- faster reduction,
- or `SKIP`.

### FL9.4 No self-promotion
Online observations may update state/forecasts, but champion weights/policy do not silently retrain and deploy themselves.

**Exit criterion:** The approved champion produces stable, auditable continuous action decisions and beats the best deterministic baseline in PAPER/shadow evaluation.

---

## FL10 — Production Fast Lane runtime integration

Integrate with the existing VPS/runtime only after the core is proven offline/PAPER.

### FL10.1 Service topology
Reuse systemd/release-manager architecture unless measurement proves a change is necessary.

### FL10.2 Fast Lane telemetry
Expose at least:

- events/sec,
- event lag,
- state-update p50/p95/p99 latency,
- inference/action latency,
- action counts by `BUY/SKIP/HOLD/REDUCE/SELL`,
- max-entry-price aborts,
- expected vs realized slippage/cost,
- position/action latency,
- dropped/late/duplicate events,
- model/strategy version.

### FL10.3 Restart reconstruction
Prove rolling state and any open PAPER position can recover/reconcile after process and host restart without duplicate economic actions.

### FL10.4 Resource headroom
Measure CPU/RAM/storage/network utilization during real event bursts. Optimize only measured bottlenecks.

### FL10.5 Dashboard adaptation
Update operator views so old “score/pass” metrics are supplemented or superseded by Fast Lane action/EV/latency evidence.

**Exit criterion:** Fast Lane runs continuously on the VPS in read-only/PAPER mode with measured latency, recovery, telemetry, and no regression to existing operations.

---

## FL11 — Shadow proof and champion promotion

### FL11.1 Independent sample
Accumulate enough independent opportunities/trades across varying market conditions. Do not declare proof from a handful of large winners.

### FL11.2 Required economics
Evaluate at least:

- net expectancy after all costs,
- profit factor,
- max drawdown/tail loss,
- average winner/loser,
- turnover,
- capacity,
- fee/slippage burden,
- expected-vs-realized EV calibration,
- entry-price efficiency,
- exit-timing efficiency,
- missed-opportunity cost,
- performance by strategy/regime/horizon.

### FL11.3 Latency proof
The measured event->decision->simulated/realistic-fill latency must be compatible with the edge claimed by short-horizon strategies.

### FL11.4 Champion/challenger promotion
Promotion remains explicit, versioned, and auditable.

**Exit criterion:** The champion demonstrates repeatable positive net expectancy with acceptable risk/capacity/latency under chronological PAPER/shadow evidence.

---

## FL12 — LIVE execution promotion gate

This remains disabled until FL11 and all required operational/risk gates pass.

### FL12.1 Live Fast Lane path
The approved runtime may request capital-changing actions, but the independent risk authority must validate them and create/authorize the execution intent.

### FL12.2 Immediate repricing
Before submission:

- verify LIVE mode is explicitly enabled,
- verify idempotency,
- recheck notional/exposure/halts,
- use freshest executable state,
- confirm current price remains inside the maximum acceptable entry/exit boundary,
- confirm slippage/impact/capacity,
- abort materially changed trades.

### FL12.3 Low-latency submission
Use appropriate Solana submission/priority mechanisms only when their measured benefit exceeds their cost and they do not create a forbidden paid-data dependency.

### FL12.4 Tiny capital first
Initial LIVE capital must be deliberately small and strictly capped.

### FL12.5 Reconciliation
Actual onchain fills, balances, fees, and positions must reconcile against intent/accounting state.

**Exit criterion:** Shreks can autonomously trade the proven Fast Lane champion with strict capital limits, deterministic risk authority, price-bound execution, and complete reconciliation.

---

# 4. CROSS-CUTTING INVARIANTS

These apply to every FL phase.

## 4.1 LIVE remains disabled
No Fast Lane observation, state, forecasting, PAPER, or learning task may implicitly enable live trading.

## 4.2 Manipulation is data; execution/risk can still veto a trade
Do not discard a token merely because activity appears coordinated/manipulated. Record the descriptors and learn the path.

A particular trade can still be blocked for capital/execution reasons such as impossible exit, stale state, excessive slippage, accounting uncertainty, or active risk halt.

## 4.3 No look-ahead leakage
Future path and counterfactual labels are research targets only.

## 4.4 Cost-aware everywhere
Strategy evaluation without realistic round-trip costs is invalid.

## 4.5 Event-driven means event-driven
Prediction horizons are not timers. A material event between horizons may immediately change the chosen action.

## 4.6 One approved champion
Research may run many challengers, but production/shadow behavior must always identify the exact approved artifact/policy version used.

## 4.7 Deterministic replay where possible
The same ordered event stream, code version, configuration, and champion artifact must reproduce the same state and decisions, subject only to explicitly documented numerical tolerances.

## 4.8 Evidence before optimization
Do not add infrastructure or complexity until profiling shows the current design is insufficient.

---

# 5. BUILD DISCIPLINE

For every implementation slice:

1. read `SHREKS_MASTER_SOURCE_OF_TRUTH.md`,
2. read this build order,
3. identify the active FL phase,
4. inspect current repository code/interfaces before designing replacements,
5. write a focused spec/plan for multi-step changes,
6. write RED tests first,
7. prove RED fails for the intended reason,
8. implement the smallest correct behavior,
9. run focused GREEN tests,
10. run full relevant CI including Rust/Python/repository-safety/ARM64 where applicable,
11. inspect the diff for architecture drift,
12. merge only with verified evidence,
13. obtain physical VPS evidence whenever runtime behavior changes,
14. update durable docs when architecture/build sequencing changes.

Never claim a phase complete without exact verification evidence.

---

# 6. CURRENT POSITION — 2026-08-28

### Canonical architecture

The Fast Lane Source of Truth was merged to `main` in commit:

`ef47e803a0f896961ce9ae519bee765322ec996f`

Its branch CI and merged-main CI are GREEN across:

- Rust,
- Python,
- repository safety,
- native ARM64 release build.

### Preserved production evidence

The canonical-pair selector correction was physically accepted on the VPS at release:

`330ace280067905b6502ba3846f73b2b461be125`

The verified-Pump-market-evidence fix is merged and GitHub-sealed at:

`29f6dd9b747e053569d14d54a2f346b46ed103ac`

Do **not** claim physical VPS acceptance of that newer seal until separate host evidence proves it.

### Active next build

**Begin FL0, then FL1/FL2.**

The first implementation target should be the smallest deterministic foundation required by everything else:

1. inspect/map existing Pump swap/event capabilities and observer/storage interfaces,
2. define the versioned Fast Lane event/state boundary,
3. implement deterministic `FastMarketState`/rolling-window behavior under RED→GREEN tests,
4. only then wire real production event ingestion into it.

Do not begin learned models, live execution, or strategy optimization before the event/state/economics/label foundations exist.

---

# 7. DEFERRED UNTIL EVIDENCE REQUIRES IT

Do not build prematurely:

- multi-chain support,
- leverage/perpetuals,
- paid data feeds/RPC as a requirement,
- social/X dependency,
- Telegram trading-control bot,
- Kafka,
- Kubernetes,
- unnecessary microservice split,
- reinforcement learning,
- self-modifying live strategies,
- custom Solana onchain program.

---

# 8. DEFINITION OF BUILD SUCCESS

The build is complete only when Shreks can:

`capture event -> reconstruct state -> forecast paths -> calculate executable net EV -> choose BUY/SKIP/HOLD/REDUCE/SELL -> enforce risk -> realistically PAPER execute -> learn counterfactuals -> prove edge -> run reliably on VPS -> promote deliberately -> trade LIVE with tiny controlled capital`

Until then, LIVE TRADING REMAINS DISABLED.
