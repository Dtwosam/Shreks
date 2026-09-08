# FL8.3 Validation V2 Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sealed, deterministic FL8.3 V2 chronological-generalization validator that keeps natural future PumpSwap rows, quarantines only cross-partition transaction signatures, enforces an identity-blind feature firewall, and exposes unseen-mint novelty evidence without changing FL8.3 V1 behavior.

**Architecture:** Implement V2 as a sibling package, `shreks_brain.fast_validation_v2`, so the sealed `shreks_brain.fast_validation` V1 package remains byte/behavior compatible. Split V2 into focused models, feature-firewall, population preparation, and model-running modules; the population layer is target-free and reusable for input-only acceptance, while the engine adds target maturity, training, prediction, and deterministic run fingerprints.

**Tech Stack:** Python 3.12, frozen/slotted dataclasses, hashlib/json canonical fingerprints, existing FL8.1 `FastTrainingBundle`, sealed FL8.2 trainer/inference, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-fl8-3-validation-v2-design.md`

## Global Constraints

- V1 `shreks_brain.fast_validation` public API, behavior, tests, and fingerprints remain unchanged.
- V2 policy version is explicit: `fl8.3-chronological-generalization-v2`.
- V2 preserves strict chronological half-open train/validation/TEST intervals.
- V2 preserves target maturity: `decision_observed_at_unix_ms + horizon_ms <= validation_started_at_unix_ms`.
- V2 preserves strict cross-partition transaction/signature isolation.
- Repeated mint and repeated actor identity across partitions are retained in V2.
- Raw mint, actor, signature, pair/pool, provider, ordinal, sequence, and derived identity encodings are forbidden model inputs.
- Current sealed FL8.2 feature names must pass the identity firewall unchanged.
- Unseen-mint novelty is defined relative to raw training only and cannot depend on target values.
- Actor novelty is diagnostic only; it cannot remove rows from the fit or future prediction populations.
- No target value, future return, model metric, PnL, or champion outcome may influence split, quarantine, or novelty membership.
- No mint balancing is added in this slice.
- No network, SQLite, PyArrow, PAPER, promotion, signing, submission, or LIVE authority is added to the V2 validator.
- Tradable-universe thresholds remain unchanged: snapshot age `<= 60000 ms`, liquidity `>= 3000.0 USD`, trailing h24 volume `>= 1000.0 USD`.
- LIVE remains disabled.
- This plan is implementation slice 1 only. First-champion plan/builder/host integration and production numeric novelty floors are deferred to a separate slice after V2 core is sealed and an input-only immutable V2 acceptance audit succeeds.

---

## File Structure

Create:

- `python/src/shreks_brain/fast_validation_v2/__init__.py` — exact V2 public API only.
- `python/src/shreks_brain/fast_validation_v2/models.py` — immutable V2 policies/results/fingerprint-validating contracts.
- `python/src/shreks_brain/fast_validation_v2/firewall.py` — exact FL8.2 feature-schema identity firewall and fingerprint.
- `python/src/shreks_brain/fast_validation_v2/population.py` — target-free chronological partitioning, signature quarantine, novelty classification, structural floors.
- `python/src/shreks_brain/fast_validation_v2/engine.py` — bundle validation, target maturity, training, prediction, run fingerprint.
- `python/tests/fast_chronological_v2_fixtures.py` — focused V2 fixtures, including giant mint/actor connectivity.
- `python/tests/test_fast_chronological_v2_models.py`
- `python/tests/test_fast_chronological_v2_firewall.py`
- `python/tests/test_fast_chronological_v2_population.py`
- `python/tests/test_fast_chronological_v2_engine.py`
- `python/tests/test_fast_chronological_v2_authority.py`

Do not modify in this slice:

- `python/src/shreks_brain/fast_validation/**`
- `python/src/shreks_brain/fast_first_champion_plan.py`
- `python/src/shreks_brain/fast_first_champion/**`
- `python/src/shreks_brain/fast_first_champion_host_run.py`
- tradable-universe policy/runtime collector code.

---

### Task 1: Define immutable V2 contracts without touching V1

**Files:**
- Create: `python/src/shreks_brain/fast_validation_v2/models.py`
- Create: `python/src/shreks_brain/fast_validation_v2/__init__.py`
- Create: `python/tests/test_fast_chronological_v2_models.py`

**Interfaces:**
- Consumes: `FastChronologicalFold` from `shreks_brain.fast_validation.models`; `FastForecastBaselineArtifact`, `FastForecastPrediction`, `FastForecastTrainingRequest`.
- Produces:
  - `FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME = "shreks.fast_lane_chronological_generalization"`
  - `FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION = 1`
  - `FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION = "fl8.3-chronological-generalization-v2"`
  - `FastChronologicalGeneralizationPolicy`
  - `FastSignatureQuarantineSummary`
  - `FastFutureNoveltySummary`
  - `FastChronologicalGeneralizationFoldResult`
  - `FastChronologicalGeneralizationRun`

- [ ] **Step 1: Write RED model-contract tests**

Create `python/tests/test_fast_chronological_v2_models.py` with tests equivalent to:

```python
from dataclasses import FrozenInstanceError

import pytest

from shreks_brain.fast_validation import FastChronologicalFold
from shreks_brain.fast_validation_v2 import (
    FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
    FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME,
    FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION,
    FastChronologicalGeneralizationPolicy,
)


def _fold() -> FastChronologicalFold:
    return FastChronologicalFold(
        name="v2-fold",
        training_started_at_unix_ms=1_000,
        training_ended_at_unix_ms=2_000,
        validation_started_at_unix_ms=2_000,
        validation_ended_at_unix_ms=3_000,
        test_started_at_unix_ms=3_000,
        test_ended_at_unix_ms=4_000,
    )


def test_v2_schema_and_policy_versions_are_explicit() -> None:
    assert FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME == (
        "shreks.fast_lane_chronological_generalization"
    )
    assert FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION == 1
    assert FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION == (
        "fl8.3-chronological-generalization-v2"
    )


def test_v2_policy_is_frozen_and_requires_positive_novelty_floors() -> None:
    policy = FastChronologicalGeneralizationPolicy(
        version=FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
        folds=(_fold(),),
        feature_identity_firewall_version="fl8.3-feature-identity-firewall-v1",
        feature_identity_firewall_fingerprint_sha256="a" * 64,
        minimum_unseen_mint_validation_rows=1,
        minimum_unseen_mint_validation_mints=1,
        minimum_unseen_mint_test_rows=1,
        minimum_unseen_mint_test_mints=1,
    )
    with pytest.raises(FrozenInstanceError):
        policy.version = "changed"  # type: ignore[misc]

    with pytest.raises(ValueError, match="unseen|positive"):
        FastChronologicalGeneralizationPolicy(
            version=FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
            folds=(_fold(),),
            feature_identity_firewall_version="fl8.3-feature-identity-firewall-v1",
            feature_identity_firewall_fingerprint_sha256="a" * 64,
            minimum_unseen_mint_validation_rows=0,
            minimum_unseen_mint_validation_mints=1,
            minimum_unseen_mint_test_rows=1,
            minimum_unseen_mint_test_mints=1,
        )
```

Also test:
- duplicate fold names/overlapping evaluation windows are rejected by reusing exact `FastChronologicalFold` rules;
- novelty summary unseen+seen row counts reconcile to the future population;
- actor seen+unseen+null counts reconcile;
- identity tuples are canonical/unique;
- SHA-256 fields reject malformed values;
- run/fold result count reconciliation rejects contradictions.

- [ ] **Step 2: Run RED tests**

Run:

```bash
python -m pytest python/tests/test_fast_chronological_v2_models.py -q
```

Expected: collection/import failure because `shreks_brain.fast_validation_v2` does not exist.

- [ ] **Step 3: Implement minimal V2 models**

In `models.py`, define the policy shape exactly:

```python
@dataclass(frozen=True, slots=True)
class FastChronologicalGeneralizationPolicy:
    version: str
    folds: tuple[FastChronologicalFold, ...]
    feature_identity_firewall_version: str
    feature_identity_firewall_fingerprint_sha256: str
    minimum_unseen_mint_validation_rows: int
    minimum_unseen_mint_validation_mints: int
    minimum_unseen_mint_test_rows: int
    minimum_unseen_mint_test_mints: int
```

Define signature quarantine with only transaction overlap authority:

```python
@dataclass(frozen=True, slots=True)
class FastSignatureQuarantineSummary:
    shared_signature_count: int
    training_quarantined_row_count: int
    validation_quarantined_row_count: int
    test_quarantined_row_count: int
    quarantine_fingerprint_sha256: str
```

Define novelty summary without raw actor addresses:

```python
@dataclass(frozen=True, slots=True)
class FastFutureNoveltySummary:
    partition: str
    prediction_count: int
    unique_mint_count: int
    unseen_mint_identities: tuple[tuple[object, ...], ...]
    seen_mint_identities: tuple[tuple[object, ...], ...]
    unseen_mint_unique_mint_count: int
    seen_actor_row_count: int
    unseen_actor_row_count: int
    null_actor_row_count: int
    novelty_fingerprint_sha256: str
```

Use exact prediction identity ordering:

```python
def _identity_sort_key(identity: tuple[object, ...]) -> tuple[object, ...]:
    return (identity[6], identity[2], identity[0], identity[1])
```

The fold result must carry natural validation/TEST predictions plus novelty summaries:

```python
@dataclass(frozen=True, slots=True)
class FastChronologicalGeneralizationFoldResult:
    fold: FastChronologicalFold
    training_raw_row_count: int
    training_row_count: int
    training_target_unavailable_at_split_count: int
    validation_raw_row_count: int
    validation_row_count: int
    test_raw_row_count: int
    test_row_count: int
    signature_quarantine: FastSignatureQuarantineSummary
    validation_novelty: FastFutureNoveltySummary
    test_novelty: FastFutureNoveltySummary
    model: FastForecastBaselineArtifact
    validation_predictions: tuple[FastForecastPrediction, ...]
    test_predictions: tuple[FastForecastPrediction, ...]
```

Make `__init__.py` export only the explicit V2 API. Do not import or mutate V1 package globals.

- [ ] **Step 4: Run model tests GREEN**

Run:

```bash
python -m pytest python/tests/test_fast_chronological_v2_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Prove V1 model contracts remain unchanged**

Run:

```bash
python -m pytest   python/tests/test_fast_chronological_models.py   python/tests/test_fast_chronological_authority.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add   python/src/shreks_brain/fast_validation_v2/__init__.py   python/src/shreks_brain/fast_validation_v2/models.py   python/tests/test_fast_chronological_v2_models.py
git commit -m "feat(fl8.3): define validation v2 contracts"
```

---

### Task 2: Add the exact identity-blind feature firewall

**Files:**
- Create: `python/src/shreks_brain/fast_validation_v2/firewall.py`
- Create: `python/tests/test_fast_chronological_v2_firewall.py`

**Interfaces:**
- Consumes: `FAST_FORECAST_FEATURE_NAMES` from `shreks_brain.fast_learning.features`.
- Produces:
  - `FAST_FORECAST_IDENTITY_FIREWALL_VERSION = "fl8.3-feature-identity-firewall-v1"`
  - `fast_forecast_identity_firewall_fingerprint_sha256(feature_names: tuple[str, ...]) -> str`
  - `validate_fast_forecast_identity_firewall(*, feature_names: tuple[str, ...], expected_version: str, expected_fingerprint_sha256: str) -> None`

- [ ] **Step 1: Write RED firewall tests**

Create tests proving the sealed feature tuple passes and any schema drift fails:

```python
import pytest

from shreks_brain.fast_learning.features import FAST_FORECAST_FEATURE_NAMES
from shreks_brain.fast_validation_v2.firewall import (
    FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
    fast_forecast_identity_firewall_fingerprint_sha256,
    validate_fast_forecast_identity_firewall,
)


def test_sealed_fl8_2_feature_schema_passes_identity_firewall() -> None:
    fingerprint = fast_forecast_identity_firewall_fingerprint_sha256(
        FAST_FORECAST_FEATURE_NAMES
    )
    validate_fast_forecast_identity_firewall(
        feature_names=FAST_FORECAST_FEATURE_NAMES,
        expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
        expected_fingerprint_sha256=fingerprint,
    )


@pytest.mark.parametrize(
    "forbidden",
    (
        "decision.mint",
        "decision.quote_mint",
        "decision.actor",
        "decision.signature",
        "decision.sequence",
        "decision.ordinal",
        "decision.provider",
        "lifecycle.signature",
        "market.pool_address",
        "identity.mint_sha256",
    ),
)
def test_raw_or_derived_identity_feature_fails_closed(forbidden: str) -> None:
    changed = FAST_FORECAST_FEATURE_NAMES + (forbidden,)
    fingerprint = fast_forecast_identity_firewall_fingerprint_sha256(changed)

    with pytest.raises(ValueError, match="identity|feature|firewall"):
        validate_fast_forecast_identity_firewall(
            feature_names=changed,
            expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
            expected_fingerprint_sha256=fingerprint,
        )
```

Also test:
- `decision.actor_present` remains allowed;
- current aggregate actor fields such as `w100.unique_buy_actors` remain allowed;
- wrong expected version fails;
- wrong expected fingerprint fails;
- any non-exact change to `FAST_FORECAST_FEATURE_NAMES` fails until explicitly reviewed.

- [ ] **Step 2: Run RED firewall tests**

```bash
python -m pytest python/tests/test_fast_chronological_v2_firewall.py -q
```

Expected: FAIL because firewall module does not exist.

- [ ] **Step 3: Implement firewall**

Canonical fingerprint material:

```python
payload = {
    "version": FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
    "approved_feature_names": list(FAST_FORECAST_FEATURE_NAMES),
    "forbidden_identity_classes": [
        "mint",
        "quote_mint",
        "pair_or_pool_address",
        "decision_actor_address",
        "transaction_signature",
        "decision_ordinal",
        "decision_sequence_identity",
        "provider_identity",
        "derived_identity_encoding",
    ],
}
```

The validator must require `feature_names == FAST_FORECAST_FEATURE_NAMES` exactly. This exact equality is the hard gate; forbidden-name checks provide a useful error if a future schema attempts obvious identity fields.

Allow the existing actor-derived aggregates because they are population statistics, not raw actor identity:

```python
_ALLOWED_ACTOR_FEATURES = frozenset(
    name
    for name in FAST_FORECAST_FEATURE_NAMES
    if (
        name == "decision.actor_present"
        or name.endswith(".unique_buy_actors")
        or name.endswith(".unique_sell_actors")
    )
)
```

Do not add aliases or automatic migration for future feature schemas.

- [ ] **Step 4: Run firewall tests GREEN**

```bash
python -m pytest python/tests/test_fast_chronological_v2_firewall.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add   python/src/shreks_brain/fast_validation_v2/firewall.py   python/tests/test_fast_chronological_v2_firewall.py
git commit -m "feat(fl8.3): enforce v2 feature identity firewall"
```

---

### Task 3: Build target-free V2 population preparation

**Files:**
- Create: `python/src/shreks_brain/fast_validation_v2/population.py`
- Create: `python/tests/fast_chronological_v2_fixtures.py`
- Create: `python/tests/test_fast_chronological_v2_population.py`

**Interfaces:**
- Consumes: tuple of exact `FastTrainingFeatureRecord`; `FastChronologicalGeneralizationPolicy`.
- Produces:
  - internal `_PreparedGeneralizationFoldPopulation`
  - `prepare_fast_chronological_generalization_populations(records, policy)`
  - no targets, labels, trainer, model, evaluator, network, DB, or clock access.

- [ ] **Step 1: Create V2 fixtures with recurring entities and isolated signatures**

Use `dataclasses.replace` over the existing `chronological_bundle()` records so feature fingerprints can be rebuilt in engine tests later. Provide fixture helpers with:
- one mint recurring train -> validation -> TEST;
- one actor recurring across all partitions;
- a separate mint first appearing in validation;
- a separate mint first appearing in TEST;
- one optional cross-partition signature;
- no equal timestamp straddling.

The fixture API must include:

```python
def v2_records(
    *,
    shared_signature: bool = False,
    giant_entity_component: bool = False,
) -> tuple[FastTrainingFeatureRecord, ...]:
    ...
```

- [ ] **Step 2: Write RED population tests**

Required tests:

```python
def test_repeated_mint_and_actor_are_retained_in_natural_future_populations():
    prepared = prepare_fast_chronological_generalization_populations(
        v2_records(),
        v2_policy(),
    )[0]

    assert prepared.validation
    assert prepared.test
    assert any(
        row.mint in {r.mint for r in prepared.training_raw}
        for row in prepared.validation
    )
    assert any(
        row.decision_actor in {
            r.decision_actor
            for r in prepared.training_raw
            if r.decision_actor is not None
        }
        for row in prepared.test
        if row.decision_actor is not None
    )


def test_shared_transaction_signature_is_quarantined_from_every_affected_partition():
    prepared = prepare_fast_chronological_generalization_populations(
        v2_records(shared_signature=True),
        v2_policy(),
    )[0]

    assert prepared.signature_quarantine.shared_signature_count == 1
    signatures = {
        row.decision_signature
        for row in (*prepared.training, *prepared.validation, *prepared.test)
    }
    assert "shared-signature" not in signatures


def test_unseen_mint_is_defined_against_raw_training_only():
    prepared = prepare_fast_chronological_generalization_populations(
        v2_records(),
        v2_policy(),
    )[0]
    assert prepared.validation_novelty.unseen_mint_identities
    assert prepared.test_novelty.unseen_mint_identities
```

Also test:
- a mint first seen in validation and repeated in TEST remains unseen relative to raw training in both;
- seen+unseen mint identity tuples exactly partition each future population;
- seen/unseen/null actor counts reconcile without exposing actor addresses;
- novelty floor shortfall fails before any target/model code is reachable;
- equal V1 fold boundaries remain unchanged;
- two fold input orders produce canonical identical prepared results.

- [ ] **Step 3: Run RED population tests**

```bash
python -m pytest python/tests/test_fast_chronological_v2_population.py -q
```

Expected: FAIL because population module does not exist.

- [ ] **Step 4: Implement chronological selection and signature-only quarantine**

Raw partition selection must stay exactly half-open:

```python
training_raw = tuple(
    record for record in records
    if fold.training_started_at_unix_ms
    <= record.decision_observed_at_unix_ms
    < fold.training_ended_at_unix_ms
)
validation_raw = tuple(
    record for record in records
    if fold.validation_started_at_unix_ms
    <= record.decision_observed_at_unix_ms
    < fold.validation_ended_at_unix_ms
)
test_raw = tuple(
    record for record in records
    if fold.test_started_at_unix_ms
    <= record.decision_observed_at_unix_ms
    < fold.test_ended_at_unix_ms
)
```

Signature membership is the only cross-partition deletion rule:

```python
shared_signatures = _shared_values(
    {
        "training": training_raw,
        "validation": validation_raw,
        "test": test_raw,
    },
    lambda record: record.decision_signature,
)

training = tuple(
    record for record in training_raw
    if record.decision_signature not in shared_signatures
)
validation = tuple(
    record for record in validation_raw
    if record.decision_signature not in shared_signatures
)
test = tuple(
    record for record in test_raw
    if record.decision_signature not in shared_signatures
)
```

Never compute shared mint/actor sets for quarantine.

Novelty is computed against `training_raw`:

```python
training_mints = {record.mint for record in training_raw}
training_actors = {
    record.decision_actor
    for record in training_raw
    if record.decision_actor is not None
}
```

Future mint classification:

```python
unseen = tuple(
    record.decision_identity
    for record in future_rows
    if record.mint not in training_mints
)
seen = tuple(
    record.decision_identity
    for record in future_rows
    if record.mint in training_mints
)
```

Enforce novelty floors after signature quarantine and before the engine can inspect target values.

- [ ] **Step 5: Run population tests GREEN**

```bash
python -m pytest python/tests/test_fast_chronological_v2_population.py -q
```

Expected: PASS.

- [ ] **Step 6: Prove giant mint↔actor connectivity no longer empties evaluation**

Add a production-shaped synthetic fixture with most rows sharing actors across multiple mints and across all three chronological partitions.

Assert:

```python
prepared = prepare_fast_chronological_generalization_populations(
    v2_records(giant_entity_component=True),
    v2_policy(),
)[0]

assert prepared.training
assert prepared.validation
assert prepared.test
assert prepared.signature_quarantine.shared_signature_count == 0
```

This is the regression test corresponding to the production finding that 80,329/80,330 rows belong to one mint-actor component.

- [ ] **Step 7: Commit Task 3**

```bash
git add   python/src/shreks_brain/fast_validation_v2/population.py   python/tests/fast_chronological_v2_fixtures.py   python/tests/test_fast_chronological_v2_population.py
git commit -m "feat(fl8.3): prepare v2 chronological populations"
```

---

### Task 4: Run sealed FL8.2 training/inference through V2 populations

**Files:**
- Create: `python/src/shreks_brain/fast_validation_v2/engine.py`
- Create: `python/tests/test_fast_chronological_v2_engine.py`

**Interfaces:**
- Consumes:
  - `FastTrainingBundle`
  - `FastForecastTrainingRequest`
  - `FastChronologicalGeneralizationPolicy`
  - target-free population preparation from Task 3
  - sealed `train_fast_forecast_baseline_for_decision_identities`
  - sealed `predict_fast_forecast`
- Produces:
  - `run_fast_chronological_generalization(bundle, request, policy) -> FastChronologicalGeneralizationRun`

- [ ] **Step 1: Write RED engine tests**

Create tests for:
- clean V2 run trains only target-mature training rows and predicts all natural validation/TEST rows;
- recurring mint and actor remain in validation/TEST predictions;
- shared signature is absent from all post-quarantine partitions;
- validation/TEST target-value mutations cannot change split, novelty membership, fitted parameters, or predictions;
- horizon maturity still removes immature training rows;
- incomplete/null selected training target is excluded, never zero-filled;
- unseen-mint prediction identities exactly match the corresponding subset of natural predictions;
- all four existing FL8.2 model families run through V2;
- fold order is deterministic.

Core assertion pattern:

```python
run = run_fast_chronological_generalization(
    v2_bundle(),
    forecast_request(),
    v2_policy(),
)
result = run.fold_results[0]

assert result.validation_predictions
assert result.test_predictions
assert (
    tuple(
        p.decision_identity
        for p in result.test_predictions
        if p.decision_identity in set(
            result.test_novelty.unseen_mint_identities
        )
    )
    == result.test_novelty.unseen_mint_identities
)
```

- [ ] **Step 2: Run RED engine tests**

```bash
python -m pytest python/tests/test_fast_chronological_v2_engine.py -q
```

Expected: FAIL because engine module/function does not exist.

- [ ] **Step 3: Implement exact bundle validation locally in V2**

Do not import V1 private helpers. Repeat the narrow authenticated checks needed by V2:

```python
manifest = bundle.manifest
if manifest.bundle_fingerprint_sha256 != bundle_logical_fingerprint_sha256(manifest):
    raise ValueError("FL8.1 training bundle manifest fingerprint is invalid")

actual_feature_fingerprint = feature_logical_fingerprint_sha256(
    bundle.features.records
)
if (
    bundle.features.logical_fingerprint_sha256 != actual_feature_fingerprint
    or manifest.feature_logical_fingerprint_sha256 != actual_feature_fingerprint
):
    raise ValueError("FL8.1 feature component fingerprint is invalid")
```

Apply the same exact future-label component authentication and feature↔label identity equality as V1.

Call the Task 2 firewall before population preparation:

```python
validate_fast_forecast_identity_firewall(
    feature_names=FAST_FORECAST_FEATURE_NAMES,
    expected_version=policy.feature_identity_firewall_version,
    expected_fingerprint_sha256=(
        policy.feature_identity_firewall_fingerprint_sha256
    ),
)
```

- [ ] **Step 4: Preserve training maturity exactly**

For each prepared fold, only target-mature post-signature-quarantine training identities may fit:

```python
mature_identities: list[tuple[object, ...]] = []

for record in prepared.training:
    label = labels_by_horizon_identity[record.decision_identity]
    if (
        record.decision_observed_at_unix_ms + request.horizon_ms
        > prepared.fold.validation_started_at_unix_ms
    ):
        maturity_unavailable += 1
        continue
    mature_identities.append(record.decision_identity)
```

Pass those identities to the sealed trainer. The trainer remains responsible for completeness/null target exclusion.

- [ ] **Step 5: Predict the full natural future populations**

Do not filter by novelty before inference:

```python
validation_predictions = tuple(
    predict_fast_forecast(model, record)
    for record in prepared.validation
)
test_predictions = tuple(
    predict_fast_forecast(model, record)
    for record in prepared.test
)
```

Novelty summaries only reference identities from these exact predictions.

- [ ] **Step 6: Fingerprint V2 runs**

Canonical run material must include at least:

```python
{
    "schema_name": FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME,
    "schema_version": FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION,
    "validation_policy_version": policy.version,
    "training_bundle_fingerprint_sha256": (
        bundle.manifest.bundle_fingerprint_sha256
    ),
    "feature_identity_firewall_version": (
        policy.feature_identity_firewall_version
    ),
    "feature_identity_firewall_fingerprint_sha256": (
        policy.feature_identity_firewall_fingerprint_sha256
    ),
    "folds": [
        {
            "boundaries": ...,
            "counts": ...,
            "signature_quarantine_fingerprint_sha256": ...,
            "validation_novelty_fingerprint_sha256": ...,
            "test_novelty_fingerprint_sha256": ...,
            "artifact_fingerprint_sha256": ...,
            "validation_predictions": ...,
            "test_predictions": ...,
        }
    ],
}
```

Use sorted-key compact JSON and exact float canonicalization consistent with V1.

- [ ] **Step 7: Run engine tests GREEN**

```bash
python -m pytest python/tests/test_fast_chronological_v2_engine.py -q
```

Expected: PASS.

- [ ] **Step 8: Run V1 + V2 chronological regression suite**

```bash
python -m pytest   python/tests/test_fast_chronological_models.py   python/tests/test_fast_chronological_engine.py   python/tests/test_fast_chronological_integration.py   python/tests/test_fast_chronological_v2_models.py   python/tests/test_fast_chronological_v2_firewall.py   python/tests/test_fast_chronological_v2_population.py   python/tests/test_fast_chronological_v2_engine.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

```bash
git add   python/src/shreks_brain/fast_validation_v2/engine.py   python/tests/test_fast_chronological_v2_engine.py
git commit -m "feat(fl8.3): run chronological generalization v2"
```

---

### Task 5: Seal V2 authority boundaries and V1 compatibility

**Files:**
- Create: `python/tests/test_fast_chronological_v2_authority.py`
- Modify only if needed to correct V2 package exports: `python/src/shreks_brain/fast_validation_v2/__init__.py`

**Interfaces:**
- Consumes: completed V2 package.
- Produces: explicit public API and no-authority proof.

- [ ] **Step 1: Write exact public API test**

The V2 root API should be exact and small:

```python
EXPECTED_PUBLIC_API = (
    "FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION",
    "FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME",
    "FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION",
    "FastChronologicalGeneralizationPolicy",
    "FastFutureNoveltySummary",
    "FastSignatureQuarantineSummary",
    "FastChronologicalGeneralizationFoldResult",
    "FastChronologicalGeneralizationRun",
    "run_fast_chronological_generalization",
)
```

Assert:

```python
import shreks_brain.fast_validation as v1
import shreks_brain.fast_validation_v2 as v2

assert v2.__all__ == EXPECTED_PUBLIC_API
assert v1.__all__ == (
    "FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME",
    "FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION",
    "FastChronologicalFold",
    "FastChronologicalValidationPolicy",
    "FastLeakageQuarantineSummary",
    "FastChronologicalFoldResult",
    "FastChronologicalValidationRun",
    "run_fast_chronological_validation",
)
```

- [ ] **Step 2: Add no-heavy-dependency/no-authority source test**

Inspect `models`, `firewall`, `population`, and `engine` source and reject:

```python
for forbidden in (
    "requests.",
    "httpx",
    "import sqlite3",
    "import pyarrow",
    "import random",
    "from random",
    "TradeIntent",
    "RuntimeMode.LIVE",
    "RuntimeMode::Live",
    "sign_transaction",
    "submit_transaction",
    "send_transaction",
    "promote_champion",
    "shreks_brain.promotion",
    "shreks_brain.registry",
    "profit_factor",
    "roc_auc",
    "accuracy_score",
):
    assert forbidden not in source
```

Also use a subprocess import test to prove importing `shreks_brain.fast_validation_v2` does not eagerly import sklearn.

- [ ] **Step 3: Run authority tests**

```bash
python -m pytest   python/tests/test_fast_chronological_authority.py   python/tests/test_fast_chronological_v2_authority.py -q
```

Expected: PASS.

- [ ] **Step 4: Run all Python tests**

```bash
python -m pytest python/tests -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add   python/src/shreks_brain/fast_validation_v2/__init__.py   python/tests/test_fast_chronological_v2_authority.py
git commit -m "test(fl8.3): seal validation v2 authority"
```

---

### Task 6: Candidate verification, scope audit, and evidence handoff

**Files:**
- No new production code unless verification exposes a defect.
- Update the approved design only if implementation discovers a factual contradiction; do not rewrite requirements to make tests pass.

**Interfaces:**
- Consumes: Tasks 1–5 exact-clean candidate branch.
- Produces: verified candidate evidence suitable for PR review and later physical/input-only acceptance.

- [ ] **Step 1: Run focused V2 suite from a clean environment**

```bash
python -m pytest   python/tests/test_fast_chronological_v2_models.py   python/tests/test_fast_chronological_v2_firewall.py   python/tests/test_fast_chronological_v2_population.py   python/tests/test_fast_chronological_v2_engine.py   python/tests/test_fast_chronological_v2_authority.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full repository CI-equivalent Python gate**

```bash
python -m pytest python/tests -q
```

Expected: PASS.

- [ ] **Step 3: Run repository-safety equivalent**

```bash
set -euo pipefail
pattern='(PRIVATE_''KEY|SEED_''PHRASE|SECRET_''KEY)='
if git grep -n -E "$pattern" -- ':!docs/**' ':!.env.example' ':!.github/workflows/ci.yml'; then
  echo "Potential secret assignment found in committed source."
  exit 1
fi
echo "No forbidden secret assignments found."
```

Expected: no forbidden secret assignments.

- [ ] **Step 4: Run Rust workspace regression gate**

```bash
cargo test --workspace
```

Expected: PASS.

- [ ] **Step 5: Audit candidate diff**

Run:

```bash
git diff --stat main...HEAD
git diff --name-only main...HEAD
```

Expected implementation scope:
- approved V2 design/plan docs;
- new `fast_validation_v2` package;
- new V2 fixtures/tests;
- no collector/runtime/tradable-universe/risk/PAPER/LIVE changes;
- no modifications to V1 `fast_validation` source.

- [ ] **Step 6: Push candidate and require four GitHub gates**

Required PR checks:
- Repository safety — SUCCESS
- Rust tests — SUCCESS
- Python tests — SUCCESS
- ARM64 release build — SUCCESS

Do not merge on partial green.

- [ ] **Step 7: Merge with expected head SHA and verify merged-main CI**

Use guarded squash/merge with the exact reviewed head SHA. After merge, require the merged-main CI workflow to complete SUCCESS across the same four gates.

- [ ] **Step 8: Do not deploy or train merely because code merged**

V2 core merge authorizes only the next evidence step:

```text
next_action=RUN_INPUT_ONLY_V2_IMMUTABLE_ACCEPTANCE_PREFLIGHT
target_values_inspected=no
future_returns_inspected=no
model_performance_inspected=no
champion_training_performed=no
eligible_identity_fingerprint_created=no
cohort_floor_accepted=NO
LIVE_TRADING=DISABLED
```

If a later preflight requires executing this Python code on the VPS, build/deploy the exact sealed release first and verify physical release identity before trusting host output.

- [ ] **Step 9: Final Task 6 commit only if verification required doc-only corrections**

If no correction is needed, do not create an empty commit. If a factual evidence note is required, commit only that focused note with:

```bash
git add docs/superpowers/specs/2026-09-08-fl8-3-validation-v2-design.md
git commit -m "docs: align FL8.3 v2 design with verified implementation"
```

---

## Slice-2 Handoff: First-Champion V2 Integration

Do **not** implement this in the current slice.

After the V2 core is sealed and the immutable input-only V2 acceptance preflight succeeds, write a separate implementation plan for:

- a versioned V2 first-champion evidence-plan type/codec;
- explicit frozen production novelty floors;
- natural TEST and unseen-mint TEST target-availability evidence;
- a V2 first-champion builder that evaluates the same predictions on both populations;
- versioned host request/writer/run artifacts that opt into V2 explicitly;
- V1 first-champion request/plan/builder compatibility;
- champion packaging/promotion evidence updates;
- physical host request/run proof;
- no LIVE enablement.

The slice-2 plan must not reuse V1 request schema bytes under changed semantics. It must version the new host/evidence contract explicitly.
