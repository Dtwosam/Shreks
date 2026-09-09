from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from fast_first_champion_v2_fixtures import synthetic_v2_build_result
from shreks_brain.fast_champion import read_fast_forecast_champion
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition
from shreks_brain.fast_evaluation.models import (
    fast_forecast_evaluation_report_fingerprint_sha256,
)
from shreks_brain.fast_learning import FastForecastModelFamily
from shreks_brain.fast_first_champion_v2.artifact import (
    _load_json,
    _validate_champion_member,
    _validate_report_pair,
    read_fast_first_champion_v2_evidence,
    write_fast_first_champion_v2_evidence,
)


def test_v2_evidence_artifact_round_trips_exact_file_set(
    tmp_path: Path,
) -> None:
    build = synthetic_v2_build_result()
    artifact = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "evidence",
    )

    files = {
        path.relative_to(artifact.path).as_posix()
        for path in artifact.path.rglob("*")
        if path.is_file()
    }
    assert files == {
        "manifest.json",
        "champion.json",
        "v2-evidence.json",
        *(
            f"natural-test/{value.target.value}@{value.horizon_ms}ms.json"
            for value in build.member_evidence
        ),
        *(
            f"unseen-mint-test/{value.target.value}@{value.horizon_ms}ms.json"
            for value in build.member_evidence
        ),
    }

    reread = read_fast_first_champion_v2_evidence(artifact.path)
    assert reread.manifest == artifact.manifest
    assert reread.champion == build.champion
    assert reread.natural_test_reports == build.natural_test_reports
    assert reread.unseen_mint_test_reports == (
        build.unseen_mint_test_reports
    )
    assert (
        reread.manifest.cohort_artifact_fingerprint_sha256
        == build.cohort_artifact_fingerprint_sha256
    )
    assert (
        reread.manifest.accepted_identity_fingerprint_sha256
        == build.accepted_identity_fingerprint_sha256
    )
    assert (
        reread.manifest.training_bundle_fingerprint_sha256
        == build.training_bundle_fingerprint_sha256
    )


def test_v2_evidence_bytes_are_deterministic(tmp_path: Path) -> None:
    build = synthetic_v2_build_result()
    first = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "first",
    )
    second = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "second",
    )

    first_files = sorted(
        path.relative_to(first.path).as_posix()
        for path in first.path.rglob("*")
        if path.is_file()
    )
    second_files = sorted(
        path.relative_to(second.path).as_posix()
        for path in second.path.rglob("*")
        if path.is_file()
    )
    assert first_files == second_files
    for relative in first_files:
        assert (first.path / relative).read_bytes() == (
            second.path / relative
        ).read_bytes()


def test_v2_evidence_refuses_overwrite(tmp_path: Path) -> None:
    build = synthetic_v2_build_result()
    destination = tmp_path / "evidence"
    write_fast_first_champion_v2_evidence(build, destination)

    with pytest.raises(FileExistsError, match="overwrite|exists"):
        write_fast_first_champion_v2_evidence(build, destination)


def test_v2_reader_rejects_hash_tamper_and_unknown_file(
    tmp_path: Path,
) -> None:
    build = synthetic_v2_build_result()
    tampered = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "tampered",
    )
    report = next((tampered.path / "natural-test").glob("*.json"))
    report.write_bytes(report.read_bytes() + b" ")

    with pytest.raises(ValueError, match="hash mismatch"):
        read_fast_first_champion_v2_evidence(tampered.path)

    unknown = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "unknown",
    )
    (unknown.path / "extra.txt").write_text("forbidden", encoding="utf-8")
    with pytest.raises(ValueError, match="file set"):
        read_fast_first_champion_v2_evidence(unknown.path)


def test_v2_reader_rejects_symlink_member(tmp_path: Path) -> None:
    build = synthetic_v2_build_result()
    artifact = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "symlink",
    )
    target = artifact.path / "champion.json"
    payload = target.read_bytes()
    target.unlink()
    external = tmp_path / "external-champion.json"
    external.write_bytes(payload)
    target.symlink_to(external)

    with pytest.raises(ValueError, match="symlink"):
        read_fast_first_champion_v2_evidence(artifact.path)


def test_existing_runtime_champion_reader_accepts_v2_champion(
    tmp_path: Path,
) -> None:
    build = synthetic_v2_build_result()
    artifact = write_fast_first_champion_v2_evidence(
        build,
        tmp_path / "compat",
    )

    champion = read_fast_forecast_champion(
        artifact.path / "champion.json"
    )
    assert champion == build.champion
    assert champion.champion_fingerprint_sha256 == (
        build.champion.champion_fingerprint_sha256
    )


def test_v2_manifest_pins_frozen_authority(tmp_path: Path) -> None:
    artifact = write_fast_first_champion_v2_evidence(
        synthetic_v2_build_result(),
        tmp_path / "authority",
    )

    with pytest.raises(ValueError, match="frozen physical cohort"):
        replace(
            artifact.manifest,
            cohort_artifact_fingerprint_sha256="f" * 64,
        )
    with pytest.raises(ValueError, match="accepted identity fingerprint"):
        replace(
            artifact.manifest,
            accepted_identity_fingerprint_sha256="e" * 64,
        )
    with pytest.raises(ValueError, match="feature firewall fingerprint"):
        replace(
            artifact.manifest,
            feature_identity_firewall_fingerprint_sha256="d" * 64,
        )


def test_v2_champion_member_must_reconcile_to_v2_member_evidence() -> None:
    build = synthetic_v2_build_result()
    bad = replace(
        build.member_evidence[0],
        runtime_artifact_fingerprint_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="champion member.*reconcile"):
        _validate_champion_member(
            build.champion,
            bad,
            build.natural_test_reports[0],
        )


def test_v2_json_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.json"
    source.write_text('{"x":1,"x":1}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate key"):
        _load_json(source)


def test_v2_reader_validation_rejects_non_test_report_partition() -> None:
    build = synthetic_v2_build_result()
    natural = build.natural_test_reports[0]
    validation_policy = replace(
        natural.evaluation_policy,
        partition=FastForecastEvaluationPartition.VALIDATION,
    )
    provisional = replace(
        natural,
        evaluation_policy=validation_policy,
        evaluation_report_fingerprint_sha256="0" * 64,
    )
    bad = replace(
        provisional,
        evaluation_report_fingerprint_sha256=(
            fast_forecast_evaluation_report_fingerprint_sha256(provisional)
        ),
    )
    evidence = replace(
        build.member_evidence[0],
        natural_test_report_fingerprint_sha256=(
            bad.evaluation_report_fingerprint_sha256
        ),
    )

    with pytest.raises(ValueError, match="TEST.*partition|partition.*TEST"):
        _validate_report_pair(
            evidence,
            bad,
            build.unseen_mint_test_reports[0],
            training_bundle_fingerprint_sha256=(
                build.training_bundle_fingerprint_sha256
            ),
        )


def test_v2_reader_validation_rejects_champion_model_family_mismatch() -> None:
    build = synthetic_v2_build_result()
    evidence = build.member_evidence[0]
    natural = build.natural_test_reports[0]
    member = SimpleNamespace(
        forecast_artifact=SimpleNamespace(
            artifact_fingerprint_sha256=(
                evidence.runtime_artifact_fingerprint_sha256
            ),
            model_family=FastForecastModelFamily.RIDGE_REGRESSION,
        ),
        validation_run_fingerprint_sha256=(
            evidence.generalization_run_fingerprint_sha256
        ),
        test_evaluation_report_fingerprint_sha256=(
            evidence.natural_test_report_fingerprint_sha256
        ),
        test_scored_observation_count=(
            evidence.natural_test_scored_observation_count
        ),
        test_target_unavailable_count=(
            evidence.natural_test_target_unavailable_count
        ),
    )
    champion = SimpleNamespace(
        member_for=lambda _target, _horizon: member,
    )

    with pytest.raises(ValueError, match="model family|model_family"):
        _validate_champion_member(champion, evidence, natural)
