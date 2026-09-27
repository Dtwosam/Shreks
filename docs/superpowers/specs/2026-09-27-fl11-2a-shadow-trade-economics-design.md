# Fast Lane FL11.2a Learned-Shadow Closed-Trade Economics — Design

**Date:** 2026-09-27  
**Base main SHA:** `a35fcbe0ca84150e646018d6fa2e7ac1c1b0884e`

## Purpose

Build the first FL11.2 economics slice for the current learned Fast Lane
PAPER-shadow runtime without creating a second PnL/accounting formula.

FL11.2a covers **executed closed-trade economics only**. It reconstructs the
persisted learned-shadow execution history, adapts the exact resulting
`PaperExecutionResult` / `PaperLedgerUpdate` values into the already-sealed
E11 paper-evaluation adapter, and then uses the existing E5 trading evaluator.

This slice reports:

- after-cost net expectancy;
- profit factor;
- maximum drawdown;
- average winner / loser;
- turnover;
- actual execution-friction and explicit-cost burden;
- loss-tail observations;
- expected selected value versus realized net return;
- entry slippage/cost efficiency;
- decision-to-close booking latency;
- holding duration versus the selected entry horizon;
- entry notional versus the authenticated trading-capital context;
- performance by regime and selected entry horizon.

It deliberately does **not** fabricate counterfactual missed-opportunity
outcomes or arbitrary fee/slippage sensitivity scenarios. Those require a
separate FL11.2 slice with authenticated counterfactual/future-path evidence.

## Prerequisite: FL11.1

The command requires a canonical FL11.1 report for the exact same:

- release;
- manifest/champion/action-policy identity;
- shadow ledger binding;
- window.

The report must say `SUFFICIENT_SAMPLE`.

An `INSUFFICIENT_SAMPLE` report cannot be bypassed by FL11.2a.

## Reconstruction boundary

The proof authenticates the exact runtime manifest, execution policy, isolated
shadow ledger/run id, decision evidence, fresh execution-source records, and
pending-BUY retry-source records.

It loads the isolated checkpoint at or before the requested window end and
requires every durable checkpoint transition from sequence zero through that
checkpoint to have exactly one authenticated source:

- one fresh learned decision; or
- one pending-BUY retry.

For every transition it:

1. loads the exact historical checkpoint/runtime pair;
2. reads the canonical source bound to that pair;
3. reconstructs the existing sealed transition without storage mutation;
4. loads the durable successor checkpoint/runtime pair;
5. requires the successor to equal the reconstruction.

This makes the economics adapter a read-only replay of already-booked PAPER
truth rather than a new simulator.

## Reuse of sealed E11/E5 economics

Terminal reconstructed executions are converted into
`FastPaperExecutionEvidenceInput` values.

Opening BUYs receive their exact authenticated `MarketRegime` entry context.
Deferred BUYs that later fill through retry retain the original learned
decision/horizon/regime while using the retry's actual trading-capital context.

The existing:

```text
extract_fast_paper_evaluation_evidence(...)
build_evaluated_trades(...)
evaluate_trading_performance(...)
```

remain authoritative for closed-trade PnL, costs, turnover, profit factor,
winner/loser averages, and drawdown.

FL11.2a must not duplicate those formulas.

## Window semantics

The proof reconstructs complete history from sequence zero through the
checkpoint at the requested end time so trades that opened before the window
can still be evaluated correctly.

The final economic population contains only trades whose canonical
`closed_at_unix_ms` is inside:

```text
[since_unix_ms, until_unix_ms)
```

That closed-trade count must reconcile with the FL11.1 report for the same
window.

## Additional descriptive metrics

### Expected-versus-realized selected value

For each evaluated closed position:

- expected value = opening learned BUY `selected_value_bps`;
- realized value = E5 net PnL / E5 entry notional, in bps;
- error = realized - expected.

The report exposes count, means, mean error, mean absolute error, and
nearest-rank p50/p95 absolute error.

This is descriptive calibration evidence, not a pass threshold.

### Loss tail

For closed losing trades report:

- worst net PnL;
- worst net return bps;
- nearest-rank p95 absolute loss in USD;
- nearest-rank p95 absolute loss in bps.

### Entry efficiency

For each evaluated position's opening BUY fill:

- signed slippage bps from the sealed fill evidence;
- explicit cost bps.

### Exit timing

For each evaluated position:

- holding duration;
- holding duration minus selected entry horizon;
- final close decision evaluation to booked-close latency.

### Capacity observation

For each evaluated entry:

- entry notional / authenticated trading capital at actual opening execution.

This is a descriptive capital-utilization observation, not a risk-limit
threshold.

## Horizon performance

E5 already reports overall and market-regime performance. FL11.2a groups the
same E5 `EvaluatedTrade` values by their authenticated opening selected
horizon and reruns the same sealed E5 evaluator on each group.

No new PnL arithmetic is introduced.

## Authority firewall

The command is read-only and must contain no:

- PAPER execution or ledger mutation;
- champion/registry mutation;
- scoring control path;
- provider/network client;
- systemd mutation;
- signing/submission;
- LIVE mode.

Every report records:

```text
promotion_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Acceptance

Repository tests must prove:

1. FL11.1 `SUFFICIENT_SAMPLE` with exact identity/window is mandatory;
2. a complete fresh BUY -> SELL closed position reconstructs into the sealed
   E11/E5 trade path;
3. deferred BUY retry -> later SELL remains attributable to the original
   learned entry decision/regime/horizon;
4. every durable checkpoint before the window end requires exactly one source;
5. durable successors must equal reconstructed transitions;
6. selected closed-trade count reconciles with FL11.1;
7. E5 net expectancy/profit factor/drawdown/winner/loser/turnover/cost metrics
   are surfaced without reimplementation;
8. regime and horizon performance reconcile to the same closed-trade
   population;
9. expected-realized, tail, entry-efficiency, exit-timing, and capital
   utilization metrics are deterministic;
10. no promotion/PAPER cutover/signing/LIVE authority is added;
11. Python, Rust, repository-safety, and ARM64 release gates stay green.

## Following FL11.2 slices

A later FL11.2 counterfactual slice must add authenticated missed-opportunity
behavior and explicit fee/slippage sensitivity evidence. Only after those
required economics pieces exist should FL11.3 latency proof be considered.

LIVE remains disabled.
