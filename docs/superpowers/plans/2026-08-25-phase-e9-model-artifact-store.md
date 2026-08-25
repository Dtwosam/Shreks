# Phase E9 Model Artifact Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist exact E3 portable logistic-regression artifacts in a canonical, restart-safe, content-addressed catalog so E7 shadow evaluation can resume after process restarts.

**Architecture:** Add a standard-library codec beside the sealed E3 learning contracts, then place a thin append-only atomic store over it. The store returns existing `TrainedLogisticRegressionModel` values unchanged and adds no training, registry, promotion, trade, or live authority.

**Tech Stack:** Python 3.12 standard library, existing `shreks_brain.learning` dataclasses, pytest 8.x, GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e9-model-artifact-store-design.md`

## Global Constraints

- Base exactly on sealed E8 head `9d40d12dd5985af7f0acbb3a3ffc3817ed071e8e`.
- Store schema is exactly `e9-model-artifacts-v1`.
- Do not modify the sealed E3 model dataclasses or training/inference behavior.
- Do not add pickle, joblib, sklearn estimator serialization, NumPy artifacts, opaque binaries, or executable class paths.
- Canonical JSON uses sorted keys, compact separators, UTF-8, `ensure_ascii=False`, and `allow_nan=False`.
- Physical files end in exactly one newline; fingerprints hash canonical model JSON without that newline.
- Same `model_version` + same content is idempotent; same `model_version` + different content fails closed.
- Writes use fsync + atomic replace and best-effort `.tmp` cleanup on error.
- Importing `shreks_brain.learning` must not eagerly import scikit-learn.
- E9 must expose no delete/overwrite/promote/registry/trade/sign/submit/live authority.

---

### Task 1: Canonical model artifact codec and integrity fingerprint

**Files:**
- Create: `python/src/shreks_brain/learning/codec.py`
- Create: `python/tests/test_learning_artifact_codec.py`

**Interfaces:**
- Consumes: `TrainedLogisticRegressionModel`, `ResearchReturnTarget`, `FeatureTransform`, `ModelFamily` from `shreks_brain.learning.models`.
- Produces:
  - `MODEL_ARTIFACT_STORE_SCHEMA_VERSION = "e9-model-artifacts-v1"`
  - `canonical_json(value: object) -> str`
  - `model_to_dict(model: TrainedLogisticRegressionModel) -> dict[str, object]`
  - `compute_artifact_fingerprint(model: TrainedLogisticRegressionModel) -> str`
  - `build_artifact_document(models: tuple[TrainedLogisticRegressionModel, ...]) -> dict[str, object]`
  - `decode_artifact_document(document: object) -> tuple[TrainedLogisticRegressionModel, ...]`

- [ ] **Step 1: Write failing codec tests**

Create fixtures using exact E3 values and assert:

```python
from dataclasses import replace
import json
import math

import pytest

from shreks_brain.learning.codec import (
    MODEL_ARTIFACT_STORE_SCHEMA_VERSION,
    build_artifact_document,
    canonical_json,
    compute_artifact_fingerprint,
    decode_artifact_document,
    model_to_dict,
)


def test_model_artifact_document_round_trips_exact_model():
    model = _model()
    document = build_artifact_document((model,))
    assert document["schema_version"] == MODEL_ARTIFACT_STORE_SCHEMA_VERSION
    assert decode_artifact_document(document) == (model,)


def test_artifact_fingerprint_covers_fitted_content():
    model = _model()
    changed = replace(model, intercept=model.intercept + 0.25)
    assert compute_artifact_fingerprint(changed) != compute_artifact_fingerprint(model)


def test_decode_rejects_tampered_model_with_stale_fingerprint():
    document = build_artifact_document((_model(),))
    document["artifacts"][0]["model"]["intercept"] = 999.0
    with pytest.raises(ValueError, match="artifact fingerprint"):
        decode_artifact_document(document)


def test_decode_rejects_unknown_fields_wrong_schema_and_non_finite_values():
    document = build_artifact_document((_model(),))
    document["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        decode_artifact_document(document)

    document = build_artifact_document((_model(),))
    document["schema_version"] = "wrong"
    with pytest.raises(ValueError, match="schema"):
        decode_artifact_document(document)

    document = build_artifact_document((_model(),))
    document["artifacts"][0]["model"]["intercept"] = math.nan
    with pytest.raises(ValueError):
        decode_artifact_document(document)


def test_canonical_json_is_compact_sorted_and_rejects_nan():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})
```

Also mutate one nested target field, one transform field, one model field, and one wrapper field with unknown keys and require exact-schema failure. Add duplicate-`model_version` rejection with two different valid artifacts.

- [ ] **Step 2: Run the focused tests and require RED**

Run:

```bash
python -m pytest python/tests/test_learning_artifact_codec.py -q
```

Expected: collection/import failure because `shreks_brain.learning.codec` does not exist.

- [ ] **Step 3: Implement the minimal codec**

`canonical_json`:

```python
def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"value is not canonical-JSON serializable: {error}") from error
```

`model_to_dict` must explicitly map every E3 field and serialize enums by `.value`, tuples as lists, target as `{horizon_seconds, minimum_return_pct}`, and transforms as exact four-field mappings.

`compute_artifact_fingerprint`:

```python
def compute_artifact_fingerprint(model: TrainedLogisticRegressionModel) -> str:
    return hashlib.sha256(canonical_json(model_to_dict(model)).encode("utf-8")).hexdigest()
```

`build_artifact_document` emits wrappers with `artifact_fingerprint_sha256` and `model`.

`decode_artifact_document` must use exact field-set guards at every object layer, validate arrays and enum strings, reconstruct exact E3 dataclasses, reject duplicate model versions, recompute every full-content artifact fingerprint independently, and return a tuple preserving file order.

- [ ] **Step 4: Run codec tests and the existing E3 learning tests**

Run:

```bash
python -m pytest python/tests/test_learning_artifact_codec.py python/tests/test_learning.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Commit message:

```text
feat: add E9 model artifact codec
```

---

### Task 2: Restart-safe append-only model artifact store

**Files:**
- Create: `python/src/shreks_brain/learning/store.py`
- Create: `python/tests/test_learning_artifact_store.py`

**Interfaces:**
- Consumes Task 1 codec functions.
- Produces:
  - `ModelArtifactStore(path: str | Path)`
  - `load() -> tuple[TrainedLogisticRegressionModel, ...]`
  - `get(model_version: str) -> TrainedLogisticRegressionModel | None`
  - `append(model: TrainedLogisticRegressionModel) -> tuple[TrainedLogisticRegressionModel, ...]`

- [ ] **Step 1: Write failing store tests**

Cover:

```python
def test_missing_store_loads_empty_and_get_returns_none(tmp_path):
    store = ModelArtifactStore(tmp_path / "models.json")
    assert store.load() == ()
    assert store.get("missing") is None


def test_append_round_trips_after_restart_and_is_idempotent(tmp_path):
    path = tmp_path / "models.json"
    model = _model()
    first = ModelArtifactStore(path).append(model)
    second = ModelArtifactStore(path).append(model)
    assert first == (model,)
    assert second == (model,)
    assert ModelArtifactStore(path).get(model.model_version) == model


def test_same_version_with_different_content_fails_closed(tmp_path):
    store = ModelArtifactStore(tmp_path / "models.json")
    model = _model()
    store.append(model)
    with pytest.raises(ValueError, match="already stored with different content"):
        store.append(replace(model, intercept=model.intercept + 0.1))


def test_store_writes_canonical_newline_and_leaves_no_tmp(tmp_path):
    path = tmp_path / "nested" / "models.json"
    ModelArtifactStore(path).append(_model())
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert not path.with_name(path.name + ".tmp").exists()
```

Also cover malformed persisted JSON wrapping errors as `ValueError("model artifact file is invalid: ...")`, invalid empty model-version lookup, exact model type checks, and best-effort `.tmp` cleanup when `os.replace` is monkeypatched to raise `OSError`.

- [ ] **Step 2: Run store tests and require RED**

Run:

```bash
python -m pytest python/tests/test_learning_artifact_store.py -q
```

Expected: import failure because `shreks_brain.learning.store` does not exist.

- [ ] **Step 3: Implement the minimal store**

`load` reads JSON and delegates all structural/integrity validation to `decode_artifact_document`.

`get` requires a non-empty string and scans the reconstructed immutable tuple.

`append` requires `type(model) is TrainedLogisticRegressionModel`, recomputes full artifact integrity, loads current state, returns unchanged state for exact idempotent matches, rejects same-version conflicting content, appends otherwise, then writes atomically.

`_write` follows:

```python
self.path.parent.mkdir(parents=True, exist_ok=True)
temporary = self.path.with_name(self.path.name + ".tmp")
payload = canonical_json(build_artifact_document(models)) + "\n"
try:
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, self.path)
except OSError:
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass
    raise
```

- [ ] **Step 4: Run Task 1+2 tests**

Run:

```bash
python -m pytest python/tests/test_learning_artifact_codec.py python/tests/test_learning_artifact_store.py python/tests/test_learning.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Commit message:

```text
feat: persist E9 model artifacts
```

---

### Task 3: Public API, import firewall, authority audit, full verification, immutable seal

**Files:**
- Modify: `python/src/shreks_brain/learning/__init__.py`
- Create: `python/tests/test_learning_artifact_public_api.py`
- Modify only at final seal: `docs/superpowers/plans/2026-08-25-phase-e9-model-artifact-store.md`

**Interfaces:**
- Public exports: `MODEL_ARTIFACT_STORE_SCHEMA_VERSION`, `ModelArtifactStore`.

- [ ] **Step 1: Write public API/firewall tests first**

Require:

```python
def test_learning_exports_e9_artifact_store():
    import shreks_brain.learning as learning
    assert learning.MODEL_ARTIFACT_STORE_SCHEMA_VERSION == "e9-model-artifacts-v1"
    assert learning.ModelArtifactStore.__name__ == "ModelArtifactStore"


def test_e9_store_exposes_no_mutating_trade_or_live_authority():
    forbidden = {
        "delete", "overwrite", "replace_model", "promote", "record_status",
        "trade", "create_trade_intent", "sign", "submit", "enable_live",
    }
    assert forbidden.isdisjoint(set(dir(ModelArtifactStore)))
```

Use a subprocess import test so the assertion is isolated from the rest of pytest:

```python
code = "import sys; import shreks_brain.learning; assert 'sklearn' not in sys.modules"
subprocess.run([sys.executable, "-c", code], check=True)
```

- [ ] **Step 2: Run public API test and require RED**

Run:

```bash
python -m pytest python/tests/test_learning_artifact_public_api.py -q
```

Expected: failure because the new symbols are not exported yet.

- [ ] **Step 3: Export the two E9 symbols**

Add imports from `.codec` and `.store`; preserve all existing E3 exports.

- [ ] **Step 4: Run focused then full Python suite**

Run:

```bash
python -m pytest python/tests/test_learning_artifact_codec.py python/tests/test_learning_artifact_store.py python/tests/test_learning_artifact_public_api.py python/tests/test_learning.py -q
python -m pytest python/tests -q
```

Expected: all PASS.

- [ ] **Step 5: Run exact PR CI and require Python, Rust/workspace, and repository safety GREEN**

Record the exact behavior-head SHA, workflow run id, Python test count/runtime, and every correction made during TDD.

- [ ] **Step 6: Cumulative scope audit from sealed E8 -> E9 behavior head**

Allowed changes only:

- E9 design/plan docs;
- `python/src/shreks_brain/learning/codec.py`;
- `python/src/shreks_brain/learning/store.py`;
- `python/src/shreks_brain/learning/__init__.py`;
- E9 learning artifact tests.

No changes to E3 training/inference/models, E4 validation, E5 evaluation, E6 registry, E7 shadow, E8 promotion, paper/risk, Rust execution, provider, observer, or live paths.

- [ ] **Step 7: Replace this plan with a verification record**

Record RED/GREEN heads and CI ids, behavior-head Python count/runtime, scope audit, restart/integrity guarantees, and explicit statement that E9 adds no promotion/trading/live authority.

- [ ] **Step 8: Audit behavior head -> seal candidate**

Require exactly one changed documentation file and zero production/test changes.

- [ ] **Step 9: Run final exact-head CI**

Require Python, Rust/workspace, and repository safety GREEN on the exact seal SHA.

- [ ] **Step 10: Update the stacked draft PR and freeze**

PR remains draft and unmerged, based exactly on sealed E8, with final seal SHA and verification evidence in the body.