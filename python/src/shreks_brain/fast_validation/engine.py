from __future__ import annotations

import hashlib
import json

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

from .models import (
    FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME,
    FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION,
    FastChronologicalFold,
    FastChronologicalFoldResult,
    FastChronologicalValidationPolicy,
    FastChronologicalValidationRun,
    FastLeakageQuarantineSummary,
)


def run_fast_chronological_validation(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    policy: FastChronologicalValidationPolicy,
) -> FastChronologicalValidationRun:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be an exact FastTrainingBundle")
    if type(request) is not FastForecastTrainingRequest:
        raise ValueError("request must be an exact FastForecastTrainingRequest")
    if type(policy) is not FastChronologicalValidationPolicy:
        raise ValueError("policy must be an exact FastChronologicalValidationPolicy")

    records, labels_by_horizon_identity = _validate_bundle(bundle, request)
    ordered_folds = tuple(sorted(policy.folds, key=_fold_sort_key))
    fold_results: list[FastChronologicalFoldResult] = []
    for fold in ordered_folds:
        try:
            fold_results.append(
                _run_fold(
                    bundle,
                    request,
                    fold,
                    records,
                    labels_by_horizon_identity,
                )
            )
        except (ValueError, RuntimeError) as exc:
            raise type(exc)(f"fold {fold.name!r}: {exc}") from exc

    canonical_results = tuple(fold_results)
    fingerprint = _run_fingerprint(
        bundle=bundle,
        request=request,
        policy=policy,
        fold_results=canonical_results,
    )
    return FastChronologicalValidationRun(
        schema_name=FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME,
        schema_version=FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION,
        validation_policy_version=policy.version,
        training_request=request,
        training_bundle_fingerprint_sha256=bundle.manifest.bundle_fingerprint_sha256,
        fold_results=canonical_results,
        validation_run_fingerprint_sha256=fingerprint,
    )


def _validate_bundle(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
) -> tuple[
    tuple[FastTrainingFeatureRecord, ...],
    dict[tuple[object, ...], FuturePathTrainingLabel],
]:
    manifest = bundle.manifest
    if manifest.bundle_fingerprint_sha256 != bundle_logical_fingerprint_sha256(manifest):
        raise ValueError("FL8.1 training bundle manifest fingerprint is invalid")

    records = bundle.features.records
    if not records:
        raise ValueError("FL8.1 feature component cannot be empty")
    actual_feature_fingerprint = feature_logical_fingerprint_sha256(records)
    if (
        bundle.features.logical_fingerprint_sha256 != actual_feature_fingerprint
        or manifest.feature_logical_fingerprint_sha256 != actual_feature_fingerprint
    ):
        raise ValueError("FL8.1 feature component fingerprint is invalid")
    if manifest.decision_count != len(records):
        raise ValueError("FL8.1 feature decision count contradicts manifest")

    labels = bundle.future_path_labels.labels
    if not labels:
        raise ValueError("FL8.1 future-path component cannot be empty")
    actual_future_fingerprint = future_path_logical_fingerprint_sha256(labels)
    if (
        bundle.future_path_labels.logical_fingerprint_sha256 != actual_future_fingerprint
        or manifest.future_path_logical_fingerprint_sha256 != actual_future_fingerprint
    ):
        raise ValueError("FL8.1 future-path component fingerprint is invalid")
    if bundle.future_path_labels.label_version != manifest.future_path_label_version:
        raise ValueError("FL8.1 future-path label version contradicts manifest")
    if manifest.future_path_label_row_count != len(labels):
        raise ValueError("FL8.1 future-path row count contradicts manifest")

    feature_identities = tuple(record.decision_identity for record in records)
    if len(set(feature_identities)) != len(feature_identities):
        raise ValueError("FL8.1 feature component contains duplicate decision identities")
    label_identities = {label.decision_identity for label in labels}
    if set(feature_identities) != label_identities:
        raise ValueError("FL8.1 feature and future-path decision identities do not match exactly")

    by_horizon: dict[tuple[object, ...], FuturePathTrainingLabel] = {}
    for label in labels:
        if label.horizon_ms != request.horizon_ms:
            continue
        identity = label.decision_identity
        if identity in by_horizon:
            raise ValueError("requested FL4 horizon contains duplicate decision identities")
        by_horizon[identity] = label
    if not by_horizon:
        raise ValueError("requested forecast horizon has no FL4 rows")

    return tuple(sorted(records, key=_record_sort_key)), by_horizon


def _run_fold(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    fold: FastChronologicalFold,
    records: tuple[FastTrainingFeatureRecord, ...],
    labels_by_horizon_identity: dict[tuple[object, ...], FuturePathTrainingLabel],
) -> FastChronologicalFoldResult:
    training_raw = tuple(
        record
        for record in records
        if fold.training_started_at_unix_ms
        <= record.decision_observed_at_unix_ms
        < fold.training_ended_at_unix_ms
    )
    validation_raw = tuple(
        record
        for record in records
        if fold.validation_started_at_unix_ms
        <= record.decision_observed_at_unix_ms
        < fold.validation_ended_at_unix_ms
    )
    test_raw = tuple(
        record
        for record in records
        if fold.test_started_at_unix_ms
        <= record.decision_observed_at_unix_ms
        < fold.test_ended_at_unix_ms
    )
    for role, population in (
        ("training", training_raw),
        ("validation", validation_raw),
        ("test", test_raw),
    ):
        if not population:
            raise ValueError(f"raw {role} interval contains no decision rows")

    training, validation, test, quarantine = _quarantine_shared_groups(
        training_raw,
        validation_raw,
        test_raw,
    )
    for role, population in (
        ("training", training),
        ("validation", validation),
        ("test", test),
    ):
        if not population:
            raise ValueError(f"post-quarantine {role} population is empty")
    _assert_group_disjointness(training, validation, test)

    mature_identities: list[tuple[object, ...]] = []
    maturity_unavailable = 0
    for record in training:
        label = labels_by_horizon_identity.get(record.decision_identity)
        if label is None:
            raise ValueError("training decision has no FL4 row at requested horizon")
        if (
            record.decision_observed_at_unix_ms + request.horizon_ms
            > fold.validation_started_at_unix_ms
        ):
            maturity_unavailable += 1
            continue
        mature_identities.append(record.decision_identity)
    if not mature_identities:
        raise ValueError("no training decision has a mature requested horizon at validation start")

    model = train_fast_forecast_baseline_for_decision_identities(
        bundle,
        request,
        tuple(mature_identities),
    )
    unavailable = maturity_unavailable + model.target_unavailable_row_count

    validation_predictions = tuple(
        predict_fast_forecast(model, record) for record in validation
    )
    test_predictions = tuple(predict_fast_forecast(model, record) for record in test)

    return FastChronologicalFoldResult(
        fold=fold,
        training_raw_row_count=len(training_raw),
        training_row_count=len(training),
        training_target_unavailable_at_split_count=unavailable,
        validation_raw_row_count=len(validation_raw),
        validation_row_count=len(validation),
        test_raw_row_count=len(test_raw),
        test_row_count=len(test),
        quarantine=quarantine,
        model=model,
        validation_predictions=validation_predictions,
        test_predictions=test_predictions,
    )


def _quarantine_shared_groups(
    training: tuple[FastTrainingFeatureRecord, ...],
    validation: tuple[FastTrainingFeatureRecord, ...],
    test: tuple[FastTrainingFeatureRecord, ...],
) -> tuple[
    tuple[FastTrainingFeatureRecord, ...],
    tuple[FastTrainingFeatureRecord, ...],
    tuple[FastTrainingFeatureRecord, ...],
    FastLeakageQuarantineSummary,
]:
    partitions = {
        "training": training,
        "validation": validation,
        "test": test,
    }
    shared_mints = _shared_values(partitions, lambda record: record.mint)
    shared_actors = _shared_values(
        partitions,
        lambda record: record.decision_actor,
        ignore_none=True,
    )
    shared_signatures = _shared_values(
        partitions,
        lambda record: record.decision_signature,
    )

    def quarantined(record: FastTrainingFeatureRecord) -> bool:
        return (
            record.mint in shared_mints
            or (
                record.decision_actor is not None
                and record.decision_actor in shared_actors
            )
            or record.decision_signature in shared_signatures
        )

    training_quarantined = tuple(record for record in training if quarantined(record))
    validation_quarantined = tuple(record for record in validation if quarantined(record))
    test_quarantined = tuple(record for record in test if quarantined(record))

    filtered_training = tuple(record for record in training if not quarantined(record))
    filtered_validation = tuple(record for record in validation if not quarantined(record))
    filtered_test = tuple(record for record in test if not quarantined(record))

    payload = {
        "shared_mints": sorted(shared_mints),
        "shared_actors": sorted(shared_actors),
        "shared_signatures": sorted(shared_signatures),
        "quarantined": {
            "training": [list(record.decision_identity) for record in training_quarantined],
            "validation": [list(record.decision_identity) for record in validation_quarantined],
            "test": [list(record.decision_identity) for record in test_quarantined],
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    summary = FastLeakageQuarantineSummary(
        shared_mint_count=len(shared_mints),
        shared_actor_count=len(shared_actors),
        shared_signature_count=len(shared_signatures),
        training_quarantined_row_count=len(training_quarantined),
        validation_quarantined_row_count=len(validation_quarantined),
        test_quarantined_row_count=len(test_quarantined),
        quarantine_fingerprint_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    return filtered_training, filtered_validation, filtered_test, summary


def _shared_values(
    partitions: dict[str, tuple[FastTrainingFeatureRecord, ...]],
    value_for,
    *,
    ignore_none: bool = False,
) -> set[str]:
    memberships: dict[str, set[str]] = {}
    for partition_name, records in partitions.items():
        for record in records:
            value = value_for(record)
            if value is None and ignore_none:
                continue
            if not isinstance(value, str) or not value:
                raise ValueError("leakage grouping value must be a non-empty string or None")
            memberships.setdefault(value, set()).add(partition_name)
    return {value for value, names in memberships.items() if len(names) > 1}


def _assert_group_disjointness(
    training: tuple[FastTrainingFeatureRecord, ...],
    validation: tuple[FastTrainingFeatureRecord, ...],
    test: tuple[FastTrainingFeatureRecord, ...],
) -> None:
    populations = (training, validation, test)
    for value_for, ignore_none, role in (
        (lambda record: record.mint, False, "mint"),
        (lambda record: record.decision_actor, True, "actor"),
        (lambda record: record.decision_signature, False, "signature"),
    ):
        sets: list[set[str]] = []
        for population in populations:
            values: set[str] = set()
            for record in population:
                value = value_for(record)
                if value is None and ignore_none:
                    continue
                if not isinstance(value, str) or not value:
                    raise ValueError(f"post-quarantine {role} grouping value is invalid")
                values.add(value)
            sets.append(values)
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ValueError(f"post-quarantine {role} groups are not disjoint")


def _run_fingerprint(
    *,
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    policy: FastChronologicalValidationPolicy,
    fold_results: tuple[FastChronologicalFoldResult, ...],
) -> str:
    training_policy = request.training_policy
    payload = {
        "schema_name": FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME,
        "schema_version": FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION,
        "validation_policy_version": policy.version,
        "training_bundle_fingerprint_sha256": bundle.manifest.bundle_fingerprint_sha256,
        "training_request": {
            "model_version": request.model_version,
            "model_family": request.model_family.value,
            "target": request.target.value,
            "horizon_ms": request.horizon_ms,
            "training_policy": {
                "version": training_policy.version,
                "ridge_alpha": _canonical_scalar(training_policy.ridge_alpha),
                "logistic_regularization_c": _canonical_scalar(
                    training_policy.logistic_regularization_c
                ),
                "logistic_max_iterations": training_policy.logistic_max_iterations,
                "logistic_tolerance": _canonical_scalar(
                    training_policy.logistic_tolerance
                ),
                "logistic_balanced_class_weight": training_policy.logistic_balanced_class_weight,
            },
        },
        "folds": [
            {
                "fold": {
                    "name": result.fold.name,
                    "training_started_at_unix_ms": result.fold.training_started_at_unix_ms,
                    "training_ended_at_unix_ms": result.fold.training_ended_at_unix_ms,
                    "validation_started_at_unix_ms": result.fold.validation_started_at_unix_ms,
                    "validation_ended_at_unix_ms": result.fold.validation_ended_at_unix_ms,
                    "test_started_at_unix_ms": result.fold.test_started_at_unix_ms,
                    "test_ended_at_unix_ms": result.fold.test_ended_at_unix_ms,
                },
                "counts": {
                    "training_raw": result.training_raw_row_count,
                    "training_post_quarantine": result.training_row_count,
                    "training_target_unavailable": result.training_target_unavailable_at_split_count,
                    "validation_raw": result.validation_raw_row_count,
                    "validation_post_quarantine": result.validation_row_count,
                    "test_raw": result.test_raw_row_count,
                    "test_post_quarantine": result.test_row_count,
                },
                "quarantine_fingerprint_sha256": result.quarantine.quarantine_fingerprint_sha256,
                "artifact_fingerprint_sha256": result.model.artifact_fingerprint_sha256,
                "validation_predictions": [
                    _prediction_payload(value) for value in result.validation_predictions
                ],
                "test_predictions": [
                    _prediction_payload(value) for value in result.test_predictions
                ],
            }
            for result in fold_results
        ],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prediction_payload(prediction) -> dict[str, object]:
    return {
        "model_version": prediction.model_version,
        "target": prediction.target.value,
        "horizon_ms": prediction.horizon_ms,
        "decision_identity": list(prediction.decision_identity),
        "predicted_value": _canonical_scalar(prediction.predicted_value),
    }


def _canonical_scalar(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return {"float_hex": value.hex()}
    raise TypeError(f"unsupported chronological fingerprint scalar: {type(value).__name__}")


def _record_sort_key(record: FastTrainingFeatureRecord) -> tuple[object, ...]:
    return (
        record.decision_observed_at_unix_ms,
        record.decision_sequence,
        record.decision_signature,
        record.decision_ordinal,
    )


def _fold_sort_key(fold: FastChronologicalFold) -> tuple[int, int, int, int, str]:
    return (
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
        fold.name,
    )
