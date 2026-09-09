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
