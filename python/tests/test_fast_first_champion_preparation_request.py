from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_first_champion_preparation_request as request_module
from fast_chronological_fixtures import HORIZON_MS, TEST_END
from fast_forecast_evaluation_fixtures import (
    chronological_policy,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition
from shreks_brain.fast_first_champion import (
    build_fast_first_champion_file_request,
    write_fast_first_champion_file_request,
)
from shreks_brain.fast_first_champion_preparation_request import (
    FAST_FIRST_CHAMPION_PREPARATION_REQUEST_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_PREPARATION_REQUEST_SCHEMA_VERSION,
    FastFirstChampionPreparationRequest,
    build_fast_first_champion_preparation_request,
    decode_fast_first_champion_preparation_request,
    encode_fast_first_champion_preparation_request,
    main,
    run_fast_first_champion_preparation_request,
    write_fast_first_champion_preparation_request,
)


def _plan(tmp_path: Path, database: Path) -> Path:
    plan = build_fast_first_champion_file_request(
        feature_jsonl_path="proof-workspace/features.jsonl",
        observer_database_path=str(database.resolve()),
        context_corpus_path="context-hydration/contexts.json",
        destination_path="first-champion",
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        validation_policy=chronological_policy(),
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        champion_version="fl9-host-first-v1",
        decision_reference="operator-selection:host-first-v1",
        decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
        reason="explicit host first champion selection",
        horizon_ms=HORIZON_MS,
        model_version_prefix="fl9-host-first",
        training_policy_version="fl9-host-naive-v1",
        minimum_test_scored_observations=1,
    )
    path = tmp_path / "first-champion-plan.json"
    write_fast_first_champion_file_request(plan, path)
    return path


def _outer_request(tmp_path: Path):
    proof = tmp_path / "proof"
    proof.mkdir()
    (proof / "features.jsonl").write_text("sealed\n", encoding="utf-8")
    database = tmp_path / "shreks.db"
    database.write_bytes(b"sealed-db")
    hydration_policy = tmp_path / "hydration-policy.json"
    hydration_policy.write_text('{"sealed":"policy"}\n', encoding="utf-8")
    plan = _plan(tmp_path, database)
    destination = tmp_path / "prepared"
    request = build_fast_first_champion_preparation_request(
        proof_workspace_path=proof.name,
        observer_database_path=database.name,
        hydration_policy_path=hydration_policy.name,
        first_champion_request_path=plan.name,
        destination_path=destination.name,
    )
    path = tmp_path / "prepare-request.json"
    write_fast_first_champion_preparation_request(request, path)
    return (
        request,
        path,
        proof,
        database,
        hydration_policy,
        plan,
        destination,
    )


def test_preparation_request_is_canonical_and_self_authenticating(
    tmp_path: Path,
) -> None:
    request, path, *_ = _outer_request(tmp_path)

    assert type(request) is FastFirstChampionPreparationRequest
    assert (
        request.schema_name
        == FAST_FIRST_CHAMPION_PREPARATION_REQUEST_SCHEMA_NAME
    )
    assert (
        request.schema_version
        == FAST_FIRST_CHAMPION_PREPARATION_REQUEST_SCHEMA_VERSION
    )

    payload = path.read_text(encoding="utf-8")
    assert payload == encode_fast_first_champion_preparation_request(request)
    assert payload.endswith("\n")
    assert decode_fast_first_champion_preparation_request(payload) == request
    assert encode_fast_first_champion_preparation_request(
        decode_fast_first_champion_preparation_request(payload)
    ) == payload

    document = json.loads(payload)
    assert set(document["request"]) == {
        "proof_workspace_path",
        "observer_database_path",
        "hydration_policy_path",
        "first_champion_request_path",
        "destination_path",
    }
    assert document["request_fingerprint_sha256"] == (
        request.request_fingerprint_sha256
    )


def test_runner_reuses_sealed_child_codecs_and_exact_plan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        _,
        request_path,
        proof,
        database,
        policy_path,
        plan_path,
        destination,
    ) = _outer_request(tmp_path)

    policy = object()
    monkeypatch.setattr(
        request_module,
        "decode_fast_forecast_context_hydration_policy",
        lambda payload: (
            policy
            if payload == policy_path.read_text(encoding="utf-8")
            else None
        ),
    )
    calls = []

    def _prepare(**kwargs):
        calls.append(kwargs)
        destination.mkdir()
        return SimpleNamespace(
            path=destination,
            request=kwargs["first_champion_request_plan"],
            context_hydration=SimpleNamespace(policy=policy),
            manifest=SimpleNamespace(
                artifact_fingerprint_sha256="1" * 64,
                champion_fingerprint_sha256="2" * 64,
            ),
            first_champion=SimpleNamespace(
                manifest=SimpleNamespace(
                    champion_fingerprint_sha256="2" * 64
                )
            ),
        )

    monkeypatch.setattr(
        request_module,
        "prepare_fast_first_champion_evidence_from_plan",
        _prepare,
    )

    artifact = run_fast_first_champion_preparation_request(request_path)
    expected_plan = request_module.decode_fast_first_champion_file_request(
        plan_path.read_text(encoding="utf-8")
    )

    assert artifact.path == destination
    assert artifact.request == expected_plan
    assert calls == [
        {
            "proof_workspace_path": proof.resolve(),
            "observer_database_path": database.resolve(),
            "destination": destination.resolve(),
            "hydration_policy": policy,
            "first_champion_request_plan": expected_plan,
        }
    ]


def test_runner_rejects_plan_that_is_not_exact_internal_preparation_plan(
    tmp_path: Path,
) -> None:
    (
        _,
        request_path,
        _,
        database,
        _,
        plan_path,
        destination,
    ) = _outer_request(tmp_path)
    plan_path.unlink()
    bad = build_fast_first_champion_file_request(
        feature_jsonl_path="external/features.jsonl",
        observer_database_path=str(database.resolve()),
        context_corpus_path="context-hydration/contexts.json",
        destination_path="first-champion",
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        validation_policy=chronological_policy(),
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        champion_version="fl9-host-first-v1",
        decision_reference="operator-selection:host-first-v1",
        decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
        reason="explicit host first champion selection",
        horizon_ms=HORIZON_MS,
        model_version_prefix="fl9-host-first",
        training_policy_version="fl9-host-naive-v1",
        minimum_test_scored_observations=1,
    )
    write_fast_first_champion_file_request(bad, plan_path)

    with pytest.raises(ValueError, match="internal|plan|feature"):
        run_fast_first_champion_preparation_request(request_path)
    assert not destination.exists()


def test_runner_rejects_plan_database_path_that_is_not_exact_resolved_source(
    tmp_path: Path,
) -> None:
    (
        _,
        request_path,
        _,
        database,
        _,
        plan_path,
        destination,
    ) = _outer_request(tmp_path)
    plan_path.unlink()
    bad = build_fast_first_champion_file_request(
        feature_jsonl_path="proof-workspace/features.jsonl",
        observer_database_path=database.name,
        context_corpus_path="context-hydration/contexts.json",
        destination_path="first-champion",
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        validation_policy=chronological_policy(),
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        champion_version="fl9-host-first-v1",
        decision_reference="operator-selection:host-first-v1",
        decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
        reason="explicit host first champion selection",
        horizon_ms=HORIZON_MS,
        model_version_prefix="fl9-host-first",
        training_policy_version="fl9-host-naive-v1",
        minimum_test_scored_observations=1,
    )
    write_fast_first_champion_file_request(bad, plan_path)

    with pytest.raises(ValueError, match="database.*absolute|database.*source"):
        run_fast_first_champion_preparation_request(request_path)
    assert not destination.exists()


def test_runner_removes_preparation_if_outer_policy_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        _,
        request_path,
        _,
        _,
        policy_path,
        _,
        destination,
    ) = _outer_request(tmp_path)

    policy = object()
    monkeypatch.setattr(
        request_module,
        "decode_fast_forecast_context_hydration_policy",
        lambda _payload: policy,
    )

    def _prepare(**kwargs):
        destination.mkdir()
        policy_path.write_text(
            '{"sealed":"mutated"}\n',
            encoding="utf-8",
        )
        return SimpleNamespace(
            path=destination,
            request=kwargs["first_champion_request_plan"],
            context_hydration=SimpleNamespace(policy=policy),
            manifest=SimpleNamespace(
                artifact_fingerprint_sha256="1" * 64,
                champion_fingerprint_sha256="2" * 64,
            ),
        )

    monkeypatch.setattr(
        request_module,
        "prepare_fast_first_champion_evidence_from_plan",
        _prepare,
    )

    with pytest.raises(ValueError, match="policy.*changed|source.*changed"):
        run_fast_first_champion_preparation_request(request_path)
    assert not destination.exists()


@pytest.mark.parametrize(
    ("message", "expected_status", "expected_code"),
    (
        (
            "TEST scored evidence does not meet the explicit minimum",
            "INSUFFICIENT_EVIDENCE",
            2,
        ),
        (
            "selected forecast evaluation partition contains zero scorable observations",
            "INSUFFICIENT_EVIDENCE",
            2,
        ),
        (
            "first champion has no target-mature pre-selection decisions",
            "INSUFFICIENT_EVIDENCE",
            2,
        ),
        (
            "database source changed during execution",
            "FAILED",
            1,
        ),
    ),
)
def test_cli_emits_machine_readable_fail_closed_status(
    monkeypatch,
    capsys,
    message: str,
    expected_status: str,
    expected_code: int,
) -> None:
    monkeypatch.setattr(
        request_module,
        "run_fast_first_champion_preparation_request",
        lambda _path: (_ for _ in ()).throw(ValueError(message)),
    )

    code = main(["request.json"])
    captured = capsys.readouterr()
    document = json.loads(captured.out)

    assert code == expected_code
    assert document["status"] == expected_status
    assert document["message"] == message
    assert captured.err == ""


def test_cli_success_is_machine_readable(monkeypatch, capsys) -> None:
    artifact = SimpleNamespace(
        path=Path("/tmp/prepared"),
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256="a" * 64,
            champion_fingerprint_sha256="b" * 64,
            request_fingerprint_sha256="c" * 64,
        ),
    )
    monkeypatch.setattr(
        request_module,
        "run_fast_first_champion_preparation_request",
        lambda _path: artifact,
    )

    code = main(["request.json"])
    document = json.loads(capsys.readouterr().out)

    assert code == 0
    assert document == {
        "schema_name": "shreks.fast_first_champion_preparation_run_result",
        "schema_version": 1,
        "status": "SUCCESS",
        "preparation_path": "/tmp/prepared",
        "preparation_artifact_fingerprint_sha256": "a" * 64,
        "champion_fingerprint_sha256": "b" * 64,
        "request_fingerprint_sha256": "c" * 64,
    }


def test_request_source_has_no_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_preparation_request.py"
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
        'shreks-fast-first-champion-preparation = '
        '"shreks_brain.fast_first_champion_preparation_request:main"'
        in pyproject
    )
