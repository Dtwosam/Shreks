from __future__ import annotations

from pathlib import Path

import pytest

from fast_forecast_evaluation_fixtures import (
    chronological_policy,
    evaluation_contexts,
    evaluation_policy,
)
from fast_chronological_fixtures import (
    HORIZON_MS,
    TEST_END,
    chronological_bundle,
    forecast_request,
)
from shreks_brain.fast_champion import (
    FAST_FIRST_CHAMPION_BUILDER_VERSION,
    FastFirstChampionBuildResult,
    build_fast_first_champion,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
)
from shreks_brain.fast_validation import run_fast_chronological_validation


REQUIRED_TARGETS = (
    FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    FastForecastTarget.ENDPOINT_RETURN_BPS,
    FastForecastTarget.MAE_BPS,
    FastForecastTarget.REVERSAL_OCCURRED,
    FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
)


def _contexts():
    bundle = chronological_bundle()
    run = run_fast_chronological_validation(
        bundle,
        forecast_request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        chronological_policy(),
    )
    return evaluation_contexts(run)


def test_first_champion_builds_exact_dependency_free_fl9_member_set() -> None:
    bundle = chronological_bundle()
    result = build_fast_first_champion(
        bundle=bundle,
        contexts=_contexts(),
        validation_policy=chronological_policy(),
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        champion_version="fl9-first-real-v1",
        decision_reference="operator-selection:fixture-v1",
        decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
        reason="explicit first dependency-free FL9 forecast champion",
        horizon_ms=HORIZON_MS,
        model_version_prefix="fl9-first",
        training_policy_version="fl9-first-naive-v1",
        minimum_test_scored_observations=1,
    )

    assert type(result) is FastFirstChampionBuildResult
    assert result.version == FAST_FIRST_CHAMPION_BUILDER_VERSION
    assert tuple(member.forecast_artifact.target for member in result.champion.members) == tuple(
        sorted(REQUIRED_TARGETS, key=lambda value: f"{value.value}@{HORIZON_MS}ms")
    )
    assert len(result.runtime_artifacts) == 5
    assert len(result.validation_runs) == 5
    assert len(result.evaluation_reports) == 5

    by_target = {
        artifact.target: artifact for artifact in result.runtime_artifacts
    }
    for target in REQUIRED_TARGETS:
        artifact = by_target[target]
        expected_family = (
            FastForecastModelFamily.PRIOR_CLASSIFIER
            if target
            in {
                FastForecastTarget.REVERSAL_OCCURRED,
                FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
            }
            else FastForecastModelFamily.MEAN_REGRESSOR
        )
        assert artifact.model_family is expected_family
        assert artifact.horizon_ms == HORIZON_MS
        assert artifact.max_training_decision_observed_at_unix_ms + HORIZON_MS <= (
            TEST_END + HORIZON_MS + 1
        )

    for report in result.evaluation_reports:
        assert report.evaluation_policy.partition is FastForecastEvaluationPartition.TEST
        assert report.overall.scored_observation_count >= 1

    assert result.champion.selection.decision_reference == (
        "operator-selection:fixture-v1"
    )
    assert result.champion.selection.decided_at_unix_ms == (
        TEST_END + HORIZON_MS + 1
    )


def test_first_champion_rejects_non_test_evaluation_policy() -> None:
    with pytest.raises(ValueError, match="TEST"):
        build_fast_first_champion(
            bundle=chronological_bundle(),
            contexts=_contexts(),
            validation_policy=chronological_policy(),
            evaluation_policy=evaluation_policy(
                FastForecastEvaluationPartition.VALIDATION
            ),
            champion_version="fl9-first-real-v1",
            decision_reference="selection",
            decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
            reason="explicit",
            horizon_ms=HORIZON_MS,
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            minimum_test_scored_observations=1,
        )


def test_first_champion_rejects_selection_before_test_or_target_maturity() -> None:
    with pytest.raises(ValueError, match="selection|test|mature|chronology"):
        build_fast_first_champion(
            bundle=chronological_bundle(),
            contexts=_contexts(),
            validation_policy=chronological_policy(),
            evaluation_policy=evaluation_policy(
                FastForecastEvaluationPartition.TEST
            ),
            champion_version="fl9-first-real-v1",
            decision_reference="selection",
            decided_at_unix_ms=TEST_END - 1,
            reason="explicit",
            horizon_ms=HORIZON_MS,
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            minimum_test_scored_observations=1,
        )


def test_first_champion_rejects_unmet_explicit_test_count_floor() -> None:
    with pytest.raises(ValueError, match="scored|evidence|minimum"):
        build_fast_first_champion(
            bundle=chronological_bundle(),
            contexts=_contexts(),
            validation_policy=chronological_policy(),
            evaluation_policy=evaluation_policy(
                FastForecastEvaluationPartition.TEST
            ),
            champion_version="fl9-first-real-v1",
            decision_reference="selection",
            decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
            reason="explicit",
            horizon_ms=HORIZON_MS,
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            minimum_test_scored_observations=4,
        )


def test_first_champion_builder_has_no_heavy_dependency_or_trading_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_champion"
        / "first_builder.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "sklearn",
        "numpy",
        "pyarrow",
        "requests.",
        "httpx",
        "sqlite3",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
    ):
        assert forbidden not in source
