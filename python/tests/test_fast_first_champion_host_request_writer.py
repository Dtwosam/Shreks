from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_first_champion_host_request_writer as writer
from shreks_brain.fast_context_hydration import (
    encode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_first_champion_host_run import (
    FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK,
    decode_fast_first_champion_host_request,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
    encode_fast_training_execution_cost_policy,
    fast_training_execution_cost_policy_fingerprint_sha256,
)
from test_fast_context_hydration import _policy


_RELEASE_SHA = "ead8a1f504e00a6491bb2a01d3240a8bc4d91d6d"





def _training_economics_policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="writer-training-cost-v1",
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


def _evaluation_policy() -> FastForecastEvaluationPolicy:
    return FastForecastEvaluationPolicy(
        version="fl9-first-test-evaluation-v1",
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=10,
        liquidity_capacity_quote_boundaries=(0.0, 1.0, 10.0),
        round_trip_cost_bps_boundaries=(0.0, 25.0, 100.0),
        binary_log_loss_clip_epsilon=1e-6,
    )


def _sources(monkeypatch, tmp_path: Path):
    proof = tmp_path / "proof-workspace"
    proof.mkdir()
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-db")
    policy_path = tmp_path / "hydration-policy.json"
    policy = _policy()
    economics_overlay = tmp_path / "training-economics"
    economics_overlay.mkdir()
    (economics_overlay / "rows.jsonl").write_text(
        '{"sealed":"rows"}\n',
        encoding="utf-8",
    )
    (economics_overlay / "manifest.json").write_text(
        '{"manifest_fingerprint_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n',
        encoding="utf-8",
    )
    training_cost_path = tmp_path / "training-cost-policy.json"
    training_cost_path.write_text(
        encode_fast_training_execution_cost_policy(
            _training_economics_policy()
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        encode_fast_forecast_context_hydration_policy(policy),
        encoding="utf-8",
    )
    proof_artifact = SimpleNamespace(
        path=proof.resolve(),
        manifest=SimpleNamespace(
            release_source_sha=_RELEASE_SHA,
            artifact_fingerprint_sha256="a" * 64,
        ),
    )
    monkeypatch.setattr(
        writer,
        "read_fast_proof_workspace",
        lambda path: proof_artifact,
    )
    monkeypatch.setattr(
        writer,
        "_read_training_economics_overlay_manifest_fingerprint",
        lambda _path: "a" * 64,
        raising=False,
    )
    return proof, database, policy_path, policy, proof_artifact


def test_writer_derives_authenticated_release_and_policy_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    proof, database, policy_path, policy, _ = _sources(
        monkeypatch,
        tmp_path,
    )
    request_path = tmp_path / "first-champion-host-request.json"
    host_run_destination = tmp_path / "first-champion-host-run"

    result = writer.write_fast_first_champion_host_request_from_sources(
        proof_workspace_path=proof,
        observer_database_path=database,
        hydration_policy_path=policy_path,
        training_economics_overlay_path=tmp_path / "training-economics",
        training_execution_cost_policy_path=tmp_path / "training-cost-policy.json",
        request_destination=request_path,
        host_run_destination=host_run_destination,
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        horizon_ms=30_000,
        minimum_raw_rows_per_partition=20,
        minimum_test_scored_observations=10,
        evaluation_policy=_evaluation_policy(),
        champion_version="fl9-first-host-v1",
        model_version_prefix="fl9-first",
        training_policy_version="fl9-first-naive-v1",
        reason="first genuine PAPER-host champion",
    )

    request = decode_fast_first_champion_host_request(
        request_path.read_text(encoding="utf-8")
    )
    assert result.path == request_path.resolve()
    assert result.request_fingerprint_sha256 == (
        request.request_fingerprint_sha256
    )
    assert result.release_source_sha == _RELEASE_SHA
    assert result.hydration_policy_fingerprint_sha256 == (
        fast_forecast_context_hydration_policy_fingerprint_sha256(
            policy
        )
    )
    assert request.proof_workspace_path == str(proof.resolve())
    assert request.observer_database_path == str(database.resolve())
    assert request.hydration_policy_path == str(policy_path.resolve())
    assert request.training_economics_overlay_path == str(
        (tmp_path / "training-economics").resolve()
    )
    assert request.expected_training_economics_overlay_manifest_fingerprint_sha256 == "a" * 64
    assert request.training_execution_cost_policy == _training_economics_policy()
    assert request.training_execution_cost_policy_fingerprint_sha256 == (
        fast_training_execution_cost_policy_fingerprint_sha256(
            _training_economics_policy()
        )
    )
    assert request.destination_path == str(host_run_destination.resolve())
    assert request.expected_release_source_sha == _RELEASE_SHA
    assert request.expected_hydration_policy_fingerprint_sha256 == (
        result.hydration_policy_fingerprint_sha256
    )
    assert request.selection_clock == FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK
    assert request.evaluation_policy == _evaluation_policy()


def test_writer_refuses_existing_request_or_host_run_destination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    proof, database, policy_path, *_ = _sources(monkeypatch, tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text("exists", encoding="utf-8")

    with pytest.raises(FileExistsError, match="request.*exists|destination"):
        writer.write_fast_first_champion_host_request_from_sources(
            proof_workspace_path=proof,
            observer_database_path=database,
            hydration_policy_path=policy_path,
            training_economics_overlay_path=tmp_path / "training-economics",
            training_execution_cost_policy_path=tmp_path / "training-cost-policy.json",
            request_destination=request_path,
            host_run_destination=tmp_path / "run",
            future_path_label_version=1,
            counterfactual_base_quantity=2.0,
            horizon_ms=30_000,
            minimum_raw_rows_per_partition=20,
            minimum_test_scored_observations=10,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-first-host-v1",
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            reason="first genuine PAPER-host champion",
        )

    request_path.unlink()
    host_run = tmp_path / "run"
    host_run.mkdir()
    with pytest.raises(FileExistsError, match="host run.*exists|destination"):
        writer.write_fast_first_champion_host_request_from_sources(
            proof_workspace_path=proof,
            observer_database_path=database,
            hydration_policy_path=policy_path,
            training_economics_overlay_path=tmp_path / "training-economics",
            training_execution_cost_policy_path=tmp_path / "training-cost-policy.json",
            request_destination=request_path,
            host_run_destination=host_run,
            future_path_label_version=1,
            counterfactual_base_quantity=2.0,
            horizon_ms=30_000,
            minimum_raw_rows_per_partition=20,
            minimum_test_scored_observations=10,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-first-host-v1",
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            reason="first genuine PAPER-host champion",
        )


def test_writer_rejects_hydration_policy_mutation_and_publishes_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    proof, database, policy_path, *_ = _sources(monkeypatch, tmp_path)
    request_path = tmp_path / "request.json"
    original_encode = writer.encode_fast_first_champion_host_request

    def _mutating_encode(request):
        payload = original_encode(request)
        policy_path.write_text(
            policy_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return payload

    monkeypatch.setattr(
        writer,
        "encode_fast_first_champion_host_request",
        _mutating_encode,
    )

    with pytest.raises(ValueError, match="hydration policy.*changed|source.*changed"):
        writer.write_fast_first_champion_host_request_from_sources(
            proof_workspace_path=proof,
            observer_database_path=database,
            hydration_policy_path=policy_path,
            training_economics_overlay_path=tmp_path / "training-economics",
            training_execution_cost_policy_path=tmp_path / "training-cost-policy.json",
            request_destination=request_path,
            host_run_destination=tmp_path / "run",
            future_path_label_version=1,
            counterfactual_base_quantity=2.0,
            horizon_ms=30_000,
            minimum_raw_rows_per_partition=20,
            minimum_test_scored_observations=10,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-first-host-v1",
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            reason="first genuine PAPER-host champion",
        )
    assert not request_path.exists()


def test_writer_rejects_proof_workspace_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    proof, database, policy_path, _, proof_artifact = _sources(
        monkeypatch,
        tmp_path,
    )
    calls = 0

    def _read(_path):
        nonlocal calls
        calls += 1
        if calls == 1:
            return proof_artifact
        return SimpleNamespace(
            path=proof.resolve(),
            manifest=SimpleNamespace(
                release_source_sha="0" * 40,
                artifact_fingerprint_sha256="b" * 64,
            ),
        )

    monkeypatch.setattr(writer, "read_fast_proof_workspace", _read)
    request_path = tmp_path / "request.json"

    with pytest.raises(ValueError, match="proof workspace.*changed|source.*changed"):
        writer.write_fast_first_champion_host_request_from_sources(
            proof_workspace_path=proof,
            observer_database_path=database,
            hydration_policy_path=policy_path,
            training_economics_overlay_path=tmp_path / "training-economics",
            training_execution_cost_policy_path=tmp_path / "training-cost-policy.json",
            request_destination=request_path,
            host_run_destination=tmp_path / "run",
            future_path_label_version=1,
            counterfactual_base_quantity=2.0,
            horizon_ms=30_000,
            minimum_raw_rows_per_partition=20,
            minimum_test_scored_observations=10,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-first-host-v1",
            model_version_prefix="fl9-first",
            training_policy_version="fl9-first-naive-v1",
            reason="first genuine PAPER-host champion",
        )
    assert not request_path.exists()


def test_cli_builds_test_evaluation_policy_without_hidden_defaults(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    proof, database, policy_path, _, _ = _sources(monkeypatch, tmp_path)
    request_path = tmp_path / "request.json"
    host_run = tmp_path / "run"

    code = writer.main(
        [
            "--proof-workspace",
            str(proof),
            "--observer-database",
            str(database),
            "--hydration-policy",
            str(policy_path),
            "--training-economics-overlay",
            str(tmp_path / "training-economics"),
            "--training-execution-cost-policy",
            str(tmp_path / "training-cost-policy.json"),
            "--request-destination",
            str(request_path),
            "--host-run-destination",
            str(host_run),
            "--future-path-label-version",
            "1",
            "--counterfactual-base-quantity",
            "2.0",
            "--horizon-ms",
            "30000",
            "--minimum-raw-rows-per-partition",
            "20",
            "--minimum-test-scored-observations",
            "10",
            "--evaluation-policy-version",
            "fl9-first-test-evaluation-v1",
            "--probability-bucket-count",
            "10",
            "--liquidity-capacity-quote-boundary",
            "0",
            "--liquidity-capacity-quote-boundary",
            "1",
            "--liquidity-capacity-quote-boundary",
            "10",
            "--round-trip-cost-bps-boundary",
            "0",
            "--round-trip-cost-bps-boundary",
            "25",
            "--round-trip-cost-bps-boundary",
            "100",
            "--binary-log-loss-clip-epsilon",
            "0.000001",
            "--champion-version",
            "fl9-first-host-v1",
            "--model-version-prefix",
            "fl9-first",
            "--training-policy-version",
            "fl9-first-naive-v1",
            "--reason",
            "first genuine PAPER-host champion",
        ]
    )
    status = json.loads(capsys.readouterr().out)
    request = decode_fast_first_champion_host_request(
        request_path.read_text(encoding="utf-8")
    )

    assert code == 0
    assert status["status"] == "SUCCEEDED"
    assert status["release_source_sha"] == _RELEASE_SHA
    assert request.evaluation_policy == _evaluation_policy()


def test_writer_source_has_no_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_host_request_writer.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
        "sqlite3",
    ):
        assert forbidden not in source

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (
        'shreks-fast-first-champion-request = '
        '"shreks_brain.fast_first_champion_host_request_writer:main"'
        in pyproject
    )
