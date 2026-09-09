from __future__ import annotations

from dataclasses import replace

import pytest

from fast_first_champion_v2_fixtures import synthetic_v2_build_result
from shreks_brain.fast_first_champion_v2.champion import (
    build_fast_first_champion_v2_runtime_champion,
)
from shreks_brain.fast_first_champion_v2.models import (
    FastFirstChampionV2Policy,
)


def test_v2_packager_maps_natural_test_evidence_into_runtime_champion() -> None:
    build = synthetic_v2_build_result()
    policy = FastFirstChampionV2Policy()

    assert len(build.champion.members) == len(policy.required_members)
    for artifact, run, report in zip(
        build.runtime_artifacts,
        build.generalization_runs,
        build.natural_test_reports,
        strict=True,
    ):
        member = build.champion.member_for(
            artifact.target,
            artifact.horizon_ms,
        )
        assert member.forecast_artifact == artifact
        assert member.validation_policy_version == (
            run.validation_policy_version
        )
        assert member.validation_run_fingerprint_sha256 == (
            run.validation_run_fingerprint_sha256
        )
        assert member.test_evaluation_report_fingerprint_sha256 == (
            report.evaluation_report_fingerprint_sha256
        )
        assert member.test_scored_observation_count == (
            report.overall.scored_observation_count
        )


def test_v2_packager_rejects_required_member_reordering() -> None:
    build = synthetic_v2_build_result()
    policy = FastFirstChampionV2Policy()
    reordered = (
        build.runtime_artifacts[1],
        build.runtime_artifacts[0],
        *build.runtime_artifacts[2:],
    )

    with pytest.raises(ValueError, match="required V2 member"):
        build_fast_first_champion_v2_runtime_champion(
            policy=policy,
            champion_version="fixture",
            decision_reference="fixture",
            reason="fixture",
            runtime_artifacts=reordered,
            generalization_runs=build.generalization_runs,
            natural_test_reports=build.natural_test_reports,
        )


def test_v2_packager_rejects_report_run_fingerprint_mismatch() -> None:
    build = synthetic_v2_build_result()
    policy = FastFirstChampionV2Policy()
    mismatched = replace(
        build.natural_test_reports[0],
        validation_run_fingerprint_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="does not match V2 generalization run"):
        build_fast_first_champion_v2_runtime_champion(
            policy=policy,
            champion_version="fixture",
            decision_reference="fixture",
            reason="fixture",
            runtime_artifacts=build.runtime_artifacts,
            generalization_runs=build.generalization_runs,
            natural_test_reports=(
                mismatched,
                *build.natural_test_reports[1:],
            ),
        )
