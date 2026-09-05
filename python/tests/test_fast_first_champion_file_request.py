from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

import shreks_brain.fast_first_champion.file_request as file_request_module
from fast_chronological_fixtures import HORIZON_MS, TEST_END, chronological_bundle
from fast_forecast_evaluation_fixtures import (
    build_run,
    chronological_policy,
    evaluation_contexts,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition
from shreks_brain.research.fast_training_bundle import (
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
    fast_training_execution_cost_policy_fingerprint_sha256,
)
from shreks_brain.fast_first_champion import (
    FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_VERSION,
    FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_VERSION,
    FastFirstChampionFileRequest,
    build_fast_first_champion_file_request,
    decode_fast_first_champion_file_request,
    encode_fast_first_champion_file_request,
    read_fast_first_champion_artifact,
    run_fast_first_champion_file_request,
    write_fast_first_champion_file_request,
    write_fast_forecast_evaluation_context_corpus,
    build_fast_forecast_evaluation_context_corpus,
)





def _training_economics_policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="first-champion-training-cost-v1",
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


def _context_corpus(tmp_path: Path) -> Path:
    _, run = build_run()
    corpus = build_fast_forecast_evaluation_context_corpus(
        evaluation_contexts(run)
    )
    path = tmp_path / "contexts.json"
    write_fast_forecast_evaluation_context_corpus(corpus, path)
    return path


def _runtime_bundle_for(features: Path):
    bundle = chronological_bundle()
    source_sha = hashlib.sha256(features.read_bytes()).hexdigest()
    feature_dataset = replace(
        bundle.features,
        source_sha256=source_sha,
    )
    provisional = replace(
        bundle.manifest,
        feature_source_jsonl_sha256=source_sha,
        bundle_fingerprint_sha256="0" * 64,
    )
    manifest = replace(
        provisional,
        bundle_fingerprint_sha256=bundle_logical_fingerprint_sha256(
            provisional
        ),
    )
    return replace(
        bundle,
        features=feature_dataset,
        manifest=manifest,
    )


def _request(tmp_path: Path):
    features = tmp_path / "features.jsonl"
    database = tmp_path / "shreks.db"
    features.write_text('{"sealed":"feature-source"}\n', encoding="utf-8")
    database.write_bytes(b"sealed-sqlite-source")
    contexts = _context_corpus(tmp_path)
    destination = tmp_path / "first-champion-artifact"

    request = build_fast_first_champion_file_request(
        feature_jsonl_path=features.name,
        observer_database_path=database.name,
        context_corpus_path=contexts.name,
        training_economics_overlay_path="training-economics",
        expected_training_economics_overlay_manifest_fingerprint_sha256="a" * 64,
        training_execution_cost_policy=_training_economics_policy(),
        training_execution_cost_policy_fingerprint_sha256=(
            fast_training_execution_cost_policy_fingerprint_sha256(
                _training_economics_policy()
            )
        ),
        destination_path=destination.name,
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        validation_policy=chronological_policy(),
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        champion_version="fl9-first-file-v1",
        decision_reference="operator-selection:file-fixture-v1",
        decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
        reason="explicit file-backed first champion selection",
        horizon_ms=HORIZON_MS,
        model_version_prefix="fl9-file-first",
        training_policy_version="fl9-file-naive-v1",
        minimum_test_scored_observations=1,
    )
    request_path = tmp_path / "request.json"
    write_fast_first_champion_file_request(request, request_path)
    return request, request_path, features, database, contexts, destination


def test_file_request_is_canonical_self_authenticating_and_round_trips(
    tmp_path: Path,
) -> None:
    request, request_path, *_ = _request(tmp_path)

    assert type(request) is FastFirstChampionFileRequest
    assert request.schema_name == FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_NAME
    assert request.schema_version == FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_VERSION

    payload = request_path.read_text(encoding="utf-8")
    assert payload == encode_fast_first_champion_file_request(request)
    assert payload.endswith("\n")
    assert '"$float"' in payload
    assert decode_fast_first_champion_file_request(payload) == request
    assert encode_fast_first_champion_file_request(
        decode_fast_first_champion_file_request(payload)
    ) == payload

    legacy = json.loads(payload)
    legacy["schema_version"] = 1
    for key in (
        "training_economics_overlay_path",
        "expected_training_economics_overlay_manifest_fingerprint_sha256",
        "training_execution_cost_policy",
        "training_execution_cost_policy_fingerprint_sha256",
    ):
        legacy["request"].pop(key)
    with pytest.raises(ValueError, match="schema_version|schema"):
        decode_fast_first_champion_file_request(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")) + "\n"
        )

    document = json.loads(payload)
    assert document["request"]["evaluation_policy"]["partition"] == "TEST"
    assert document["request"]["training_economics_overlay_path"] == "training-economics"
    assert document["request"][
        "expected_training_economics_overlay_manifest_fingerprint_sha256"
    ] == "a" * 64
    assert document["request"][
        "training_execution_cost_policy_fingerprint_sha256"
    ] == fast_training_execution_cost_policy_fingerprint_sha256(
        _training_economics_policy()
    )
    assert set(document["request"]["training_execution_cost_policy"]) == {
        "version",
        "additional_entry_slippage_bps",
        "additional_exit_slippage_bps",
        "entry_latency_bps",
        "exit_latency_bps",
        "entry_network_fee_quote",
        "exit_network_fee_quote",
        "entry_priority_fee_quote",
        "exit_priority_fee_quote",
        "entry_expected_failure_cost_quote",
        "exit_expected_failure_cost_quote",
    }
    assert document["request_fingerprint_sha256"] == (
        request.request_fingerprint_sha256
    )


def test_file_request_runs_runtime_bundle_and_atomically_publishes_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request, request_path, features, database, contexts, destination = _request(
        tmp_path
    )
    bundle = _runtime_bundle_for(features)
    calls = []

    def _runtime_bundle(**kwargs):
        calls.append(kwargs)
        return bundle

    monkeypatch.setattr(
        file_request_module,
        "build_fast_training_bundle_from_runtime_sources",
        _runtime_bundle,
    )

    artifact = run_fast_first_champion_file_request(request_path)
    reopened = read_fast_first_champion_artifact(destination)

    assert reopened.manifest == artifact.manifest
    assert reopened.context_corpus == artifact.context_corpus
    assert reopened.champion == artifact.champion
    assert reopened.evaluation_reports == artifact.evaluation_reports
    assert artifact.manifest.schema_name == FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_NAME
    assert artifact.manifest.schema_version == FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_VERSION
    assert artifact.manifest.request_fingerprint_sha256 == (
        request.request_fingerprint_sha256
    )
    assert artifact.manifest.training_bundle_fingerprint_sha256 == (
        bundle.manifest.bundle_fingerprint_sha256
    )
    assert artifact.manifest.context_fingerprint_sha256 == (
        file_request_module.read_fast_forecast_evaluation_context_corpus(
            contexts
        ).context_fingerprint_sha256
    )
    assert artifact.manifest.champion_fingerprint_sha256 == (
        artifact.champion.champion_fingerprint_sha256
    )
    assert len(artifact.evaluation_reports) == 5
    assert len(artifact.manifest.evaluation_reports) == 5

    assert calls == [
        {
            "feature_jsonl_path": features.resolve(),
            "sqlite_path": database.resolve(),
            "future_path_label_version": 1,
            "counterfactual_base_quantity": 2.0,
            "training_economics_overlay_path": (
                tmp_path / "training-economics"
            ).resolve(),
            "training_execution_cost_policy": _training_economics_policy(),
        }
    ]

    assert {entry.name for entry in destination.iterdir()} == {
        "request.json",
        "contexts.json",
        "champion.json",
        "manifest.json",
        *{
            f"evaluation-{report.target.value}@{report.horizon_ms}ms.json"
            for report in artifact.evaluation_reports
        },
    }


def test_file_request_rejects_source_mutation_and_leaves_no_partial_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, request_path, features, _, _, destination = _request(tmp_path)
    bundle = _runtime_bundle_for(features)

    def _runtime_bundle(**_kwargs):
        features.write_bytes(features.read_bytes() + b"mutation")
        return bundle

    monkeypatch.setattr(
        file_request_module,
        "build_fast_training_bundle_from_runtime_sources",
        _runtime_bundle,
    )

    with pytest.raises(ValueError, match="source.*changed|fingerprint.*changed"):
        run_fast_first_champion_file_request(request_path)
    assert not destination.exists()


def test_file_request_authenticates_sqlite_wal_and_request_bytes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, request_path, _, database, _, destination = _request(tmp_path)
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"wal-before")
    bundle = _runtime_bundle_for(tmp_path / "features.jsonl")

    def _runtime_bundle(**_kwargs):
        wal.write_bytes(b"wal-after")
        request_path.write_text(
            request_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )
        return bundle

    monkeypatch.setattr(
        file_request_module,
        "build_fast_training_bundle_from_runtime_sources",
        _runtime_bundle,
    )

    with pytest.raises(ValueError, match="source.*changed|request.*changed|fingerprint"):
        run_fast_first_champion_file_request(request_path)
    assert not destination.exists()


def test_file_request_refuses_existing_destination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, request_path, _, _, _, destination = _request(tmp_path)
    destination.mkdir()

    monkeypatch.setattr(
        file_request_module,
        "build_fast_training_bundle_from_runtime_sources",
        lambda **_kwargs: chronological_bundle(),
    )

    with pytest.raises(FileExistsError, match="exists|overwrite"):
        run_fast_first_champion_file_request(request_path)


def test_first_champion_artifact_reader_rejects_report_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, request_path, _, _, _, destination = _request(tmp_path)
    monkeypatch.setattr(
        file_request_module,
        "build_fast_training_bundle_from_runtime_sources",
        lambda **_kwargs: _runtime_bundle_for(tmp_path / "features.jsonl"),
    )
    artifact = run_fast_first_champion_file_request(request_path)
    report = next(
        destination
        / f"evaluation-{value.target.value}@{value.horizon_ms}ms.json"
        for value in artifact.evaluation_reports
    )
    report.write_bytes(report.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="fingerprint|hash|canonical|invalid"):
        read_fast_first_champion_artifact(destination)


def test_file_request_source_has_no_network_trading_promotion_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion"
        / "file_request.py"
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
    ):
        assert forbidden not in source
