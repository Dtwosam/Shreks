# FL8.3 Chronological Validation Design

## Status

Approved for autonomous implementation under the project instruction to continue the build order without repeated approval prompts.

## Source-of-truth alignment

FL8.3 follows the Fast Lane build order:

- FL8.1 is SEALED and provides the immutable point-in-time training bundle.
- FL8.2 is SEALED at merged-main `1ec24302951dd154ecbcff577f45fa6e9c673aa6` and provides simple forecast baselines plus pure-Python inference.
- `SHREKS_BUILD_ORDER.md` defines FL8.3 as **Chronological validation**: training/validation/test splits must be time-aware and resistant to wallet/token/event leakage.

FL8.3 deliberately stops before FL8.4. It does not compute predictive quality, calibration, trading economics, champion status, promotion, action policy, PAPER execution, signing, transaction submission, or LIVE authority.

## Problem

A timestamp-only split is necessary but insufficient for Fast Lane data.

Three independent leakage classes matter:

1. **future-label leakage** — a training decision may precede validation while its selected future horizon has not elapsed by validation start;
2. **entity leakage** — the same mint or decision actor can appear in training and later evaluation populations, allowing repeated-token or repeated-wallet structure to masquerade as generalization;
3. **event leakage** — different logical decision rows can share the same transaction signature/transaction-level evidence and must not straddle partitions.

FL8.3 must create reproducible training, validation, and test populations that are chronological and exclude cross-partition entity/event reuse before fitting any model.

## Reuse of older E4 validation

The preserved `shreks_brain.validation` E4 package already proves useful chronology principles for legacy D6 rows:

- half-open explicit intervals;
- no random splits;
- training decision-time boundaries;
- target-maturity checks;
- deterministic folds and fingerprints;
- validation predictions without reading validation labels.

FL8.3 reuses those principles, not the E4 data/model types. E4 is bound to D6/E3 logistic models and has no separate test partition or Fast Lane mint/actor/signature quarantine.

## Selected architecture

Add a focused sibling package:

```text
python/src/shreks_brain/fast_validation/
  __init__.py
  models.py
  engine.py
```

Do **not** extend `shreks_brain.fast_learning.__all__`; the sealed FL8.2 root API remains unchanged.

FL8.3 consumes:

- exact `FastTrainingBundle` values from FL8.1;
- exact `FastForecastTrainingRequest` values from FL8.2;
- FL8.2 training/inference implementation.

One narrow trainer-submodule extension is permitted:

```python
train_fast_forecast_baseline_for_decision_identities(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    decision_identities: tuple[tuple[object, ...], ...],
) -> FastForecastBaselineArtifact
```

It is not added to `shreks_brain.fast_learning.__all__`. Existing `train_fast_forecast_baseline(bundle, request)` behavior remains unchanged. The helper reuses the same preprocessing/fitting/fingerprint logic but restricts eligible FL4 rows to an explicit decision-identity set supplied by FL8.3.

## Public schema

```python
FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME = "shreks.fast_lane_chronological_validation"
FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION = 1
```

## Public models

### `FastChronologicalFold`

Immutable slotted dataclass:

- `name: str`
- `training_started_at_unix_ms: int`
- `training_ended_at_unix_ms: int`
- `validation_started_at_unix_ms: int`
- `validation_ended_at_unix_ms: int`
- `test_started_at_unix_ms: int`
- `test_ended_at_unix_ms: int`

Half-open intervals:

```text
training:   [training_start, training_end)
validation: [validation_start, validation_end)
test:       [test_start, test_end)
```

Required ordering:

```text
training_start < training_end <= validation_start < validation_end <= test_start < test_end
```

Gaps are explicit and allowed. FL8.3 invents no embargo duration.

### `FastChronologicalValidationPolicy`

Immutable slotted dataclass:

- `version: str`
- `folds: tuple[FastChronologicalFold, ...]`

Rules:

- non-empty version;
- at least one fold;
- unique fold names;
- input order is not semantic;
- validation/test evaluation intervals from different folds may not overlap any other validation/test interval.

Training windows may overlap to support expanding or rolling walk-forward designs.

### `FastLeakageQuarantineSummary`

Immutable slotted dataclass containing only counts/fingerprints, not raw wallet identities:

- `shared_mint_count`
- `shared_actor_count`
- `shared_signature_count`
- `training_quarantined_row_count`
- `validation_quarantined_row_count`
- `test_quarantined_row_count`
- `quarantine_fingerprint_sha256`

The fingerprint covers canonical shared group keys and quarantined decision identities. Raw actor/mint/signature lists are deliberately not copied into the public result surface.

### `FastChronologicalFoldResult`

Immutable slotted dataclass:

- `fold`
- raw and post-quarantine row counts for training/validation/test;
- `training_target_unavailable_at_split_count`;
- `quarantine`;
- `model: FastForecastBaselineArtifact`;
- `validation_predictions: tuple[FastForecastPrediction, ...]`;
- `test_predictions: tuple[FastForecastPrediction, ...]`.

Reconciliation rules require:

- the model training row count equals mature target-eligible post-quarantine training rows;
- validation/test prediction counts equal post-quarantine validation/test row counts;
- prediction target/horizon/model version match the fold artifact;
- prediction identities are unique and canonically ordered;
- validation/test prediction decision timestamps lie inside their respective intervals.

### `FastChronologicalValidationRun`

Immutable slotted dataclass:

- `schema_name`
- `schema_version`
- `validation_policy_version`
- `training_request`
- `training_bundle_fingerprint_sha256`
- `fold_results`
- `validation_run_fingerprint_sha256`

The fingerprint is provenance, not a performance score.

## Input and identity contract

`run_fast_chronological_validation` accepts one exact FL8.1 bundle, one exact FL8.2 training request, and one exact policy.

The bundle already proves exact feature↔FL4 decision identity equality. FL8.3 additionally validates that feature decision identities remain unique.

Canonical decision identity remains FL8.1's tuple:

```text
(signature, ordinal, sequence, mint, quote_mint, venue, observed_at_unix_ms)
```

Rows are processed canonically by:

```text
(decision_observed_at_unix_ms, decision_sequence, decision_signature, decision_ordinal)
```

## Raw chronological populations

For each fold, a feature record enters exactly one raw population by decision timestamp:

```text
training_start <= decision_time < training_end
validation_start <= decision_time < validation_end
test_start <= decision_time < test_end
```

Rows in explicit gaps are unused for that fold.

A fold with an empty raw training, validation, or test population fails closed.

## Cross-partition leakage quarantine

After raw populations are selected, FL8.3 computes group membership across training, validation, and test.

Mandatory V1 group keys:

- token: `record.mint`;
- wallet/actor: non-null `record.decision_actor`;
- event/transaction: `record.decision_signature`.

A group key is **shared** when it appears in more than one partition. Every row carrying any shared key is quarantined from that fold, regardless of which partition it belongs to.

This is intentionally conservative. FL8.3 does not silently keep the training copy, keep the first copy, randomize a group assignment, or allow validation/test reuse.

After quarantine:

- no mint may exist in more than one partition;
- no non-null decision actor may exist in more than one partition;
- no decision signature may exist in more than one partition.

A post-quarantine empty training, validation, or test population fails closed.

## Training target maturity

FL8.1 FL4 labels do not carry a separate derived-label creation timestamp. Therefore FL8.3 can prove **historical reconstructability**, not that a label file happened to have been materialized at that historical instant.

A post-quarantine training decision is eligible for the selected target only when:

- an exact FL4 row exists for `request.horizon_ms`;
- `completeness == "complete"`;
- the requested target field is non-null and type-compatible;
- `decision_observed_at_unix_ms + request.horizon_ms <= validation_started_at_unix_ms`.

The final rule prevents a training row from using a future horizon that had not yet elapsed by validation start. FL4 completeness already proves contiguous canonical coverage through the horizon boundary.

Rows that fail maturity/target availability are excluded from fitting and counted in `training_target_unavailable_at_split_count`.

The selected mature decision identities are passed to `train_fast_forecast_baseline_for_decision_identities`.

If the selected model family cannot train after quarantine/maturity filtering, the fold fails closed. No fallback model or wider window is substituted.

## Validation and test prediction firewall

FL8.3 does not inspect validation or test target values before prediction.

For each post-quarantine validation/test feature row, FL8.3 calls sealed FL8.2 pure-Python inference using the **same training-only model artifact**.

This matters for FL8.4:

- validation predictions can later fit/check calibration;
- test predictions remain an independent holdout for calibration/quality assessment;
- FL8.3 itself performs neither operation.

Validation/test label completeness or values cannot change partition membership, leakage quarantine, mature training selection, fitted feature transforms, fitted coefficients/intercept/constant, or validation/test predictions. Sealed FL8.2 training-data/artifact fingerprints include the exact whole-source bundle fingerprint, and the FL8.3 run fingerprint also retains that source provenance. Therefore changing any source label may change those provenance fingerprints even when the selected training evidence and predictions are unchanged; that is intentional audit sensitivity, not model leakage.

## Determinism

FL8.3 has no randomness.

Equivalent bundle contents and policy definitions produce identical results regardless of fold input order because:

- FL8.1 feature rows are canonical;
- folds are canonically sorted;
- group keys and quarantined identities are canonically sorted before hashing;
- FL8.2 fitting is deterministic under its sealed policies;
- inference is pure;
- fingerprints canonicalize finite floats exactly.

## Error handling

FL8.3 fails closed for:

- malformed policy/fold boundaries;
- overlapping evaluation intervals;
- duplicate feature identity;
- empty raw partition;
- empty post-quarantine partition;
- cross-partition mint/actor/signature surviving quarantine;
- requested horizon absent from FL4;
- malformed selected target type;
- insufficient mature training rows;
- one-class logistic training after quarantine;
- FL8.2 fit/inference contradiction;
- non-finite predictions;
- result/fingerprint reconciliation failure.

No error path randomizes a split, widens an interval, moves a row to a different partition, disables a leakage group, or reuses another fold's model.

## Metric firewall

FL8.3 result models contain no fields for:

- accuracy/AUC;
- calibration error;
- RMSE/MAE evaluation score;
- expectancy/PnL/profit factor;
- drawdown/win rate/turnover;
- regime/strategy/liquidity bucket quality;
- champion/promotion state.

FL8.3 answers only:

**Which rows formed leakage-resistant chronological train/validation/test populations, what training-only model was fit, and what did it predict on the unseen validation/test populations?**

FL8.4 owns forecast calibration and quality measurement.

## Dependency and authority boundary

FL8.3 adds no dependency. `shreks_brain.fast_validation` must not eagerly import sklearn.

Production FL8.3 code must not import or use:

- provider/network clients;
- sqlite3/PyArrow/file I/O;
- wall-clock time or randomness;
- strategy/action policy code;
- PAPER execution;
- signer/transaction submission;
- registry/promotion/champion code;
- LIVE mode.

LIVE remains disabled.

## Public API

`shreks_brain.fast_validation.__all__` exposes exactly:

```text
FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME
FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION
FastChronologicalFold
FastChronologicalValidationPolicy
FastLeakageQuarantineSummary
FastChronologicalFoldResult
FastChronologicalValidationRun
run_fast_chronological_validation
```

The FL8.2 trainer submodule helper is intentionally not re-exported from `shreks_brain.fast_learning`.

## TDD requirements

Required independent RED/GREEN proof includes:

1. exact train/validation/test half-open boundaries;
2. fold ordering and non-overlapping evaluation intervals;
3. training horizon maturity at validation start;
4. incomplete/null selected targets excluded, never zero-filled;
5. same mint across partitions quarantines every affected row;
6. same non-null decision actor across partitions quarantines every affected row;
7. same decision signature across partitions quarantines every affected row;
8. post-quarantine group disjointness;
9. validation/test future-label mutations cannot change membership, fitted parameters, or predictions, while exact source-derived training-data/artifact/run provenance fingerprints remain sensitive to the changed source evidence;
10. deterministic result under fold reordering;
11. all four FL8.2 model families work through the chronological adapter;
12. pure-Python validation/test inference and no eager sklearn import;
13. no metric/promotion/execution/LIVE authority;
14. real FL8.1 on-disk bundle integration;
15. existing FL8.2 full-bundle training behavior remains unchanged after the decision-identity trainer extension.

## Seal procedure

FL8.3 follows the established gate:

1. intentional RED contracts;
2. implementation GREEN;
3. candidate four-gate CI GREEN;
4. exact scope audit;
5. clean history `design -> plan -> consolidated RED -> implementation`;
6. fresh exact-clean-head four-gate GREEN;
7. guarded merge with expected head SHA;
8. fresh merged-main four-gate GREEN;
9. only then mark FL8.3 SEALED.

No predictive-edge or profitability claim is allowed from FL8.3 alone.
