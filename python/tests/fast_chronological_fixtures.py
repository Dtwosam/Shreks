from __future__ import annotations

from dataclasses import replace

from fast_forecast_fixtures import WSOL, feature_record, future_label
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.research.counterfactual_parquet import (
    COUNTERFACTUAL_DATASET_SCHEMA_NAME,
    COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
    CounterfactualDatasetManifest,
)
from shreks_brain.research.counterfactuals import COUNTERFACTUAL_ACTION_LABEL_VERSION
from shreks_brain.research.fast_training_bundle import (
    FAST_TRAINING_BUNDLE_SCHEMA_NAME,
    FAST_TRAINING_BUNDLE_SCHEMA_VERSION,
    FastTrainingBundle,
    FastTrainingBundleManifest,
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
    FastTrainingFeatureDataset,
    feature_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
    FuturePathTrainingLabelDataset,
    future_path_logical_fingerprint_sha256,
)

TRAINING_START = 1_000
TRAINING_END = 1_600
VALIDATION_START = 2_000
VALIDATION_END = 2_300
TEST_START = 3_000
TEST_END = 3_300
HORIZON_MS = 250

_TIMES = (
    1_000,
    1_100,
    1_200,
    1_300,
    1_400,
    1_500,
    2_000,
    2_100,
    2_200,
    3_000,
    3_100,
    3_200,
)


def forecast_request(
    family: FastForecastModelFamily = FastForecastModelFamily.RIDGE_REGRESSION,
    target: FastForecastTarget = FastForecastTarget.ENDPOINT_RETURN_BPS,
) -> FastForecastTrainingRequest:
    if family is FastForecastModelFamily.RIDGE_REGRESSION:
        policy = FastForecastTrainingPolicy(version="ridge-v1", ridge_alpha=1.0)
    elif family is FastForecastModelFamily.LOGISTIC_REGRESSION:
        policy = FastForecastTrainingPolicy(
            version="logit-v1",
            logistic_regularization_c=1.0,
            logistic_max_iterations=2_000,
            logistic_tolerance=1e-10,
            logistic_balanced_class_weight=False,
        )
    else:
        policy = FastForecastTrainingPolicy(version="naive-v1")
    return FastForecastTrainingRequest(
        model_version=f"fl8-3-{family.value.lower()}-{target.value}",
        model_family=family,
        target=target,
        horizon_ms=HORIZON_MS,
        training_policy=policy,
    )


def chronological_bundle(
    *,
    shared_mint: bool = False,
    shared_actor: bool = False,
    shared_signature: bool = False,
    validation_target_shift: float = 0.0,
    test_target_shift: float = 0.0,
    incomplete_training_index: int | None = None,
) -> FastTrainingBundle:
    records = []
    for index, observed in enumerate(_TIMES):
        record = feature_record(
            index,
            float(index),
            signature=f"decision-fl8-3-{index}",
            observed_at_unix_ms=observed,
            actor=f"wallet-fl8-3-{index}",
        )
        record = replace(record, mint=f"mint-fl8-3-{index}")
        records.append(record)

    if shared_mint:
        records[6] = replace(records[6], mint=records[0].mint)
    if shared_actor:
        records[9] = replace(records[9], decision_actor=records[1].decision_actor)
    if shared_signature:
        records[7] = replace(
            records[7],
            decision_signature=records[2].decision_signature,
            decision_ordinal=1,
        )

    record_tuple = tuple(records)
    features = FastTrainingFeatureDataset(
        records=record_tuple,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(record_tuple),
        source_sha256="3" * 64,
    )

    labels = []
    for index, record in enumerate(record_tuple):
        shift = 0.0
        if VALIDATION_START <= record.decision_observed_at_unix_ms < VALIDATION_END:
            shift = validation_target_shift
        elif TEST_START <= record.decision_observed_at_unix_ms < TEST_END:
            shift = test_target_shift
        completeness = "incomplete" if incomplete_training_index == index else "complete"
        labels.append(
            future_label(
                record,
                HORIZON_MS,
                endpoint_return_bps=-100.0 + index * 25.0 + shift,
                reversal_occurred=index % 2 == 1,
                completeness=completeness,
            )
        )
    label_tuple = tuple(labels)
    future_path = FuturePathTrainingLabelDataset(
        labels=label_tuple,
        logical_fingerprint_sha256=future_path_logical_fingerprint_sha256(label_tuple),
        label_version=1,
    )

    counterfactual_manifest = CounterfactualDatasetManifest(
        schema_name=COUNTERFACTUAL_DATASET_SCHEMA_NAME,
        schema_version=COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        row_count=1,
        min_action_observed_at_unix_ms=record_tuple[0].decision_observed_at_unix_ms,
        max_action_observed_at_unix_ms=record_tuple[0].decision_observed_at_unix_ms,
        dataset_fingerprint_sha256="4" * 64,
    )
    provisional = FastTrainingBundleManifest(
        schema_name=FAST_TRAINING_BUNDLE_SCHEMA_NAME,
        schema_version=FAST_TRAINING_BUNDLE_SCHEMA_VERSION,
        feature_schema_name=FAST_TRAINING_FEATURE_SCHEMA_NAME,
        feature_schema_version=FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        future_path_schema_name=FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
        future_path_schema_version=FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
        future_path_label_version=1,
        counterfactual_schema_name=COUNTERFACTUAL_DATASET_SCHEMA_NAME,
        counterfactual_schema_version=COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
        counterfactual_label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        decision_count=len(record_tuple),
        future_path_label_row_count=len(label_tuple),
        counterfactual_row_count=1,
        min_decision_observed_at_unix_ms=min(
            value.decision_observed_at_unix_ms for value in record_tuple
        ),
        max_decision_observed_at_unix_ms=max(
            value.decision_observed_at_unix_ms for value in record_tuple
        ),
        feature_logical_fingerprint_sha256=features.logical_fingerprint_sha256,
        feature_source_jsonl_sha256=features.source_sha256,
        future_path_logical_fingerprint_sha256=future_path.logical_fingerprint_sha256,
        counterfactual_logical_fingerprint_sha256=counterfactual_manifest.dataset_fingerprint_sha256,
        bundle_fingerprint_sha256="0" * 64,
    )
    manifest = replace(
        provisional,
        bundle_fingerprint_sha256=bundle_logical_fingerprint_sha256(provisional),
    )
    return FastTrainingBundle(
        manifest=manifest,
        features=features,
        future_path_labels=future_path,
        counterfactual_rows=({"placeholder": True, "quote_mint": WSOL},),
        counterfactual_manifest=counterfactual_manifest,
    )
