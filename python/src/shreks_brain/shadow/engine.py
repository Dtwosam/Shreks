from __future__ import annotations

from dataclasses import replace

from shreks_brain.decision import DecisionAction
from shreks_brain.learning import TrainedLogisticRegressionModel, predict_positive_probability
from shreks_brain.registry import ChampionChallengerRegistry, RegistryStatus
from shreks_brain.regime import MarketRegime
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)
from shreks_brain.safety import SafetyDecision
from shreks_brain.setups import SetupState

from .fingerprint import decision_feature_fingerprint, record_fingerprint
from .models import (
    SHADOW_CHALLENGER_SCHEMA_VERSION,
    ShadowDecisionPolicy,
    ShadowDecisionRecord,
    ShadowReasonCode,
)


_ENTRY_ACTIONS = frozenset(
    (DecisionAction.REJECT, DecisionAction.WATCH, DecisionAction.ENTER)
)
_EXPECTED_ROW_COLUMNS = frozenset(RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS)


def evaluate_shadow_challenger(
    registry: ChampionChallengerRegistry,
    candidate_version: str,
    model: TrainedLogisticRegressionModel,
    row: dict[str, object],
    policy: ShadowDecisionPolicy,
) -> ShadowDecisionRecord:
    if type(registry) is not ChampionChallengerRegistry:
        raise ValueError("registry must be an exact ChampionChallengerRegistry")
    if not isinstance(candidate_version, str) or not candidate_version.strip():
        raise ValueError("candidate_version must be a non-empty string")
    if type(model) is not TrainedLogisticRegressionModel:
        raise ValueError("model must be an exact TrainedLogisticRegressionModel")
    if type(row) is not dict:
        raise ValueError("row must be an exact dict")
    if type(policy) is not ShadowDecisionPolicy:
        raise ValueError("policy must be an exact ShadowDecisionPolicy")

    candidate = next(
        (
            value
            for value in registry.candidates
            if value.candidate_version == candidate_version
        ),
        None,
    )
    if candidate is None:
        raise ValueError(f"candidate '{candidate_version}' is not registered")
    if registry.current_status(candidate_version) is not RegistryStatus.CHALLENGER:
        raise ValueError("shadow evaluation requires current CHALLENGER status")

    if candidate.model_version is None:
        raise ValueError("E7-v1 requires a model-backed registry candidate")
    if candidate.model_training_schema_version is None:
        raise ValueError("model-backed candidate is missing training schema provenance")
    if candidate.model_training_fingerprint_sha256 is None:
        raise ValueError("model-backed candidate is missing training fingerprint provenance")

    if candidate.model_version != model.model_version:
        raise ValueError("registry and supplied model version must match")
    if candidate.model_training_schema_version != model.schema_version:
        raise ValueError("registry and supplied model training schema must match")
    if candidate.model_training_fingerprint_sha256 != model.training_fingerprint_sha256:
        raise ValueError("registry and supplied model training fingerprint must match")
    model_feature_columns = tuple(
        transform.feature_name for transform in model.feature_transforms
    )
    if candidate.feature_columns != model_feature_columns:
        raise ValueError("registry and supplied model feature columns must match exactly")
    if candidate.feature_schema_version != model.research_dataset_schema_version:
        raise ValueError("registry feature schema must match supplied model research schema")

    if frozenset(row) != _EXPECTED_ROW_COLUMNS or len(row) != len(_EXPECTED_ROW_COLUMNS):
        raise ValueError("row column set must exactly match sealed D6 physical columns")
    if row.get("dataset_schema_version") != RESEARCH_DATASET_SCHEMA_VERSION:
        raise ValueError("row dataset schema must equal sealed D6 schema")
    if row["dataset_schema_version"] != candidate.feature_schema_version:
        raise ValueError("row dataset schema must match registry feature schema")

    as_of_unix_ms = _require_non_negative_int("as_of_unix_ms", row["as_of_unix_ms"])
    if as_of_unix_ms < candidate.registered_at_unix_ms:
        raise ValueError("shadow decision timestamp cannot precede candidate registration")
    candidate_mint = _require_non_empty_string("candidate_mint", row["candidate_mint"])
    setup_name = _require_non_empty_string("setup_name", row["setup_name"])

    safety_decision = _parse_enum(SafetyDecision, "safety_decision", row["safety_decision"])
    setup_state = _parse_enum(SetupState, "setup_state", row["setup_state"])
    market_regime = _parse_enum(MarketRegime, "market_regime", row["market_regime"])
    baseline_action = _parse_enum(DecisionAction, "decision_action", row["decision_action"])
    if baseline_action not in _ENTRY_ACTIONS:
        raise ValueError("baseline decision_action must be entry-side REJECT/WATCH/ENTER")

    prediction = predict_positive_probability(model, row)
    probability = prediction.positive_probability

    if safety_decision is not SafetyDecision.PASS:
        challenger_action = DecisionAction.REJECT
        reason = ShadowReasonCode.SAFETY_NOT_PASS
    elif setup_state is SetupState.BLOCKED:
        challenger_action = DecisionAction.REJECT
        reason = ShadowReasonCode.SETUP_BLOCKED
    elif market_regime is MarketRegime.DEAD:
        challenger_action = DecisionAction.REJECT
        reason = ShadowReasonCode.REGIME_DEAD
    elif setup_state is SetupState.WATCH:
        challenger_action = DecisionAction.WATCH
        reason = ShadowReasonCode.SETUP_WATCH
    elif setup_state is SetupState.READY:
        if probability >= policy.enter_min_probability:
            challenger_action = DecisionAction.ENTER
            reason = ShadowReasonCode.PROBABILITY_ENTER_APPROVED
        else:
            challenger_action = DecisionAction.WATCH
            reason = ShadowReasonCode.PROBABILITY_BELOW_ENTER_THRESHOLD
    else:  # pragma: no cover - exact enum exhaustiveness guard
        raise ValueError("unsupported setup state")

    draft = ShadowDecisionRecord(
        schema_version=SHADOW_CHALLENGER_SCHEMA_VERSION,
        candidate_version=candidate.candidate_version,
        strategy_version=candidate.strategy_version,
        candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
        registry_fingerprint_sha256=registry.registry_fingerprint_sha256,
        model_version=model.model_version,
        model_training_fingerprint_sha256=model.training_fingerprint_sha256,
        target_horizon_seconds=model.target.horizon_seconds,
        target_minimum_return_pct=model.target.minimum_return_pct,
        shadow_policy_version=policy.version,
        enter_min_probability=policy.enter_min_probability,
        candidate_mint=candidate_mint,
        as_of_unix_ms=as_of_unix_ms,
        dataset_schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        decision_feature_fingerprint_sha256=decision_feature_fingerprint(row),
        setup_name=setup_name,
        safety_decision=safety_decision.value,
        setup_state=setup_state.value,
        market_regime=market_regime.value,
        baseline_action=baseline_action,
        positive_probability=probability,
        challenger_action=challenger_action,
        reason=reason,
        record_fingerprint_sha256="0" * 64,
    )
    return replace(
        draft,
        record_fingerprint_sha256=record_fingerprint(draft),
    )


def _require_non_empty_string(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _parse_enum(enum_type, name: str, value: object):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a supported string value")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a supported string value") from error
