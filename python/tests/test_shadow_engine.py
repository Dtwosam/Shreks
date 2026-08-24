from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.evaluation import TradingEvaluationReport, TradingPerformanceMetrics
from shreks_brain.learning import (
    ClassWeightMode,
    FeatureTransform,
    LogisticRegressionTrainingPolicy,
    ModelFamily,
    ModelTrainingRequest,
    ResearchReturnTarget,
    TrainedLogisticRegressionModel,
)
from shreks_brain.registry import (
    ChampionChallengerRegistry,
    RegistryStatus,
    RegistryStatusEvent,
    build_registry_candidate,
)
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)
from shreks_brain.shadow import (
    ShadowDecisionPolicy,
    ShadowReasonCode,
    evaluate_shadow_challenger,
)
from shreks_brain.validation import (
    ChronologicalValidationFold,
    TimeAwareValidationRun,
    ValidationFoldResult,
)


MODEL_SHA = "a" * 64
VALIDATION_SHA = "b" * 64
EVALUATION_SHA = "c" * 64
REGISTRY_SHA = "d" * 64


def model(
    *,
    version: str = "challenger-model-v1",
    training_fingerprint: str = MODEL_SHA,
    feature_name: str = "market_liquidity_usd",
) -> TrainedLogisticRegressionModel:
    return TrainedLogisticRegressionModel(
        schema_version="e3-training-v1",
        model_version=version,
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        training_policy_version="lr-shadow-v1",
        research_dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        target=ResearchReturnTarget(horizon_seconds=300, minimum_return_pct=5.0),
        feature_transforms=(FeatureTransform(feature_name, 200.0, 200.0, 100.0),),
        coefficients=(2.0,),
        intercept=0.0,
        training_row_count=4,
        positive_row_count=2,
        negative_row_count=2,
        target_unavailable_row_count=1,
        min_training_as_of_unix_ms=1_000,
        max_training_as_of_unix_ms=4_000,
        training_fingerprint_sha256=training_fingerprint,
    )


def validation(artifact: TrainedLogisticRegressionModel) -> TimeAwareValidationRun:
    request = ModelTrainingRequest(
        model_version=artifact.model_version,
        model_family=ModelFamily.LOGISTIC_REGRESSION,
        feature_columns=tuple(value.feature_name for value in artifact.feature_transforms),
        target=artifact.target,
        training_policy=LogisticRegressionTrainingPolicy(
            version="lr-shadow-v1",
            regularization_c=1.0,
            max_iterations=100,
            tolerance=1e-6,
            class_weight_mode=ClassWeightMode.NONE,
        ),
    )
    fold = ChronologicalValidationFold(
        name="fold-1",
        training_started_at_unix_ms=0,
        training_ended_at_unix_ms=4_000,
        validation_started_at_unix_ms=5_000,
        validation_ended_at_unix_ms=6_000,
    )
    return TimeAwareValidationRun(
        schema_version="e4-time-validation-v1",
        validation_policy_version="walk-forward-shadow-v1",
        model_training_request=request,
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
        validation_run_fingerprint_sha256=VALIDATION_SHA,
    )


def evaluation(candidate_version: str = "challenger-v1") -> TradingEvaluationReport:
    metrics = TradingPerformanceMetrics(
        trade_count=0,
        win_count=0,
        loss_count=0,
        flat_count=0,
        gross_pnl_usd=0.0,
        net_pnl_usd=0.0,
        net_expectancy_usd=None,
        net_expectancy_pct=None,
        profit_factor=None,
        maximum_drawdown_usd=0.0,
        maximum_drawdown_pct=0.0,
        average_winner_usd=None,
        average_loser_usd=None,
        win_rate=None,
        turnover_usd=0.0,
        turnover_to_starting_equity=0.0,
        execution_friction_usd=0.0,
        explicit_cost_usd=0.0,
        total_cost_usd=0.0,
        cost_burden_pct=None,
    )
    return TradingEvaluationReport(
        schema_version="e5-trading-evaluation-v1",
        policy_version="eval-shadow-v1",
        candidate_version=candidate_version,
        metrics=metrics,
        calibration=None,
        setup_performance=(),
        regime_performance=(),
        evaluation_fingerprint_sha256=EVALUATION_SHA,
    )


def registered_candidate(
    artifact: TrainedLogisticRegressionModel | None = None,
    *,
    candidate_version: str = "challenger-v1",
    registered_at: int = 4_500,
):
    if artifact is None:
        artifact = model()
    return build_registry_candidate(
        candidate_version=candidate_version,
        strategy_version="shadow-entry-v1",
        feature_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        feature_columns=tuple(value.feature_name for value in artifact.feature_transforms),
        evaluation_report=evaluation(candidate_version),
        registered_at_unix_ms=registered_at,
        trained_model=artifact,
        validation_run=validation(artifact),
    )


def registry_with(candidate, *, champion: bool = False) -> ChampionChallengerRegistry:
    events: tuple[RegistryStatusEvent, ...] = ()
    if champion:
        events = (
            RegistryStatusEvent(
                candidate_version=candidate.candidate_version,
                from_status=RegistryStatus.CHALLENGER,
                to_status=RegistryStatus.CHAMPION,
                decision_reference="e8-test-decision",
                decided_at_unix_ms=candidate.registered_at_unix_ms + 1,
                reason="test promotion state",
                event_fingerprint_sha256="e" * 64,
            ),
        )
    return ChampionChallengerRegistry(
        schema_version="e6-registry-v1",
        candidates=(candidate,),
        status_events=events,
        registry_fingerprint_sha256=REGISTRY_SHA,
    )


def row(
    *,
    liquidity: float = 300.0,
    as_of: int = 5_000,
    safety: str = "PASS",
    setup_state: str = "READY",
    regime: str = "NORMAL",
    baseline: str = "WATCH",
) -> dict[str, object]:
    value = {
        column: None
        for column in RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
    }
    value.update(
        {
            "dataset_schema_version": RESEARCH_DATASET_SCHEMA_VERSION,
            "candidate_mint": "mint-a",
            "as_of_unix_ms": as_of,
            "market_liquidity_usd": liquidity,
            "safety_decision": safety,
            "setup_name": "fresh_launch_continuation",
            "setup_state": setup_state,
            "market_regime": regime,
            "decision_action": baseline,
        }
    )
    return value


def evaluate(**changes):
    artifact = changes.pop("model", model())
    candidate = changes.pop("candidate", registered_candidate(artifact))
    registry = changes.pop("registry", registry_with(candidate))
    input_row = changes.pop("row", row())
    policy = changes.pop("policy", ShadowDecisionPolicy("shadow-policy-v1", 0.8))
    assert not changes
    return evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        input_row,
        policy,
    )


def test_eligible_baseline_watch_can_be_shadow_enter() -> None:
    result = evaluate()

    assert result.baseline_action is DecisionAction.WATCH
    assert result.challenger_action is DecisionAction.ENTER
    assert result.reason is ShadowReasonCode.PROBABILITY_ENTER_APPROVED
    assert result.positive_probability > 0.8
    assert result.candidate_version == "challenger-v1"
    assert result.strategy_version == "shadow-entry-v1"
    assert result.target_horizon_seconds == 300
    assert result.target_minimum_return_pct == 5.0
    assert result.registry_fingerprint_sha256 == REGISTRY_SHA
    assert len(result.decision_feature_fingerprint_sha256) == 64
    assert len(result.record_fingerprint_sha256) == 64


def test_probability_below_explicit_threshold_stays_watch() -> None:
    result = evaluate(policy=ShadowDecisionPolicy("shadow-policy-high-v1", 0.95))
    assert result.challenger_action is DecisionAction.WATCH
    assert result.reason is ShadowReasonCode.PROBABILITY_BELOW_ENTER_THRESHOLD


@pytest.mark.parametrize(
    ("changes", "expected_action", "expected_reason"),
    (
        ({"safety": "REJECT"}, DecisionAction.REJECT, ShadowReasonCode.SAFETY_NOT_PASS),
        ({"setup_state": "BLOCKED"}, DecisionAction.REJECT, ShadowReasonCode.SETUP_BLOCKED),
        ({"regime": "DEAD"}, DecisionAction.REJECT, ShadowReasonCode.REGIME_DEAD),
        ({"setup_state": "WATCH"}, DecisionAction.WATCH, ShadowReasonCode.SETUP_WATCH),
    ),
)
def test_deterministic_hard_gates_cannot_be_overridden_by_high_probability(
    changes, expected_action, expected_reason
) -> None:
    result = evaluate(row=row(**changes))
    assert result.positive_probability > 0.8
    assert result.challenger_action is expected_action
    assert result.reason is expected_reason


def test_hard_gate_precedence_is_stable() -> None:
    result = evaluate(row=row(safety="REJECT", setup_state="BLOCKED", regime="DEAD"))
    assert result.reason is ShadowReasonCode.SAFETY_NOT_PASS


def test_candidate_must_exist_be_current_challenger_and_be_model_backed() -> None:
    artifact = model()
    candidate = registered_candidate(artifact)
    registry = registry_with(candidate)
    with pytest.raises(ValueError, match="not registered"):
        evaluate_shadow_challenger(
            registry,
            "missing",
            artifact,
            row(),
            ShadowDecisionPolicy("shadow-policy-v1", 0.8),
        )

    with pytest.raises(ValueError, match="CHALLENGER"):
        evaluate(registry=registry_with(candidate, champion=True), candidate=candidate)

    strategy_only = build_registry_candidate(
        candidate_version="strategy-only-v1",
        strategy_version="deterministic-v0",
        feature_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        feature_columns=("market_liquidity_usd",),
        evaluation_report=evaluation("strategy-only-v1"),
        registered_at_unix_ms=4_500,
        trained_model=None,
        validation_run=None,
    )
    with pytest.raises(ValueError, match="model-backed"):
        evaluate_shadow_challenger(
            registry_with(strategy_only),
            strategy_only.candidate_version,
            artifact,
            row(),
            ShadowDecisionPolicy("shadow-policy-v1", 0.8),
        )


def test_registry_and_supplied_model_provenance_must_align_exactly() -> None:
    artifact = model()
    candidate = registered_candidate(artifact)
    registry = registry_with(candidate)

    with pytest.raises(ValueError, match="model version"):
        evaluate_shadow_challenger(
            registry,
            candidate.candidate_version,
            model(version="other-model"),
            row(),
            ShadowDecisionPolicy("shadow-policy-v1", 0.8),
        )
    with pytest.raises(ValueError, match="training fingerprint"):
        evaluate_shadow_challenger(
            registry,
            candidate.candidate_version,
            model(training_fingerprint="f" * 64),
            row(),
            ShadowDecisionPolicy("shadow-policy-v1", 0.8),
        )
    with pytest.raises(ValueError, match="feature columns"):
        evaluate_shadow_challenger(
            registry,
            candidate.candidate_version,
            model(feature_name="market_price_usd"),
            row(),
            ShadowDecisionPolicy("shadow-policy-v1", 0.8),
        )

    mismatched_schema_candidate = replace(
        candidate,
        model_training_schema_version="other-training-schema",
        candidate_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="training schema"):
        evaluate_shadow_challenger(
            registry_with(mismatched_schema_candidate),
            mismatched_schema_candidate.candidate_version,
            artifact,
            row(),
            ShadowDecisionPolicy("shadow-policy-v1", 0.8),
        )


def test_row_must_be_exact_d6_and_not_predate_registration() -> None:
    bad = row()
    bad.pop("market_liquidity_usd")
    with pytest.raises(ValueError, match="column"):
        evaluate(row=bad)

    bad_schema = row()
    bad_schema["dataset_schema_version"] = "wrong"
    with pytest.raises(ValueError, match="schema"):
        evaluate(row=bad_schema)

    with pytest.raises(ValueError, match="registration"):
        evaluate(row=row(as_of=4_499))


def test_non_entry_baseline_actions_fail_closed() -> None:
    for action in ("HOLD", "REDUCE", "EXIT"):
        with pytest.raises(ValueError, match="entry-side"):
            evaluate(row=row(baseline=action))


def test_shadow_engine_source_has_no_execution_registry_mutation_or_live_surface() -> None:
    from shreks_brain.shadow import engine

    source = inspect.getsource(engine)
    for forbidden in (
        "record_status",
        "RegistryStore",
        "TradeIntent",
        "RiskAssessment",
        "PaperExecutionResult",
        "execute_paper",
        "enable_live",
        "sign(",
        "submit(",
    ):
        assert forbidden not in source
