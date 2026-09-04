from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_first_champion_host_run as host_module
from fast_chronological_fixtures import HORIZON_MS, chronological_bundle
from fast_forecast_evaluation_fixtures import evaluation_policy
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition
from shreks_brain.fast_first_champion_host_run import (
    FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_VERSION,
    FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK,
    FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_VERSION,
    build_fast_first_champion_host_request,
    decode_fast_first_champion_host_request,
    encode_fast_first_champion_host_request,
    read_fast_first_champion_host_run,
    run_fast_first_champion_host_request,
)
from shreks_brain.research.fast_training_bundle import (
    bundle_logical_fingerprint_sha256,
)


RELEASE_SHA = "21a4fcf77eb66e6589088f5951a60f66ba5fa76f"
POLICY_FP = "4" * 64
SELECTION_AT = 4_000


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bundle_for_source(source_sha: str):
    bundle = chronological_bundle()
    features = replace(bundle.features, source_sha256=source_sha)
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
    return replace(bundle, features=features, manifest=manifest)


def _request(tmp_path: Path):
    return build_fast_first_champion_host_request(
        proof_workspace_path="proof-source",
        observer_database_path="shreks.db",
        hydration_policy_path="hydration-policy.json",
        destination_path="host-run",
        expected_release_source_sha=RELEASE_SHA,
        expected_hydration_policy_fingerprint_sha256=POLICY_FP,
        selection_clock=FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK,
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        horizon_ms=HORIZON_MS,
        minimum_raw_rows_per_partition=2,
        minimum_test_scored_observations=2,
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        champion_version="fl9-host-first-v1",
        model_version_prefix="fl9-host-first",
        training_policy_version="fl9-host-naive-v1",
        reason="sealed host-clock first champion selection",
    )


def _install_fakes(monkeypatch, tmp_path: Path):
    proof = tmp_path / "proof-source"
    proof.mkdir()
    feature_path = proof / "features.jsonl"
    feature_path.write_bytes(b"sealed-host-feature-jsonl\n")
    (proof / "manifest.json").write_bytes(b"sealed-proof-manifest\n")
    feature_sha = _sha(feature_path.read_bytes())
    bundle = _bundle_for_source(feature_sha)
    proof_manifest = SimpleNamespace(
        release_source_sha=RELEASE_SHA,
        artifact_fingerprint_sha256="2" * 64,
        feature_jsonl_sha256=feature_sha,
        feature_logical_fingerprint_sha256=(
            bundle.features.logical_fingerprint_sha256
        ),
    )
    proof_artifact = SimpleNamespace(
        path=proof,
        manifest=proof_manifest,
        features=bundle.features,
    )
    monkeypatch.setattr(
        host_module,
        "read_fast_proof_workspace",
        lambda _path: proof_artifact,
    )
    monkeypatch.setattr(
        host_module,
        "build_fast_training_bundle_from_runtime_sources",
        lambda **_kwargs: bundle,
    )

    hydration = tmp_path / "hydration-policy.json"
    hydration.write_text("sealed-hydration-policy\n", encoding="utf-8")
    hydration_policy = object()
    monkeypatch.setattr(
        host_module,
        "decode_fast_forecast_context_hydration_policy",
        lambda _payload: hydration_policy,
    )
    monkeypatch.setattr(
        host_module,
        "fast_forecast_context_hydration_policy_fingerprint_sha256",
        lambda _policy: POLICY_FP,
    )
    monkeypatch.setattr(
        host_module,
        "_host_wall_clock_unix_ms",
        lambda: SELECTION_AT,
    )

    prep_holder = {}

    def _prepare(**kwargs):
        destination = Path(kwargs["destination"])
        destination.mkdir()
        (destination / "placeholder").write_bytes(b"prepared")
        plan = prep_holder["plan"]
        request = SimpleNamespace(
            validation_policy=plan.validation_policy,
            evaluation_policy=kwargs["evaluation_policy"],
            horizon_ms=plan.horizon_ms,
            decided_at_unix_ms=plan.selection_at_unix_ms,
            minimum_test_scored_observations=(
                plan.minimum_test_scored_observations
            ),
            decision_reference=kwargs["decision_reference"],
            reason=kwargs["reason"],
        )
        context_hydration = SimpleNamespace(
            manifest=SimpleNamespace(
                validation_policy=plan.validation_policy,
                hydration_policy_fingerprint_sha256=POLICY_FP,
                context_fingerprint_sha256="6" * 64,
            )
        )
        artifact = SimpleNamespace(
            path=destination,
            manifest=SimpleNamespace(
                proof_workspace_release_source_sha=RELEASE_SHA,
                proof_workspace_artifact_fingerprint_sha256="2" * 64,
                training_bundle_fingerprint_sha256=(
                    bundle.manifest.bundle_fingerprint_sha256
                ),
                validation_policy_fingerprint_sha256="a" * 64,
                hydration_policy_fingerprint_sha256=POLICY_FP,
                context_fingerprint_sha256="6" * 64,
                artifact_fingerprint_sha256="7" * 64,
                champion_fingerprint_sha256="8" * 64,
                champion_version=kwargs["champion_version"],
                selection_decision_reference=kwargs[
                    "decision_reference"
                ],
                selection_decided_at_unix_ms=kwargs[
                    "decided_at_unix_ms"
                ],
                selection_reason=kwargs["reason"],
            ),
            request=request,
            context_hydration=context_hydration,
            first_champion=SimpleNamespace(
                champion=SimpleNamespace(
                    champion_fingerprint_sha256="8" * 64,
                    champion_version=kwargs["champion_version"],
                )
            ),
        )
        prep_holder["artifact"] = artifact
        return artifact

    monkeypatch.setattr(
        host_module,
        "prepare_fast_first_champion_evidence",
        _prepare,
    )
    monkeypatch.setattr(
        host_module,
        "read_fast_first_champion_preparation",
        lambda _path: prep_holder["artifact"],
    )

    original_plan_builder = host_module.build_fast_first_champion_evidence_plan

    def _plan(**kwargs):
        plan = original_plan_builder(**kwargs)
        prep_holder["plan"] = plan
        return plan

    monkeypatch.setattr(
        host_module,
        "build_fast_first_champion_evidence_plan",
        _plan,
    )
    return bundle, proof_artifact, prep_holder


def test_host_request_codec_is_canonical_and_authenticated(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    payload = encode_fast_first_champion_host_request(request)

    assert request.schema_name == FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_NAME
    assert request.schema_version == FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_VERSION
    assert request.selection_clock == FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK
    assert '"$float"' in payload
    decoded = decode_fast_first_champion_host_request(payload)
    assert decoded == request
    assert encode_fast_first_champion_host_request(decoded) == payload


def test_host_run_captures_clock_plans_and_cross_links_preparation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle, proof, _ = _install_fakes(monkeypatch, tmp_path)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-host-db")
    request_path = tmp_path / "host-request.json"
    request_path.write_text(
        encode_fast_first_champion_host_request(_request(tmp_path)),
        encoding="utf-8",
    )

    artifact = run_fast_first_champion_host_request(request_path)
    reopened = read_fast_first_champion_host_run(tmp_path / "host-run")

    assert reopened.manifest == artifact.manifest
    assert artifact.manifest.schema_name == FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_NAME
    assert artifact.manifest.schema_version == FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_VERSION
    assert artifact.manifest.selection_clock == FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK
    assert artifact.manifest.selection_at_unix_ms == SELECTION_AT
    assert artifact.manifest.proof_workspace_artifact_fingerprint_sha256 == (
        proof.manifest.artifact_fingerprint_sha256
    )
    assert artifact.manifest.training_bundle_fingerprint_sha256 == (
        bundle.manifest.bundle_fingerprint_sha256
    )
    assert artifact.plan.selection_at_unix_ms == SELECTION_AT
    assert artifact.plan.validation_policy == (
        artifact.preparation.request.validation_policy
    )
    assert artifact.preparation.request.decision_reference == (
        f"first-champion-plan:{artifact.plan.plan_fingerprint_sha256}"
    )
    assert {value.name for value in (tmp_path / "host-run").iterdir()} == {
        "request.json",
        "hydration-policy.json",
        "plan.json",
        "preparation",
        "manifest.json",
    }


def test_host_run_rejects_hydration_policy_fingerprint_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(
        host_module,
        "fast_forecast_context_hydration_policy_fingerprint_sha256",
        lambda _policy: "5" * 64,
    )
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-host-db")
    request_path = tmp_path / "host-request.json"
    request_path.write_text(
        encode_fast_first_champion_host_request(_request(tmp_path)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hydration.*fingerprint"):
        run_fast_first_champion_host_request(request_path)
    assert not (tmp_path / "host-run").exists()


def test_host_run_rejects_source_request_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, _, holder = _install_fakes(monkeypatch, tmp_path)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-host-db")
    request_path = tmp_path / "host-request.json"
    request_path.write_text(
        encode_fast_first_champion_host_request(_request(tmp_path)),
        encoding="utf-8",
    )
    original_prepare = host_module.prepare_fast_first_champion_evidence

    def _mutating_prepare(**kwargs):
        artifact = original_prepare(**kwargs)
        request_path.write_bytes(request_path.read_bytes() + b"mutation")
        return artifact

    monkeypatch.setattr(
        host_module,
        "prepare_fast_first_champion_evidence",
        _mutating_prepare,
    )

    with pytest.raises(ValueError, match="request.*changed|source.*changed"):
        run_fast_first_champion_host_request(request_path)
    assert holder.get("artifact") is not None
    assert not (tmp_path / "host-run").exists()


def test_host_reader_rejects_plan_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_fakes(monkeypatch, tmp_path)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-host-db")
    request_path = tmp_path / "host-request.json"
    request_path.write_text(
        encode_fast_first_champion_host_request(_request(tmp_path)),
        encoding="utf-8",
    )
    run_fast_first_champion_host_request(request_path)

    plan_path = tmp_path / "host-run" / "plan.json"
    plan_path.write_bytes(plan_path.read_bytes() + b"tamper")
    with pytest.raises(
        ValueError,
        match="hash|fingerprint|canonical|JSON|trailing newline",
    ):
        read_fast_first_champion_host_run(tmp_path / "host-run")


def test_host_run_exposes_one_console_command_and_no_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_host_run.py"
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
        'shreks-fast-first-champion-run = "shreks_brain.fast_first_champion_host_run:main"'
        in pyproject
    )
