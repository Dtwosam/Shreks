from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.registry import (
    CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
    ChampionChallengerRegistry,
    RegistryCandidate,
    RegistryEvaluationEvidence,
    RegistryStatus,
    RegistryStatusEvent,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def evaluation() -> RegistryEvaluationEvidence:
    return RegistryEvaluationEvidence(
        schema_version="e5-trading-evaluation-v1",
        policy_version="eval-v1",
        evaluation_fingerprint_sha256=SHA_A,
        trade_count=12,
        net_pnl_usd=120.0,
        net_expectancy_usd=10.0,
        net_expectancy_pct=2.0,
        profit_factor=1.8,
        maximum_drawdown_usd=40.0,
        maximum_drawdown_pct=8.0,
        win_rate=0.5,
        turnover_usd=4_000.0,
        total_cost_usd=20.0,
        brier_score=0.2,
        expected_calibration_error=0.08,
    )


def candidate(**changes: object) -> RegistryCandidate:
    base = RegistryCandidate(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidate_version="candidate-v1",
        strategy_version="strategy-v1",
        model_version="model-v1",
        model_training_schema_version="e3-training-v1",
        model_training_fingerprint_sha256=SHA_B,
        feature_schema_version="d6-research-v1",
        feature_columns=("feature_a", "feature_b"),
        training_started_at_unix_ms=100,
        training_ended_at_unix_ms=200,
        validation_schema_version="e4-time-validation-v1",
        validation_policy_version="walk-forward-v1",
        validation_run_fingerprint_sha256=SHA_C,
        evaluation=evaluation(),
        registered_at_unix_ms=300,
        initial_status=RegistryStatus.CHALLENGER,
        candidate_fingerprint_sha256="0" * 64,
    )
    if not changes:
        return base
    return replace(base, **changes)


def event(**changes: object) -> RegistryStatusEvent:
    base = RegistryStatusEvent(
        candidate_version="candidate-v1",
        from_status=RegistryStatus.CHALLENGER,
        to_status=RegistryStatus.CHAMPION,
        decision_reference="promotion-decision-1",
        decided_at_unix_ms=400,
        reason="Explicit external promotion decision.",
        event_fingerprint_sha256=SHA_A,
    )
    if not changes:
        return base
    return replace(base, **changes)


def test_registry_schema_and_status_vocabulary_are_exact() -> None:
    assert CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION == "e6-registry-v1"
    assert tuple(status.value for status in RegistryStatus) == (
        "CHALLENGER",
        "CHAMPION",
        "RETIRED",
    )


def test_candidate_requires_challenger_initial_status_and_complete_ml_provenance() -> None:
    with pytest.raises(ValueError, match="initial_status"):
        candidate(initial_status=RegistryStatus.CHAMPION)

    with pytest.raises(ValueError, match="model provenance"):
        candidate(model_training_fingerprint_sha256=None)

    with pytest.raises(ValueError, match="training timestamps"):
        candidate(training_started_at_unix_ms=None, training_ended_at_unix_ms=200)


def test_strategy_only_candidate_requires_all_ml_provenance_to_be_absent() -> None:
    strategy_only = candidate(
        model_version=None,
        model_training_schema_version=None,
        model_training_fingerprint_sha256=None,
        training_started_at_unix_ms=None,
        training_ended_at_unix_ms=None,
        validation_schema_version=None,
        validation_policy_version=None,
        validation_run_fingerprint_sha256=None,
    )
    assert strategy_only.model_version is None

    with pytest.raises(ValueError, match="model provenance"):
        replace(strategy_only, validation_policy_version="unexpected")


def test_evaluation_evidence_validates_counts_fractions_and_calibration_pair() -> None:
    with pytest.raises(ValueError, match="trade_count"):
        replace(evaluation(), trade_count=-1)
    with pytest.raises(ValueError, match="win_rate"):
        replace(evaluation(), win_rate=1.1)
    with pytest.raises(ValueError, match="calibration"):
        replace(evaluation(), brier_score=None)


def test_status_event_is_explicit_and_cannot_be_a_noop() -> None:
    with pytest.raises(ValueError, match="different"):
        event(to_status=RegistryStatus.CHALLENGER)
    with pytest.raises(ValueError, match="decision_reference"):
        event(decision_reference=" ")
    with pytest.raises(ValueError, match="reason"):
        event(reason="")


def test_registry_is_canonical_and_reconstructs_status_without_metric_logic() -> None:
    second = candidate(
        candidate_version="candidate-v2",
        model_version=None,
        model_training_schema_version=None,
        model_training_fingerprint_sha256=None,
        training_started_at_unix_ms=None,
        training_ended_at_unix_ms=None,
        validation_schema_version=None,
        validation_policy_version=None,
        validation_run_fingerprint_sha256=None,
        candidate_fingerprint_sha256="1" * 64,
    )
    registry = ChampionChallengerRegistry(
        schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
        candidates=(candidate(), second),
        status_events=(event(),),
        registry_fingerprint_sha256=SHA_B,
    )
    assert registry.current_status("candidate-v1") is RegistryStatus.CHAMPION
    assert registry.current_champion() == candidate()
    assert tuple(item.candidate_version for item in registry.challengers()) == (
        "candidate-v2",
    )


def test_registry_rejects_two_reconstructed_champions() -> None:
    second = candidate(
        candidate_version="candidate-v2",
        model_version=None,
        model_training_schema_version=None,
        model_training_fingerprint_sha256=None,
        training_started_at_unix_ms=None,
        training_ended_at_unix_ms=None,
        validation_schema_version=None,
        validation_policy_version=None,
        validation_run_fingerprint_sha256=None,
        candidate_fingerprint_sha256="1" * 64,
    )
    second_event = RegistryStatusEvent(
        candidate_version="candidate-v2",
        from_status=RegistryStatus.CHALLENGER,
        to_status=RegistryStatus.CHAMPION,
        decision_reference="promotion-decision-2",
        decided_at_unix_ms=401,
        reason="Another explicit decision.",
        event_fingerprint_sha256=SHA_C,
    )
    with pytest.raises(ValueError, match="one current champion"):
        ChampionChallengerRegistry(
            schema_version=CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION,
            candidates=(candidate(), second),
            status_events=(event(), second_event),
            registry_fingerprint_sha256=SHA_B,
        )
