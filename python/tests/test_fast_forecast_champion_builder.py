from __future__ import annotations

from dataclasses import replace

import pytest

from fast_forecast_champion_fixtures import (
    champion_source,
    continuous_and_binary_sources,
)
from shreks_brain.fast_champion import build_fast_forecast_champion
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition


def _build(sources):
    return build_fast_forecast_champion(
        champion_version="forecast-champion-v1",
        decision_reference="selection-proof-001",
        decided_at_unix_ms=10_000,
        reason="explicit fixture selection for packaging test",
        member_sources=tuple((value[1], value[2], value[3]) for value in sources),
    )


def test_builder_packages_canonical_multi_target_sources_independent_of_input_order() -> None:
    continuous, binary = continuous_and_binary_sources()
    first = _build((continuous, binary))
    second = _build((binary, continuous))
    assert first == second
    assert first.champion_fingerprint_sha256 == second.champion_fingerprint_sha256
    assert tuple(value.member_key for value in first.members) == tuple(
        sorted(value.member_key for value in first.members)
    )
    assert len(first.members) == 2


def test_builder_requires_test_evaluation_evidence() -> None:
    source = champion_source()
    report = source[3]
    validation_policy = replace(
        report.evaluation_policy,
        partition=FastForecastEvaluationPartition.VALIDATION,
    )
    validation_report = replace(report, evaluation_policy=validation_policy)
    with pytest.raises(ValueError, match="TEST"):
        build_fast_forecast_champion(
            champion_version="forecast-champion-v1",
            decision_reference="selection-proof-001",
            decided_at_unix_ms=10_000,
            reason="fixture",
            member_sources=((source[1], source[2], validation_report),),
        )


def test_builder_fails_closed_on_artifact_run_report_identity_mismatch() -> None:
    continuous, binary = continuous_and_binary_sources()
    with pytest.raises(ValueError):
        build_fast_forecast_champion(
            champion_version="forecast-champion-v1",
            decision_reference="selection-proof-001",
            decided_at_unix_ms=10_000,
            reason="fixture",
            member_sources=((continuous[1], binary[2], binary[3]),),
        )


def test_builder_fails_closed_on_source_bundle_or_training_policy_mismatch() -> None:
    source = champion_source()
    bad_bundle_artifact = replace(
        source[1],
        training_bundle_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError):
        _build(((source[0], bad_bundle_artifact, source[2], source[3]),))

    bad_policy_artifact = replace(source[1], training_policy_version="different-policy")
    with pytest.raises(ValueError):
        _build(((source[0], bad_policy_artifact, source[2], source[3]),))


def test_builder_rejects_duplicate_target_horizon_members() -> None:
    source = champion_source()
    with pytest.raises(ValueError, match="duplicate"):
        _build((source, source))


def test_builder_recomputes_runtime_artifact_and_evaluation_report_fingerprints() -> None:
    source = champion_source()
    bad_artifact = replace(source[1], artifact_fingerprint_sha256="a" * 64)
    with pytest.raises(ValueError, match="artifact fingerprint"):
        _build(((source[0], bad_artifact, source[2], source[3]),))

    bad_report = replace(source[3], evaluation_report_fingerprint_sha256="b" * 64)
    with pytest.raises(ValueError, match="evaluation report fingerprint"):
        _build(((source[0], source[1], source[2], bad_report),))
