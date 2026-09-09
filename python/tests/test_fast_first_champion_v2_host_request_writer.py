from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_first_champion_v2.host_request as request_module
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_first_champion_v2.host_request import (
    decode_fast_first_champion_v2_host_request,
    write_fast_first_champion_v2_host_request_from_sources,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
)


RELEASE_SHA = "1" * 40
COHORT_FP = (
    "bd6875c4d65ee9b2eb67783e7ecfa233"
    "2305bf6c3251f5d474e66465fd17d93a"
)
HYDRATION_FP = "2" * 64
OVERLAY_FP = "3" * 64
COST_FP = "4" * 64


def _evaluation_policy() -> FastForecastEvaluationPolicy:
    return FastForecastEvaluationPolicy(
        version="fl9-v2-host-test-eval-v1",
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=10,
        liquidity_capacity_quote_boundaries=(10.0, 100.0),
        round_trip_cost_bps_boundaries=(25.0, 50.0),
        binary_log_loss_clip_epsilon=1e-12,
    )


def _cost_policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="fl9-v2-host-cost-v1",
        additional_entry_slippage_bps=10,
        additional_exit_slippage_bps=20,
        entry_latency_bps=5,
        exit_latency_bps=5,
        entry_network_fee_quote=0.0,
        exit_network_fee_quote=0.0,
        entry_priority_fee_quote=0.0,
        exit_priority_fee_quote=0.0,
        entry_expected_failure_cost_quote=0.0,
        exit_expected_failure_cost_quote=0.0,
    )


def _sources(tmp_path: Path) -> dict[str, Path]:
    proof = tmp_path / "proof"
    proof.mkdir()
    (proof / "features.jsonl").write_text("{}\n", encoding="utf-8")
    (proof / "manifest.json").write_text("{}\n", encoding="utf-8")
    database = tmp_path / "observer.db"
    database.write_bytes(b"sqlite")
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "manifest.json").write_text("{}\n", encoding="utf-8")
    hydration = tmp_path / "hydration.json"
    hydration.write_text("{}\n", encoding="utf-8")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "manifest.json").write_text("{}\n", encoding="utf-8")
    (overlay / "rows.jsonl").write_text("{}\n", encoding="utf-8")
    cost = tmp_path / "cost.json"
    cost.write_text("{}\n", encoding="utf-8")
    return dict(
        proof=proof,
        database=database,
        cohort=cohort,
        hydration=hydration,
        overlay=overlay,
        cost=cost,
    )


def _install_authenticated_sources(monkeypatch, *, cohort_fp=COHORT_FP):
    proof = SimpleNamespace(
        manifest=SimpleNamespace(release_source_sha=RELEASE_SHA)
    )
    cohort = SimpleNamespace(
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256=cohort_fp,
            accepted_identity_fingerprint_sha256="5" * 64,
        )
    )
    hydration_policy = object()
    cost_policy = _cost_policy()
    overlay = SimpleNamespace(
        manifest=SimpleNamespace(
            manifest_fingerprint_sha256=OVERLAY_FP
        )
    )
    monkeypatch.setattr(
        request_module,
        "read_fast_proof_workspace",
        lambda _path: proof,
    )
    monkeypatch.setattr(
        request_module,
        "read_fl9_v2_cohort_acceptance",
        lambda _path: cohort,
    )
    monkeypatch.setattr(
        request_module,
        "decode_fast_forecast_context_hydration_policy",
        lambda _payload: hydration_policy,
    )
    monkeypatch.setattr(
        request_module,
        "fast_forecast_context_hydration_policy_fingerprint_sha256",
        lambda _policy: HYDRATION_FP,
    )
    monkeypatch.setattr(
        request_module,
        "read_fast_training_economics_overlay",
        lambda _path: overlay,
    )
    monkeypatch.setattr(
        request_module,
        "decode_fast_training_execution_cost_policy",
        lambda _payload: cost_policy,
    )
    monkeypatch.setattr(
        request_module,
        "fast_training_execution_cost_policy_fingerprint_sha256",
        lambda _policy: COST_FP,
    )


def test_v2_source_writer_has_no_split_horizon_or_floor_parameters() -> None:
    parameters = set(
        inspect.signature(
            write_fast_first_champion_v2_host_request_from_sources
        ).parameters
    )
    for forbidden in (
        "horizon_ms",
        "selection_at_unix_ms",
        "training_cut_unix_ms",
        "validation_cut_unix_ms",
        "test_end_unix_ms",
        "minimum_test_scored_observations",
        "minimum_natural_test_scored_observations",
        "minimum_unseen_mint_test_scored_observations",
    ):
        assert forbidden not in parameters


def test_v2_source_writer_authenticates_sources_and_writes_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = _sources(tmp_path)
    _install_authenticated_sources(monkeypatch)
    request_path = tmp_path / "request.json"
    evidence_path = tmp_path / "evidence"

    result = write_fast_first_champion_v2_host_request_from_sources(
        proof_workspace_path=paths["proof"],
        observer_database_path=paths["database"],
        cohort_artifact_path=paths["cohort"],
        hydration_policy_path=paths["hydration"],
        training_economics_overlay_path=paths["overlay"],
        training_execution_cost_policy_path=paths["cost"],
        request_destination=request_path,
        evidence_destination=evidence_path,
        future_path_label_version=1,
        counterfactual_base_quantity=1.0,
        evaluation_policy=_evaluation_policy(),
        champion_version="fl9-v2-runtime-v1",
        model_version_prefix="fl9-v2",
        training_policy_version="fl9-v2-training-v1",
        reason="production V2 first champion evidence",
    )
    request = decode_fast_first_champion_v2_host_request(
        request_path.read_text(encoding="utf-8")
    )

    assert result.path == request_path.resolve()
    assert request.expected_release_source_sha == RELEASE_SHA
    assert request.expected_cohort_artifact_fingerprint_sha256 == COHORT_FP
    assert request.expected_hydration_policy_fingerprint_sha256 == HYDRATION_FP
    assert (
        request.expected_training_economics_overlay_manifest_fingerprint_sha256
        == OVERLAY_FP
    )
    assert request.training_execution_cost_policy_fingerprint_sha256 == COST_FP
    assert request.destination_path == str(evidence_path.resolve())


def test_v2_source_writer_rejects_noncanonical_physical_cohort(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = _sources(tmp_path)
    _install_authenticated_sources(monkeypatch, cohort_fp="f" * 64)

    with pytest.raises(ValueError, match="cohort.*fingerprint|frozen"):
        write_fast_first_champion_v2_host_request_from_sources(
            proof_workspace_path=paths["proof"],
            observer_database_path=paths["database"],
            cohort_artifact_path=paths["cohort"],
            hydration_policy_path=paths["hydration"],
            training_economics_overlay_path=paths["overlay"],
            training_execution_cost_policy_path=paths["cost"],
            request_destination=tmp_path / "request.json",
            evidence_destination=tmp_path / "evidence",
            future_path_label_version=1,
            counterfactual_base_quantity=1.0,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-v2-runtime-v1",
            model_version_prefix="fl9-v2",
            training_policy_version="fl9-v2-training-v1",
            reason="production V2 first champion evidence",
        )
    assert not (tmp_path / "request.json").exists()
