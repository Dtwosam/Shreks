from __future__ import annotations

import hashlib
import json
import math

from shreks_brain.fast_learning.features import FAST_FORECAST_FEATURE_NAMES
from shreks_brain.fast_learning.inference import predict_fast_forecast
from shreks_brain.fast_learning.models import FastForecastTrainingRequest
from shreks_brain.fast_learning.trainer import (
    train_fast_forecast_baseline_for_decision_identities,
)
from shreks_brain.research.fast_training_bundle import (
    FastTrainingBundle,
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    feature_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    FuturePathTrainingLabel,
    future_path_logical_fingerprint_sha256,
)

from .firewall import validate_fast_forecast_identity_firewall
from .models import (
    FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME,
    FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION,
    FastChronologicalGeneralizationFoldResult,
    FastChronologicalGeneralizationPolicy,
    FastChronologicalGeneralizationRun,
)
from .population import (
    prepare_fast_chronological_generalization_populations,
)


def run_fast_chronological_generalization(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    policy: FastChronologicalGeneralizationPolicy,
) -> FastChronologicalGeneralizationRun:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be an exact FastTrainingBundle")
    if type(request) is not FastForecastTrainingRequest:
        raise ValueError(
            "request must be an exact FastForecastTrainingRequest"
        )
    if type(policy) is not FastChronologicalGeneralizationPolicy:
        raise ValueError(
            "policy must be an exact FastChronologicalGeneralizationPolicy"
        )

    records, labels_by_horizon_identity = _validate_bundle(
        bundle,
        request,
    )
    validate_fast_forecast_identity_firewall(
        feature_names=FAST_FORECAST_FEATURE_NAMES,
        expected_version=policy.feature_identity_firewall_version,
        expected_fingerprint_sha256=(
            policy.feature_identity_firewall_fingerprint_sha256
        ),
    )
    prepared_folds = (
        prepare_fast_chronological_generalization_populations(
            records,
            policy,
        )
    )

    results: list[FastChronologicalGeneralizationFoldResult] = []
    for prepared in prepared_folds:
        try:
            mature_identities: list[tuple[object, ...]] = []
            maturity_unavailable = 0
            for record in prepared.training:
                label = labels_by_horizon_identity.get(
                    record.decision_identity
                )
                if (
                    label is None
                    or (
                        record.decision_observed_at_unix_ms
                        + request.horizon_ms
                        > prepared.fold.validation_started_at_unix_ms
                    )
                ):
                    maturity_unavailable += 1
                    continue
                mature_identities.append(record.decision_identity)

            if not mature_identities:
                raise ValueError(
                    "no target-mature training decisions remain"
                )

            model = (
                train_fast_forecast_baseline_for_decision_identities(
                    bundle,
                    request,
                    tuple(mature_identities),
                )
            )
            total_unavailable = (
                maturity_unavailable
                + model.target_unavailable_row_count
            )
            if (
                model.training_row_count + total_unavailable
                != len(prepared.training)
            ):
                raise ValueError(
                    "training target availability counts do not reconcile"
                )

            validation_predictions = tuple(
                predict_fast_forecast(model, record)
                for record in prepared.validation
            )
            test_predictions = tuple(
                predict_fast_forecast(model, record)
                for record in prepared.test
            )

            results.append(
                FastChronologicalGeneralizationFoldResult(
                    fold=prepared.fold,
                    training_raw_row_count=len(
                        prepared.training_raw
                    ),
                    training_row_count=len(prepared.training),
                    training_target_unavailable_at_split_count=(
                        total_unavailable
                    ),
                    validation_raw_row_count=len(
                        prepared.validation_raw
                    ),
                    validation_row_count=len(prepared.validation),
                    test_raw_row_count=len(prepared.test_raw),
                    test_row_count=len(prepared.test),
                    signature_quarantine=(
                        prepared.signature_quarantine
                    ),
                    validation_novelty=prepared.validation_novelty,
                    test_novelty=prepared.test_novelty,
                    model=model,
                    validation_predictions=validation_predictions,
                    test_predictions=test_predictions,
                )
            )
        except (ValueError, RuntimeError) as exc:
            raise type(exc)(
                f"fold {prepared.fold.name!r}: {exc}"
            ) from exc

    canonical_results = tuple(results)
    material = _run_material(
        bundle=bundle,
        request=request,
        policy=policy,
        fold_results=canonical_results,
    )
    return FastChronologicalGeneralizationRun(
        schema_name=FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME,
        schema_version=(
            FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION
        ),
        validation_policy_version=policy.version,
        training_request=request,
        training_bundle_fingerprint_sha256=(
            bundle.manifest.bundle_fingerprint_sha256
        ),
        feature_identity_firewall_version=(
            policy.feature_identity_firewall_version
        ),
        feature_identity_firewall_fingerprint_sha256=(
            policy.feature_identity_firewall_fingerprint_sha256
        ),
        fold_results=canonical_results,
        validation_run_fingerprint_sha256=(
            _sha256_canonical(material)
        ),
    )


def _validate_bundle(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
) -> tuple[
    tuple[FastTrainingFeatureRecord, ...],
    dict[tuple[object, ...], FuturePathTrainingLabel],
]:
    manifest = bundle.manifest
    if (
        manifest.bundle_fingerprint_sha256
        != bundle_logical_fingerprint_sha256(manifest)
    ):
        raise ValueError(
            "FL8.1 training bundle manifest fingerprint is invalid"
        )

    records = bundle.features.records
    if not records:
        raise ValueError("FL8.1 feature component cannot be empty")
    actual_feature_fingerprint = (
        feature_logical_fingerprint_sha256(records)
    )
    if (
        bundle.features.logical_fingerprint_sha256
        != actual_feature_fingerprint
        or manifest.feature_logical_fingerprint_sha256
        != actual_feature_fingerprint
    ):
        raise ValueError(
            "FL8.1 feature component fingerprint is invalid"
        )
    if manifest.decision_count != len(records):
        raise ValueError(
            "FL8.1 feature decision count contradicts manifest"
        )

    labels = bundle.future_path_labels.labels
    if not labels:
        raise ValueError(
            "FL8.1 future-path component cannot be empty"
        )
    actual_future_fingerprint = (
        future_path_logical_fingerprint_sha256(labels)
    )
    if (
        bundle.future_path_labels.logical_fingerprint_sha256
        != actual_future_fingerprint
        or manifest.future_path_logical_fingerprint_sha256
        != actual_future_fingerprint
    ):
        raise ValueError(
            "FL8.1 future-path component fingerprint is invalid"
        )
    if (
        bundle.future_path_labels.label_version
        != manifest.future_path_label_version
    ):
        raise ValueError(
            "FL8.1 future-path label version contradicts manifest"
        )
    if manifest.future_path_label_row_count != len(labels):
        raise ValueError(
            "FL8.1 future-path row count contradicts manifest"
        )

    feature_identities = tuple(
        record.decision_identity for record in records
    )
    if len(set(feature_identities)) != len(feature_identities):
        raise ValueError(
            "FL8.1 feature component contains duplicate decision identities"
        )
    label_identities = {
        label.decision_identity for label in labels
    }
    if set(feature_identities) != label_identities:
        raise ValueError(
            "FL8.1 feature and future-path decision identities "
            "do not match exactly"
        )

    by_horizon: dict[
        tuple[object, ...],
        FuturePathTrainingLabel,
    ] = {}
    for label in labels:
        if label.horizon_ms != request.horizon_ms:
            continue
        identity = label.decision_identity
        if identity in by_horizon:
            raise ValueError(
                "requested FL4 horizon contains duplicate decision identities"
            )
        by_horizon[identity] = label
    if not by_horizon:
        raise ValueError(
            "requested forecast horizon has no FL4 rows"
        )

    return (
        tuple(sorted(records, key=_record_sort_key)),
        by_horizon,
    )


def _run_material(
    *,
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    policy: FastChronologicalGeneralizationPolicy,
    fold_results: tuple[
        FastChronologicalGeneralizationFoldResult,
        ...,
    ],
) -> dict[str, object]:
    return {
        "schema_name": (
            FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION
        ),
        "validation_policy_version": policy.version,
        "training_bundle_fingerprint_sha256": (
            bundle.manifest.bundle_fingerprint_sha256
        ),
        "request": {
            "model_version": request.model_version,
            "model_family": request.model_family.value,
            "target": request.target.value,
            "horizon_ms": request.horizon_ms,
            "training_policy_version": (
                request.training_policy.version
            ),
        },
        "feature_identity_firewall_version": (
            policy.feature_identity_firewall_version
        ),
        "feature_identity_firewall_fingerprint_sha256": (
            policy.feature_identity_firewall_fingerprint_sha256
        ),
        "novelty_floors": {
            "minimum_unseen_mint_validation_rows": (
                policy.minimum_unseen_mint_validation_rows
            ),
            "minimum_unseen_mint_validation_mints": (
                policy.minimum_unseen_mint_validation_mints
            ),
            "minimum_unseen_mint_test_rows": (
                policy.minimum_unseen_mint_test_rows
            ),
            "minimum_unseen_mint_test_mints": (
                policy.minimum_unseen_mint_test_mints
            ),
        },
        "folds": [
            {
                "name": result.fold.name,
                "training_started_at_unix_ms": (
                    result.fold.training_started_at_unix_ms
                ),
                "training_ended_at_unix_ms": (
                    result.fold.training_ended_at_unix_ms
                ),
                "validation_started_at_unix_ms": (
                    result.fold.validation_started_at_unix_ms
                ),
                "validation_ended_at_unix_ms": (
                    result.fold.validation_ended_at_unix_ms
                ),
                "test_started_at_unix_ms": (
                    result.fold.test_started_at_unix_ms
                ),
                "test_ended_at_unix_ms": (
                    result.fold.test_ended_at_unix_ms
                ),
                "training_raw_row_count": (
                    result.training_raw_row_count
                ),
                "training_row_count": result.training_row_count,
                "training_target_unavailable_at_split_count": (
                    result.training_target_unavailable_at_split_count
                ),
                "validation_raw_row_count": (
                    result.validation_raw_row_count
                ),
                "validation_row_count": (
                    result.validation_row_count
                ),
                "test_raw_row_count": result.test_raw_row_count,
                "test_row_count": result.test_row_count,
                "signature_quarantine_fingerprint_sha256": (
                    result.signature_quarantine
                    .quarantine_fingerprint_sha256
                ),
                "validation_novelty_fingerprint_sha256": (
                    result.validation_novelty
                    .novelty_fingerprint_sha256
                ),
                "test_novelty_fingerprint_sha256": (
                    result.test_novelty
                    .novelty_fingerprint_sha256
                ),
                "model_artifact_fingerprint_sha256": (
                    result.model.artifact_fingerprint_sha256
                ),
                "validation_predictions": [
                    _prediction_material(value)
                    for value in result.validation_predictions
                ],
                "test_predictions": [
                    _prediction_material(value)
                    for value in result.test_predictions
                ],
            }
            for result in fold_results
        ],
    }


def _prediction_material(value) -> dict[str, object]:
    return {
        "decision_identity": list(value.decision_identity),
        "predicted_value": _canonical_value(
            value.predicted_value
        ),
    }


def _record_sort_key(
    record: FastTrainingFeatureRecord,
) -> tuple[object, ...]:
    return (
        record.decision_observed_at_unix_ms,
        record.decision_sequence,
        record.decision_signature,
        record.decision_ordinal,
    )


def _canonical_value(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "validation fingerprint rejects non-finite floats"
            )
        return {"__float_hex__": value.hex()}
    if isinstance(value, dict):
        return {
            key: _canonical_value(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _sha256_canonical(value: object) -> str:
    encoded = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
