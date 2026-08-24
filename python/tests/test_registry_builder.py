from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.evaluation import (
    CalibrationBucket,
    CalibrationReport,
    SegmentPerformance,
    TradingEvaluationReport,
    TradingPerformanceMetrics,
)
from shreks_brain.learning import (
    ClassWeightMode,
    FeatureTransform,
    LogisticRegressionTrainingPolicy,
    ModelFamily,
    ModelTrainingRequest,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)
from shreks_brain.registry import RegistryStatus, build_registry_candidate
from shreks_brain.validation import (
    ChronologicalValidationFold,
    TimeAwareValidationRun,
    ValidationFoldResult,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def training_request(*, features: tuple[str, ...] = ("feature_a", "feature_b")) -> ModelTrainingRequest:
    return ModelTrainingRequest(
        model_version="model-v1",
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=features,
        target=ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=20.0),
        training_policy=LogisticRegressionTrainingPolicy(
            version="lr-policy-v1",
            regularization_c=1.0,
            max_iterations=100,
            tolerance=1e-6,
            class_weight_mode=ClassWeightMode.NONE,
        ),
    )


def model(*, version: str = "model-v1") -> TrainedLogisticRegressionModel:
    return TrainedLogisticRegressionModel(
        schema_version="e3-training-v1",
        model_version=version,
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="lr-policy-v1",
        research_dataset_schema_version="d6-research-v1",
        target=ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=20.0),
        feature_transforms=(
            FeatureTransform("feature_a", 0.0, 0.0, 1.0),
            FeatureTransform("feature_b", 0.0, 0.0, 1.0),
        ),
        coefficients=(0.5, -0.25),
        intercept=0.1,
        training_row_count=4,
        positive_row_count=2,
        negative_row_count=2,
        target_unavailable_row_count=1,
        min_training_as_of_unix_ms=10,
        max_training_as_of_unix_ms=90,
        training_fingerprint_sha256=SHA_A,
    )


def validation(*, request: ModelTrainingRequest | None = None) -> TimeAwareValidationRun:
    artifact = model()
    fold = ChronologicalValidationFold(
        name="fold-1",
        training_started_at_unix_ms=0,
        training_ended_at_unix_ms=100,
        validation_started_at_unix_ms=200,
        validation_ended_at_unix_ms=300,
    )
    return TimeAwareValidationRun(
        schema_version="e4-time-validation-v1",
        validation_policy_version="walk-forward-v1",
        model_training_request=request or training_request(),
        fold_results=(
            ValidationFoldResult(
                fold=fold,
                training_window_row_count=5,
                training_mature_target_row_count=4,
                training_target_unavailable_at_split_count=1,
                validation_row_count=0,
                model=artifact,
                predictions=(),
            ),
        ),
        validation_run_fingerprint_sha256=SHA_B,
    )


def metrics() -> TradingPerformanceMetrics:
    return TradingPerformanceMetrics(
        trade_count=2,
        win_count=1,
        loss_count=1,
        flat_count=0,
        gross_pnl_usd=30.0,
        net_pnl_usd=20.0,
        net_expectancy_usd=10.0,
        net_expectancy_pct=2.0,
        profit_factor=3.0,
        maximum_drawdown_usd=5.0,
        maximum_drawdown_pct=5.0,
        average_winner_usd=30.0,
        average_loser_usd=-10.0,
        win_rate=0.5,
        turnover_usd=1_000.0,
        turnover_to_starting_equity=10.0,
        execution_friction_usd=6.0,
        explicit_cost_usd=4.0,
        total_cost_usd=10.0,
        cost_burden_pct=1.0,
    )


def calibration() -> CalibrationReport:
    return CalibrationReport(
        observation_count=2,
        positive_count=1,
        brier_score=0.04,
        expected_calibration_error=0.2,
        buckets=(
            CalibrationBucket(0, 0.0, 0.5, 1, 0.2, 0.0, 0.2),
            CalibrationBucket(1, 0.5, 1.0, 1, 0.8, 1.0, 0.2),
        ),
    )


def report(*, candidate_version: str = "candidate-v1", fingerprint: str = SHA_C) -> TradingEvaluationReport:
    overall = metrics()
    segment = SegmentPerformance("all", overall)
    return TradingEvaluationReport(
        schema_version="e5-trading-evaluation-v1",
        policy_version="eval-v1",
        candidate_version=candidate_version,
        metrics=overall,
        calibration=calibration(),
        setup_performance=(segment,),
        regime_performance=(segment,),
        evaluation_fingerprint_sha256=fingerprint,
    )


def build(**changes: object):
    kwargs = dict(
        candidate_version="candidate-v1",
        strategy_version="strategy-v1",
        feature_schema_version="d6-research-v1",
        feature_columns=("feature_a", "feature_b"),
        evaluation_report=report(),
        registered_at_unix_ms=400,
        trained_model=model(),
        validation_run=validation(),
    )
    kwargs.update(changes)
    return build_registry_candidate(**kwargs)


def test_model_backed_candidate_preserves_sealed_provenance_and_headline_evaluation() -> None:
    candidate = build()

    assert candidate.initial_status is RegistryStatus.CHALLENGER
    assert candidate.model_version == "model-v1"
    assert candidate.model_training_schema_version == "e3-training-v1"
    assert candidate.model_training_fingerprint_sha256 == SHA_A
    assert candidate.training_started_at_unix_ms == 10
    assert candidate.training_ended_at_unix_ms == 90
    assert candidate.validation_schema_version == "e4-time-validation-v1"
    assert candidate.validation_policy_version == "walk-forward-v1"
    assert candidate.validation_run_fingerprint_sha256 == SHA_B
    assert candidate.evaluation.evaluation_fingerprint_sha256 == SHA_C
    assert candidate.evaluation.trade_count == 2
    assert candidate.evaluation.net_expectancy_usd == 10.0
    assert candidate.evaluation.profit_factor == 3.0
    assert candidate.evaluation.maximum_drawdown_pct == 5.0
    assert candidate.evaluation.total_cost_usd == 10.0
    assert candidate.evaluation.brier_score == 0.04
    assert candidate.evaluation.expected_calibration_error == 0.2


def test_strategy_only_registration_is_explicit_and_has_no_fake_ml_provenance() -> None:
    candidate = build(trained_model=None, validation_run=None)

    assert candidate.model_version is None
    assert candidate.model_training_fingerprint_sha256 is None
    assert candidate.training_started_at_unix_ms is None
    assert candidate.training_ended_at_unix_ms is None
    assert candidate.validation_run_fingerprint_sha256 is None


def test_partial_ml_provenance_fails_closed() -> None:
    with pytest.raises(ValueError, match="together"):
        build(trained_model=model(), validation_run=None)
    with pytest.raises(ValueError, match="together"):
        build(trained_model=None, validation_run=validation())


def test_model_and_validation_identity_must_align() -> None:
    with pytest.raises(ValueError, match="model version"):
        build(trained_model=model(version="different-model"))


def test_feature_columns_must_align_with_model_and_validation_request() -> None:
    with pytest.raises(ValueError, match="feature columns"):
        build(feature_columns=("feature_b", "feature_a"))

    mismatched_request = training_request(features=("feature_a",))
    bad_validation = validation(request=mismatched_request)
    with pytest.raises(ValueError, match="feature columns"):
        build(validation_run=bad_validation)


def test_evaluation_candidate_version_must_match_registry_candidate_version() -> None:
    with pytest.raises(ValueError, match="candidate version"):
        build(evaluation_report=report(candidate_version="other"))


def test_candidate_fingerprint_is_deterministic_and_materially_sensitive() -> None:
    first = build()
    second = build()
    changed = build(evaluation_report=report(fingerprint="d" * 64))

    assert first == second
    assert first.candidate_fingerprint_sha256 == second.candidate_fingerprint_sha256
    assert first.candidate_fingerprint_sha256 != changed.candidate_fingerprint_sha256
