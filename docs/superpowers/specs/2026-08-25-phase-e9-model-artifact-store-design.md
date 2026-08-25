# Phase E9 Model Artifact Store Design

## Purpose

Phase E9 closes a restart-safety gap between sealed E3 model training and sealed E7 shadow evaluation.

E3 deliberately emits an immutable, portable `TrainedLogisticRegressionModel` made only of standard-library values. E6 persists registry metadata for that model, and E7 requires the actual model artifact to evaluate a challenger. The repository currently has no durable model-artifact store, so a process restart can preserve challenger metadata while losing the fitted coefficients/transforms required to resume shadow evidence collection.

E9 adds only durable, content-addressed persistence for E3 portable model artifacts. It does not train models, choose a strategy, promote a challenger, mutate registry status, create trade intents, paper trade, or enable live execution.

E9 is based exactly on sealed E8 head `9d40d12dd5985af7f0acbb3a3ffc3817ed071e8e`.

## Core boundary

The persistence path is:

```text
TrainedLogisticRegressionModel
  -> exact standard-library model mapping
  -> full-content artifact fingerprint
  -> append-only artifact catalog
  -> canonical JSON
  -> fsync temporary sibling
  -> atomic replace
```

The restart path is:

```text
artifact catalog JSON
  -> exact schema validation
  -> reconstruct E3 immutable model
  -> independently recompute full-content artifact fingerprint
  -> return exact model object
```

No pickle, joblib, sklearn estimator, NumPy array, arbitrary class path, executable serialization, or opaque binary payload is permitted.

## Package changes

Extend `shreks_brain.learning` with:

- `learning/codec.py` — exact JSON mapping, canonical JSON, and full-content artifact fingerprinting;
- `learning/store.py` — restart-safe append-only `ModelArtifactStore`;
- `learning/__init__.py` — export `MODEL_ARTIFACT_STORE_SCHEMA_VERSION` and `ModelArtifactStore`.

Do not change the sealed E3 model dataclasses or training/inference behavior.

## Store schema

Use store schema version:

```text
e9-model-artifacts-v1
```

The physical document is exactly:

```json
{
  "schema_version": "e9-model-artifacts-v1",
  "artifacts": [
    {
      "artifact_fingerprint_sha256": "<64 lowercase hex>",
      "model": { "... exact E3 model fields ..." }
    }
  ]
}
```

Every nested object is exact-schema. Unknown or missing fields fail closed.

The model mapping contains every field from `TrainedLogisticRegressionModel`, with enums serialized by `.value`, tuples serialized as arrays, and the nested `ResearchReturnTarget` and `FeatureTransform` values represented as exact objects.

## Artifact fingerprint

E3 `training_fingerprint_sha256` proves the training population/request provenance. It is not treated as a full at-rest content checksum for the fitted artifact.

E9 therefore computes `artifact_fingerprint_sha256` over the canonical JSON mapping of the complete model content, including:

- schema/model/model-family/training-policy versions;
- research dataset schema;
- target;
- all feature transforms in order;
- all coefficients in order;
- intercept;
- all row counts and training time bounds;
- E3 training fingerprint.

Changing any persisted model value while retaining the old artifact fingerprint must fail on load.

## Canonical JSON

Canonical JSON uses:

- UTF-8;
- sorted keys;
- compact separators;
- `ensure_ascii=False`;
- `allow_nan=False`;
- exactly one trailing newline in the physical file.

The fingerprint hashes the canonical JSON bytes without the trailing file newline.

## Store API

`ModelArtifactStore(path)` exposes only:

```text
load() -> tuple[TrainedLogisticRegressionModel, ...]
get(model_version) -> TrainedLogisticRegressionModel | None
append(model) -> tuple[TrainedLogisticRegressionModel, ...]
```

Behavior:

- missing file loads as an empty tuple;
- append preserves existing artifact order and adds the new model at the end;
- appending the exact same model version/content is idempotent;
- appending the same `model_version` with different content fails closed;
- `get` returns the exact stored artifact by model version or `None`;
- the store exposes no delete, overwrite, replace-model, promotion, registry-status, trade, signing, submission, or live-mode method.

## Validation and corruption handling

Load fails closed for:

- malformed JSON;
- non-object top-level document;
- wrong store schema version;
- missing/unknown top-level fields;
- non-array artifact collection;
- missing/unknown artifact wrapper fields;
- missing/unknown model fields;
- missing/unknown nested target/transform fields;
- invalid enum values;
- wrong scalar/container types;
- non-finite numeric content;
- invalid SHA-256 strings;
- duplicate `model_version` values;
- stale/tampered full-content artifact fingerprints;
- any model content that violates the existing E3 dataclass invariants.

The E3 training fingerprint cannot be independently re-derived without the original D6 training rows; E9 validates its shape through E3 and protects it as part of the independently hashed full artifact.

## Atomic persistence

Writes follow the sealed E6/E7/E8 pattern:

1. create parent directories;
2. write canonical payload to `<name>.tmp`;
3. flush and `os.fsync`;
4. `os.replace` temporary -> destination;
5. on write/replace error, best-effort remove the temporary sibling and re-raise.

Successful writes leave no `.tmp` sibling.

## Dependency/import boundary

`learning.codec` and `learning.store` use only the Python standard library plus existing E3 immutable contracts.

Importing `shreks_brain.learning` must continue not to import scikit-learn eagerly. Training remains the only path that lazy-loads the optional ML dependency.

## Relationship to E6/E7/E8

E9 does not alter E6 registry semantics. Registry metadata remains the authority for whether a version is registered/challenger/champion.

E9 does not alter E7 shadow decisions. It only makes it possible for a runtime to recover the exact E3 artifact needed by the already-sealed `evaluate_shadow_challenger(...)` function after restart.

E9 does not alter E8 promotion rules and cannot satisfy a promotion gate by itself. It is infrastructure required to accumulate trustworthy shadow evidence over time.

## Explicit non-goals

E9 does not:

- retrain or tune a model;
- persist sklearn/joblib/pickle artifacts;
- choose a feature set or target;
- run chronological validation;
- calculate trading performance;
- create or modify registry candidates/status events;
- create shadow decisions automatically;
- promote a challenger;
- create `TradeIntent`;
- paper trade or live trade;
- sign or submit transactions;
- manage private keys;
- define live-capital thresholds.

## Exit criterion

E9 is complete when an exact E3 portable model artifact can be appended, recovered after restart, independently integrity-checked from its full persisted content, and safely retrieved by model version without adding any trading or promotion authority.