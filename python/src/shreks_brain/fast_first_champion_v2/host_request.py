from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_proof_workspace import read_fast_proof_workspace
from shreks_brain.fl9_v2_cohort_acceptance import (
    read_fl9_v2_cohort_acceptance,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
    decode_fast_training_execution_cost_policy,
    encode_fast_training_execution_cost_policy,
    fast_training_execution_cost_policy_fingerprint_sha256,
    validate_fast_training_economics_overlay,
)

from .models import FastFirstChampionV2Policy


FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_NAME = (
    "shreks.fast_first_champion_v2_host_request"
)
FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request",
        "request_fingerprint_sha256",
    }
)
_REQUEST_KEYS = frozenset(
    {
        "proof_workspace_path",
        "observer_database_path",
        "cohort_artifact_path",
        "expected_cohort_artifact_fingerprint_sha256",
        "hydration_policy_path",
        "expected_hydration_policy_fingerprint_sha256",
        "training_economics_overlay_path",
        "expected_training_economics_overlay_manifest_fingerprint_sha256",
        "training_execution_cost_policy",
        "training_execution_cost_policy_fingerprint_sha256",
        "destination_path",
        "expected_release_source_sha",
        "future_path_label_version",
        "counterfactual_base_quantity",
        "evaluation_policy",
        "champion_version",
        "model_version_prefix",
        "training_policy_version",
        "reason",
    }
)
_EVALUATION_POLICY_KEYS = frozenset(
    {
        "version",
        "partition",
        "probability_bucket_count",
        "liquidity_capacity_quote_boundaries",
        "round_trip_cost_bps_boundaries",
        "binary_log_loss_clip_epsilon",
    }
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2HostRequest:
    schema_name: str
    schema_version: int
    proof_workspace_path: str
    observer_database_path: str
    cohort_artifact_path: str
    expected_cohort_artifact_fingerprint_sha256: str
    hydration_policy_path: str
    expected_hydration_policy_fingerprint_sha256: str
    training_economics_overlay_path: str
    expected_training_economics_overlay_manifest_fingerprint_sha256: str
    training_execution_cost_policy: FastTrainingExecutionCostPolicy
    training_execution_cost_policy_fingerprint_sha256: str
    destination_path: str
    expected_release_source_sha: str
    future_path_label_version: int
    counterfactual_base_quantity: float | int
    evaluation_policy: FastForecastEvaluationPolicy
    champion_version: str
    model_version_prefix: str
    training_policy_version: str
    reason: str
    request_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_NAME:
            raise ValueError("unsupported V2 first-champion host request schema_name")
        if self.schema_version != FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported V2 first-champion host request schema_version")
        for name in (
            "proof_workspace_path",
            "observer_database_path",
            "cohort_artifact_path",
            "hydration_policy_path",
            "training_economics_overlay_path",
            "destination_path",
            "champion_version",
            "model_version_prefix",
            "training_policy_version",
            "reason",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_safe_destination(self.destination_path)
        _require_source_sha(self.expected_release_source_sha)
        for name in (
            "expected_cohort_artifact_fingerprint_sha256",
            "expected_hydration_policy_fingerprint_sha256",
            "expected_training_economics_overlay_manifest_fingerprint_sha256",
            "training_execution_cost_policy_fingerprint_sha256",
            "request_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        policy = FastFirstChampionV2Policy()
        if (
            self.expected_cohort_artifact_fingerprint_sha256
            != policy.expected_cohort_artifact_fingerprint_sha256
        ):
            raise ValueError(
                "V2 host request cohort artifact fingerprint does not match "
                "the frozen physical cohort"
            )
        if type(self.training_execution_cost_policy) is not FastTrainingExecutionCostPolicy:
            raise ValueError(
                "training_execution_cost_policy must be exact "
                "FastTrainingExecutionCostPolicy"
            )
        if self.training_execution_cost_policy_fingerprint_sha256 != (
            fast_training_execution_cost_policy_fingerprint_sha256(
                self.training_execution_cost_policy
            )
        ):
            raise ValueError(
                "V2 host request training execution cost policy fingerprint mismatch"
            )
        if (
            isinstance(self.future_path_label_version, bool)
            or not isinstance(self.future_path_label_version, int)
            or self.future_path_label_version <= 0
        ):
            raise ValueError("future_path_label_version must be positive")
        _require_positive_finite(
            "counterfactual_base_quantity",
            self.counterfactual_base_quantity,
        )
        if type(self.evaluation_policy) is not FastForecastEvaluationPolicy:
            raise ValueError(
                "evaluation_policy must be exact FastForecastEvaluationPolicy"
            )
        if self.evaluation_policy.partition is not FastForecastEvaluationPartition.TEST:
            raise ValueError("V2 first-champion host request requires TEST evaluation")
        if self.request_fingerprint_sha256 != _sha256_canonical(
            _request_material(self)
        ):
            raise ValueError("V2 first-champion host request fingerprint mismatch")


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2HostRequestWriteResult:
    path: Path
    request_fingerprint_sha256: str
    release_source_sha: str
    cohort_artifact_fingerprint_sha256: str
    hydration_policy_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        _require_sha256(
            "request_fingerprint_sha256",
            self.request_fingerprint_sha256,
        )
        _require_source_sha(self.release_source_sha)
        _require_sha256(
            "cohort_artifact_fingerprint_sha256",
            self.cohort_artifact_fingerprint_sha256,
        )
        _require_sha256(
            "hydration_policy_fingerprint_sha256",
            self.hydration_policy_fingerprint_sha256,
        )


def build_fast_first_champion_v2_host_request(
    *,
    proof_workspace_path: str,
    observer_database_path: str,
    cohort_artifact_path: str,
    expected_cohort_artifact_fingerprint_sha256: str,
    hydration_policy_path: str,
    expected_hydration_policy_fingerprint_sha256: str,
    training_economics_overlay_path: str,
    expected_training_economics_overlay_manifest_fingerprint_sha256: str,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
    training_execution_cost_policy_fingerprint_sha256: str,
    destination_path: str,
    expected_release_source_sha: str,
    future_path_label_version: int,
    counterfactual_base_quantity: float | int,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    model_version_prefix: str,
    training_policy_version: str,
    reason: str,
) -> FastFirstChampionV2HostRequest:
    material = _request_material_from_values(
        proof_workspace_path=proof_workspace_path,
        observer_database_path=observer_database_path,
        cohort_artifact_path=cohort_artifact_path,
        expected_cohort_artifact_fingerprint_sha256=(
            expected_cohort_artifact_fingerprint_sha256
        ),
        hydration_policy_path=hydration_policy_path,
        expected_hydration_policy_fingerprint_sha256=(
            expected_hydration_policy_fingerprint_sha256
        ),
        training_economics_overlay_path=training_economics_overlay_path,
        expected_training_economics_overlay_manifest_fingerprint_sha256=(
            expected_training_economics_overlay_manifest_fingerprint_sha256
        ),
        training_execution_cost_policy=training_execution_cost_policy,
        training_execution_cost_policy_fingerprint_sha256=(
            training_execution_cost_policy_fingerprint_sha256
        ),
        destination_path=destination_path,
        expected_release_source_sha=expected_release_source_sha,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
    )
    return FastFirstChampionV2HostRequest(
        schema_name=FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_NAME,
        schema_version=FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_VERSION,
        proof_workspace_path=proof_workspace_path,
        observer_database_path=observer_database_path,
        cohort_artifact_path=cohort_artifact_path,
        expected_cohort_artifact_fingerprint_sha256=(
            expected_cohort_artifact_fingerprint_sha256
        ),
        hydration_policy_path=hydration_policy_path,
        expected_hydration_policy_fingerprint_sha256=(
            expected_hydration_policy_fingerprint_sha256
        ),
        training_economics_overlay_path=training_economics_overlay_path,
        expected_training_economics_overlay_manifest_fingerprint_sha256=(
            expected_training_economics_overlay_manifest_fingerprint_sha256
        ),
        training_execution_cost_policy=training_execution_cost_policy,
        training_execution_cost_policy_fingerprint_sha256=(
            training_execution_cost_policy_fingerprint_sha256
        ),
        destination_path=destination_path,
        expected_release_source_sha=expected_release_source_sha,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
        request_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_first_champion_v2_host_request(
    request: FastFirstChampionV2HostRequest,
) -> str:
    if type(request) is not FastFirstChampionV2HostRequest:
        raise ValueError(
            "request must be exact FastFirstChampionV2HostRequest"
        )
    if request.request_fingerprint_sha256 != _sha256_canonical(
        _request_material(request)
    ):
        raise ValueError("V2 host request fingerprint mismatch before encode")
    return _canonical(
        {
            "schema_name": request.schema_name,
            "schema_version": request.schema_version,
            "request": _request_material(request),
            "request_fingerprint_sha256": request.request_fingerprint_sha256,
        }
    )


def decode_fast_first_champion_v2_host_request(
    payload: str,
) -> FastFirstChampionV2HostRequest:
    document = _load_canonical(
        payload,
        label="V2 first-champion host request",
    )
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "V2 first-champion host request has unknown or missing top-level fields"
        )
    if (
        document["schema_name"]
        != FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_NAME
        or document["schema_version"]
        != FAST_FIRST_CHAMPION_V2_HOST_REQUEST_SCHEMA_VERSION
    ):
        raise ValueError("unsupported V2 first-champion host request schema")
    raw = document["request"]
    if not isinstance(raw, dict) or frozenset(raw) != _REQUEST_KEYS:
        raise ValueError("V2 first-champion host request fields are incompatible")

    training_policy = _decode_training_execution_cost_policy(
        raw["training_execution_cost_policy"]
    )
    evaluation_policy = _decode_evaluation_policy(raw["evaluation_policy"])
    request = FastFirstChampionV2HostRequest(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        proof_workspace_path=_text(raw["proof_workspace_path"], "proof_workspace_path"),
        observer_database_path=_text(raw["observer_database_path"], "observer_database_path"),
        cohort_artifact_path=_text(raw["cohort_artifact_path"], "cohort_artifact_path"),
        expected_cohort_artifact_fingerprint_sha256=_text(
            raw["expected_cohort_artifact_fingerprint_sha256"],
            "expected_cohort_artifact_fingerprint_sha256",
        ),
        hydration_policy_path=_text(raw["hydration_policy_path"], "hydration_policy_path"),
        expected_hydration_policy_fingerprint_sha256=_text(
            raw["expected_hydration_policy_fingerprint_sha256"],
            "expected_hydration_policy_fingerprint_sha256",
        ),
        training_economics_overlay_path=_text(
            raw["training_economics_overlay_path"],
            "training_economics_overlay_path",
        ),
        expected_training_economics_overlay_manifest_fingerprint_sha256=_text(
            raw[
                "expected_training_economics_overlay_manifest_fingerprint_sha256"
            ],
            "expected_training_economics_overlay_manifest_fingerprint_sha256",
        ),
        training_execution_cost_policy=training_policy,
        training_execution_cost_policy_fingerprint_sha256=_text(
            raw["training_execution_cost_policy_fingerprint_sha256"],
            "training_execution_cost_policy_fingerprint_sha256",
        ),
        destination_path=_text(raw["destination_path"], "destination_path"),
        expected_release_source_sha=_text(
            raw["expected_release_source_sha"],
            "expected_release_source_sha",
        ),
        future_path_label_version=_integer(
            raw["future_path_label_version"],
            "future_path_label_version",
        ),
        counterfactual_base_quantity=_decode_numeric(
            raw["counterfactual_base_quantity"],
            "counterfactual_base_quantity",
        ),
        evaluation_policy=evaluation_policy,
        champion_version=_text(raw["champion_version"], "champion_version"),
        model_version_prefix=_text(
            raw["model_version_prefix"],
            "model_version_prefix",
        ),
        training_policy_version=_text(
            raw["training_policy_version"],
            "training_policy_version",
        ),
        reason=_text(raw["reason"], "reason"),
        request_fingerprint_sha256=_text(
            document["request_fingerprint_sha256"],
            "request_fingerprint_sha256",
        ),
    )
    if encode_fast_first_champion_v2_host_request(request) != payload:
        raise ValueError("V2 first-champion host request is not canonical")
    return request


def write_fast_first_champion_v2_host_request(
    request: FastFirstChampionV2HostRequest,
    destination: str | Path,
) -> Path:
    payload = encode_fast_first_champion_v2_host_request(request).encode("utf-8")
    path = Path(destination).expanduser().resolve()
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "V2 first-champion host request destination exists; overwrite forbidden"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    staging = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        staging.chmod(0o600)
        if staging.read_bytes() != payload:
            raise ValueError("staged V2 host request bytes changed")
        if path.exists() or path.is_symlink():
            raise FileExistsError(
                "V2 first-champion host request destination appeared during write"
            )
        staging.rename(path)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return path


def write_fast_first_champion_v2_host_request_from_sources(
    *,
    proof_workspace_path: str | Path,
    observer_database_path: str | Path,
    cohort_artifact_path: str | Path,
    hydration_policy_path: str | Path,
    training_economics_overlay_path: str | Path,
    training_execution_cost_policy_path: str | Path,
    request_destination: str | Path,
    evidence_destination: str | Path,
    future_path_label_version: int,
    counterfactual_base_quantity: float | int,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    model_version_prefix: str,
    training_policy_version: str,
    reason: str,
) -> FastFirstChampionV2HostRequestWriteResult:
    proof_path = _existing_directory(proof_workspace_path, "proof workspace")
    database_path = _existing_file(observer_database_path, "observer database")
    cohort_path = _existing_directory(cohort_artifact_path, "cohort artifact")
    hydration_path = _existing_file(hydration_policy_path, "hydration policy")
    overlay_path = _existing_directory(
        training_economics_overlay_path,
        "training economics overlay",
    )
    if {item.name for item in overlay_path.iterdir()} != {
        "manifest.json",
        "rows.jsonl",
    }:
        raise ValueError(
            "training economics overlay must contain exactly manifest.json and rows.jsonl"
        )
    cost_path = _existing_file(
        training_execution_cost_policy_path,
        "training execution cost policy",
    )

    request_path = Path(request_destination).expanduser().resolve()
    if request_path.exists() or request_path.is_symlink():
        raise FileExistsError("V2 host request destination already exists")
    evidence_path = Path(evidence_destination).expanduser().resolve()
    if evidence_path.exists() or evidence_path.is_symlink():
        raise FileExistsError("V2 evidence destination already exists")
    if request_path == evidence_path:
        raise ValueError("request and evidence destinations must differ")
    _require_safe_destination(str(evidence_path))

    proof = read_fast_proof_workspace(proof_path)
    cohort = read_fl9_v2_cohort_acceptance(cohort_path)
    policy = FastFirstChampionV2Policy()
    cohort_fingerprint = cohort.manifest.artifact_fingerprint_sha256
    if cohort_fingerprint != policy.expected_cohort_artifact_fingerprint_sha256:
        raise ValueError(
            "V2 source writer cohort artifact fingerprint does not match frozen authority"
        )

    hydration_payload = _read_text_stable(hydration_path, "hydration policy")
    hydration_policy = decode_fast_forecast_context_hydration_policy(
        hydration_payload
    )
    hydration_fingerprint = (
        fast_forecast_context_hydration_policy_fingerprint_sha256(
            hydration_policy
        )
    )
    cost_payload = _read_text_stable(
        cost_path,
        "training execution cost policy",
    )
    cost_policy = decode_fast_training_execution_cost_policy(cost_payload)
    cost_fingerprint = fast_training_execution_cost_policy_fingerprint_sha256(
        cost_policy
    )
    overlay_manifest = validate_fast_training_economics_overlay(overlay_path)
    overlay_fingerprint = overlay_manifest.manifest_fingerprint_sha256

    request = build_fast_first_champion_v2_host_request(
        proof_workspace_path=str(proof_path),
        observer_database_path=str(database_path),
        cohort_artifact_path=str(cohort_path),
        expected_cohort_artifact_fingerprint_sha256=cohort_fingerprint,
        hydration_policy_path=str(hydration_path),
        expected_hydration_policy_fingerprint_sha256=hydration_fingerprint,
        training_economics_overlay_path=str(overlay_path),
        expected_training_economics_overlay_manifest_fingerprint_sha256=(
            overlay_fingerprint
        ),
        training_execution_cost_policy=cost_policy,
        training_execution_cost_policy_fingerprint_sha256=cost_fingerprint,
        destination_path=str(evidence_path),
        expected_release_source_sha=proof.manifest.release_source_sha,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
    )
    write_fast_first_champion_v2_host_request(request, request_path)

    if _read_text_stable(hydration_path, "hydration policy") != hydration_payload:
        request_path.unlink(missing_ok=True)
        raise ValueError("hydration policy source changed during request creation")
    if _read_text_stable(
        cost_path,
        "training execution cost policy",
    ) != cost_payload:
        request_path.unlink(missing_ok=True)
        raise ValueError(
            "training execution cost policy source changed during request creation"
        )
    proof_after = read_fast_proof_workspace(proof_path)
    cohort_after = read_fl9_v2_cohort_acceptance(cohort_path)
    overlay_after = validate_fast_training_economics_overlay(overlay_path)
    if proof_after.manifest != proof.manifest:
        request_path.unlink(missing_ok=True)
        raise ValueError("proof workspace source changed during request creation")
    if cohort_after.manifest != cohort.manifest:
        request_path.unlink(missing_ok=True)
        raise ValueError("cohort artifact source changed during request creation")
    if overlay_after != overlay_manifest:
        request_path.unlink(missing_ok=True)
        raise ValueError(
            "training economics overlay source changed during request creation"
        )

    return FastFirstChampionV2HostRequestWriteResult(
        path=request_path,
        request_fingerprint_sha256=request.request_fingerprint_sha256,
        release_source_sha=proof.manifest.release_source_sha,
        cohort_artifact_fingerprint_sha256=cohort_fingerprint,
        hydration_policy_fingerprint_sha256=hydration_fingerprint,
    )


def _request_material(
    request: FastFirstChampionV2HostRequest,
) -> dict[str, object]:
    return _request_material_from_values(
        proof_workspace_path=request.proof_workspace_path,
        observer_database_path=request.observer_database_path,
        cohort_artifact_path=request.cohort_artifact_path,
        expected_cohort_artifact_fingerprint_sha256=(
            request.expected_cohort_artifact_fingerprint_sha256
        ),
        hydration_policy_path=request.hydration_policy_path,
        expected_hydration_policy_fingerprint_sha256=(
            request.expected_hydration_policy_fingerprint_sha256
        ),
        training_economics_overlay_path=(
            request.training_economics_overlay_path
        ),
        expected_training_economics_overlay_manifest_fingerprint_sha256=(
            request.expected_training_economics_overlay_manifest_fingerprint_sha256
        ),
        training_execution_cost_policy=request.training_execution_cost_policy,
        training_execution_cost_policy_fingerprint_sha256=(
            request.training_execution_cost_policy_fingerprint_sha256
        ),
        destination_path=request.destination_path,
        expected_release_source_sha=request.expected_release_source_sha,
        future_path_label_version=request.future_path_label_version,
        counterfactual_base_quantity=request.counterfactual_base_quantity,
        evaluation_policy=request.evaluation_policy,
        champion_version=request.champion_version,
        model_version_prefix=request.model_version_prefix,
        training_policy_version=request.training_policy_version,
        reason=request.reason,
    )


def _request_material_from_values(
    *,
    proof_workspace_path: str,
    observer_database_path: str,
    cohort_artifact_path: str,
    expected_cohort_artifact_fingerprint_sha256: str,
    hydration_policy_path: str,
    expected_hydration_policy_fingerprint_sha256: str,
    training_economics_overlay_path: str,
    expected_training_economics_overlay_manifest_fingerprint_sha256: str,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
    training_execution_cost_policy_fingerprint_sha256: str,
    destination_path: str,
    expected_release_source_sha: str,
    future_path_label_version: int,
    counterfactual_base_quantity: float | int,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    model_version_prefix: str,
    training_policy_version: str,
    reason: str,
) -> dict[str, object]:
    return {
        "proof_workspace_path": proof_workspace_path,
        "observer_database_path": observer_database_path,
        "cohort_artifact_path": cohort_artifact_path,
        "expected_cohort_artifact_fingerprint_sha256": (
            expected_cohort_artifact_fingerprint_sha256
        ),
        "hydration_policy_path": hydration_policy_path,
        "expected_hydration_policy_fingerprint_sha256": (
            expected_hydration_policy_fingerprint_sha256
        ),
        "training_economics_overlay_path": training_economics_overlay_path,
        "expected_training_economics_overlay_manifest_fingerprint_sha256": (
            expected_training_economics_overlay_manifest_fingerprint_sha256
        ),
        "training_execution_cost_policy": _training_execution_cost_policy_document(
            training_execution_cost_policy
        ),
        "training_execution_cost_policy_fingerprint_sha256": (
            training_execution_cost_policy_fingerprint_sha256
        ),
        "destination_path": destination_path,
        "expected_release_source_sha": expected_release_source_sha,
        "future_path_label_version": future_path_label_version,
        "counterfactual_base_quantity": _encode_numeric(
            counterfactual_base_quantity
        ),
        "evaluation_policy": _evaluation_policy_document(evaluation_policy),
        "champion_version": champion_version,
        "model_version_prefix": model_version_prefix,
        "training_policy_version": training_policy_version,
        "reason": reason,
    }


def _training_execution_cost_policy_document(
    policy: FastTrainingExecutionCostPolicy,
) -> dict[str, object]:
    return json.loads(
        encode_fast_training_execution_cost_policy(policy),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_keys,
    )


def _decode_training_execution_cost_policy(
    raw: object,
) -> FastTrainingExecutionCostPolicy:
    if not isinstance(raw, dict):
        raise ValueError("training execution cost policy must be an object")
    return decode_fast_training_execution_cost_policy(_canonical(raw))


def _evaluation_policy_document(
    policy: FastForecastEvaluationPolicy,
) -> dict[str, object]:
    if type(policy) is not FastForecastEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact FastForecastEvaluationPolicy"
        )
    return {
        "version": policy.version,
        "partition": policy.partition.value,
        "probability_bucket_count": policy.probability_bucket_count,
        "liquidity_capacity_quote_boundaries": [
            _encode_numeric(value)
            for value in policy.liquidity_capacity_quote_boundaries
        ],
        "round_trip_cost_bps_boundaries": [
            _encode_numeric(value)
            for value in policy.round_trip_cost_bps_boundaries
        ],
        "binary_log_loss_clip_epsilon": _encode_numeric(
            policy.binary_log_loss_clip_epsilon
        ),
    }


def _decode_evaluation_policy(raw: object) -> FastForecastEvaluationPolicy:
    if not isinstance(raw, dict) or frozenset(raw) != _EVALUATION_POLICY_KEYS:
        raise ValueError("V2 evaluation policy fields are incompatible")
    partition = _text(raw["partition"], "evaluation_policy.partition")
    try:
        partition_value = FastForecastEvaluationPartition(partition)
    except ValueError as exc:
        raise ValueError("invalid V2 evaluation partition") from exc
    liquidity = raw["liquidity_capacity_quote_boundaries"]
    costs = raw["round_trip_cost_bps_boundaries"]
    if not isinstance(liquidity, list) or not isinstance(costs, list):
        raise ValueError("V2 evaluation bucket boundaries must be arrays")
    return FastForecastEvaluationPolicy(
        version=_text(raw["version"], "evaluation_policy.version"),
        partition=partition_value,
        probability_bucket_count=_integer(
            raw["probability_bucket_count"],
            "evaluation_policy.probability_bucket_count",
        ),
        liquidity_capacity_quote_boundaries=tuple(
            float(_decode_numeric(value, "liquidity boundary"))
            for value in liquidity
        ),
        round_trip_cost_bps_boundaries=tuple(
            float(_decode_numeric(value, "cost boundary"))
            for value in costs
        ),
        binary_log_loss_clip_epsilon=float(
            _decode_numeric(
                raw["binary_log_loss_clip_epsilon"],
                "evaluation_policy.binary_log_loss_clip_epsilon",
            )
        ),
    )


def _existing_directory(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} path must be an existing real directory")
    return path


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} path must be an existing regular file")
    return path


def _read_text_stable(path: Path, label: str) -> str:
    before = path.stat()
    payload = path.read_text(encoding="utf-8")
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(f"{label} source changed while reading")
    return payload


def _require_safe_destination(value: object) -> None:
    _require_non_empty("destination_path", value)
    path = Path(str(value)).expanduser()
    if path == Path("/") or path.name in ("", ".", "..") or ".." in path.parts:
        raise ValueError("destination_path is unsafe")


def _encode_numeric(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric value")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numeric value is forbidden")
        return {"$float": value.hex()}
    raise ValueError("numeric value must be int or float")


def _decode_numeric(value: object, name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    if isinstance(value, int):
        return value
    if (
        isinstance(value, dict)
        and frozenset(value) == {"$float"}
        and isinstance(value["$float"], str)
    ):
        try:
            decoded = float.fromhex(value["$float"])
        except ValueError as exc:
            raise ValueError(f"{name} contains invalid float encoding") from exc
        if not math.isfinite(decoded):
            raise ValueError(f"{name} contains non-finite float")
        return decoded
    raise ValueError(f"{name} must use canonical numeric encoding")


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise ValueError(f"{label} payload must be text")
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} contains invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant forbidden: {value}")


def _canonical(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be positive finite numeric")


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("expected release source SHA must be 40 lowercase hex")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{name} must be 64 lowercase hex")
