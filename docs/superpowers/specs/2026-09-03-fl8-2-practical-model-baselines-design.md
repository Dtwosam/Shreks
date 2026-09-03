# FL8.2 Practical Model Baselines — Design

**Status:** implementation design for the Fast Lane rebuild  
**Base:** SEALED FL8.1 merged-main `74f6041a62d47451e339458dcdc0dc643fbb7570`  
**Build-order owner:** FL8.2 Practical model baselines  
**Scope:** offline Python training/inference artifacts only; no validation, promotion, PAPER authority, provider/signing, transaction submission, or LIVE authority

---

## 1. Goal

FL8.2 turns the sealed FL8.1 training bundle into small, deterministic, auditable forecast baselines that later phases can evaluate chronologically.

The immediate objective is not to prove profitability or select a champion. It is to establish practical model families that:

- consume the exact point-in-time feature records sealed by FL8.1;
- train separately for explicit FL4 horizons and targets;
- produce immutable, versioned, non-executable JSON artifacts;
- support pure-Python reference inference without importing scikit-learn at inference time;
- are cheap enough to become a realistic latency baseline for eventual Rust parity;
- provide naive comparators so FL8.3 can reject models that fail to beat trivial predictions.

FL8.2 does not create an action policy. FL5 counterfactual labels remain in the bundle for later action learning, while FL8.2 forecasts FL4 future-path targets. FL9 owns continuous action comparison.

---

## 2. Preserved boundaries

The following sealed responsibilities remain unchanged:

- Rust `FastMarketState` remains the Fast Lane feature-calculation authority.
- FL4 remains the future-path label authority.
- FL5 remains the counterfactual action-label authority.
- FL8.1 remains the bundle/join/version/fingerprint authority.
- Existing legacy `shreks_brain.learning` E3/E4/E5 code remains a preserved baseline and must not be silently reinterpreted for Fast Lane data.
- Existing champion/challenger registry and promotion machinery receives no authority from FL8.2.
- No code in FL8.2 may create `TradeIntent`, mutate positions, call providers, sign, submit transactions, enable PAPER execution, or enable LIVE.

A new focused package, `shreks_brain.fast_learning`, isolates the Fast Lane learning contract from the older D6/E3 learning contract.

---

## 3. Model families

FL8.2 intentionally begins with simple models whose inference contract can be represented with standard-library values.

### 3.1 Continuous targets

For each requested `(horizon_ms, target)` pair:

1. **MEAN_REGRESSOR** — predicts the mean training target and acts as the trivial comparator.
2. **RIDGE_REGRESSION** — median-imputed, standardized linear regression with L2 regularization using scikit-learn only during fitting.

Supported V1 continuous FL4 targets:

- `endpoint_return_bps`
- `mfe_bps`
- `mae_bps`
- `best_cost_adjusted_return_bps`
- `endpoint_cost_adjusted_return_bps`

Only `completeness == "complete"` rows with a non-null target are eligible.

### 3.2 Binary targets

For each requested `(horizon_ms, target)` pair:

1. **PRIOR_CLASSIFIER** — predicts the observed positive-class fraction and acts as the trivial comparator.
2. **LOGISTIC_REGRESSION** — median-imputed, standardized logistic regression using scikit-learn only during fitting.

Supported V1 binary FL4 targets:

- `reversal_occurred`
- `route_unavailability_observed`

Only complete rows with a non-null target are eligible. Logistic fitting requires both classes; the prior classifier remains valid for a single-class training slice so the absence of class diversity is visible rather than fabricated.

### 3.3 Why no boosted trees yet

Gradient boosting is a plausible later challenger for tabular data, but FL8.2 first needs a stable, portable inference contract and a chronological evaluation harness. Introducing a tree serialization/runtime format before FL8.3 proves linear baselines inadequate would add artifact and Rust-parity complexity without evidence. FL8.2 therefore keeps the first contract deliberately small.

---

## 4. Canonical feature vector

`shreks_brain.fast_learning.features` owns a versioned, deterministic flattening of one `FastTrainingFeatureRecord` into numeric values.

### 4.1 Excluded fields

The model feature vector must not include:

- decision signature or ordinal;
- mint or quote-mint identifiers;
- wallet/actor identity;
- absolute decision timestamp;
- slot or sequence identifiers;
- any FL4 future target;
- any FL5 counterfactual outcome;
- any bundle fingerprint as a numeric feature.

These values may exist in provenance metadata but not in the predictor vector.

### 4.2 Included fields

V1 includes only point-in-time information already sealed in FL8.1:

- decision executable entry price and optional entry total quote;
- snapshot last price;
- decision event-kind indicator (`buy`/`sell`);
- venue indicators for Pump bonding curve and PumpSwap;
- actor-present indicator without actor identity;
- reserve-context kind indicators and numeric reserve/decimal fields;
- lifecycle-present indicator and non-negative detection/occurrence age relative to the decision when available;
- for each sealed window `100, 250, 500, 1000, 2000, 5000, 10000 ms`:
  - buy/sell counts;
  - unique buy/sell actor counts;
  - buy/sell arrival rates;
  - count imbalance;
  - buy/sell base quantity;
  - buy/sell/net quote quantity;
  - quote-flow imbalance, velocity, and acceleration;
  - local-high/local-low/post-high-low/last price where present;
  - drawdown from local high;
  - recovery from local low.

Every feature name and order is sealed by `FAST_FORECAST_FEATURE_SCHEMA_VERSION = 1`. A schema change requires a version bump.

### 4.3 Missing values and transforms

Raw extraction represents unavailable optional numeric evidence as `None`.

Trainable linear models fit one transform per feature:

1. median imputation from the eligible training rows;
2. mean centering after imputation;
3. population standard deviation scaling;
4. a zero/degenerate scale is stored as `1.0`.

All learned transform values must be finite. The artifact stores them explicitly so inference does not depend on sklearn or NumPy.

---

## 5. Requests and artifacts

### 5.1 Training request

A `FastForecastTrainingRequest` contains:

- unique non-empty `model_version`;
- exact model family;
- exact target;
- positive `horizon_ms` that exists in the FL8.1 bundle labels;
- versioned training policy.

The training policy stores only family-relevant fit parameters:

- ridge `alpha > 0`;
- logistic `regularization_c > 0`, positive `max_iterations`, positive `tolerance`, and optional balanced class weights.

Naive models do not accept hidden fit knobs.

### 5.2 Artifact

`FastForecastBaselineArtifact` is frozen and standard-library-only. It records:

- schema name/version;
- model version/family;
- target and target kind;
- horizon;
- feature schema version;
- training-policy version;
- FL8.1 bundle fingerprint;
- FL4 label version;
- eligible and unavailable row counts;
- min/max training decision timestamps;
- deterministic training-data fingerprint;
- feature transforms for trained linear models;
- coefficients/intercept for linear models, or a constant prediction for naive models;
- artifact logical fingerprint.

It contains no sklearn estimator, NumPy array, pickle/joblib payload, executable class path, evaluation metric, promotion state, trading threshold, position size, or execution authority.

### 5.3 Immutable JSON codec

`codec.py` writes one canonical JSON object plus trailing newline and refuses to overwrite an existing destination. Reading:

- validates exact keys;
- validates enums/types/schema versions;
- reconstructs the frozen artifact;
- recomputes and verifies the logical fingerprint.

JSON is chosen now because FL8.5 owns the eventual champion packaging contract; FL8.2 only needs a deterministic research artifact.

---

## 6. Training-data construction

Training begins from an already validated `FastTrainingBundle` returned by `read_fast_training_bundle`.

For a request:

1. locate FL4 labels with the requested horizon;
2. require exact `decision_identity` mapping to an FL8.1 feature record;
3. retain only `completeness == "complete"` and non-null requested target;
4. extract the canonical V1 feature vector from that feature record;
5. preserve canonical order by decision sequence/signature/ordinal from the sealed bundle;
6. compute a deterministic fingerprint over request identity, bundle fingerprint, feature names/values, targets, and decision identities;
7. train the requested family.

If no label exists for the horizon, no eligible rows exist, a feature is non-finite, or identity invariants fail, training fails closed.

Trainable ridge requires at least two eligible rows. Logistic requires at least two eligible rows and both classes. Naive models require at least one eligible row.

No random train/test split occurs in FL8.2. FL8.3 owns chronological validation and leakage-resistant splitting.

---

## 7. Reference inference

`inference.py` accepts one exact artifact and one `FastTrainingFeatureRecord`.

For linear models it:

- re-extracts the canonical V1 raw feature vector;
- applies only the artifact's stored imputation/mean/scale values;
- computes the dot product and intercept in pure Python;
- returns the raw regression value for ridge;
- applies a numerically stable sigmoid for logistic.

Naive models return their stored constant.

`FastForecastPrediction` includes model version, target, horizon, decision identity, and predicted value. Binary predictions are probabilities in `[0, 1]`; continuous predictions must be finite.

Inference must not import sklearn, NumPy, providers, execution, registry promotion, or LIVE-control modules.

---

## 8. Determinism and reproducibility

With the same:

- FL8.1 bundle;
- request/policy;
- Python/scikit-learn-supported fit path;

training must produce the same logical artifact values and fingerprint within the repository's supported environment.

The artifact fingerprint excludes itself and hashes canonical JSON of every other artifact field.

Changing only a future-path target must change the training-data/artifact fingerprint while leaving the sealed FL8.1 feature fingerprint untouched.

---

## 9. Failure behavior

FL8.2 fails closed on at least:

- wrong bundle or feature schema version;
- unsupported target/family pairing;
- unknown horizon;
- incomplete-only target slice;
- null/non-finite target values;
- insufficient rows;
- single-class logistic data;
- missing scikit-learn when a trained linear family is requested;
- non-convergence or non-finite fitted parameters;
- feature-schema/order mismatch;
- artifact fingerprint mismatch;
- overwrite attempt;
- inference against an incompatible artifact/feature schema.

No fallback silently switches targets, horizons, model families, or training data.

---

## 10. Authority boundary tests

Tests must prove that `shreks_brain.fast_learning` exposes no provider, signer, transaction, trade-intent, execution, registry-promotion, PAPER-mode, or LIVE-enablement authority.

The package may read research artifacts and produce predictions only.

---

## 11. Verification and exit criterion

FL8.2 is complete only when:

1. naive and trained baseline families fit from a sealed FL8.1 bundle fixture;
2. exact horizon/target eligibility and missing/completeness semantics are tested;
3. feature extraction is deterministic and contains no identity/future-target columns;
4. fitted artifacts are immutable, canonical, fingerprinted, and standard-library-only;
5. reference inference works without sklearn/NumPy imports and matches sklearn reference predictions within explicit tolerance for ridge/logistic fixtures;
6. target-only changes alter training/artifact fingerprints but not FL8.1 feature fingerprints;
7. authority-boundary tests remain green;
8. full repository safety, Python, Rust, and native ARM64 CI are green on the exact clean head;
9. merged-main receives a fresh push-triggered four-gate green seal.

FL8.2 does **not** claim predictive edge, chronological generalization, calibration, trading profitability, champion status, or permission to trade. Those belong to later FL8/FL9 proof stages. LIVE remains disabled.