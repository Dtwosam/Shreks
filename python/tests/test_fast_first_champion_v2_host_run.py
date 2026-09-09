from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path

import pytest

from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_first_champion_v2.host_request import (
    FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_VERSION,
    FastFirstChampionV2HostRequest,
    build_fast_first_champion_v2_host_request,
    decode_fast_first_champion_v2_host_request,
    encode_fast_first_champion_v2_host_request,
    write_fast_first_champion_v2_host_request,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
    fast_training_execution_cost_policy_fingerprint_sha256,
)


RELEASE_SHA = "1" * 40
COHORT_FP = (
    "bd6875c4d65ee9b2eb67783e7ecfa233"
    "2305bf6c3251f5d474e66465fd17d93a"
)
HYDRATION_FP = "2" * 64
OVERLAY_FP = "3" * 64


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


def _evaluation_policy() -> FastForecastEvaluationPolicy:
    return FastForecastEvaluationPolicy(
        version="fl9-v2-host-test-eval-v1",
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=10,
        liquidity_capacity_quote_boundaries=(10.0, 100.0),
        round_trip_cost_bps_boundaries=(25.0, 50.0),
        binary_log_loss_clip_epsilon=1e-12,
    )


def _request(**overrides) -> FastFirstChampionV2HostRequest:
    cost = _cost_policy()
    values = dict(
        proof_workspace_path="/var/lib/shreks/fast-proof-v2",
        observer_database_path="/var/lib/shreks/shreks.db",
        cohort_artifact_path="/var/lib/shreks/fl9-v2-cohort",
        expected_cohort_artifact_fingerprint_sha256=COHORT_FP,
        hydration_policy_path="/var/lib/shreks/fast-context-policy.json",
        expected_hydration_policy_fingerprint_sha256=HYDRATION_FP,
        training_economics_overlay_path="/var/lib/shreks/training-economics",
        expected_training_economics_overlay_manifest_fingerprint_sha256=(
            OVERLAY_FP
        ),
        training_execution_cost_policy=cost,
        training_execution_cost_policy_fingerprint_sha256=(
            fast_training_execution_cost_policy_fingerprint_sha256(cost)
        ),
        destination_path="/var/lib/shreks/fl9-v2-first-champion-evidence",
        expected_release_source_sha=RELEASE_SHA,
        future_path_label_version=1,
        counterfactual_base_quantity=1.0,
        evaluation_policy=_evaluation_policy(),
        champion_version="fl9-v2-first-champion-runtime-v1",
        model_version_prefix="fl9-v2-first-champion",
        training_policy_version="fl9-v2-first-champion-training-v1",
        reason="frozen FL9 V2 first-champion production evidence",
    )
    values.update(overrides)
    return build_fast_first_champion_v2_host_request(**values)


def test_v2_host_request_contract_is_exact_and_has_no_tuning_fields() -> None:
    request = _request()

    assert (
        request.schema_name
        == FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_NAME
    )
    assert (
        request.schema_version
        == FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_VERSION
    )
    assert request.expected_cohort_artifact_fingerprint_sha256 == COHORT_FP
    assert request.expected_release_source_sha == RELEASE_SHA

    names = {value.name for value in fields(FastFirstChampionV2HostRequest)}
    for forbidden in (
        "horizon_ms",
        "selection_at_unix_ms",
        "training_started_at_unix_ms",
        "training_ended_at_unix_ms",
        "validation_started_at_unix_ms",
        "validation_ended_at_unix_ms",
        "test_started_at_unix_ms",
        "test_ended_at_unix_ms",
        "minimum_natural_test_scored_observations",
        "minimum_unseen_mint_test_scored_observations",
        "minimum_test_scored_observations",
    ):
        assert forbidden not in names


def test_v2_host_request_codec_is_canonical_and_authenticated() -> None:
    request = _request()
    payload = encode_fast_first_champion_v2_host_request(request)

    assert '"$float"' in payload
    decoded = decode_fast_first_champion_v2_host_request(payload)
    assert decoded == request
    assert encode_fast_first_champion_v2_host_request(decoded) == payload

    document = json.loads(payload)
    document["request"]["unexpected"] = 1
    with pytest.raises(ValueError, match="unknown|fields|incompatible"):
        decode_fast_first_champion_v2_host_request(
            json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        )


def test_v2_host_request_rejects_duplicate_keys_and_raw_non_finite() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        decode_fast_first_champion_v2_host_request(
            '{"x":1,"x":2}\n'
        )
    with pytest.raises(ValueError, match="non-finite|constant|JSON"):
        decode_fast_first_champion_v2_host_request(
            '{"x":NaN}\n'
        )


def test_v2_host_request_rejects_wrong_frozen_authority() -> None:
    with pytest.raises(ValueError, match="cohort.*fingerprint|frozen"):
        _request(
            expected_cohort_artifact_fingerprint_sha256="f" * 64
        )
    with pytest.raises(ValueError, match="release.*SHA|source SHA"):
        _request(expected_release_source_sha="not-a-release")
    with pytest.raises(ValueError, match="destination.*unsafe|safe"):
        _request(destination_path="../escape")


def test_v2_host_request_writer_refuses_overwrite(tmp_path: Path) -> None:
    request = _request(destination_path=str(tmp_path / "evidence"))
    destination = tmp_path / "request.json"

    write_fast_first_champion_v2_host_request(request, destination)
    first = destination.read_bytes()
    assert decode_fast_first_champion_v2_host_request(
        first.decode("utf-8")
    ) == request

    with pytest.raises(FileExistsError, match="exists|overwrite"):
        write_fast_first_champion_v2_host_request(request, destination)
    assert destination.read_bytes() == first


def test_v2_host_run_uses_frozen_cohort_order_and_no_host_clock(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    import shreks_brain.fast_first_champion_v2.host_run as host_module
    from shreks_brain.fast_first_champion_v2.host_run import (
        run_fast_first_champion_v2_host_request,
    )
    from shreks_brain.fast_first_champion_v2.models import (
        FastFirstChampionV2Policy,
    )

    policy = FastFirstChampionV2Policy()
    proof = tmp_path / "proof"
    proof.mkdir()
    (proof / "features.jsonl").write_text("{}\n", encoding="utf-8")
    database = tmp_path / "observer.db"
    database.write_bytes(b"sqlite")
    cohort_path = tmp_path / "cohort"
    cohort_path.mkdir()
    hydration_path = tmp_path / "hydration.json"
    hydration_path.write_text("{}\n", encoding="utf-8")
    overlay_path = tmp_path / "overlay"
    overlay_path.mkdir()
    (overlay_path / "manifest.json").write_text("{}\n", encoding="utf-8")
    (overlay_path / "rows.jsonl").write_text("{}\n", encoding="utf-8")
    destination = tmp_path / "evidence"

    request = _request(
        proof_workspace_path=str(proof),
        observer_database_path=str(database),
        cohort_artifact_path=str(cohort_path),
        hydration_policy_path=str(hydration_path),
        training_economics_overlay_path=str(overlay_path),
        destination_path=str(destination),
    )
    request_path = tmp_path / "request.json"
    write_fast_first_champion_v2_host_request(request, request_path)

    events: list[str] = []
    feature_sha = "6" * 64
    feature_logical = "7" * 64
    bundle_fp = "8" * 64
    champion_fp = "9" * 64
    evidence_fp = "a" * 64

    proof_artifact = SimpleNamespace(
        manifest=SimpleNamespace(
            release_source_sha=RELEASE_SHA,
            feature_jsonl_sha256=feature_sha,
            feature_logical_fingerprint_sha256=feature_logical,
        )
    )
    cohort = SimpleNamespace(
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256=COHORT_FP,
            accepted_identity_fingerprint_sha256=(
                policy.expected_accepted_identity_fingerprint_sha256
            ),
            selection_at_unix_ms=policy.selection_at_unix_ms,
            horizon_ms=policy.horizon_ms,
            training_cut_unix_ms=policy.training_ended_at_unix_ms,
            validation_cut_unix_ms=policy.validation_ended_at_unix_ms,
            test_end_unix_ms=policy.test_ended_at_unix_ms,
        )
    )
    bundle = SimpleNamespace(
        features=SimpleNamespace(
            source_sha256=feature_sha,
            logical_fingerprint_sha256=feature_logical,
        ),
        manifest=SimpleNamespace(
            bundle_fingerprint_sha256=bundle_fp,
        ),
    )
    hydration_result = SimpleNamespace(
        context_corpus=SimpleNamespace(contexts=("ctx",)),
    )
    build = SimpleNamespace(
        training_bundle_fingerprint_sha256=bundle_fp,
        champion=SimpleNamespace(
            champion_fingerprint_sha256=champion_fp,
        ),
    )
    evidence = SimpleNamespace(
        path=destination,
        manifest=SimpleNamespace(
            cohort_artifact_fingerprint_sha256=COHORT_FP,
            training_bundle_fingerprint_sha256=bundle_fp,
            champion_fingerprint_sha256=champion_fp,
            artifact_fingerprint_sha256=evidence_fp,
        ),
        champion=build.champion,
    )

    monkeypatch.setattr(
        host_module,
        "read_fast_proof_workspace",
        lambda _path: events.append("release") or proof_artifact,
    )
    monkeypatch.setattr(
        host_module,
        "read_fl9_v2_cohort_acceptance",
        lambda _path: events.append("cohort") or cohort,
    )
    monkeypatch.setattr(
        host_module,
        "_validate_cohort",
        lambda _cohort, _policy: events.append("cohort-verify"),
    )
    monkeypatch.setattr(
        host_module,
        "read_fast_training_economics_overlay",
        lambda _path: SimpleNamespace(
            manifest=SimpleNamespace(
                manifest_fingerprint_sha256=OVERLAY_FP,
            )
        ),
    )
    hydration_policy = object()
    monkeypatch.setattr(
        host_module,
        "decode_fast_forecast_context_hydration_policy",
        lambda _payload: hydration_policy,
    )
    monkeypatch.setattr(
        host_module,
        "fast_forecast_context_hydration_policy_fingerprint_sha256",
        lambda _policy: HYDRATION_FP,
    )
    monkeypatch.setattr(
        host_module,
        "build_fast_first_champion_v2_bundle",
        lambda **_kwargs: events.append("bundle") or (cohort, bundle),
    )

    captured = {}

    def fake_hydrate(**kwargs):
        events.append("hydrate")
        captured["validation_policy"] = kwargs["validation_policy"]
        captured["horizon_ms"] = kwargs["horizon_ms"]
        return hydration_result

    monkeypatch.setattr(
        host_module,
        "hydrate_fast_forecast_evaluation_contexts",
        fake_hydrate,
    )
    monkeypatch.setattr(
        host_module,
        "build_fast_first_champion_v2",
        lambda **kwargs: events.append("build") or build,
    )
    monkeypatch.setattr(
        host_module,
        "write_fast_first_champion_v2_evidence",
        lambda _build, _destination, policy=None: (
            events.append("write") or evidence
        ),
    )
    monkeypatch.setattr(
        host_module,
        "read_fast_first_champion_v2_evidence",
        lambda _path: events.append("read") or evidence,
    )

    result = run_fast_first_champion_v2_host_request(request_path)

    assert result == evidence
    assert events == [
        "release",
        "cohort",
        "cohort-verify",
        "bundle",
        "hydrate",
        "build",
        "write",
        "read",
        "cohort",
    ]
    assert captured["horizon_ms"] == policy.horizon_ms
    fold = captured["validation_policy"].folds[0]
    assert (
        fold.training_started_at_unix_ms,
        fold.training_ended_at_unix_ms,
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
    ) == (
        policy.training_started_at_unix_ms,
        policy.training_ended_at_unix_ms,
        policy.validation_started_at_unix_ms,
        policy.validation_ended_at_unix_ms,
        policy.test_started_at_unix_ms,
        policy.test_ended_at_unix_ms,
    )


def test_v2_host_run_rejects_release_mismatch_before_cohort(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    import shreks_brain.fast_first_champion_v2.host_run as host_module
    from shreks_brain.fast_first_champion_v2.host_run import (
        run_fast_first_champion_v2_host_request,
    )

    proof = tmp_path / "proof"
    proof.mkdir()
    database = tmp_path / "observer.db"
    database.write_bytes(b"sqlite")
    cohort_path = tmp_path / "cohort"
    cohort_path.mkdir()
    hydration_path = tmp_path / "hydration.json"
    hydration_path.write_text("{}\n", encoding="utf-8")
    overlay_path = tmp_path / "overlay"
    overlay_path.mkdir()
    (overlay_path / "manifest.json").write_text("{}\n", encoding="utf-8")
    (overlay_path / "rows.jsonl").write_text("{}\n", encoding="utf-8")
    request = _request(
        proof_workspace_path=str(proof),
        observer_database_path=str(database),
        cohort_artifact_path=str(cohort_path),
        hydration_policy_path=str(hydration_path),
        training_economics_overlay_path=str(overlay_path),
        destination_path=str(tmp_path / "evidence"),
    )
    request_path = tmp_path / "request.json"
    write_fast_first_champion_v2_host_request(request, request_path)

    cohort_read = False
    monkeypatch.setattr(
        host_module,
        "read_fast_proof_workspace",
        lambda _path: SimpleNamespace(
            manifest=SimpleNamespace(release_source_sha="f" * 40)
        ),
    )

    def forbidden_cohort(_path):
        nonlocal cohort_read
        cohort_read = True
        raise AssertionError("cohort must not be read after release mismatch")

    monkeypatch.setattr(
        host_module,
        "read_fl9_v2_cohort_acceptance",
        forbidden_cohort,
    )

    with pytest.raises(ValueError, match="release.*mismatch"):
        run_fast_first_champion_v2_host_request(request_path)
    assert cohort_read is False
    assert not (tmp_path / "evidence").exists()


def test_v2_host_run_cli_and_authority_surface() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_v2"
        / "host_run.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "time.",
        "_host_wall_clock",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
        "paper_executor",
    ):
        assert forbidden not in source

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (
        'shreks-fl9-v2-first-champion = '
        '"shreks_brain.fast_first_champion_v2.host_run:main"'
        in pyproject
    )
