# Phase E3 Model Training Pipeline Design

## Purpose

Phase E3 introduces the first supervised model-training boundary for Shreks. It must make the D6 research dataset trainable without weakening the project’s point-in-time guarantees or prematurely absorbing the responsibilities of E4 chronological validation, E5 trading evaluation, or E6 model persistence/promotion.

The build-order requirement is to begin with practical tabular models rather than exotic AI. E3-v1 therefore starts with one deliberately boring and auditable family: binary logistic regression. Tree/boosting families can be added after the E4/E5 evaluation harness exists and can prove they beat simpler alternatives. Reinforcement learning remains explicitly out of scope.

E3 is based exactly on sealed E2 head `caeb7b127b39a9c7fd5cf40ca877fbe677ba703f`.

## Core boundary

E3 consumes caller-supplied logical D6 rows. It does not read Parquet, SQLite, providers, files, network resources, or the wall clock.

The training path is:

```text
D6 logical rows
  -> validate sealed D6 schema
  -> select caller-specified trainable decision-time columns
  -> derive caller-specified binary future-return target
  -> deterministically sort eligible training rows
  -> training-only median imputation + standardization
  -> sklearn logistic-regression fit
  -> immutable portable logistic artifact
```

The inference path is:

```text
D6 logical row
  -> validate sealed D6 schema
  -> apply artifact’s stored transforms
  -> pure-Python logistic sigmoid
  -> positive-class probability
```

Only training requires the optional ML dependency. Inference from an already-created artifact remains standard-library Python.

## Package

Create `shreks_brain.learning` with schema version `e3-training-v1`.

Suggested files:

- `learning/models.py` — immutable public contracts and validation;
- `learning/features.py` — sealed trainable decision-time feature allow-list, row validation, deterministic transforms, target extraction, and training fingerprint;
- `learning/trainer.py` — lazy scikit-learn training adapter;
- `learning/inference.py` — pure-Python artifact inference;
- `learning/__init__.py` — explicit public API.

## Dependency boundary

The base `shreks-brain` installation remains dependency-free.

Add an optional `learning` extra containing scikit-learn and include the same dependency in `dev` so CI exercises training:

```toml
learning = ["scikit-learn>=1.7,<2"]
dev = ["pytest>=8,<9", "pyarrow==25.0.*", "scikit-learn>=1.7,<2"]
```

No NumPy/scikit-learn object becomes part of the public trained-model artifact. `trainer.py` lazy-loads scikit-learn only when fitting.

## Model family

E3-v1 supports exactly:

```text
LOGISTIC_REGRESSION
```

This is enough to prove the full supervised-training contract and gives later E4/E5 evaluation a strong, interpretable linear baseline. Adding random forest, gradient boosting, or histogram boosting before chronological validation exists would multiply model-selection degrees of freedom without any reliable way to prove improvement.

## Training target

E3-v1 trains a binary classifier against one caller-supplied D6 future return target:

```text
ResearchReturnTarget(
    horizon_seconds,
    minimum_return_pct,
)
```

`horizon_seconds` must be one of the sealed D6 horizons. `minimum_return_pct` must be finite. A completed D6 return is positive when:

```text
label_<horizon>s_return_pct >= minimum_return_pct
```

E3 ships no default horizon or return threshold. The caller must state the research hypothesis explicitly.

Rows whose selected target label is not `COMPLETED` or whose target return is absent are excluded from training and counted as target-unavailable. E3 does not turn pending/unknown targets into negatives or zeros.

The D6 baseline timestamp already equals the decision timestamp, so E3 never re-anchors future labels.

## Trainable feature boundary

E3 accepts an explicit tuple of feature names. Every requested feature must belong to a sealed E3 allow-list of scalar numeric/boolean D6 decision-time evidence.

The allow-list includes numeric/boolean evidence from:

- B2 market features;
- B1 soft-safety flags carried by B2;
- D5 wallet research features;
- B6 numeric regime evidence, including point-in-time recent-performance evidence when present;
- B7 score-family values and `total_score`.

The allow-list deliberately excludes:

- every `label_...` column;
- candidate identity and absolute `as_of_unix_ms`;
- schema/policy version strings;
- source-observation absolute timestamps;
- setup/regime/safety/decision categorical strings in E3-v1;
- missing-feature/reason-code collections and JSON audit payloads;
- B8 `decision_action` and `required_score_threshold`.

The last exclusion keeps the first learned challenger from simply learning the current B8 gate as a target proxy. B7 scores remain permitted because they are point-in-time explanatory evidence and can be tested later for incremental value.

Feature tuples must be non-empty, duplicate-free, and caller supplied. E3 ships no production/default model feature set.

## Missing feature handling

For each selected feature, training derives a deterministic transform from eligible training rows only:

1. accept finite `int`, `float`, or `bool` values; booleans become `0.0/1.0`;
2. treat `None` as missing;
3. reject unsupported or non-finite values;
4. require at least one observed value for each selected feature;
5. compute the training median for imputation;
6. impute missing training values with that median;
7. compute the mean and population standard deviation of the imputed training values;
8. use scale `1.0` when the standard deviation is zero.

The resulting immutable `FeatureTransform` stores `feature_name`, `imputation_median`, `mean`, and `scale`.

Prediction uses only those stored transforms. A later prediction row with `None` uses the training median; a row with an unsupported/non-finite value fails closed.

## Training configuration

`LogisticRegressionTrainingPolicy` is explicit and versioned. It contains:

- `version`;
- positive finite `regularization_c`;
- positive integer `max_iterations`;
- positive finite `tolerance`;
- `class_weight_mode`: `NONE` or `BALANCED`.

E3 ships no production training policy values.

The sklearn adapter uses logistic regression with the deterministic `lbfgs` solver and the caller-supplied values above. Fit includes an intercept. A convergence warning/failure is treated as a training error rather than silently accepting a partially converged artifact.

## Training request

`ModelTrainingRequest` contains:

- explicit non-empty `model_version`;
- `ModelFamily.LOGISTIC_REGRESSION`;
- exact feature tuple;
- `ResearchReturnTarget`;
- `LogisticRegressionTrainingPolicy`.

E3 does not infer model versions or silently choose hyperparameters.

## Portable artifact

`TrainedLogisticRegressionModel` is immutable and contains only standard-library values:

- schema/model/model-family/training-policy versions;
- sealed D6 research schema version;
- target specification;
- ordered feature transforms;
- ordered coefficient tuple;
- intercept;
- eligible training-row count;
- positive/negative counts;
- target-unavailable count;
- minimum/maximum training `as_of_unix_ms`;
- deterministic training fingerprint SHA-256.

The artifact does not contain a sklearn estimator, NumPy array, pickle, joblib payload, arbitrary class path, executable serialization, evaluation metric, promotion state, or live-trading authority.

The training fingerprint is over the deterministic eligible training population after sorting by `(as_of_unix_ms, candidate_mint)`, the exact selected raw feature values, derived binary targets, target specification, and training-policy/model-version provenance. Input row order cannot change it.

## Training validity

Training fails closed when:

- rows are not a non-empty tuple of exact D6 logical row mappings;
- a row does not expose exactly the sealed D6 physical column set or schema version;
- candidate identity is missing/invalid;
- duplicate `(candidate_mint, as_of_unix_ms)` identities exist;
- requested features are absent, duplicate, or outside the E3 allow-list;
- a selected feature has no observed training values;
- a selected feature contains unsupported/non-finite evidence;
- fewer than two target-eligible rows exist;
- target-eligible rows contain only one class;
- scikit-learn is unavailable when training is requested;
- logistic fitting does not converge;
- fitted coefficients/intercept are not finite or have unexpected dimensions.

E3 never fabricates a class balance or synthetic training example.

## Prediction API

`predict_positive_probability(model, row)` returns a `ModelPrediction` carrying:

- `model_version`;
- `candidate_mint`;
- `as_of_unix_ms`;
- `positive_probability` in `[0, 1]`.

Prediction computes:

```text
z = intercept + sum(coef_i * standardized_feature_i)
probability = stable_sigmoid(z)
```

It uses no label column. Mutating future D6 labels while leaving decision-time feature evidence unchanged must not alter a prediction.

## Determinism

For identical logical rows, request, and dependency version:

- input row order does not change training population order;
- transforms are deterministic;
- fingerprint is deterministic;
- logistic coefficients/intercept are expected to be deterministic under `lbfgs`;
- prediction is deterministic.

E3 records enough provenance for E4/E6 to detect when the training population or policy changed.

## Relationship to E2

E2 remains untouched. E3 does not modify V0, threshold variants, E1 replay, B7 scoring, or B8 decisions.

E3 is a challenger-training primitive. Later E4/E5 must compare its predictions and derived strategy behavior against E2 baselines using chronological unseen data and realistic trading metrics.

## Explicit E3 non-goals

E3 does not:

- choose a production feature set;
- choose a production return horizon/threshold;
- split data into train/validation/test periods;
- perform walk-forward validation;
- calculate accuracy, AUC, calibration, expectancy, PnL, win rate, drawdown, turnover, costs, or profit factor;
- search hyperparameters;
- select a champion;
- persist a model registry;
- change B7/B8/B9 production behavior;
- create `TradeIntent`;
- paper trade or live trade;
- use reinforcement learning;
- sign or submit transactions.

E4 owns chronological validation. E5 owns trading evaluation. E6 owns champion/challenger persistence and promotion metadata.

## Verification strategy

E3 follows RED -> GREEN in independent gates:

1. model/public API RED, then immutable contract GREEN;
2. feature/target/preprocessing RED, then pure standard-library GREEN;
3. logistic training/inference RED, then lazy scikit-learn GREEN;
4. full Python/Rust/repository-safety verification;
5. sealed-E2 -> E3 diff audit;
6. additions-only README append plus verification record as a detached documentation seal;
7. exact-head final CI before E3 is frozen.

Tests must explicitly prove future-label leakage isolation, input-order determinism, one-class failure, pending-target exclusion, all-missing feature failure, missing-at-inference imputation, dependency isolation on import, and that E3 performs no E4/E5 behavior.
