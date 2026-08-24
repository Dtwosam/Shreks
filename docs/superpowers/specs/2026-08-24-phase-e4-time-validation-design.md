# Phase E4 Time-Aware Validation Design

## Status

Approved for autonomous implementation under the project instruction to continue the build order without repeated approval prompts.

## Source-of-truth alignment

Phase E4 follows the repository source hierarchy:

1. `SHREKS_MASTER_SOURCE_OF_TRUTH.md` requires challengers to use point-in-time data, be evaluated on unseen data, and avoid leakage before paper/shadow comparison or promotion.
2. `SHREKS_BUILD_ORDER.md` defines E4 as **Time-aware validation: split data chronologically to prevent leakage**.
3. Sealed E3 head `1328efce85464f3f1b1636d837bcefb1193c2eac` provides the deterministic training and pure inference interfaces E4 must reuse unchanged.

E4 deliberately stops before E5. It does not compute trading or predictive evaluation metrics, and it does not decide whether a challenger is good.

## Problem

A normal random train/test split is invalid for Shreks because later market information can leak into earlier decisions. A simple `training as_of < validation as_of` rule is still insufficient: an old decision row may contain a future target that did not become known until after validation began.

Example:

- candidate decision: 10:00;
- selected target horizon: 4 hours;
- validation begins: 12:00;
- target becomes observable/completed: 14:00.

That 10:00 row is chronologically old, but using its 14:00 label to train a model evaluated at 12:00 leaks two hours of future information.

E4 therefore needs two independent chronological gates:

1. **decision-time gate** — training decision timestamps must be inside the fold's training interval and strictly before validation;
2. **label-availability gate** — the selected target must have been completed and available no later than the fold's validation start.

## Goals

E4-v1 must:

- split logical D6 rows using explicit chronological intervals;
- prevent random splitting;
- prevent decision-time leakage;
- prevent target-maturity leakage;
- train one fresh E3 model artifact per fold using only eligible historical rows;
- predict every candidate in the fold's validation interval without reading validation labels;
- preserve exact fold/model/prediction provenance;
- be deterministic under input-row and input-fold reordering;
- produce outputs E5 can evaluate without recomputing E4 boundaries;
- remain pure Python orchestration over caller-supplied rows;
- add no new dependency beyond sealed E3's optional learning dependency.

## Non-goals

E4-v1 does **not**:

- generate arbitrary default calendar periods;
- choose a production training window;
- choose model features, target horizon, target threshold, or hyperparameters;
- randomize or stratify rows;
- search hyperparameters;
- compute accuracy, AUC, calibration, expectancy, PnL, profit factor, drawdown, win rate, turnover, costs, setup performance, or regime performance;
- compare a challenger to E2 baselines economically;
- select or promote a champion;
- persist a model registry;
- alter B7, B8, B9, paper, exit, or execution behavior;
- create `TradeIntent` objects;
- enable live money.

E5 owns trading/economic evaluation. E6 owns champion/challenger persistence and promotion state.

## Approaches considered

### 1. Explicit caller-supplied chronological folds — selected

The caller supplies exact training and validation timestamp intervals for every fold.

Advantages:

- no invented duration or sample-count defaults;
- every boundary is auditable;
- supports expanding or rolling windows;
- supports explicit gaps/embargo periods naturally;
- deterministic and easy to reproduce;
- cleanly separates E4 mechanics from later data-driven policy selection.

Trade-off: callers must construct fold boundaries explicitly.

### 2. Automatic duration-based walk-forward generator

E4 could accept train/validation durations and synthesize folds.

Rejected for E4-v1 because it introduces more policy surface before Shreks has evidence for sensible durations. A later helper can be added without changing the core explicit-fold contract.

### 3. One fixed chronological holdout

This is simple but too weak as the only E4 abstraction. It makes it easy to overfit conclusions to one period and does not naturally support repeated walk-forward evaluation.

E4 can still represent a single holdout as one explicit fold, but the architecture supports multiple folds from day one.

## Package boundary

Add a new pure Python package:

```text
python/src/shreks_brain/validation/
  __init__.py
  models.py
  engine.py
```

Public schema version:

```python
TIME_AWARE_VALIDATION_SCHEMA_VERSION = "e4-time-validation-v1"
```

E4 reuses sealed E3 public functions unchanged:

- `train_logistic_regression`
- `predict_positive_probability`
- `ModelTrainingRequest`
- `TrainedLogisticRegressionModel`
- `ModelPrediction`

E4 does not duplicate preprocessing, logistic fitting, or probability math.

## Public models

### `ChronologicalValidationFold`

Immutable, slotted dataclass with:

- `name: str`
- `training_started_at_unix_ms: int`
- `training_ended_at_unix_ms: int`
- `validation_started_at_unix_ms: int`
- `validation_ended_at_unix_ms: int`

Intervals use half-open semantics:

```text
training:   [training_started_at, training_ended_at)
validation: [validation_started_at, validation_ended_at)
```

Validation rules:

- name is non-empty;
- all timestamps are non-negative integers and not bools;
- training start < training end;
- training end <= validation start;
- validation start < validation end.

A gap is allowed and is represented explicitly by `training_ended_at < validation_started_at`. E4 invents no gap duration.

### `TimeAwareValidationPolicy`

Immutable, slotted dataclass with:

- `version: str`
- `folds: tuple[ChronologicalValidationFold, ...]`

Validation rules:

- version is non-empty;
- at least one fold exists;
- fold names are unique;
- validation intervals do not overlap.

Training intervals may overlap. This allows both expanding-window and rolling-window validation.

Input fold order is not semantic. E4 processes folds canonically by:

```text
(validation_started_at_unix_ms, validation_ended_at_unix_ms, name)
```

### `ValidationFoldResult`

Immutable, slotted dataclass with:

- `fold: ChronologicalValidationFold`
- `training_window_row_count: int`
- `training_mature_target_row_count: int`
- `training_target_unavailable_at_split_count: int`
- `validation_row_count: int`
- `model: TrainedLogisticRegressionModel`
- `predictions: tuple[ModelPrediction, ...]`

Reconciliation rules:

- `training_mature_target_row_count == model.training_row_count`;
- `training_window_row_count == mature + unavailable_at_split`;
- `validation_row_count == len(predictions)`;
- every prediction model version equals the artifact model version;
- predictions are canonically ordered by `(as_of_unix_ms, candidate_mint)`;
- every prediction timestamp lies inside the fold's validation interval.

### `TimeAwareValidationRun`

Immutable, slotted dataclass with:

- `schema_version: str`
- `validation_policy_version: str`
- `model_training_request: ModelTrainingRequest`
- `fold_results: tuple[ValidationFoldResult, ...]`
- `validation_run_fingerprint_sha256: str`

The run fingerprint is deterministic over:

- E4 schema version;
- validation policy version and canonical fold boundaries;
- E3 model-training request provenance;
- each fold artifact training fingerprint;
- each prediction identity and exact finite probability.

It is provenance, not a performance score.

## Row contract

`run_time_aware_validation` accepts:

```python
rows: tuple[dict[str, object], ...]
request: ModelTrainingRequest
policy: TimeAwareValidationPolicy
```

Rows are caller-supplied logical D6 rows. E4 performs no Parquet, SQLite, provider, filesystem, network, or wall-clock reads.

Before fold execution E4 validates globally:

- `rows` is a non-empty tuple;
- every row is an exact dict;
- every row exposes exactly the sealed D6 physical column set;
- `dataset_schema_version == d6-research-v1`;
- `candidate_mint` is a non-empty string;
- `as_of_unix_ms` is a non-negative integer;
- `(candidate_mint, as_of_unix_ms)` identities are unique.

Rows are canonically sorted by:

```text
(as_of_unix_ms, candidate_mint)
```

## Training-row selection

For one fold, a row first enters the **training-window population** when:

```text
training_started_at <= as_of_unix_ms < training_ended_at
```

A training-window row becomes **mature-target eligible** only when the selected E3 target label satisfies all of the following at the fold boundary:

- status is `COMPLETED`;
- baseline timestamp equals row `as_of_unix_ms`;
- due timestamp equals `as_of + target_horizon`;
- checkpoint timestamp exists and is no earlier than due;
- completion timestamp exists and is no earlier than checkpoint;
- completion timestamp is **<= validation_started_at_unix_ms**;
- selected return is a finite number.

The final condition is the critical target-maturity gate.

A row with an eventual completed target after validation begins is excluded from that fold's training set and counted in `training_target_unavailable_at_split_count`. A pending target is treated the same way.

Completion exactly at validation start is allowed because the evidence is available at the split boundary.

E4 does not rewrite a late target to `PENDING`; it simply withholds that row from training.

The mature rows are passed unchanged into sealed E3 `train_logistic_regression`.

If a fold has too few mature rows, only one target class, all-missing requested features, or any other E3 training contradiction, the fold fails closed with its fold name in the error context. E4 does not manufacture a fallback model.

## Validation-row selection

A row enters a fold's validation population when:

```text
validation_started_at <= as_of_unix_ms < validation_ended_at
```

Every such row is predicted, even when its future target is still pending.

This is intentional:

- prediction population is defined only by decision time;
- target availability cannot decide whether a candidate receives a prediction;
- later E5 evaluation can join outcomes by prediction identity as they mature.

For each validation row E4 calls sealed E3 `predict_positive_probability(model, row)`.

E4 never reads a validation label before prediction, and inference itself ignores every label column.

A fold with zero validation rows fails closed because it cannot represent an unseen evaluation interval.

## Walk-forward semantics

Later folds may train on rows that appeared in earlier validation folds **only after those rows' selected labels have matured by the later fold's validation start**.

This is valid sequential walk-forward behavior:

- fold 1 prediction remains untouched;
- later knowledge may train fold 2;
- no later label can flow backward into an earlier fold.

Validation intervals may not overlap, preventing one decision from being counted as unseen validation evidence in multiple E4 folds.

## Determinism

E4 has no randomness.

Equivalent row populations and fold definitions produce identical results regardless of input order because:

- rows are sorted by `(as_of, mint)`;
- folds are sorted by canonical validation boundary/name;
- E3 training preparation is already deterministic;
- E3 inference is pure;
- E4 fingerprints canonicalize finite floats with exact hexadecimal encoding.

## Error handling

E4 fails closed for:

- malformed D6 rows;
- duplicate row identity;
- malformed or overlapping fold definitions;
- contradictory selected-target chronology in a training window;
- empty validation window population;
- insufficient mature training data;
- one-class training data;
- E3 preprocessing/fitting failures;
- non-finite values where a finite target/probability is required;
- result reconciliation failures.

No error path substitutes random splits, backfills labels, widens a validation window, or reuses a model from a different fold.

## Leakage invariants

Tests must prove all of these separately:

1. A row whose decision time is historical but whose selected label completes after validation begins cannot train that fold.
2. Completion exactly at validation start is eligible.
3. A pending selected label cannot train the fold.
4. Changing any non-target future label cannot change a fold artifact or prediction.
5. Changing target/future-label values for rows in a fold's validation interval cannot change that same fold's model, predictions, validation membership, or fingerprint; those rows may affect only a later fold after the selected target has matured by that later fold's validation start.
6. Validation label availability cannot change validation population membership.
7. A row validated in an earlier fold may train a later fold only after label maturity.
8. Random/input ordering cannot change folds, artifacts, predictions, or run fingerprint.

## Metric firewall

E4 result models must contain no fields named or semantically equivalent to:

- accuracy;
- AUC;
- calibration;
- expectancy;
- PnL;
- profit factor;
- drawdown;
- average winner/loser;
- win rate;
- turnover;
- costs;
- setup performance;
- regime performance;
- promotion status.

E4 answers only: **what historical data was knowable at this split, what model was trained, and what did it predict on the next unseen interval?**

E5 answers whether those predictions or policies were economically useful.

## Dependency and purity boundary

E4 adds no dependency.

Importing `shreks_brain.validation` must not eagerly import sklearn. E4 can trigger sklearn only indirectly when `run_time_aware_validation` calls sealed E3 training.

Production E4 modules must not import or use:

- `sqlite3`;
- PyArrow;
- pathlib/file I/O;
- requests/network clients;
- wall-clock time;
- random-number generators.

## Public API

`shreks_brain.validation.__all__` must expose exactly:

```text
TIME_AWARE_VALIDATION_SCHEMA_VERSION
ChronologicalValidationFold
TimeAwareValidationPolicy
ValidationFoldResult
TimeAwareValidationRun
run_time_aware_validation
```

No private split helper is public in E4-v1. E5 can use fold results/prediction identities to align baseline and challenger evaluation populations.

## Test strategy

### Contract/model RED -> GREEN

Tests first define:

- schema constant;
- frozen/slotted models;
- fold boundary validation;
- unique names;
- non-overlapping validation intervals;
- result reconciliation;
- explicit public API.

Expected RED is missing `shreks_brain.validation`.

### Engine RED -> GREEN

Behavior tests then prove:

- canonical row/fold order;
- half-open boundary membership;
- label-maturity exclusion;
- exact-boundary maturity inclusion;
- pending-target exclusion;
- validation of every row in the unseen interval regardless of target status;
- fold-local E3 training;
- prediction identity/order;
- earlier-validation-to-later-training walk-forward behavior;
- future-label isolation;
- duplicate identity rejection;
- empty validation rejection;
- deterministic run fingerprint;
- absence of evaluation metrics;
- import/purity boundary.

The behavior RED must fail only because `run_time_aware_validation` is not implemented yet.

### Full repository gate

Every GREEN point runs the existing full CI:

- repository safety;
- all Python tests;
- Rust tests/workspace metadata.

## Phase boundary

E4 completion proves only that Shreks can construct reproducible, leakage-safe chronological challenger predictions.

It does **not** prove that the challenger beats E2 baselines or makes money. Phase E5 must perform trading evaluation on the exact E4 unseen populations before any performance claim or promotion decision exists.
