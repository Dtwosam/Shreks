from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from fast_forecast_champion_fixtures import artifact_with_horizon, champion_source
from shreks_brain.fast_champion import (
    FAST_FORECAST_CHAMPION_SCHEMA_NAME,
    FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
    FastForecastChampionArtifact,
    FastForecastChampionMember,
    FastForecastChampionSelection,
)
from shreks_brain.fast_champion.models import fast_forecast_champion_fingerprint_sha256
from shreks_brain.fast_learning import FastForecastTarget


def _member(artifact, run, report) -> FastForecastChampionMember:
    return FastForecastChampionMember(
        member_key=f"{artifact.target.value}@{artifact.horizon_ms}ms",
        forecast_artifact=artifact,
        validation_policy_version=run.validation_policy_version,
        validation_run_fingerprint_sha256=run.validation_run_fingerprint_sha256,
        test_evaluation_policy_version=report.evaluation_policy.version,
        test_evaluation_report_fingerprint_sha256=report.evaluation_report_fingerprint_sha256,
        test_scored_observation_count=report.overall.scored_observation_count,
        test_target_unavailable_count=report.overall.target_unavailable_count,
    )


def _champion(members: tuple[FastForecastChampionMember, ...]) -> FastForecastChampionArtifact:
    first = members[0].forecast_artifact
    provisional = FastForecastChampionArtifact(
        schema_name=FAST_FORECAST_CHAMPION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
        champion_version="fixture-champion-v1",
        selection=FastForecastChampionSelection(
            decision_reference="fixture-selection-001",
            decided_at_unix_ms=5_000,
            reason="fixture-only explicit selection",
        ),
        feature_schema_version=first.feature_schema_version,
        training_bundle_fingerprint_sha256=first.training_bundle_fingerprint_sha256,
        future_path_label_version=first.future_path_label_version,
        members=members,
        champion_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        champion_fingerprint_sha256=fast_forecast_champion_fingerprint_sha256(provisional),
    )


def test_schema_and_selection_contract_is_exact_and_frozen() -> None:
    assert FAST_FORECAST_CHAMPION_SCHEMA_NAME == "shreks.fast_lane_forecast_champion"
    assert FAST_FORECAST_CHAMPION_SCHEMA_VERSION == 1
    selection = FastForecastChampionSelection(
        decision_reference="decision-1",
        decided_at_unix_ms=0,
        reason="explicit fixture selection",
    )
    with pytest.raises(FrozenInstanceError):
        selection.reason = "changed"  # type: ignore[misc]
    for kwargs in (
        {"decision_reference": ""},
        {"decided_at_unix_ms": -1},
        {"reason": ""},
    ):
        values = {
            "decision_reference": "decision-1",
            "decided_at_unix_ms": 1,
            "reason": "reason",
            **kwargs,
        }
        with pytest.raises(ValueError):
            FastForecastChampionSelection(**values)


def test_member_key_must_be_derived_exactly_from_target_and_horizon() -> None:
    _, artifact, run, report = champion_source()
    member = _member(artifact, run, report)
    assert member.member_key == f"{artifact.target.value}@{artifact.horizon_ms}ms"
    with pytest.raises(ValueError):
        replace(member, member_key="invented")


def test_champion_supports_multi_horizon_lookup_without_fallback() -> None:
    _, artifact, run, report = champion_source()
    member_250 = _member(artifact, run, report)
    artifact_500 = artifact_with_horizon(artifact, 500)
    member_500 = replace(
        member_250,
        member_key=f"{artifact_500.target.value}@500ms",
        forecast_artifact=artifact_500,
    )
    champion = _champion((member_250, member_500))
    assert champion.member_for(FastForecastTarget.ENDPOINT_RETURN_BPS, 250) == member_250
    assert champion.member_for(FastForecastTarget.ENDPOINT_RETURN_BPS, 500) == member_500
    with pytest.raises(KeyError):
        champion.member_for(FastForecastTarget.ENDPOINT_RETURN_BPS, 499)


def test_champion_requires_canonical_unique_members_and_common_source_contract() -> None:
    _, artifact, run, report = champion_source()
    member_250 = _member(artifact, run, report)
    artifact_500 = artifact_with_horizon(artifact, 500)
    member_500 = replace(
        member_250,
        member_key=f"{artifact_500.target.value}@500ms",
        forecast_artifact=artifact_500,
    )
    with pytest.raises(ValueError):
        _champion((member_500, member_250))
    with pytest.raises(ValueError):
        _champion((member_250, member_250))

    foreign_artifact = replace(
        artifact_500,
        training_bundle_fingerprint_sha256="f" * 64,
    )
    foreign_member = replace(member_500, forecast_artifact=foreign_artifact)
    with pytest.raises(ValueError):
        _champion((member_250, foreign_member))
