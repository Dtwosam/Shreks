# FL8.4 Forecast Calibration Design

## Status

Approved for autonomous implementation under the project instruction to continue the Fast Lane build order without repeated approval prompts.

## Source-of-truth alignment

FL8.4 follows the canonical Fast Lane build order after SEALED FL8.3 merged-main `e233870fc2fa62b8a94869472e63f4a2b5e9c52e`.

The build order defines FL8.4 as **Forecast calibration**: measure prediction quality by horizon, regime, strategy family, and liquidity/cost bucket.

The master source of truth requires learning evidence to remain point-in-time safe, chronological, cost-aware, auditable, and separate from promotion authority. It requires explicit measurement of calibration by horizon and performance by strategy/regime, while LIVE remains disabled until later proof and promotion gates pass.

FL8.4 is therefore a **measurement layer only**. It does not fit a calibrator, retrain a model, choose a champion, set a trading threshold, size a position, create a PAPER action, create a `TradeIntent`, sign/submit a transaction, or enable LIVE.

## Problem

FL8.3 produces leakage-resistant unseen validation and test predictions, but intentionally does not inspect their targets or compute performance metrics.

FL8.4 must answer:

1. how accurate is a forecast on its selected chronological holdout partition;
2. for binary forecasts, how well calibrated are its probabilities;
3. how does quality vary across explicit point-in-time market regime, strategy-family relevance, executable liquidity, and expected round-trip cost context;
4. which predictions could not be scored because the exact FL4 target was unavailable;
5. can every reported number be reproduced from exact FL8.1 labels, the exact FL8.3 validation run, and explicit point-in-time context.

FL8.4 must not answer which model should be champion. FL8.5 owns comparison/selection and immutable champion construction.

## Reuse of preserved evaluation infrastructure

The legacy `shreks_brain.evaluation` package already contains useful generic calibration arithmetic:

- equal-width probability buckets;
- Brier score;
- expected calibration error (ECE);
- deterministic canonical fingerprinting of finite floating-point values.

Those mathematical conventions are reusable.

The legacy package is not the FL8.4 domain model because it is coupled to legacy trading reports, candidate versions, setup/regime trading performance, and later promotion/registry evidence. FL8.4 must not import promotion or registry authority and must not reinterpret forecast rows as trades.

## Selected architecture

Add an isolated package:

```text
python/src/shreks_brain/fast_evaluation/
  __init__.py
  models.py
  engine.py
  codec.py
```

FL8.4 consumes only:

- exact `FastTrainingBundle` values from FL8.1;
- exact `FastChronologicalValidationRun` values from FL8.3;
- explicit point-in-time `FastForecastEvaluationContext` rows supplied by the caller;
- one exact `FastForecastEvaluationPolicy`.

It produces immutable forecast-evaluation evidence that FL8.5 may later compare, without granting FL8.5 authority in this phase.

## Public schema

```python
FAST_FORECAST_EVALUATION_SCHEMA_NAME = "shreks.fast_lane_forecast_evaluation"
FAST_FORECAST_EVALUATION_SCHEMA_VERSION = 1
```

## Evaluation partition

```python
class FastForecastEvaluationPartition(StrEnum):
    VALIDATION = "VALIDATION"
    TEST = "TEST"
```

A report scores exactly one partition. Validation and test evidence are never mixed into one metric population.

The intended discipline is:

- validation can support model-development diagnostics and later calibration choices;
- test remains an independent chronological holdout;
- FL8.4 itself does not tune either model weights or calibration parameters from either partition.

## Point-in-time evaluation context

`FastTrainingFeatureRecord` does not contain all segmentation dimensions required by FL8.4. In particular it does not encode strategy-family relevance or a comparable quote-denominated executable-liquidity/cost context.

FL8.4 therefore requires explicit context rows rather than guessing those values from future labels or legacy strategy state.

### `FastForecastEvaluationContext`

Frozen slotted dataclass:

- `decision_identity: tuple[object, ...]`
- `as_of_unix_ms: int`
- `market_regime: str`
- `strategy_families: tuple[str, ...]`
- `executable_exit_capacity_quote: float | None`
- `expected_round_trip_cost_bps: float | None`

Rules:

- identity must use the exact FL8.1 seven-field decision shape;
- `as_of_unix_ms` must equal identity timestamp field 7;
- market regime must be a non-empty caller-supplied point-in-time label;
- strategy families must be a non-empty, lexically sorted, unique tuple of non-empty strings;
- quote-denominated exit capacity, when present, must be finite and non-negative;
- expected round-trip cost bps, when present, must be finite and non-negative;
- context contains no future-path target and no post-decision realized value.

A context can contain more than one strategy family because one point-in-time opportunity may be relevant to several independently measurable Fast Lane strategies. Strategy-family segments therefore overlap by design; overall observation counts are not derived by summing strategy segment counts.

### Exact context coverage

The supplied context tuple must contain exactly one row for every unique prediction identity present anywhere in the FL8.3 run's validation and test partitions, and no extra identity.

This stronger all-partition coverage has two benefits:

1. one context corpus can reproduce either validation or test evaluation without changing context membership;
2. the selected partition cannot influence which context was collected.

Context rows are canonically ordered by the same decision ordering used by FL8.3.

## Evaluation policy

### `FastForecastEvaluationPolicy`

Frozen slotted dataclass:

- `version: str`
- `partition: FastForecastEvaluationPartition`
- `probability_bucket_count: int`
- `liquidity_capacity_quote_boundaries: tuple[float, ...]`
- `round_trip_cost_bps_boundaries: tuple[float, ...]`
- `binary_log_loss_clip_epsilon: float`

Rules:

- non-empty version;
- exact partition enum;
- probability bucket count integer within `[2, 100]`;
- liquidity boundaries are finite, strictly increasing, non-negative;
- cost boundaries are finite, strictly increasing, non-negative;
- log-loss epsilon is finite and strictly within `(0, 0.5)`.

No default economic thresholds are embedded. Policy values are explicit/versioned caller inputs.

## Bucketing semantics

For numeric segmentation, boundaries define deterministic left-closed/right-open buckets, with the final bucket unbounded above.

For boundaries `(10.0, 100.0)`:

```text
bucket_0: [0, 10)
bucket_1: [10, 100)
bucket_2: [100, +inf)
unknown:  None
```

Boundary equality enters the higher bucket.

`None` is not silently discarded. It enters an explicit `unknown` bucket so missing point-in-time liquidity/cost evidence remains visible in the report.

The report persists the exact evaluation policy, so bucket meaning is auditable.

## Joining predictions to FL4 targets

FL8.4 joins each selected prediction to the exact FL4 future-path row using:

- exact seven-field decision identity;
- `prediction.horizon_ms`;
- the FL4 label version recorded by the fitted artifact/run source bundle.

For the requested forecast target:

- `completeness == "complete"` and a non-null type-compatible target => scored;
- incomplete row => target unavailable;
- complete row with null selected target => target unavailable;
- no exact row, duplicate row, incompatible horizon/version, malformed target type, or identity contradiction => fail closed.

Unavailable targets are never converted to zero or imputed.

Each metric population records:

- `prediction_count`;
- `scored_observation_count`;
- `target_unavailable_count`.

The counts must reconcile exactly. A selected partition with zero scored observations fails closed.

## Continuous forecast metrics

For continuous targets, define immutable `FastContinuousForecastMetrics`:

- `observation_count`
- `mean_predicted_value`
- `mean_actual_value`
- `mean_error` where error is `prediction - actual`
- `mean_absolute_error`
- `root_mean_squared_error`

All values must be finite and arithmetically reconcile within explicit tight tolerances.

These metrics are forecast-quality evidence, not PnL.

For `BEST_COST_ADJUSTED_RETURN_BPS` and `ENDPOINT_COST_ADJUSTED_RETURN_BPS`, the report marks `target_is_cost_adjusted=True`. FL8.4 does not subtract a second synthetic cost estimate from those labels.

## Binary forecast metrics and calibration

For binary targets, define:

### `FastCalibrationBucket`

- bucket index/bounds;
- observation count;
- mean predicted probability or `None` when empty;
- observed positive rate or `None` when empty;
- absolute calibration gap or `None` when empty.

Use equal-width probability buckets across `[0, 1]`, preserving the existing E5 convention. Probability exactly `1.0` belongs to the final bucket.

### `FastBinaryForecastMetrics`

- `observation_count`
- `positive_count`
- `mean_predicted_probability`
- `brier_score`
- `log_loss`
- `expected_calibration_error`
- `calibration_buckets`

Brier score:

```text
mean((p - y)^2)
```

Binary log loss clips probability only for logarithm evaluation using the policy epsilon:

```text
p' = min(max(p, epsilon), 1 - epsilon)
mean(-(y*ln(p') + (1-y)*ln(1-p')))
```

ECE is the observation-count-weighted mean absolute calibration gap.

FL8.4 does not fit isotonic, Platt, temperature, or any other recalibration transform.

## Metric population model

Define `FastForecastMetricPopulation`:

- `name: str`
- `prediction_count: int`
- `scored_observation_count: int`
- `target_unavailable_count: int`
- `continuous_metrics: FastContinuousForecastMetrics | None`
- `binary_metrics: FastBinaryForecastMetrics | None`

Exactly one metric payload must match the run target kind.

Names are stable canonical strings.

## Required segmentation

Every report contains:

- one `overall` population;
- per-fold populations;
- per-market-regime populations;
- per-strategy-family populations;
- per-liquidity-capacity bucket populations;
- per-round-trip-cost bucket populations.

Segment tuples are lexically ordered by stable segment name and contain no empty prediction populations.

### Count reconciliation

For mutually exclusive dimensions, scored/prediction counts must reconcile to overall:

- folds;
- market regime;
- liquidity bucket;
- cost bucket.

Strategy-family populations may overlap and therefore do not reconcile by summation. Each scored prediction contributes once to overall and once to every strategy family explicitly attached to its context.

## Report model

### `FastForecastEvaluationReport`

Frozen slotted dataclass:

- schema name/version;
- exact evaluation policy;
- validation policy version;
- FL8.3 validation run fingerprint;
- FL8.1 training bundle fingerprint;
- model version/family;
- target/target kind;
- horizon ms;
- `target_is_cost_adjusted`;
- fold artifact fingerprint tuple;
- context fingerprint;
- overall population;
- fold populations;
- regime populations;
- strategy-family populations;
- liquidity-bucket populations;
- cost-bucket populations;
- evaluation report fingerprint.

The report contains no champion, promotion, threshold, action, position-size, or execution field.

## Provenance and determinism

FL8.4 is deterministic and has no randomness.

The context fingerprint covers canonical context rows and policy-independent point-in-time values.

The report fingerprint covers:

- schema/version;
- exact policy;
- selected partition;
- FL8.3 validation run/source fingerprints;
- model target/horizon/family/version;
- fold artifact fingerprints;
- canonical context fingerprint;
- scored target values and target availability state;
- all metric populations.

Finite floats are canonicalized with `float.hex()` before sorted compact JSON hashing.

Equivalent inputs produce byte-identical reports regardless of caller tuple ordering where input order is explicitly non-semantic.

### Evaluation-label mutation semantics

Sealed FL8.2/FL8.3 provenance intentionally includes the whole source bundle fingerprint. Therefore changing validation labels can change source/model/run provenance even when test predictions are numerically unchanged.

For a TEST report:

- validation-label-only changes must not change test scored values or test metric payloads;
- source-derived validation-run/report provenance may change and should remain auditable.

FL8.4 must not erase that provenance signal merely to make fingerprints stable across changed source evidence.

## Immutable JSON codec

`codec.py` provides:

```python
write_fast_forecast_evaluation_report(report, path)
read_fast_forecast_evaluation_report(path)
```

Rules mirror FL8.2 artifact discipline:

- sorted compact JSON;
- exact enums as string values;
- `allow_nan=False`;
- trailing newline;
- refuse overwrite;
- exact schema/key validation;
- recompute and verify report fingerprint;
- no pickle/joblib/executable class path.

## Error handling

Fail closed for:

- non-exact FL8.1 bundle/run/policy/context types;
- bundle fingerprint mismatch between bundle and FL8.3 run;
- duplicate/missing/extra context identity;
- context timestamp mismatch;
- malformed or non-finite context values;
- malformed policy/bucket boundaries;
- duplicate or missing prediction identities;
- prediction/model/target/horizon contradictions;
- missing/duplicate exact FL4 rows;
- malformed selected FL4 target type;
- zero scorable observations;
- non-finite prediction or metric value;
- count-reconciliation failure;
- report fingerprint contradiction;
- codec overwrite/tampering/unknown keys.

No error path changes partition, substitutes a target, drops an unknown-context row, retrains a model, widens a fold, falls back to a different model family, or promotes anything.

## Dependency and authority boundary

FL8.4 adds no runtime dependency. Standard-library arithmetic is sufficient.

`shreks_brain.fast_evaluation` must not eagerly import sklearn or NumPy and must not import/use:

- provider/network clients;
- sqlite3/PyArrow/file source readers in engine/models;
- wall-clock time or randomness;
- strategy action selection;
- PAPER execution;
- signer/transaction submission;
- registry/promotion/champion code;
- LIVE mode.

The codec may use `pathlib` only for explicit caller-requested report persistence.

LIVE remains disabled.

## Public API

`shreks_brain.fast_evaluation.__all__` exposes only:

```text
FAST_FORECAST_EVALUATION_SCHEMA_NAME
FAST_FORECAST_EVALUATION_SCHEMA_VERSION
FastForecastEvaluationPartition
FastForecastEvaluationContext
FastForecastEvaluationPolicy
FastCalibrationBucket
FastContinuousForecastMetrics
FastBinaryForecastMetrics
FastForecastMetricPopulation
FastForecastEvaluationReport
evaluate_fast_forecasts
write_fast_forecast_evaluation_report
read_fast_forecast_evaluation_report
```

## TDD requirements

Independent RED/GREEN proof must cover at least:

1. exact schema/frozen contract and policy bounds;
2. validation vs test partition isolation;
3. exact identity+horizon FL4 join;
4. incomplete/null target exclusion with explicit unavailable count;
5. continuous mean/bias/MAE/RMSE arithmetic;
6. binary Brier/log-loss/ECE arithmetic and 0/1 bucket boundaries;
7. deterministic input ordering;
8. exact all-partition context coverage and timestamp equality;
9. regime segmentation;
10. overlapping strategy-family segmentation without duplicating overall population;
11. quote-denominated liquidity bucket boundaries and explicit unknown bucket;
12. round-trip-cost bucket boundaries and explicit unknown bucket;
13. TEST metric isolation from validation-label-only changes while retaining source provenance changes;
14. explicit cost-adjusted-target flag/measurement without double-subtracting costs;
15. actual FL8.1 + FL8.3 integration across continuous and binary, naive and trained families;
16. exact public API/no eager sklearn/NumPy;
17. no promotion/execution/LIVE authority;
18. canonical report JSON round trip, overwrite refusal, tamper/unknown-key rejection.

## Seal procedure

FL8.4 follows the established gate:

1. design;
2. implementation plan;
3. intentional RED contracts;
4. implementation GREEN;
5. candidate four-gate CI GREEN;
6. exact scope audit;
7. clean history `design -> plan -> consolidated RED -> implementation` preserving the verified tree;
8. fresh exact-clean-head four-gate GREEN;
9. guarded merge using expected head SHA;
10. fresh merged-main four-gate GREEN;
11. only then mark FL8.4 SEALED.

FL8.4 does not establish champion status, predictive edge sufficient for trading, economic profitability, or trading authority. FL8.5 remains the next phase.
