# Phase E5 Trading Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic E5 measurement layer that aggregates normalized after-cost closed-trade economics, segments performance by setup/regime, and evaluates calibration of frozen E4 unseen probabilities without inventing fills or promotion rules.

**Architecture:** Add `shreks_brain.evaluation` with immutable contracts in `models.py`, E4/D6 joining in `calibration.py`, and trading/calibration aggregation plus canonical fingerprinting in `engine.py`. E5 consumes explicit normalized economics rather than deriving trades from D6 return labels, and uses E4 predictions only for later calibration against completed selected targets.

**Tech Stack:** Python 3.12+, standard-library dataclasses/hashlib/json/math/statistics, sealed D6 research schema, sealed E3/E4 prediction contracts, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-e5-trading-evaluation-design.md`

## Global Constraints

- Base exactly on frozen E4 head `bde1be6b2d89b6934497c25e225ad63d911790e3`; do not modify E1/E2/E3/E4 production files.
- Public schema version is exactly `e5-trading-evaluation-v1`.
- E5 invents no starting capital, calibration bucket count, fill assumption, probability threshold, promotion threshold, or cost default.
- Trading metrics use normalized closed-trade economics supplied by the caller; E5 does not derive a trade from D6 future returns.
- `net_pnl_usd == gross_pnl_usd - execution_friction_usd - explicit_cost_usd` for every trade.
- Trading metrics use net realized PnL after costs.
- Maximum drawdown is realized-equity drawdown from explicit starting equity, not an MFE/MAE proxy.
- Calibration uses all supplied unseen probability observations, not only traded observations.
- E4 probability adapter may read the selected future target only after prediction and must never alter frozen E4 model/prediction evidence.
- E5 does not compare reports, declare a winner, persist champion/challenger state, define promotion rules, or enable live money.
- Input order must not change canonical outputs or evaluation fingerprint.
- E5 adds no dependency and must not import sklearn or PyArrow eagerly.
- Production E5 code performs no SQLite, filesystem, network, wall-clock, or random access.
- Every branch move is single-purpose: tests-only RED, implementation GREEN, or docs-only seal.

---

### Task 1: Immutable E5 contracts

**Files:**
- Create: `python/src/shreks_brain/evaluation/__init__.py`
- Create: `python/src/shreks_brain/evaluation/models.py`
- Create: `python/tests/test_trading_evaluation_models.py`
- Create: `python/tests/test_trading_evaluation_public_api.py`

**Interfaces:**
- Produces `TRADING_EVALUATION_SCHEMA_VERSION = "e5-trading-evaluation-v1"`.
- Produces frozen/slotted `TradingEvaluationPolicy`, `EvaluatedTrade`, `ProbabilityObservation`, `TradingPerformanceMetrics`, `CalibrationBucket`, `CalibrationReport`, `SegmentPerformance`, and `TradingEvaluationReport`.
- Task 1 public API contains only those nine contract symbols; Task 2/3 REDs add the two public functions.

- [ ] **Step 1: Write contract RED tests**

Require schema and frozen/slotted contracts. Core fixtures should include:

```python
policy = TradingEvaluationPolicy(
    version="eval-policy-v1",
    starting_equity_usd=1_000.0,
    calibration_bucket_count=10,
)

trade = EvaluatedTrade(
    candidate_version="challenger-v1",
    position_id="position-1",
    candidate_mint="mint-a",
    setup_name="fresh_launch_continuation",
    market_regime="NORMAL",
    opened_at_unix_ms=1_000,
    closed_at_unix_ms=2_000,
    entry_notional_usd=100.0,
    turnover_usd=210.0,
    gross_pnl_usd=12.0,
    execution_friction_usd=1.0,
    explicit_cost_usd=1.0,
    net_pnl_usd=10.0,
)
```

Tests must separately reject:

- empty strings;
- bool/negative timestamps;
- non-finite numeric values;
- non-positive starting equity/entry notional;
- calibration bucket counts outside `[2,100]` or bool;
- close before open;
- turnover below entry notional;
- negative execution friction or explicit cost;
- non-reconciling gross/cost/net PnL;
- probability outside `[0,1]` or non-bool target;
- invalid count reconciliation in `TradingPerformanceMetrics`;
- malformed empty/non-empty calibration bucket semantics;
- malformed `CalibrationReport` bucket ordering/count reconciliation;
- malformed segment/report ordering, duplicate names, or segment-count reconciliation;
- invalid SHA-256 fingerprint.

Explicitly prove undefined metric semantics allow `None` where the spec says undefined.

Task 1 public API must equal:

```python
(
    "TRADING_EVALUATION_SCHEMA_VERSION",
    "TradingEvaluationPolicy",
    "EvaluatedTrade",
    "ProbabilityObservation",
    "TradingPerformanceMetrics",
    "CalibrationBucket",
    "CalibrationReport",
    "SegmentPerformance",
    "TradingEvaluationReport",
)
```

- [ ] **Step 2: Attach tests-only RED and verify expected failure**

Run full CI on the tests-only head. Expected Python failure: `ModuleNotFoundError: No module named 'shreks_brain.evaluation'`. Repository safety and Rust/workspace must stay green.

- [ ] **Step 3: Implement contract models**

`models.py` must use exact-type/fail-closed validation consistent with E3/E4. Include private helpers for non-empty strings, exact bool, timestamps, finite/positive/non-negative numbers, optional finite values, counts, `[0,1]` fractions, close arithmetic, and lowercase SHA-256.

`EvaluatedTrade.__post_init__` must enforce:

```python
closed_at_unix_ms >= opened_at_unix_ms
turnover_usd >= entry_notional_usd
net_pnl_usd == gross_pnl_usd - execution_friction_usd - explicit_cost_usd
```

`TradingPerformanceMetrics.__post_init__` must enforce:

```python
trade_count == win_count + loss_count + flat_count
```

and consistency rules such as no average winner when `win_count == 0`, no average loser when `loss_count == 0`, `win_rate is None` when `trade_count == 0`, and non-negative drawdown/cost/turnover fields.

`CalibrationBucket` requires deterministic bounds and `None` statistics for empty buckets; non-empty buckets require finite probabilities/rates/gap.

`CalibrationReport` requires non-empty observations, bucket indices `0..N-1`, total bucket count reconciliation, and positive count reconciliation.

`TradingEvaluationReport` requires canonical lexical setup/regime segments and overall/segment trade-count reconciliation.

- [ ] **Step 4: Verify contract GREEN**

Run:

```bash
python -m pytest python/tests/test_trading_evaluation_models.py -q
python -m pytest python/tests/test_trading_evaluation_public_api.py -q
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: full repository GREEN.

- [ ] **Step 5: Commit**

Commit message:

```text
feat: define E5 evaluation contracts
```

---

### Task 2: Frozen-E4 probability observation adapter

**Files:**
- Create: `python/src/shreks_brain/evaluation/calibration.py`
- Modify: `python/src/shreks_brain/evaluation/__init__.py`
- Create: `python/tests/test_trading_evaluation_e4_adapter.py`
- Modify: `python/tests/test_trading_evaluation_public_api.py`

**Interfaces:**
- Consumes sealed D6 rows and exact `TimeAwareValidationRun`.
- Produces:

```python
build_probability_observations_from_e4(
    rows: tuple[dict[str, object], ...],
    validation_run: TimeAwareValidationRun,
    candidate_version: str,
) -> tuple[ProbabilityObservation, ...]
```

- [ ] **Step 1: Write adapter RED tests**

Build D6 logical rows using the sealed research physical columns. Build a small exact E4 `TimeAwareValidationRun` fixture with at least two predictions and one selected target horizon.

Tests must prove:

1. the adapter returns canonical `(as_of_unix_ms, candidate_mint)` order even when rows are shuffled;
2. `target_positive` uses exactly the E4 request's selected horizon and `minimum_return_pct`;
3. a selected target completed after E4 validation start is valid evaluation evidence and does not alter the frozen probability;
4. selected target status `PENDING` fails closed with prediction identity context;
5. missing/non-finite selected return fails closed;
6. `setup_name`, `market_regime`, `model_version`, and fold name are preserved;
7. changing only non-selected future-label values does not alter returned observations;
8. extra D6 rows outside the E4 prediction population are ignored;
9. malformed D6 schema, duplicate D6 identity, missing E4 prediction identity, duplicate prediction identity, wrong validation-run type, or empty candidate version fails closed.

Update public API expectation to include `build_probability_observations_from_e4` but not `evaluate_trading_performance` yet.

- [ ] **Step 2: Attach adapter tests-only RED**

Expected Python failure: cannot import `build_probability_observations_from_e4` from `shreks_brain.evaluation`. No unrelated failure.

- [ ] **Step 3: Implement D6/E4 join**

In `calibration.py`:

```python
_D6_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
_D6_COLUMN_SET = frozenset(_D6_COLUMNS)
```

Validate rows globally with the sealed D6 schema and unique `(candidate_mint, as_of_unix_ms)` identity. Do not semantically validate non-selected future labels.

For selected horizon:

```python
prefix = f"label_{validation_run.model_training_request.target.horizon_seconds}s_"
status_column = prefix + "status"
return_column = prefix + "return_pct"
```

For every E4 prediction, require exact row identity, selected status `COMPLETED`, and finite selected return. Compute:

```python
target_positive = (
    selected_return
    >= float(validation_run.model_training_request.target.minimum_return_pct)
)
```

Copy the prediction probability unchanged and preserve row setup/regime plus fold name.

- [ ] **Step 4: Verify adapter GREEN**

Run focused adapter/public API tests, then full Python/Rust/repository-safety CI.

- [ ] **Step 5: Commit**

```text
feat: join E4 predictions to evaluation targets
```

---

### Task 3: Trading metrics, calibration, segmentation, and fingerprint

**Files:**
- Create: `python/src/shreks_brain/evaluation/engine.py`
- Modify: `python/src/shreks_brain/evaluation/__init__.py`
- Create: `python/tests/test_trading_evaluation_engine.py`
- Modify: `python/tests/test_trading_evaluation_public_api.py`

**Interfaces:**
- Produces:

```python
evaluate_trading_performance(
    trades: tuple[EvaluatedTrade, ...],
    probability_observations: tuple[ProbabilityObservation, ...],
    policy: TradingEvaluationPolicy,
    candidate_version: str,
) -> TradingEvaluationReport
```

- [ ] **Step 1: Write metrics-engine RED tests**

Use a deterministic trade set containing wins, losses, and flats with at least two setups and two regimes. Hand-calculate expected metrics.

Tests must separately prove:

1. overall gross/net PnL, USD expectancy, and entry-notional-normalized expectancy;
2. profit factor uses net PnL and is `None` with no losing trades;
3. realized-equity maximum drawdown uses canonical close order, not input order;
4. maximum drawdown percent is relative to the running equity peak;
5. cumulative equity below zero fails closed;
6. winner/loser averages and win/loss/flat counts reconcile;
7. win rate excludes flats from wins but uses total trade count as denominator;
8. turnover, turnover/start-equity, execution friction, explicit cost, total cost, and cost burden are exact;
9. empty trade tuple yields zero PnL/cost/turnover/drawdown, empty segments, and undefined expectancy/profit-factor/win-rate/averages;
10. setup segments reuse exact global formulas and sort lexically;
11. regime segments reuse exact global formulas and sort lexically;
12. segment trade counts reconcile to overall count;
13. calibration uses every supplied probability observation even when there are fewer trades;
14. Brier score is exact for a hand-computed fixture;
15. fixed-width bucket assignment treats `1.0` as part of the last bucket;
16. empty calibration buckets remain present with `None` statistics;
17. ECE is the weighted absolute bucket calibration gap;
18. empty probability tuple produces `calibration is None`;
19. shuffled trades/observations produce an equal report and identical fingerprint;
20. duplicate trade position IDs, duplicate probability identities, wrong input container/type, candidate-version mismatch, or invalid policy fail closed;
21. result models contain no winner-selection, baseline-beating, promotion, shadow, or live-authority fields;
22. importing `shreks_brain.evaluation` does not eagerly import sklearn or PyArrow in a fresh subprocess;
23. production E5 source contains no SQLite/pathlib/requests/random/wall-clock imports.

Update public API to require exactly the final 11 symbols from the spec.

- [ ] **Step 2: Attach engine tests-only RED**

Expected Python failure: missing `evaluate_trading_performance`. No unrelated failure.

- [ ] **Step 3: Implement canonical trading metrics**

In `engine.py`, canonicalize exact trades by:

```python
(closed_at_unix_ms, opened_at_unix_ms, position_id, candidate_mint)
```

Compute:

```python
trade_count = len(trades)
wins = [t for t in trades if t.net_pnl_usd > 0.0]
losses = [t for t in trades if t.net_pnl_usd < 0.0]
flats = [t for t in trades if t.net_pnl_usd == 0.0]
```

Use `math.fsum` for additive money metrics. Expectancy is arithmetic mean; percentage expectancy is the mean of per-trade `net_pnl_usd / entry_notional_usd * 100`.

Profit factor:

```python
profit_factor = None if not losses else sum_wins / abs(sum_losses)
```

If losses exist and there are no wins, profit factor is `0.0`.

Cost burden is `None` when turnover is zero, otherwise `total_cost_usd / turnover_usd * 100`.

- [ ] **Step 4: Implement realized-equity drawdown**

Start at `policy.starting_equity_usd`. Apply canonical net PnL one trade at a time. Fail if equity becomes negative beyond arithmetic tolerance. Track peak equity and largest peak-current decline. Percentage drawdown is `drawdown / peak * 100` at the worst point.

- [ ] **Step 5: Implement segment metrics**

Group the same canonical trade tuple by exact `setup_name` and `market_regime`. Sort keys lexically. Reuse one private metric function so global and segmented formulas cannot drift.

- [ ] **Step 6: Implement calibration**

Canonicalize observations by `(as_of_unix_ms, candidate_mint)`. For `N = calibration_bucket_count`, compute bucket index:

```python
index = min(int(probability * N), N - 1)
```

Brier score:

```python
mean((probability - float(target_positive)) ** 2)
```

Per non-empty bucket compute mean probability, observed positive rate, and absolute gap. ECE is the observation-count-weighted sum of gaps.

- [ ] **Step 7: Implement canonical fingerprint**

Build one JSON payload from schema/policy/candidate, canonical trade economics, canonical observations, metrics, segments, and calibration. Encode finite floats as:

```python
{"float_hex": value.hex()}
```

Hash sorted compact UTF-8 JSON with SHA-256.

- [ ] **Step 8: Verify engine GREEN**

Run focused E5 engine/public API tests, then:

```bash
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Require repository safety GREEN as well.

- [ ] **Step 9: Commit**

```text
feat: evaluate E5 trading performance
```

---

### Task 4: Scope audit and E5 seal

**Files:**
- Modify: `README.md` (additions only)
- Replace plan content with final verification record: `docs/superpowers/plans/2026-08-24-phase-e5-trading-evaluation.md`

**Interfaces:**
- No production behavior change.
- Records exact TDD/CI evidence and frozen E5 head.

- [ ] **Step 1: Audit frozen-E4 -> E5 behavior diff**

Require cumulative behavior diff before seal to contain only:

```text
docs/superpowers/specs/2026-08-24-phase-e5-trading-evaluation-design.md
docs/superpowers/plans/2026-08-24-phase-e5-trading-evaluation.md
python/src/shreks_brain/evaluation/*
python/tests/test_trading_evaluation_*.py
```

No E1/E2/E3/E4, D6, B7/B8/B9, paper/exit, Rust, migration, dependency, or workflow file may change.

- [ ] **Step 2: Write docs-only seal detached from final behavior GREEN**

README additions must explain:

- normalized after-cost closed-trade measurement;
- source-of-truth metrics;
- E4 unseen calibration;
- no fill simulation, winner selection, promotion, or live-money authority in E5.

Replace this plan with a concise verification record containing:

- E4 base SHA;
- design SHA;
- contract RED/GREEN SHAs and CI evidence;
- adapter RED/GREEN SHAs and CI evidence;
- engine RED/GREEN SHAs and CI evidence;
- cumulative scope audit;
- seal audit;
- final exact-head CI.

- [ ] **Step 3: Audit seal before attachment**

Require exactly two changed files:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-e5-trading-evaluation.md
```

README must have zero deletions. No production/test file may change.

- [ ] **Step 4: Attach seal and run exact-head CI**

Require Python, Rust/workspace metadata/tests, and repository safety all GREEN on the seal SHA.

- [ ] **Step 5: Freeze E5**

Update the stacked E5 draft PR with exact verification evidence. Do not modify tracked E5 files after the frozen seal unless exact-head CI demonstrates a real defect.