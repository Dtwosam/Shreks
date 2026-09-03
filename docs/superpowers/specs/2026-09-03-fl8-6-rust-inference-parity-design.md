# FL8.6 Rust Inference Parity — Design

## Status and base

Approved for autonomous implementation under the project build order.

Base: SEALED FL8.5 merged-main `04483643a9fbb24264c27f87291f5446ff7d466a`, merged-main four-gate GREEN CI `33805473489`.

## Goal

Implement the Rust consumer for the sealed FL8.5 champion artifact and prove numerical inference parity with the sealed Python FL8.2 evaluator within explicit tolerances.

The build order requires Rust numerical/decision parity when champion inference runs in Rust. Shreks' production Fast Lane is Rust, so FL8.6 implements that parity layer now.

FL8.6 is an inference/cross-language verification phase. It is not live feature extraction, action policy, execution, or promotion.

## Boundary

FL8.6 owns:

- parsing the exact FL8.5 champion JSON schema in Rust;
- rejecting unknown fields and incompatible schemas/artifacts;
- recomputing the FL8.5 top-level champion fingerprint with Python-compatible canonicalization;
- exact target/horizon lookup with no fallback;
- sealed FL8.2 transform/inference equations over a 169-element raw feature vector;
- mean, ridge, prior, and logistic inference;
- explicit Python/Rust parity tolerances;
- test-only binary side-of-0.5 diagnostic parity;
- fail-closed behavior for tamper, missing member, non-finite input, and wrong feature count.

FL8.6 does not train/retrain, fit calibration, select/promote champions, map live `FastMarketState` into features, choose actions, size positions, execute PAPER/LIVE trades, sign, submit, or mutate the registry. FL9 owns action policy; FL10 owns live-state feature/runtime wiring; FL11 owns independent shadow proof/promotion.

## Why raw feature-vector inference is the seam

FL8.2 already separates feature extraction from model inference:

1. extract 169 named raw features;
2. impute/standardize with artifact transforms;
3. calculate constant or linear/logistic prediction.

FL8.6 isolates steps 2–3. Reimplementing live feature extraction here would mix cross-language math parity with runtime integration and make failures ambiguous. FL10 will wire Rust Fast Lane state to this sealed vector.

## Rust placement and dependencies

Add:

```text
crates/shreks-core/src/fast_lane/forecast.rs
```

Update:

```text
crates/shreks-core/src/fast_lane/mod.rs
crates/shreks-core/src/lib.rs
crates/shreks-core/Cargo.toml
```

`fast_lane/mod.rs` owns the module-level forecast surface and `lib.rs` follows the existing `shreks-core` convention by re-exporting that narrow surface at crate root for runtime/tests.

Add only deterministic data-format/hash dependencies:

- `serde` with derive;
- `serde_json`;
- `sha2`.

No async/network/database/training/execution dependency is added.

## Sealed feature contract

Rust defines:

```text
FAST_FORECAST_FEATURE_SCHEMA_VERSION = 1
FAST_FORECAST_FEATURE_COUNT = 169
```

Feature order is exactly FL8.2:

- 22 top-level decision/reserve/lifecycle fields;
- 21 numeric fields for each sealed window `100, 250, 500, 1000, 2000, 5000, 10000` ms.

Trained artifacts require exactly 169 transforms in exact feature-name order and 169 coefficients.

Inference input is `&[Option<f64>]` length 169. `None` is imputed with the artifact median. Present values must be finite.

## Champion JSON model

Rust mirrors the exact FL8.5/FL8.2 wire values needed at runtime:

- champion schema/version/version string;
- explicit selection record;
- common feature schema/source-bundle/FL4 label provenance;
- canonical members;
- embedded FL8.2 artifacts;
- FL8.3/FL8.4 evidence references/counts;
- champion fingerprint.

Every deserialized object uses `deny_unknown_fields`.

Exact enums:

- families: `MEAN_REGRESSOR`, `RIDGE_REGRESSION`, `PRIOR_CLASSIFIER`, `LOGISTIC_REGRESSION`;
- targets: `endpoint_return_bps`, `mfe_bps`, `mae_bps`, `best_cost_adjusted_return_bps`, `endpoint_cost_adjusted_return_bps`, `reversal_occurred`, `route_unavailability_observed`;
- kinds: `continuous`, `binary`.

## Structural validation

The loader fails closed unless:

- champion schema is `shreks.fast_lane_forecast_champion` version `1`;
- selection/version strings are non-empty;
- feature schema is `1`;
- fingerprint/evidence strings are lowercase 64-character SHA-256 hex;
- future-path label version is positive;
- members are non-empty, lexical by key, and unique;
- key is exactly `{target}@{horizon_ms}ms`;
- all artifacts share champion feature schema/source bundle/FL4 version;
- artifact schema is `shreks.fast_lane_forecast_baseline` version `1`;
- target kind and family/target kind are compatible;
- horizon/training rows are positive;
- binary class counts reconcile; continuous artifacts carry none;
- training timestamp bounds are ordered;
- trained artifacts contain exact transforms/coefficients/intercept and no constant;
- naive artifacts contain no transforms/coefficients/intercept and do contain a finite constant;
- binary constants lie in `[0, 1]`;
- transforms/coefficients/intercepts/constants are finite and scales positive;
- test scored observation count is positive.

The embedded FL8.2 artifact fingerprint stays part of the validated structure and top-level fingerprint material. FL8.6 does not duplicate FL8.2's decimal-JSON artifact hash implementation: FL8.5 already validates it before packaging, and the FL8.5 champion fingerprint covers every embedded artifact field plus the artifact fingerprint.

## Champion fingerprint parity

FL8.5 hashes all material champion fields except `champion_fingerprint_sha256` after recursively replacing floats with:

```json
{"float_hex":"<python float.hex()>"}
```

Rust reimplements finite IEEE-754 binary64 Python `float.hex()` exactly:

- signed zero preserved;
- normal values `0x1.<13 hex digits>p±e`;
- subnormal values `0x0.<13 hex digits>p-1022`;
- non-finite values rejected.

The transformed value is compact sorted-key UTF-8 JSON and SHA-256 hashed. The committed cross-language fixture's Python-authored champion fingerprint must reproduce exactly in Rust; a mismatch fails before inference.

## Inference semantics

Mean/prior return the exact `constant_prediction`.

Ridge/logistic apply:

```text
scalar = raw if present else imputation_median
transformed = (scalar - mean) / scale
score = sum(coefficient_i * transformed_i) + intercept
```

Rust uses compensated summation to stay close to Python `math.fsum`.

Ridge returns the finite score.

Logistic uses the exact stable branch:

```text
if score >= 0:
    z = exp(-score)
    p = 1 / (1 + z)
else:
    z = exp(score)
    p = z / (1 + z)
```

Binary predictions must remain in `[0, 1]`.

## Public Rust surface

`shreks-core` exports only the forecast parity/runtime-loading contracts needed later by FL10:

```text
FAST_FORECAST_FEATURE_SCHEMA_VERSION
FAST_FORECAST_FEATURE_COUNT
FastForecastModelFamily
FastForecastTarget
FastForecastTargetKind
FastForecastFeatureTransform
FastForecastArtifact
FastForecastChampionSelection
FastForecastChampionMember
FastForecastChampion
FastForecastPrediction
FastForecastInferenceError
load_fast_forecast_champion_json
predict_fast_forecast
```

Missing target/horizon is an error; no nearest-member fallback. No rank/promote/action/position/trade/live API is added.

## Compact cross-language parity spec

Commit one immutable compact fixture:

```text
crates/shreks-core/tests/fixtures/fl8_6_parity_spec.json
```

It contains common champion/selection/evidence metadata, four sparse model specifications covering all four FL8.2 families, Python-authoritative artifact/champion fingerprints, sparse raw-feature cases, expected predictions, and absolute/relative tolerances of `1e-12`.

Both languages expand the same compact specification into the full 169-feature structures. This avoids a large generated champion blob while strengthening drift detection: Python and Rust independently construct the same full champion identity from the same sparse source.

### Python proof

A Python test:

1. expands the compact spec into exact FL8.2 artifacts with all 169 transforms/coefficients;
2. verifies each expected artifact fingerprint using sealed FL8.2 hashing;
3. builds the exact FL8.5 champion and verifies the expected champion fingerprint;
4. writes/reads it through the sealed FL8.5 codec;
5. expands each sparse feature case and computes predictions with sealed FL8.2 transform/inference math;
6. verifies every committed expected value and test-only binary side-of-0.5 diagnostic.

### Rust proof

A Rust integration test:

1. parses the same compact spec as test data;
2. expands it into the full Rust champion structs and serializes an exact FL8.5 JSON document;
3. loads that JSON through the production Rust loader, which must reproduce the Python champion fingerprint;
4. expands identical sparse raw cases;
5. verifies all four model-family predictions using `abs_error <= abs_tol + rel_tol * abs(expected)`;
6. verifies binary side-of-0.5 diagnostic parity exactly;
7. proves tamper/unknown-field/missing-member/wrong-length/non-finite failures.

The `0.5` diagnostic is test-only and is not an action threshold.

## Authority boundary

The production forecast module may use only `serde`, `serde_json`, `sha2`, and standard-library math/error utilities. Source tests reject provider/network, database, wall-clock/randomness, training-action/trade, signer/submission, promotion, and LIVE-control dependencies/tokens in `forecast.rs`, and lock the new `shreks-core` dependency set to the three approved format/hash crates.

## Determinism and latency boundary

Champion validation/hash occurs at configuration load. Hot inference performs only exact lookup, 169 transforms/multiply terms, and optionally one sigmoid. No training, network, DB, wall-clock read, randomness, or provider access occurs.

FL10 will benchmark production event-to-inference latency after live feature wiring.

## TDD and seal

Required sequence:

1. design;
2. plan;
3. compact fixture + Python/Rust RED contracts before production module exists;
4. intentional Rust compile RED while Python remains green;
5. minimal Rust implementation;
6. candidate four-gate GREEN;
7. exact scope audit;
8. clean history `design -> plan -> consolidated RED -> implementation` preserving verified tree;
9. fresh clean-head four-gate GREEN;
10. guarded merge with expected head SHA;
11. merged-main four-gate GREEN;
12. mark FL8.6 SEALED.

## Exit criterion

Rust can load/validate the sealed FL8.5 champion representation, perform all four model-family predictions from the sealed 169-feature vector, and match Python reference values within explicit `1e-12` absolute/relative tolerances, while failing closed on incompatible/tampered inputs.

FL8.6 does not establish economic edge, profitability, action-policy quality, live-runtime latency, shadow performance, or LIVE eligibility. LIVE remains disabled.