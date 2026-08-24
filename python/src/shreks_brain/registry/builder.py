from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from shreks_brain.evaluation.models import TradingEvaluationReport
from shreks_brain.learning.models import TrainedLogisticRegressionModel
from shreks_brain.validation.models import TimeAwareValidationRun

from .models import (
    CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
    RegistryCandidate,
    RegistryEvaluationEvidence,
    RegistryStatus,
)


def build_registry_candidate(
    *,
    candidate_version: str,
    strategy_version: str,
    feature_schema_version: str,
    feature_columns: tuple[str, ...],
    evaluation_report: TradingEvaluationReport,
    registered_at_unix_ms: int,
    trained_model: TrainedLogisticRegressionModel | None,
    validation_run: TimeAwareValidationRun | None,
) -> RegistryCandidate:
    if type(evaluation_report) is not TradingEvaluationReport:
        raise ValueError("evaluation_report must be an exact TradingEvaluationReport")
    if evaluation_report.candidate_version != candidate_version:
        raise ValueError("evaluation candidate version must match registry candidate version")

    if (trained_model is None) != (validation_run is None):
        raise ValueError("trained_model and validation_run must be supplied together")

    model_version: str | None = None
    model_training_schema_version: str | None = None
    model_training_fingerprint_sha256: str | None = None
    training_started_at_unix_ms: int | None = None
    training_ended_at_unix_ms: int | None = None
    validation_schema_version: str | None = None
    validation_policy_version: str | None = None
    validation_run_fingerprint_sha256: str | None = None

    if trained_model is not None and validation_run is not None:
        if type(trained_model) is not TrainedLogisticRegressionModel:
            raise ValueError("trained_model must be an exact TrainedLogisticRegressionModel")
        if type(validation_run) is not TimeAwareValidationRun:
            raise ValueError("validation_run must be an exact TimeAwareValidationRun")
        request = validation_run.model_training_request
        if trained_model.model_version != request.model_version:
            raise ValueError("registered model version must match validation model version")
        if trained_model.model_family is not request.model_family:
            raise ValueError("registered model family must match validation model family")
        if trained_model.target != request.target:
            raise ValueError("registered model target must match validation target")
        if trained_model.training_policy_version != request.training_policy.version:
            raise ValueError(
                "registered model training policy must match validation training policy"
            )

        model_features = tuple(
            transform.feature_name for transform in trained_model.feature_transforms
        )
        if model_features != feature_columns:
            raise ValueError("registered feature columns must match trained model feature columns")
        if request.feature_columns != feature_columns:
            raise ValueError("registered feature columns must match validation feature columns")
        for fold_result in validation_run.fold_results:
            fold_model = fold_result.model
            fold_features = tuple(
                transform.feature_name for transform in fold_model.feature_transforms
            )
            if fold_model.model_version != trained_model.model_version:
                raise ValueError("validation fold model version must match registered model version")
            if fold_features != feature_columns:
                raise ValueError("validation fold feature columns must match registered feature columns")

        model_version = trained_model.model_version
        model_training_schema_version = trained_model.schema_version
        model_training_fingerprint_sha256 = trained_model.training_fingerprint_sha256
        training_started_at_unix_ms = trained_model.min_training_as_of_unix_ms
        training_ended_at_unix_ms = trained_model.max_training_as_of_unix_ms
        validation_schema_version = validation_run.schema_version
        validation_policy_version = validation_run.validation_policy_version
        validation_run_fingerprint_sha256 = (
            validation_run.validation_run_fingerprint_sha256
        )

    evaluation = _evaluation_evidence(evaluation_report)
    material = {
        "schema_version": CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        "candidate_version": candidate_version,
        "strategy_version": strategy_version,
        "model_version": model_version,
        "model_training_schema_version": model_training_schema_version,
        "model_training_fingerprint_sha256": model_training_fingerprint_sha256,
        "feature_schema_version": feature_schema_version,
        "feature_columns": list(feature_columns),
        "training_started_at_unix_ms": training_started_at_unix_ms,
        "training_ended_at_unix_ms": training_ended_at_unix_ms,
        "validation_schema_version": validation_schema_version,
        "validation_policy_version": validation_policy_version,
        "validation_run_fingerprint_sha256": validation_run_fingerprint_sha256,
        "evaluation": asdict(evaluation),
        "registered_at_unix_ms": registered_at_unix_ms,
        "initial_status": RegistryStatus.CHALLENGER.value,
    }
    fingerprint = _sha256(material)
    return RegistryCandidate(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidate_version=candidate_version,
        strategy_version=strategy_version,
        model_version=model_version,
        model_training_schema_version=model_training_schema_version,
        model_training_fingerprint_sha256=model_training_fingerprint_sha256,
        feature_schema_version=feature_schema_version,
        feature_columns=feature_columns,
        training_started_at_unix_ms=training_started_at_unix_ms,
        training_ended_at_unix_ms=training_ended_at_unix_ms,
        validation_schema_version=validation_schema_version,
        validation_policy_version=validation_policy_version,
        validation_run_fingerprint_sha256=validation_run_fingerprint_sha256,
        evaluation=evaluation,
        registered_at_unix_ms=registered_at_unix_ms,
        initial_status=RegistryStatus.CHALLENGER,
        candidate_fingerprint_sha256=fingerprint,
    )


def _evaluation_evidence(report: TradingEvaluationReport) -> RegistryEvaluationEvidence:
    calibration = report.calibration
    return RegistryEvaluationEvidence(
        schema_version=report.schema_version,
        policy_version=report.policy_version,
        evaluation_fingerprint_sha256=report.evaluation_fingerprint_sha256,
        trade_count=report.metrics.trade_count,
        net_pnl_usd=report.metrics.net_pnl_usd,
        net_expectancy_usd=report.metrics.net_expectancy_usd,
        net_expectancy_pct=report.metrics.net_expectancy_pct,
        profit_factor=report.metrics.profit_factor,
        maximum_drawdown_usd=report.metrics.maximum_drawdown_usd,
        maximum_drawdown_pct=report.metrics.maximum_drawdown_pct,
        win_rate=report.metrics.win_rate,
        turnover_usd=report.metrics.turnover_usd,
        total_cost_usd=report.metrics.total_cost_usd,
        brier_score=None if calibration is None else calibration.brier_score,
        expected_calibration_error=(
            None if calibration is None else calibration.expected_calibration_error
        ),
    )


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
