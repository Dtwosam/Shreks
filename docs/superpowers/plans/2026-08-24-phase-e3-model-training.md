# Phase E3 Model Training Pipeline Verification Record

## Sealed predecessor

Phase E3 was built from the immutable Phase E2 seal:

- E2 head: `caeb7b127b39a9c7fd5cf40ca877fbe677ba703f`
- E3 branch: `feat/phase-e3-model-training`
- E3 design: `docs/superpowers/specs/2026-08-24-phase-e3-model-training-design.md`

E3 does not modify E1 replay, E2 baselines, B7 scoring, B8 decisions, Rust source, or migrations.

## Delivered boundary

E3 adds `shreks_brain.learning` with schema `e3-training-v1` and one deliberately simple supervised challenger family: binary logistic regression.

The implementation:

- consumes caller-supplied logical D6 `d6-research-v1` rows;
- accepts only an explicit caller-supplied tuple of allow-listed numeric/boolean decision-time features;
- excludes all future-label columns, candidate identity/time, categorical policy/state strings, collections/JSON audit payloads, and B8 `decision_action` / `required_score_threshold` from the trainable feature surface;
- derives a binary target only from the caller-supplied D6 return horizon and finite return threshold, using inclusive `>=` semantics;
- excludes pending/unavailable targets rather than treating them as negatives or zero;
- deterministically sorts eligible rows by `(as_of_unix_ms, candidate_mint)`;
- derives training-only median imputation, mean, and population-standard-deviation transforms;
- records deterministic training provenance and a SHA-256 training fingerprint;
- lazy-loads scikit-learn only when fitting;
- exports only immutable standard-library values rather than a sklearn/NumPy estimator object;
- performs inference in standard-library Python with stored transforms and a numerically stable sigmoid;
- reads no future-label value during inference.

The base package remains dependency-free. `scikit-learn>=1.7,<2` is isolated to the optional `learning` extra and the `dev` test extra.

## TDD evidence

### Model/API RED

Commit: `5d6f03daf2d302944f6dce23f56fd14afa4459e3`  
CI: `32762589979`

Expected RED: two collection errors because `shreks_brain.learning` did not exist.

### Model/API GREEN

Commit: `f4e48bb334189e14bbd1c23b947bf522929c7772`  
CI: `32762742101`

Immutable learning contracts and the explicit public API were added without preprocessing, sklearn, or fitting behavior. Repository safety, Python, and Rust/workspace gates were green.

### Feature-preparation RED

Commit: `1f41f32337c4da096aa90a430f97e327468dbcb1`  
CI: `32764822800`

Expected RED: collection reached the E3 package and failed specifically because `TRAINABLE_RESEARCH_FEATURE_COLUMNS` was not yet exported.

### Feature-preparation implementation

Commit: `0be93d74a631ecdf8398cb884a67ba05f1b75194`  
CI: `32765242825`

Result: `1 failed, 1735 passed`.

The sole failure was a test-fixture error, not a production semantic defect: the fixture changed a target return from `+10%` to `+50%` while the configured positive boundary was `+5%`, so the binary target correctly remained positive.

### Feature test-only repair

Commit: `00fff146ca852fdfef810685a583c1a9d503c270`  
CI: `32765464217`

The fixture was changed only from `+50%` to `-50%` so the test actually crossed the configured class boundary. No production code changed. Repository safety, Python, and Rust/workspace gates were green.

### Training/inference RED

Commit: `b4d3ef6e0195f2dcd1cc8deec351227f95b9425f`  
CI: `32765770710`

Expected RED: exactly two collection errors, one for the missing `train_logistic_regression` function and one for the missing `predict_positive_probability` function. No sklearn dependency or trainer/inference production code existed at this RED point.

### Production GREEN

Commit: `d795a03913d995d6e737df3e8482d669f3d7de97`  
CI: `32766079490`

Fresh exact-head evidence:

- repository safety: GREEN;
- Python: `1751 passed in 4.59s`;
- Rust tests: GREEN;
- workspace metadata: GREEN.

The CI environment installed and exercised `scikit-learn 1.9.0`, proving the real lazy training path rather than only import-level behavior.

## Behavior proved by tests

The E3 suite proves:

- only sealed decision-time scalar evidence can be requested as model features;
- future labels cannot enter the feature matrix;
- non-target future-label changes cannot change prepared training data, fingerprints, trained artifacts, or predictions;
- pending targets are excluded and counted;
- target threshold equality is positive;
- missing selected features use training medians;
- booleans become numeric evidence;
- unsupported/non-finite evidence fails closed;
- an all-missing selected feature fails closed;
- training population/order/transforms/fingerprint are input-order independent;
- training requires at least two eligible rows and both target classes;
- coefficients/intercept are finite and dimensionally reconciled;
- the trained artifact carries no accuracy, AUC, expectancy, PnL, drawdown, win-rate, profit-factor, turnover, or promotion fields;
- importing `shreks_brain.learning` does not import sklearn;
- inference uses no sklearn or NumPy and remains stable for extreme logits;
- inference uses only stored training transforms and decision-time row evidence.

## Sealed-E2 -> E3 implementation diff audit

Before documentation seal, the exact comparison from E2 `caeb7b127b39a9c7fd5cf40ca877fbe677ba703f` to production GREEN `d795a03913d995d6e737df3e8482d669f3d7de97` contained only:

- the E3 design and implementation-plan documents;
- `python/pyproject.toml` optional `learning` / `dev` dependency change;
- `python/src/shreks_brain/learning/__init__.py`;
- `python/src/shreks_brain/learning/models.py`;
- `python/src/shreks_brain/learning/features.py`;
- `python/src/shreks_brain/learning/trainer.py`;
- `python/src/shreks_brain/learning/inference.py`;
- E3 learning model, feature, training, inference, and public-API tests.

No predecessor production file, Rust source file, migration, setup evaluator, score engine, decision engine, risk engine, or execution path changed.

## Scope boundary

E3 does not choose a production feature set, target horizon, target return threshold, or training policy. It does not split data chronologically, perform walk-forward validation, compute trading/economic metrics, search hyperparameters, select a champion, persist a model registry, change B7/B8/B9 behavior, create a `TradeIntent`, execute a trade, sign a transaction, or enable live money.

Profitability remains unproven. Phase E4 must validate models with chronological unseen data; Phase E5 must measure post-cost trading behavior before any challenger can be considered useful.

## Seal rule

The final documentation seal is permitted to change only:

- `README.md`, additions only;
- this verification-record file.

After the seal is attached and exact-head CI is green, E3 is immutable and Phase E4 Time-Aware Validation must start from that exact SHA.
