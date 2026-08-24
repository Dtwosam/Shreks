# Phase E5 Trading Evaluation Design

## Status

Approved for autonomous implementation under the project instruction to continue the build order without repeated approval prompts.

## Source-of-truth alignment

Phase E5 follows the repository hierarchy:

1. `SHREKS_MASTER_SOURCE_OF_TRUTH.md` defines the optimization target as positive trading expectancy after real costs and names the primary evaluation metrics: expectancy after costs, profit factor, maximum drawdown, average winner, average loser, win rate, calibration, setup performance, market-regime performance, turnover, and cost burden.
2. `SHREKS_BUILD_ORDER.md` defines E5 as **Trading evaluation** and lists the same measurement families.
3. Frozen E4 head `bde1be6b2d89b6934497c25e225ad63d911790e3` provides leakage-safe chronological unseen probabilities and preserves exact prediction identities/fold provenance.
4. Earlier sealed paper/accounting layers already define realistic execution economics and authoritative realized PnL/cost concepts. E5 must measure those economics, not replace them with a second fill simulator.

E5 deliberately stops before E6. It measures and records performance but does not select a champion, decide whether a challenger beats a baseline, set promotion thresholds, paper/shadow deploy a challenger, or enable live money.

## Problem

A model can look good on a classification metric and still lose money after trading costs. A strategy can show a high win rate while one large loser destroys expectancy. A backtest can also look profitable only because it assumes perfect fills or hides fees, slippage, price impact, failed execution, or poor exits.

E4 solves chronological leakage, but its output intentionally contains no trading metric. E5 therefore needs a strict measurement layer that:

- evaluates realized/normalized closed-trade economics after costs;
- computes the source-of-truth trading metrics deterministically;
- segments performance by setup and market regime;
- evaluates probabilistic calibration on E4's unseen prediction population;
- preserves provenance and reproducibility;
- does not invent trade selection, fill assumptions, or promotion rules.

## Key design decision: measurement, not simulation

E5-v1 does **not** derive a trade from a D6 future-return label and does not invent a synthetic fill model.

Instead, callers supply normalized closed-trade economic evidence. Each trade explicitly carries:

- pre-cost gross PnL;
- execution-friction cost already attributed by the caller (for example slippage/price-impact effects);
- explicit fees/costs already attributed by the caller (for example swap/network costs);
- net realized PnL;
- turnover/notional evidence;
- setup and regime provenance.

E5 verifies that those economics reconcile and then aggregates them.

This boundary is deliberate. Historical replay, paper execution, or later shadow/live adapters may create the normalized trade evidence, but E5 itself cannot claim realism by fabricating execution assumptions.

## Approaches considered

### 1. Normalize economic evidence, then aggregate — selected

Create one explicit `EvaluatedTrade` contract and one deterministic evaluator.

Advantages:

- no hidden fill assumptions;
- can consume historical, paper, shadow, or later live normalized outcomes;
- cost accounting stays auditable;
- E5 remains pure and deterministic;
- later E6 can persist reports without recomputing metrics.

Trade-off: callers must produce valid closed-trade economics before E5 can evaluate them.

### 2. Build a second historical fill simulator inside E5

Rejected. C1/C2 already own realistic fill mechanics, and D6 future-return labels do not contain enough information to reconstruct a truthful route/latency/partial-fill path. A second simulator would create conflicting economics.

### 3. Evaluate raw D6 return labels directly as trading returns

Rejected. That would silently ignore execution costs and exit constraints, violating the master source of truth and making false-profit results too easy.

## Package boundary

Add a new pure Python package:

```text
python/src/shreks_brain/evaluation/
  __init__.py
  models.py
  engine.py
  calibration.py
```

Public schema version:

```python
TRADING_EVALUATION_SCHEMA_VERSION = "e5-trading-evaluation-v1"
```

E5 adds no external dependency.

## Public models

### `TradingEvaluationPolicy`

Immutable, slotted dataclass:

- `version: str`
- `starting_equity_usd: float`
- `calibration_bucket_count: int`

Rules:

- version is non-empty;
- starting equity is finite and strictly positive;
- calibration bucket count is an integer from 2 through 100 and not bool.

E5 ships no default starting capital and no default calibration bucket count.

### `EvaluatedTrade`

Immutable, slotted dataclass:

- `candidate_version: str`
- `position_id: str`
- `candidate_mint: str`
- `setup_name: str`
- `market_regime: str`
- `opened_at_unix_ms: int`
- `closed_at_unix_ms: int`
- `entry_notional_usd: float`
- `turnover_usd: float`
- `gross_pnl_usd: float`
- `execution_friction_usd: float`
- `explicit_cost_usd: float`
- `net_pnl_usd: float`

Definitions:

- `gross_pnl_usd` is the caller's pre-cost closed-trade economic result;
- `execution_friction_usd` is non-negative caller-attributed execution friction such as slippage/price-impact effects;
- `explicit_cost_usd` is non-negative caller-attributed explicit fees such as swap/network costs;
- `net_pnl_usd = gross_pnl_usd - execution_friction_usd - explicit_cost_usd`;
- `turnover_usd` is the total capital transacted for that closed trade and must be at least the positive entry notional;
- close time cannot precede open time.

`candidate_version` identifies the strategy/model candidate being measured. E5 does not interpret whether that version is a baseline, deterministic policy, model challenger, paper run, or later live version.

### `ProbabilityObservation`

Immutable, slotted dataclass:

- `candidate_version: str`
- `model_version: str`
- `candidate_mint: str`
- `as_of_unix_ms: int`
- `positive_probability: float`
- `target_positive: bool`
- `setup_name: str`
- `market_regime: str`
- `fold_name: str`

Rules:

- probability is finite in `[0, 1]`;
- target is exact bool;
- strings are non-empty;
- timestamp is non-negative int and not bool.

The observation represents an unseen E4 prediction after its selected target has matured for evaluation. E5 never uses that target to change the already-frozen prediction.

### `TradingPerformanceMetrics`

Immutable, slotted dataclass with:

- `trade_count`
- `win_count`
- `loss_count`
- `flat_count`
- `gross_pnl_usd`
- `net_pnl_usd`
- `net_expectancy_usd`
- `net_expectancy_pct`
- `profit_factor`
- `maximum_drawdown_usd`
- `maximum_drawdown_pct`
- `average_winner_usd`
- `average_loser_usd`
- `win_rate`
- `turnover_usd`
- `turnover_to_starting_equity`
- `execution_friction_usd`
- `explicit_cost_usd`
- `total_cost_usd`
- `cost_burden_pct`

Undefined metrics are represented by `None`, not fabricated zeros. Examples:

- no trades -> expectancy, profit factor, win rate, average winner/loser are `None`;
- no losing trades -> profit factor is `None` rather than infinity;
- no winning trades -> average winner is `None`.

Zero-valued metrics remain valid where economically defined, such as total cost or maximum drawdown.

### Metric formulas

For canonical closed trades:

```text
net_expectancy_usd = mean(net_pnl_usd)
net_expectancy_pct = mean(net_pnl_usd / entry_notional_usd * 100)
profit_factor = sum(positive net_pnl) / abs(sum(negative net_pnl))
win_rate = wins / trade_count
turnover_to_starting_equity = turnover_usd / starting_equity_usd
total_cost_usd = execution_friction_usd + explicit_cost_usd
cost_burden_pct = total_cost_usd / turnover_usd * 100
```

A flat trade has net PnL exactly zero and is neither a win nor a loss.

Maximum drawdown is calculated over the canonical realized-equity path:

```text
equity_0 = starting_equity_usd
equity_n = starting_equity_usd + cumulative net_pnl_usd through trade n
```

Trades are ordered by:

```text
(closed_at_unix_ms, opened_at_unix_ms, position_id, candidate_mint)
```

At each point E5 tracks the running equity peak. Drawdown is the largest peak-minus-current-equity decline. Percentage drawdown is relative to that running peak. If any cumulative equity would become negative, evaluation fails closed because the supplied trade sequence is inconsistent with the configured no-leverage starting-equity basis.

### `CalibrationBucket`

Immutable, slotted dataclass:

- `bucket_index`
- `lower_probability`
- `upper_probability`
- `observation_count`
- `mean_predicted_probability`
- `observed_positive_rate`
- `absolute_calibration_gap`

Fixed equal-width buckets are defined by `calibration_bucket_count` across `[0,1]`. All buckets except the last are half-open; the last includes probability `1.0`.

Empty buckets are retained with count `0` and `None` means/rates/gaps. Keeping them makes the calibration schema stable and auditable.

### `CalibrationReport`

Immutable, slotted dataclass:

- `observation_count`
- `positive_count`
- `brier_score`
- `expected_calibration_error`
- `buckets`

Formulas:

```text
brier_score = mean((probability - target)^2)
expected_calibration_error = sum(bucket_count / total * absolute_bucket_gap)
```

Both are deterministic descriptive metrics. E5 does not choose acceptance thresholds.

### `SegmentPerformance`

Immutable, slotted dataclass:

- `segment_name: str`
- `metrics: TradingPerformanceMetrics`

Setup segments are keyed by `setup_name` and sorted lexically. Regime segments are keyed by the supplied regime string and sorted lexically.

Every trade belongs to exactly one setup segment and exactly one regime segment. Segment trade counts must reconcile to the overall trade count.

### `TradingEvaluationReport`

Immutable, slotted dataclass:

- `schema_version`
- `policy_version`
- `candidate_version`
- `metrics`
- `calibration: CalibrationReport | None`
- `setup_performance: tuple[SegmentPerformance, ...]`
- `regime_performance: tuple[SegmentPerformance, ...]`
- `evaluation_fingerprint_sha256`

Rules:

- exact schema version;
- non-empty policy/candidate versions;
- canonical segment ordering;
- unique segment names;
- segment counts reconcile to overall metrics;
- lowercase 64-character SHA-256 fingerprint.

Calibration may be `None` for a non-probabilistic candidate or when the caller intentionally evaluates trading economics without probability observations. If probability observations are supplied, calibration is required and all observations must use the report candidate version.

## E4 probability adapter

E5 exposes:

```python
build_probability_observations_from_e4(
    rows: tuple[dict[str, object], ...],
    validation_run: TimeAwareValidationRun,
    candidate_version: str,
) -> tuple[ProbabilityObservation, ...]
```

Purpose: join frozen E4 unseen predictions to the selected target only after evaluation evidence exists.

Rules:

- rows must be non-empty exact D6 logical row dicts with the sealed physical column set and unique `(candidate_mint, as_of_unix_ms)` identity;
- every E4 prediction identity must exist exactly once in rows;
- selected target horizon comes from `validation_run.model_training_request.target.horizon_seconds`;
- selected target status must be `COMPLETED` at E5 evaluation time;
- selected return must be finite;
- target positivity uses the exact E3 training threshold:

```text
return_pct >= model_training_request.target.minimum_return_pct
```

- prediction probability is copied unchanged from E4;
- `setup_name` and `market_regime` come from the D6 decision-time row;
- fold name comes from the E4 fold containing the prediction;
- observations are sorted by `(as_of_unix_ms, candidate_mint)`;
- duplicate prediction identities across folds are rejected;
- extra D6 rows outside E4 validation populations are allowed and ignored.

A target may complete after the fold's validation start because E5 is precisely the later evaluation phase. That later target can score the frozen prediction but can never alter it.

## Evaluation engine

Public function:

```python
evaluate_trading_performance(
    trades: tuple[EvaluatedTrade, ...],
    probability_observations: tuple[ProbabilityObservation, ...],
    policy: TradingEvaluationPolicy,
    candidate_version: str,
) -> TradingEvaluationReport
```

Behavior:

1. validate exact input container/types;
2. require every trade/observation candidate version to equal `candidate_version`;
3. require unique trade `position_id` values;
4. require unique probability `(candidate_mint, as_of_unix_ms)` identities;
5. canonicalize trade and probability order;
6. compute overall trading metrics;
7. compute setup and regime segments from the same trade population;
8. compute calibration when observations exist;
9. compute a canonical report fingerprint.

Input ordering is not semantic.

## Evaluation fingerprint

The report fingerprint is SHA-256 over canonical standard-library values including:

- E5 schema version;
- policy version and starting-equity/calibration settings;
- candidate version;
- every canonical trade identity and exact economics;
- every probability observation identity/probability/target/fold;
- overall metrics;
- setup/regime segment metrics;
- calibration report.

Finite floats are encoded with exact hexadecimal representation before JSON hashing.

The fingerprint is provenance, not a score and not a promotion decision.

## Metric semantics

### Net expectancy

Net expectancy is calculated after all supplied execution friction and explicit costs have already been deducted into `net_pnl_usd`.

E5 reports both USD-per-trade and entry-notional-normalized percentage expectancy.

### Profit factor

Uses net realized PnL, not gross PnL.

### Drawdown

Uses the realized closed-trade equity sequence and the explicit starting equity. E5-v1 does not manufacture mark-to-market drawdown from missing intra-trade prices.

This makes E5's drawdown conservative in scope: **realized-equity drawdown**, not an intratrade MFE/MAE proxy.

### Average winner/loser and win rate

Based strictly on net realized PnL after costs.

### Turnover

Uses supplied trade turnover. E5 does not infer turnover from entry notional alone.

### Costs

E5 separates:

- execution friction;
- explicit costs;
- total costs;
- total-cost burden relative to turnover.

It never subtracts cost twice because `EvaluatedTrade` reconciliation fixes the relationship between gross PnL, costs, and net PnL.

### Calibration

Calibration is computed over all supplied unseen probability observations, not only observations that later became trades. Restricting calibration to entered trades would introduce selection bias.

### Setup and regime performance

Both reuse the exact same normalized trade records and formulas as the global report. No segment-specific metric formula is allowed.

## Non-goals

E5-v1 does **not**:

- choose a probability threshold;
- convert E4 probabilities into `ENTER` decisions;
- generate `TradeIntent` objects;
- simulate fills or exits;
- infer missing costs;
- infer missing turnover;
- derive realized PnL from D6 future returns;
- compare two reports and declare a winner;
- decide whether a challenger beats E2 baselines;
- define acceptable drawdown;
- define sample-size requirements;
- define promotion gates;
- persist a champion/challenger registry;
- shadow/paper deploy a challenger;
- alter E1/E2/E3/E4 behavior;
- alter B7/B8/B9/C1-C6 behavior;
- sign or submit a transaction;
- enable live money.

E6 owns durable champion/challenger evaluation records and promotion state. E7/E8 own shadow/paper challenger operation and explicit promotion rules.

## Purity and dependency boundary

Production E5 code is standard-library only.

It performs no:

- SQLite access;
- PyArrow access;
- filesystem I/O;
- network calls;
- wall-clock reads;
- random-number generation;
- sklearn import.

Importing `shreks_brain.evaluation` must not eagerly import sklearn or PyArrow.

## Determinism

Equivalent logical inputs produce identical reports and fingerprints regardless of input ordering because:

- trades are sorted canonically;
- probability observations are sorted canonically;
- setup/regime segments are sorted lexically;
- calibration buckets use deterministic fixed boundaries;
- floats use exact hexadecimal fingerprint encoding;
- no random or wall-clock input exists.

## Error handling

E5 fails closed for:

- malformed trade economics;
- non-reconciling gross/cost/net PnL;
- duplicate trade position IDs;
- negative/invalid turnover or entry notional;
- impossible chronological trade boundaries;
- trade/observation candidate-version mismatch;
- duplicate probability identities;
- malformed probability or target values;
- malformed D6 rows in the E4 adapter;
- missing E4 prediction identity in D6 rows;
- selected E4 target still pending at evaluation;
- selected target return missing/non-finite;
- cumulative realized equity below zero under configured starting equity;
- non-finite derived metrics;
- report reconciliation/fingerprint contradictions.

No failure path drops a losing trade, changes a target, widens a fold, fills missing costs with zero, or substitutes a promotion decision.

## Public API

`shreks_brain.evaluation.__all__` must expose exactly:

```text
TRADING_EVALUATION_SCHEMA_VERSION
TradingEvaluationPolicy
EvaluatedTrade
ProbabilityObservation
TradingPerformanceMetrics
CalibrationBucket
CalibrationReport
SegmentPerformance
TradingEvaluationReport
build_probability_observations_from_e4
evaluate_trading_performance
```

## Test strategy

### Contract RED -> GREEN

Tests first define:

- schema constant;
- frozen/slotted contracts;
- exact input validation;
- trade economic reconciliation;
- optional/undefined metric semantics;
- calibration bucket/report reconciliation;
- segment/report reconciliation;
- explicit public API.

Expected RED: missing `shreks_brain.evaluation`.

### E4 adapter RED -> GREEN

Tests prove:

- E4 prediction identity joins to exact D6 rows;
- selected target horizon/threshold come from frozen E4 request;
- future target completion may score a frozen prediction;
- pending/missing selected target fails closed;
- setup/regime/fold provenance is preserved;
- unrelated non-selected future labels cannot alter observations;
- shuffled rows produce identical observations;
- duplicate/missing identities fail closed.

### Metrics engine RED -> GREEN

Tests separately prove:

- net expectancy in USD and percent;
- profit factor on net PnL;
- no-loss profit factor is `None`;
- realized-equity maximum drawdown and percentage;
- average winner/loser;
- win/loss/flat counts and win rate;
- turnover and turnover/equity ratio;
- execution friction, explicit cost, total cost, and cost burden;
- deterministic setup performance;
- deterministic regime performance;
- empty-trade behavior;
- deterministic calibration buckets, Brier score, and ECE;
- calibration uses all supplied probability observations, independent of trade population;
- input-order independence;
- deterministic evaluation fingerprint;
- candidate-version isolation;
- no promotion/winner field exists;
- import/purity boundary.

### Full repository gate

Every GREEN point runs existing CI:

- repository safety;
- all Python tests;
- Rust tests/workspace metadata.

## Phase boundary

E5 completion proves that Shreks can measure normalized unseen/paper trading evidence consistently, after supplied realistic costs, and can quantify model probability calibration without leakage.

It still does **not** prove that any challenger deserves promotion or that Shreks is profitable. E6 must persist champion/challenger evaluation records; later paper/shadow evidence and explicit E8 gates are still required before any promotion or live-money authority.