from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import time

from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_first_champion_plan import (
    FastFirstChampionEvidencePlan,
    build_fast_first_champion_evidence_plan,
    read_fast_first_champion_evidence_plan,
    write_fast_first_champion_evidence_plan,
)
from shreks_brain.fast_first_champion_preparation import (
    prepare_fast_first_champion_evidence,
    read_fast_first_champion_preparation,
)
from shreks_brain.fast_proof_workspace import read_fast_proof_workspace
from shreks_brain.research.fast_training_bundle import (
    build_fast_training_bundle_from_runtime_sources,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
    decode_fast_training_execution_cost_policy,
    encode_fast_training_execution_cost_policy,
    fast_training_execution_cost_policy_fingerprint_sha256,
)


FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_NAME = (
    "shreks.fast_first_champion_host_request"
)
FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_VERSION = 2
FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_NAME = (
    "shreks.fast_first_champion_host_run"
)
FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_VERSION = 2
FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK = (
    "HOST_WALL_CLOCK_AT_RUN_START"
)
FAST_FIRST_CHAMPION_HOST_STATUS_SCHEMA_NAME = (
    "shreks.fast_first_champion_host_status"
)
FAST_FIRST_CHAMPION_HOST_STATUS_SCHEMA_VERSION = 1

_REQUEST_FILE = "request.json"
_HYDRATION_POLICY_FILE = "hydration-policy.json"
_PLAN_FILE = "plan.json"
_PREPARATION_DIR = "preparation"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset(
    {
        _REQUEST_FILE,
        _HYDRATION_POLICY_FILE,
        _PLAN_FILE,
        _PREPARATION_DIR,
        _MANIFEST_FILE,
    }
)

_REQUEST_TOP_KEYS = frozenset(
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
        "hydration_policy_path",
        "training_economics_overlay_path",
        "expected_training_economics_overlay_manifest_fingerprint_sha256",
        "training_execution_cost_policy",
        "training_execution_cost_policy_fingerprint_sha256",
        "destination_path",
        "expected_release_source_sha",
        "expected_hydration_policy_fingerprint_sha256",
        "selection_clock",
        "future_path_label_version",
        "counterfactual_base_quantity",
        "horizon_ms",
        "minimum_raw_rows_per_partition",
        "minimum_test_scored_observations",
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
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request_fingerprint_sha256",
        "request_file_sha256",
        "hydration_policy_fingerprint_sha256",
        "hydration_policy_file_sha256",
        "selection_clock",
        "selection_at_unix_ms",
        "expected_release_source_sha",
        "proof_workspace_artifact_fingerprint_sha256",
        "feature_source_jsonl_sha256",
        "training_economics_overlay_manifest_fingerprint_sha256",
        "training_execution_cost_policy_fingerprint_sha256",
        "plan_fingerprint_sha256",
        "plan_file_sha256",
        "training_bundle_fingerprint_sha256",
        "validation_policy_fingerprint_sha256",
        "preparation_artifact_fingerprint_sha256",
        "context_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "champion_version",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionHostRequest:
    schema_name: str
    schema_version: int
    proof_workspace_path: str
    observer_database_path: str
    hydration_policy_path: str
    training_economics_overlay_path: str
    expected_training_economics_overlay_manifest_fingerprint_sha256: str
    training_execution_cost_policy: FastTrainingExecutionCostPolicy
    training_execution_cost_policy_fingerprint_sha256: str
    destination_path: str
    expected_release_source_sha: str
    expected_hydration_policy_fingerprint_sha256: str
    selection_clock: str
    future_path_label_version: int
    counterfactual_base_quantity: float | int
    horizon_ms: int
    minimum_raw_rows_per_partition: int
    minimum_test_scored_observations: int
    evaluation_policy: FastForecastEvaluationPolicy
    champion_version: str
    model_version_prefix: str
    training_policy_version: str
    reason: str
    request_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_NAME:
            raise ValueError(
                "unsupported first champion host request schema_name"
            )
        if self.schema_version != FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                "unsupported first champion host request schema_version"
            )
        for name in (
            "proof_workspace_path",
            "observer_database_path",
            "hydration_policy_path",
            "training_economics_overlay_path",
            "destination_path",
            "champion_version",
            "model_version_prefix",
            "training_policy_version",
            "reason",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_source_sha(self.expected_release_source_sha)
        _require_sha256(
            "expected_training_economics_overlay_manifest_fingerprint_sha256",
            self.expected_training_economics_overlay_manifest_fingerprint_sha256,
        )
        if type(self.training_execution_cost_policy) is not FastTrainingExecutionCostPolicy:
            raise ValueError(
                "training_execution_cost_policy must be exact FastTrainingExecutionCostPolicy"
            )
        _require_sha256(
            "training_execution_cost_policy_fingerprint_sha256",
            self.training_execution_cost_policy_fingerprint_sha256,
        )
        if self.training_execution_cost_policy_fingerprint_sha256 != (
            fast_training_execution_cost_policy_fingerprint_sha256(
                self.training_execution_cost_policy
            )
        ):
            raise ValueError(
                "first champion host training execution cost policy fingerprint mismatch"
            )
        _require_sha256(
            "expected_hydration_policy_fingerprint_sha256",
            self.expected_hydration_policy_fingerprint_sha256,
        )
        if self.selection_clock != FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK:
            raise ValueError(
                "unsupported first champion host selection clock"
            )
        for name in (
            "future_path_label_version",
            "horizon_ms",
            "minimum_raw_rows_per_partition",
            "minimum_test_scored_observations",
        ):
            _require_positive_int(name, getattr(self, name))
        _require_positive_finite(
            "counterfactual_base_quantity",
            self.counterfactual_base_quantity,
        )
        if type(self.evaluation_policy) is not FastForecastEvaluationPolicy:
            raise ValueError(
                "evaluation_policy must be exact FastForecastEvaluationPolicy"
            )
        if (
            self.evaluation_policy.partition
            is not FastForecastEvaluationPartition.TEST
        ):
            raise ValueError(
                "first champion host request requires TEST evaluation"
            )
        if self.request_fingerprint_sha256 != _sha256_canonical(
            _request_material(self)
        ):
            raise ValueError(
                "first champion host request fingerprint mismatch"
            )


@dataclass(frozen=True, slots=True)
class FastFirstChampionHostRunManifest:
    schema_name: str
    schema_version: int
    request_fingerprint_sha256: str
    request_file_sha256: str
    hydration_policy_fingerprint_sha256: str
    hydration_policy_file_sha256: str
    selection_clock: str
    selection_at_unix_ms: int
    expected_release_source_sha: str
    proof_workspace_artifact_fingerprint_sha256: str
    feature_source_jsonl_sha256: str
    training_economics_overlay_manifest_fingerprint_sha256: str
    training_execution_cost_policy_fingerprint_sha256: str
    plan_fingerprint_sha256: str
    plan_file_sha256: str
    training_bundle_fingerprint_sha256: str
    validation_policy_fingerprint_sha256: str
    preparation_artifact_fingerprint_sha256: str
    context_fingerprint_sha256: str
    champion_fingerprint_sha256: str
    champion_version: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_NAME:
            raise ValueError(
                "unsupported first champion host run schema_name"
            )
        if self.schema_version != FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_VERSION:
            raise ValueError(
                "unsupported first champion host run schema_version"
            )
        for name in (
            "request_fingerprint_sha256",
            "request_file_sha256",
            "hydration_policy_fingerprint_sha256",
            "hydration_policy_file_sha256",
            "proof_workspace_artifact_fingerprint_sha256",
            "feature_source_jsonl_sha256",
            "training_economics_overlay_manifest_fingerprint_sha256",
            "training_execution_cost_policy_fingerprint_sha256",
            "plan_fingerprint_sha256",
            "plan_file_sha256",
            "training_bundle_fingerprint_sha256",
            "validation_policy_fingerprint_sha256",
            "preparation_artifact_fingerprint_sha256",
            "context_fingerprint_sha256",
            "champion_fingerprint_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.selection_clock != FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK:
            raise ValueError(
                "unsupported first champion host run selection clock"
            )
        _require_non_negative_int(
            "selection_at_unix_ms",
            self.selection_at_unix_ms,
        )
        _require_source_sha(self.expected_release_source_sha)
        _require_non_empty("champion_version", self.champion_version)


@dataclass(frozen=True, slots=True)
class FastFirstChampionHostRunArtifact:
    path: Path
    manifest: FastFirstChampionHostRunManifest
    request: FastFirstChampionHostRequest
    hydration_policy: object
    plan: FastFirstChampionEvidencePlan
    preparation: object

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        if type(self.manifest) is not FastFirstChampionHostRunManifest:
            raise ValueError(
                "manifest must be exact FastFirstChampionHostRunManifest"
            )
        if type(self.request) is not FastFirstChampionHostRequest:
            raise ValueError(
                "request must be exact FastFirstChampionHostRequest"
            )
        if type(self.plan) is not FastFirstChampionEvidencePlan:
            raise ValueError(
                "plan must be exact FastFirstChampionEvidencePlan"
            )


@dataclass(frozen=True, slots=True)
class _TrainingEconomicsSnapshot:
    manifest_fingerprint_sha256: str
    manifest_file_sha256: str
    rows_file_sha256: str


def build_fast_first_champion_host_request(
    *,
    proof_workspace_path: str,
    observer_database_path: str,
    hydration_policy_path: str,
    training_economics_overlay_path: str,
    expected_training_economics_overlay_manifest_fingerprint_sha256: str,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
    training_execution_cost_policy_fingerprint_sha256: str,
    destination_path: str,
    expected_release_source_sha: str,
    expected_hydration_policy_fingerprint_sha256: str,
    selection_clock: str,
    future_path_label_version: int,
    counterfactual_base_quantity: float | int,
    horizon_ms: int,
    minimum_raw_rows_per_partition: int,
    minimum_test_scored_observations: int,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    model_version_prefix: str,
    training_policy_version: str,
    reason: str,
) -> FastFirstChampionHostRequest:
    material = _request_material_from_values(
        proof_workspace_path=proof_workspace_path,
        observer_database_path=observer_database_path,
        hydration_policy_path=hydration_policy_path,
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
        expected_hydration_policy_fingerprint_sha256=(
            expected_hydration_policy_fingerprint_sha256
        ),
        selection_clock=selection_clock,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        horizon_ms=horizon_ms,
        minimum_raw_rows_per_partition=minimum_raw_rows_per_partition,
        minimum_test_scored_observations=(
            minimum_test_scored_observations
        ),
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
    )
    return FastFirstChampionHostRequest(
        schema_name=FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_NAME,
        schema_version=FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_VERSION,
        proof_workspace_path=proof_workspace_path,
        observer_database_path=observer_database_path,
        hydration_policy_path=hydration_policy_path,
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
        expected_hydration_policy_fingerprint_sha256=(
            expected_hydration_policy_fingerprint_sha256
        ),
        selection_clock=selection_clock,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        horizon_ms=horizon_ms,
        minimum_raw_rows_per_partition=minimum_raw_rows_per_partition,
        minimum_test_scored_observations=(
            minimum_test_scored_observations
        ),
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
        request_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_first_champion_host_request(
    request: FastFirstChampionHostRequest,
) -> str:
    if type(request) is not FastFirstChampionHostRequest:
        raise ValueError(
            "request must be exact FastFirstChampionHostRequest"
        )
    if request.request_fingerprint_sha256 != _sha256_canonical(
        _request_material(request)
    ):
        raise ValueError(
            "first champion host request fingerprint mismatch before encode"
        )
    return _canonical(
        {
            "schema_name": request.schema_name,
            "schema_version": request.schema_version,
            "request": _request_material(request),
            "request_fingerprint_sha256": (
                request.request_fingerprint_sha256
            ),
        }
    )


def decode_fast_first_champion_host_request(
    payload: str,
) -> FastFirstChampionHostRequest:
    document = _load_canonical(
        payload,
        label="first champion host request",
    )
    if frozenset(document) != _REQUEST_TOP_KEYS:
        raise ValueError(
            "first champion host request has unknown or missing top-level fields"
        )
    if (
        document["schema_name"]
        != FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_NAME
        or document["schema_version"]
        != FAST_FIRST_CHAMPION_HOST_REQUEST_SCHEMA_VERSION
    ):
        raise ValueError("unsupported first champion host request schema")
    raw = document["request"]
    if not isinstance(raw, dict) or frozenset(raw) != _REQUEST_KEYS:
        raise ValueError(
            "first champion host request fields are incompatible"
        )
    request = FastFirstChampionHostRequest(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        proof_workspace_path=_text(
            raw["proof_workspace_path"],
            "proof_workspace_path",
        ),
        observer_database_path=_text(
            raw["observer_database_path"],
            "observer_database_path",
        ),
        hydration_policy_path=_text(
            raw["hydration_policy_path"],
            "hydration_policy_path",
        ),
        training_economics_overlay_path=_text(
            raw["training_economics_overlay_path"],
            "training_economics_overlay_path",
        ),
        expected_training_economics_overlay_manifest_fingerprint_sha256=_text(
            raw["expected_training_economics_overlay_manifest_fingerprint_sha256"],
            "expected_training_economics_overlay_manifest_fingerprint_sha256",
        ),
        training_execution_cost_policy=training_execution_cost_policy,
        training_execution_cost_policy_fingerprint_sha256=_text(
            raw["training_execution_cost_policy_fingerprint_sha256"],
            "training_execution_cost_policy_fingerprint_sha256",
        ),
        destination_path=_text(
            raw["destination_path"],
            "destination_path",
        ),
        expected_release_source_sha=_text(
            raw["expected_release_source_sha"],
            "expected_release_source_sha",
        ),
        expected_hydration_policy_fingerprint_sha256=_text(
            raw["expected_hydration_policy_fingerprint_sha256"],
            "expected_hydration_policy_fingerprint_sha256",
        ),
        selection_clock=_text(
            raw["selection_clock"],
            "selection_clock",
        ),
        future_path_label_version=_integer(
            raw["future_path_label_version"],
            "future_path_label_version",
        ),
        counterfactual_base_quantity=_decode_numeric(
            raw["counterfactual_base_quantity"],
            "counterfactual_base_quantity",
        ),
        horizon_ms=_integer(raw["horizon_ms"], "horizon_ms"),
        minimum_raw_rows_per_partition=_integer(
            raw["minimum_raw_rows_per_partition"],
            "minimum_raw_rows_per_partition",
        ),
        minimum_test_scored_observations=_integer(
            raw["minimum_test_scored_observations"],
            "minimum_test_scored_observations",
        ),
        evaluation_policy=_decode_evaluation_policy(
            raw["evaluation_policy"]
        ),
        champion_version=_text(
            raw["champion_version"],
            "champion_version",
        ),
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
    if encode_fast_first_champion_host_request(request) != payload:
        raise ValueError(
            "first champion host request must use canonical JSON"
        )
    return request


def run_fast_first_champion_host_request(
    request_path: str | Path,
) -> FastFirstChampionHostRunArtifact:
    source = Path(request_path).expanduser().resolve()
    if source.is_symlink() or not source.is_file():
        raise ValueError(
            "first champion host request path must be an existing regular file"
        )
    request_payload = source.read_text(encoding="utf-8")
    request = decode_fast_first_champion_host_request(request_payload)
    base = source.parent

    proof_path = _resolve_directory(
        base,
        request.proof_workspace_path,
        label="proof workspace",
    )
    database_path = _resolve_file(
        base,
        request.observer_database_path,
        label="observer database",
    )
    hydration_policy_path = _resolve_file(
        base,
        request.hydration_policy_path,
        label="hydration policy",
    )
    destination = _resolve_destination(
        base,
        request.destination_path,
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "first champion host run destination already exists"
        )

    hydration_payload = hydration_policy_path.read_text(encoding="utf-8")
    hydration_policy = (
        decode_fast_forecast_context_hydration_policy(
            hydration_payload
        )
    )
    hydration_fingerprint = (
        fast_forecast_context_hydration_policy_fingerprint_sha256(
            hydration_policy
        )
    )
    if (
        hydration_fingerprint
        != request.expected_hydration_policy_fingerprint_sha256
    ):
        raise ValueError(
            "first champion host hydration policy fingerprint mismatch"
        )

    proof_workspace = read_fast_proof_workspace(proof_path)
    if (
        proof_workspace.manifest.release_source_sha
        != request.expected_release_source_sha
    ):
        raise ValueError(
            "first champion host proof workspace release source mismatch"
        )

    selection_at = _host_wall_clock_unix_ms()
    _require_non_negative_int(
        "captured selection_at_unix_ms",
        selection_at,
    )
    bundle = build_fast_training_bundle_from_runtime_sources(
        feature_jsonl_path=proof_path / "features.jsonl",
        sqlite_path=database_path,
        future_path_label_version=request.future_path_label_version,
        counterfactual_base_quantity=request.counterfactual_base_quantity,
        training_economics_overlay_path=training_economics_overlay_path,
        training_execution_cost_policy=request.training_execution_cost_policy,
    )
    if (
        bundle.features.source_sha256
        != proof_workspace.manifest.feature_jsonl_sha256
        or bundle.features.logical_fingerprint_sha256
        != proof_workspace.manifest.feature_logical_fingerprint_sha256
    ):
        raise ValueError(
            "first champion host training bundle does not match proof workspace"
        )

    plan = build_fast_first_champion_evidence_plan(
        bundle=bundle,
        horizon_ms=request.horizon_ms,
        selection_at_unix_ms=selection_at,
        minimum_raw_rows_per_partition=(
            request.minimum_raw_rows_per_partition
        ),
        minimum_test_scored_observations=(
            request.minimum_test_scored_observations
        ),
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    staging.chmod(0o700)
    try:
        copied_request = staging / _REQUEST_FILE
        copied_hydration = staging / _HYDRATION_POLICY_FILE
        plan_path = staging / _PLAN_FILE
        copied_request.write_text(
            request_payload,
            encoding="utf-8",
        )
        copied_hydration.write_text(
            hydration_payload,
            encoding="utf-8",
        )
        write_fast_first_champion_evidence_plan(
            plan,
            plan_path,
        )
        for path in (
            copied_request,
            copied_hydration,
            plan_path,
        ):
            path.chmod(0o600)

        decision_reference = (
            f"first-champion-plan:{plan.plan_fingerprint_sha256}"
        )
        preparation = prepare_fast_first_champion_evidence(
            proof_workspace_path=proof_path,
            observer_database_path=database_path,
            training_economics_overlay_path=training_economics_overlay_path,
            training_execution_cost_policy=request.training_execution_cost_policy,
            destination=staging / _PREPARATION_DIR,
            hydration_policy=hydration_policy,
            validation_policy=plan.validation_policy,
            evaluation_policy=request.evaluation_policy,
            future_path_label_version=request.future_path_label_version,
            counterfactual_base_quantity=(
                request.counterfactual_base_quantity
            ),
            champion_version=request.champion_version,
            decision_reference=decision_reference,
            decided_at_unix_ms=plan.selection_at_unix_ms,
            reason=request.reason,
            horizon_ms=plan.horizon_ms,
            model_version_prefix=request.model_version_prefix,
            training_policy_version=request.training_policy_version,
            minimum_test_scored_observations=(
                plan.minimum_test_scored_observations
            ),
        )
        preparation = read_fast_first_champion_preparation(
            staging / _PREPARATION_DIR
        )

        if source.read_text(encoding="utf-8") != request_payload:
            raise ValueError(
                "first champion host request source changed during execution"
            )
        if (
            hydration_policy_path.read_text(encoding="utf-8")
            != hydration_payload
        ):
            raise ValueError(
                "first champion host hydration policy source changed during execution"
            )
        economics_after = _capture_training_economics(
            training_economics_overlay_path
        )
        if economics_after != economics_before:
            raise ValueError(
                "first champion host training economics source changed during execution"
            )
        proof_after = read_fast_proof_workspace(proof_path)
        if proof_after.manifest != proof_workspace.manifest:
            raise ValueError(
                "first champion host proof workspace source changed during execution"
            )

        _validate_preparation_chain(
            request=request,
            hydration_fingerprint=hydration_fingerprint,
            proof_workspace=proof_workspace,
            bundle=bundle,
            plan=plan,
            preparation=preparation,
        )

        material = {
            "schema_name": FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_NAME,
            "schema_version": FAST_FIRST_CHAMPION_HOST_RUN_SCHEMA_VERSION,
            "request_fingerprint_sha256": (
                request.request_fingerprint_sha256
            ),
            "request_file_sha256": _sha256_file_stable(
                copied_request
            ),
            "hydration_policy_fingerprint_sha256": (
                hydration_fingerprint
            ),
            "hydration_policy_file_sha256": _sha256_file_stable(
                copied_hydration
            ),
            "selection_clock": request.selection_clock,
            "selection_at_unix_ms": plan.selection_at_unix_ms,
            "expected_release_source_sha": (
                request.expected_release_source_sha
            ),
            "proof_workspace_artifact_fingerprint_sha256": (
                proof_workspace.manifest.artifact_fingerprint_sha256
            ),
            "feature_source_jsonl_sha256": (
                plan.feature_source_jsonl_sha256
            ),
            "plan_fingerprint_sha256": plan.plan_fingerprint_sha256,
            "plan_file_sha256": _sha256_file_stable(plan_path),
            "training_bundle_fingerprint_sha256": (
                plan.training_bundle_fingerprint_sha256
            ),
            "validation_policy_fingerprint_sha256": (
                preparation.manifest.validation_policy_fingerprint_sha256
            ),
            "preparation_artifact_fingerprint_sha256": (
                preparation.manifest.artifact_fingerprint_sha256
            ),
            "context_fingerprint_sha256": (
                preparation.manifest.context_fingerprint_sha256
            ),
            "champion_fingerprint_sha256": (
                preparation.manifest.champion_fingerprint_sha256
            ),
            "champion_version": preparation.manifest.champion_version,
        }
        manifest = FastFirstChampionHostRunManifest(
            **material,
            artifact_fingerprint_sha256=_sha256_canonical(material),
        )
        manifest_path = staging / _MANIFEST_FILE
        manifest_path.write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)

        verified = read_fast_first_champion_host_run(staging)
        if verified.manifest != manifest:
            raise ValueError(
                "staged first champion host run did not round-trip"
            )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                "first champion host run destination appeared during execution"
            )
        staging.rename(destination)
        return read_fast_first_champion_host_run(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fast_first_champion_host_run(
    path: str | Path,
) -> FastFirstChampionHostRunArtifact:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "first champion host run must be an existing real directory"
        )
    actual = {child.name for child in root.iterdir()}
    if actual != _ROOT_ENTRIES:
        raise ValueError(
            "first champion host run has unknown or missing entries"
        )
    preparation_path = root / _PREPARATION_DIR
    if preparation_path.is_symlink() or not preparation_path.is_dir():
        raise ValueError(
            "first champion host preparation must be a real directory"
        )
    for name in (
        _REQUEST_FILE,
        _HYDRATION_POLICY_FILE,
        _PLAN_FILE,
        _MANIFEST_FILE,
    ):
        value = root / name
        if value.is_symlink() or not value.is_file():
            raise ValueError(
                "first champion host metadata must be regular files"
            )

    document = _load_canonical(
        (root / _MANIFEST_FILE).read_text(encoding="utf-8"),
        label="first champion host run manifest",
    )
    if frozenset(document) != _MANIFEST_KEYS:
        raise ValueError(
            "first champion host run manifest has unknown or missing fields"
        )
    try:
        manifest = FastFirstChampionHostRunManifest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            request_fingerprint_sha256=document[
                "request_fingerprint_sha256"
            ],
            request_file_sha256=document["request_file_sha256"],
            hydration_policy_fingerprint_sha256=document[
                "hydration_policy_fingerprint_sha256"
            ],
            hydration_policy_file_sha256=document[
                "hydration_policy_file_sha256"
            ],
            selection_clock=document["selection_clock"],
            selection_at_unix_ms=document["selection_at_unix_ms"],
            expected_release_source_sha=document[
                "expected_release_source_sha"
            ],
            proof_workspace_artifact_fingerprint_sha256=document[
                "proof_workspace_artifact_fingerprint_sha256"
            ],
            feature_source_jsonl_sha256=document[
                "feature_source_jsonl_sha256"
            ],
            training_economics_overlay_manifest_fingerprint_sha256=document[
                "training_economics_overlay_manifest_fingerprint_sha256"
            ],
            training_execution_cost_policy_fingerprint_sha256=document[
                "training_execution_cost_policy_fingerprint_sha256"
            ],
            plan_fingerprint_sha256=document[
                "plan_fingerprint_sha256"
            ],
            plan_file_sha256=document["plan_file_sha256"],
            training_bundle_fingerprint_sha256=document[
                "training_bundle_fingerprint_sha256"
            ],
            validation_policy_fingerprint_sha256=document[
                "validation_policy_fingerprint_sha256"
            ],
            preparation_artifact_fingerprint_sha256=document[
                "preparation_artifact_fingerprint_sha256"
            ],
            context_fingerprint_sha256=document[
                "context_fingerprint_sha256"
            ],
            champion_fingerprint_sha256=document[
                "champion_fingerprint_sha256"
            ],
            champion_version=document["champion_version"],
            artifact_fingerprint_sha256=document[
                "artifact_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"first champion host run manifest is invalid: {exc}"
        ) from exc

    material = dict(document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "first champion host run artifact fingerprint mismatch"
        )

    request_path = root / _REQUEST_FILE
    hydration_path = root / _HYDRATION_POLICY_FILE
    plan_path = root / _PLAN_FILE
    if _sha256_file_stable(request_path) != manifest.request_file_sha256:
        raise ValueError(
            "first champion host request file hash mismatch"
        )
    if (
        _sha256_file_stable(hydration_path)
        != manifest.hydration_policy_file_sha256
    ):
        raise ValueError(
            "first champion host hydration policy file hash mismatch"
        )
    if _sha256_file_stable(plan_path) != manifest.plan_file_sha256:
        raise ValueError(
            "first champion host plan file hash mismatch"
        )

    request = decode_fast_first_champion_host_request(
        request_path.read_text(encoding="utf-8")
    )
    hydration_policy = (
        decode_fast_forecast_context_hydration_policy(
            hydration_path.read_text(encoding="utf-8")
        )
    )
    hydration_fingerprint = (
        fast_forecast_context_hydration_policy_fingerprint_sha256(
            hydration_policy
        )
    )
    plan = read_fast_first_champion_evidence_plan(plan_path)
    preparation = read_fast_first_champion_preparation(
        preparation_path
    )

    _validate_reopened_chain(
        manifest=manifest,
        request=request,
        hydration_fingerprint=hydration_fingerprint,
        plan=plan,
        preparation=preparation,
    )
    return FastFirstChampionHostRunArtifact(
        path=root,
        manifest=manifest,
        request=request,
        hydration_policy=hydration_policy,
        plan=plan,
        preparation=preparation,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-first-champion-run",
        description=(
            "Run the sealed FL9 first-champion evidence chain from one "
            "canonical host request."
        ),
    )
    parser.add_argument("--request", required=True)
    args = parser.parse_args(argv)
    artifact = run_fast_first_champion_host_request(args.request)
    print(
        json.dumps(
            {
                "schema_name": (
                    FAST_FIRST_CHAMPION_HOST_STATUS_SCHEMA_NAME
                ),
                "schema_version": (
                    FAST_FIRST_CHAMPION_HOST_STATUS_SCHEMA_VERSION
                ),
                "status": "SUCCEEDED",
                "artifact_path": str(artifact.path),
                "selection_at_unix_ms": (
                    artifact.manifest.selection_at_unix_ms
                ),
                "plan_fingerprint_sha256": (
                    artifact.manifest.plan_fingerprint_sha256
                ),
                "champion_fingerprint_sha256": (
                    artifact.manifest.champion_fingerprint_sha256
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


def _validate_preparation_chain(
    *,
    request: FastFirstChampionHostRequest,
    hydration_fingerprint: str,
    proof_workspace,
    bundle,
    plan: FastFirstChampionEvidencePlan,
    preparation,
) -> None:
    manifest = preparation.manifest
    if (
        manifest.proof_workspace_release_source_sha
        != request.expected_release_source_sha
        or manifest.proof_workspace_artifact_fingerprint_sha256
        != proof_workspace.manifest.artifact_fingerprint_sha256
    ):
        raise ValueError(
            "first champion host preparation proof workspace mismatch"
        )
    if (
        plan.training_bundle_fingerprint_sha256
        != bundle.manifest.bundle_fingerprint_sha256
        or manifest.training_bundle_fingerprint_sha256
        != plan.training_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "first champion host preparation training bundle mismatch"
        )
    if (
        plan.feature_source_jsonl_sha256
        != proof_workspace.manifest.feature_jsonl_sha256
    ):
        raise ValueError(
            "first champion host plan feature source mismatch"
        )
    if (
        manifest.hydration_policy_fingerprint_sha256
        != hydration_fingerprint
    ):
        raise ValueError(
            "first champion host preparation hydration policy mismatch"
        )
    child_hydration = preparation.context_hydration.manifest
    if (
        child_hydration.validation_policy != plan.validation_policy
        or child_hydration.hydration_policy_fingerprint_sha256
        != hydration_fingerprint
    ):
        raise ValueError(
            "first champion host preparation context hydration mismatch"
        )
    child_request = preparation.request
    expected_reference = (
        f"first-champion-plan:{plan.plan_fingerprint_sha256}"
    )
    if (
        child_request.validation_policy != plan.validation_policy
        or child_request.evaluation_policy != request.evaluation_policy
        or child_request.horizon_ms != plan.horizon_ms
        or child_request.decided_at_unix_ms
        != plan.selection_at_unix_ms
        or child_request.minimum_test_scored_observations
        != plan.minimum_test_scored_observations
        or child_request.decision_reference != expected_reference
        or child_request.reason != request.reason
    ):
        raise ValueError(
            "first champion host preparation request does not match plan"
        )
    if (
        manifest.champion_version != request.champion_version
        or preparation.first_champion.champion.champion_version
        != request.champion_version
    ):
        raise ValueError(
            "first champion host preparation champion version mismatch"
        )


def _validate_reopened_chain(
    *,
    manifest: FastFirstChampionHostRunManifest,
    request: FastFirstChampionHostRequest,
    hydration_fingerprint: str,
    plan: FastFirstChampionEvidencePlan,
    preparation,
) -> None:
    if (
        request.expected_training_economics_overlay_manifest_fingerprint_sha256
        != manifest.training_economics_overlay_manifest_fingerprint_sha256
        or request.training_execution_cost_policy_fingerprint_sha256
        != manifest.training_execution_cost_policy_fingerprint_sha256
    ):
        raise ValueError(
            "first champion host economics inputs do not match run manifest"
        )
    if (
        request.request_fingerprint_sha256
        != manifest.request_fingerprint_sha256
        or request.selection_clock != manifest.selection_clock
        or request.expected_release_source_sha
        != manifest.expected_release_source_sha
        or request.expected_hydration_policy_fingerprint_sha256
        != manifest.hydration_policy_fingerprint_sha256
    ):
        raise ValueError(
            "first champion host request does not match run manifest"
        )
    if hydration_fingerprint != manifest.hydration_policy_fingerprint_sha256:
        raise ValueError(
            "first champion host hydration policy does not match run manifest"
        )
    if (
        plan.plan_fingerprint_sha256
        != manifest.plan_fingerprint_sha256
        or plan.selection_at_unix_ms
        != manifest.selection_at_unix_ms
        or plan.training_bundle_fingerprint_sha256
        != manifest.training_bundle_fingerprint_sha256
        or plan.feature_source_jsonl_sha256
        != manifest.feature_source_jsonl_sha256
    ):
        raise ValueError(
            "first champion host plan does not match run manifest"
        )

    prep = preparation.manifest
    if (
        prep.proof_workspace_release_source_sha
        != manifest.expected_release_source_sha
        or prep.proof_workspace_artifact_fingerprint_sha256
        != manifest.proof_workspace_artifact_fingerprint_sha256
        or prep.training_economics_overlay_manifest_fingerprint_sha256
        != manifest.training_economics_overlay_manifest_fingerprint_sha256
        or prep.training_execution_cost_policy_fingerprint_sha256
        != manifest.training_execution_cost_policy_fingerprint_sha256
        or prep.training_bundle_fingerprint_sha256
        != manifest.training_bundle_fingerprint_sha256
        or prep.validation_policy_fingerprint_sha256
        != manifest.validation_policy_fingerprint_sha256
        or prep.hydration_policy_fingerprint_sha256
        != manifest.hydration_policy_fingerprint_sha256
        or prep.artifact_fingerprint_sha256
        != manifest.preparation_artifact_fingerprint_sha256
        or prep.context_fingerprint_sha256
        != manifest.context_fingerprint_sha256
        or prep.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
        or prep.champion_version != manifest.champion_version
        or prep.selection_decided_at_unix_ms
        != manifest.selection_at_unix_ms
        or prep.selection_decision_reference
        != f"first-champion-plan:{plan.plan_fingerprint_sha256}"
        or prep.selection_reason != request.reason
    ):
        raise ValueError(
            "first champion host preparation does not match run manifest"
        )
    if preparation.context_hydration.manifest.validation_policy != (
        plan.validation_policy
    ):
        raise ValueError(
            "first champion host plan/preparation validation policy mismatch"
        )
    child_request = preparation.request
    if (
        child_request.validation_policy != plan.validation_policy
        or child_request.evaluation_policy != request.evaluation_policy
        or child_request.expected_training_economics_overlay_manifest_fingerprint_sha256
        != request.expected_training_economics_overlay_manifest_fingerprint_sha256
        or child_request.training_execution_cost_policy
        != request.training_execution_cost_policy
        or child_request.training_execution_cost_policy_fingerprint_sha256
        != request.training_execution_cost_policy_fingerprint_sha256
        or child_request.horizon_ms != request.horizon_ms
        or child_request.minimum_test_scored_observations
        != request.minimum_test_scored_observations
        or child_request.decided_at_unix_ms
        != manifest.selection_at_unix_ms
    ):
        raise ValueError(
            "first champion host child request does not match host request"
        )


def _request_material(
    request: FastFirstChampionHostRequest,
) -> dict[str, object]:
    return _request_material_from_values(
        proof_workspace_path=request.proof_workspace_path,
        observer_database_path=request.observer_database_path,
        hydration_policy_path=request.hydration_policy_path,
        training_economics_overlay_path=request.training_economics_overlay_path,
        expected_training_economics_overlay_manifest_fingerprint_sha256=(
            request.expected_training_economics_overlay_manifest_fingerprint_sha256
        ),
        training_execution_cost_policy=request.training_execution_cost_policy,
        training_execution_cost_policy_fingerprint_sha256=(
            request.training_execution_cost_policy_fingerprint_sha256
        ),
        destination_path=request.destination_path,
        expected_release_source_sha=(
            request.expected_release_source_sha
        ),
        expected_hydration_policy_fingerprint_sha256=(
            request.expected_hydration_policy_fingerprint_sha256
        ),
        selection_clock=request.selection_clock,
        future_path_label_version=request.future_path_label_version,
        counterfactual_base_quantity=(
            request.counterfactual_base_quantity
        ),
        horizon_ms=request.horizon_ms,
        minimum_raw_rows_per_partition=(
            request.minimum_raw_rows_per_partition
        ),
        minimum_test_scored_observations=(
            request.minimum_test_scored_observations
        ),
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
    hydration_policy_path: str,
    training_economics_overlay_path: str,
    expected_training_economics_overlay_manifest_fingerprint_sha256: str,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
    training_execution_cost_policy_fingerprint_sha256: str,
    destination_path: str,
    expected_release_source_sha: str,
    expected_hydration_policy_fingerprint_sha256: str,
    selection_clock: str,
    future_path_label_version: int,
    counterfactual_base_quantity: float | int,
    horizon_ms: int,
    minimum_raw_rows_per_partition: int,
    minimum_test_scored_observations: int,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    model_version_prefix: str,
    training_policy_version: str,
    reason: str,
) -> dict[str, object]:
    return {
        "proof_workspace_path": proof_workspace_path,
        "observer_database_path": observer_database_path,
        "hydration_policy_path": hydration_policy_path,
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
        "expected_hydration_policy_fingerprint_sha256": (
            expected_hydration_policy_fingerprint_sha256
        ),
        "selection_clock": selection_clock,
        "future_path_label_version": future_path_label_version,
        "counterfactual_base_quantity": _encode_numeric(
            counterfactual_base_quantity
        ),
        "horizon_ms": horizon_ms,
        "minimum_raw_rows_per_partition": (
            minimum_raw_rows_per_partition
        ),
        "minimum_test_scored_observations": (
            minimum_test_scored_observations
        ),
        "evaluation_policy": _evaluation_policy_document(
            evaluation_policy
        ),
        "champion_version": champion_version,
        "model_version_prefix": model_version_prefix,
        "training_policy_version": training_policy_version,
        "reason": reason,
    }


def _training_execution_cost_policy_document(
    policy: FastTrainingExecutionCostPolicy,
) -> dict[str, object]:
    return json.loads(encode_fast_training_execution_cost_policy(policy))


def _decode_training_execution_cost_policy(
    value: object,
) -> FastTrainingExecutionCostPolicy:
    if not isinstance(value, dict):
        raise ValueError("training execution cost policy must be an object")
    return decode_fast_training_execution_cost_policy(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


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


def _decode_evaluation_policy(
    value: object,
) -> FastForecastEvaluationPolicy:
    if (
        not isinstance(value, dict)
        or frozenset(value) != _EVALUATION_POLICY_KEYS
    ):
        raise ValueError(
            "first champion host evaluation policy fields are incompatible"
        )
    try:
        partition = FastForecastEvaluationPartition(
            value["partition"]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "first champion host evaluation partition is incompatible"
        ) from exc
    liquidity = value["liquidity_capacity_quote_boundaries"]
    costs = value["round_trip_cost_bps_boundaries"]
    if not isinstance(liquidity, list) or not isinstance(costs, list):
        raise ValueError(
            "first champion host evaluation boundaries must be arrays"
        )
    return FastForecastEvaluationPolicy(
        version=_text(
            value["version"],
            "evaluation policy version",
        ),
        partition=partition,
        probability_bucket_count=_integer(
            value["probability_bucket_count"],
            "probability_bucket_count",
        ),
        liquidity_capacity_quote_boundaries=tuple(
            _decode_numeric(item, "liquidity boundary")
            for item in liquidity
        ),
        round_trip_cost_bps_boundaries=tuple(
            _decode_numeric(item, "cost boundary")
            for item in costs
        ),
        binary_log_loss_clip_epsilon=_decode_numeric(
            value["binary_log_loss_clip_epsilon"],
            "binary_log_loss_clip_epsilon",
        ),
    )


def _manifest_document(
    manifest: FastFirstChampionHostRunManifest,
) -> dict[str, object]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "request_fingerprint_sha256": (
            manifest.request_fingerprint_sha256
        ),
        "request_file_sha256": manifest.request_file_sha256,
        "hydration_policy_fingerprint_sha256": (
            manifest.hydration_policy_fingerprint_sha256
        ),
        "hydration_policy_file_sha256": (
            manifest.hydration_policy_file_sha256
        ),
        "selection_clock": manifest.selection_clock,
        "selection_at_unix_ms": manifest.selection_at_unix_ms,
        "expected_release_source_sha": (
            manifest.expected_release_source_sha
        ),
        "proof_workspace_artifact_fingerprint_sha256": (
            manifest.proof_workspace_artifact_fingerprint_sha256
        ),
        "feature_source_jsonl_sha256": (
            manifest.feature_source_jsonl_sha256
        ),
        "training_economics_overlay_manifest_fingerprint_sha256": (
            manifest.training_economics_overlay_manifest_fingerprint_sha256
        ),
        "training_execution_cost_policy_fingerprint_sha256": (
            manifest.training_execution_cost_policy_fingerprint_sha256
        ),
        "plan_fingerprint_sha256": manifest.plan_fingerprint_sha256,
        "plan_file_sha256": manifest.plan_file_sha256,
        "training_bundle_fingerprint_sha256": (
            manifest.training_bundle_fingerprint_sha256
        ),
        "validation_policy_fingerprint_sha256": (
            manifest.validation_policy_fingerprint_sha256
        ),
        "preparation_artifact_fingerprint_sha256": (
            manifest.preparation_artifact_fingerprint_sha256
        ),
        "context_fingerprint_sha256": (
            manifest.context_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "artifact_fingerprint_sha256": (
            manifest.artifact_fingerprint_sha256
        ),
    }


def _host_wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _resolve_directory(
    base: Path,
    value: str,
    *,
    label: str,
) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} directory is missing: {value}")
    return path


def _resolve_file(
    base: Path,
    value: str,
    *,
    label: str,
) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} file is missing: {value}")
    return path


def _resolve_source_directory(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if path.is_symlink() or not path.is_dir():
        raise ValueError(
            f"first champion host source directory is missing or unsafe: {value}"
        )
    if {child.name for child in path.iterdir()} != {"rows.jsonl", "manifest.json"}:
        raise ValueError(
            "first champion host training economics overlay must contain exactly rows.jsonl and manifest.json"
        )
    return path


def _capture_training_economics(
    overlay: Path,
) -> _TrainingEconomicsSnapshot:
    manifest = overlay / "manifest.json"
    rows = overlay / "rows.jsonl"
    if manifest.is_symlink() or rows.is_symlink():
        raise ValueError("training economics overlay files must not be symlinks")
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("training economics overlay manifest is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("training economics overlay manifest must be an object")
    fingerprint = document.get("manifest_fingerprint_sha256")
    _require_sha256(
        "training_economics_overlay_manifest_fingerprint_sha256",
        fingerprint,
    )
    return _TrainingEconomicsSnapshot(
        manifest_fingerprint_sha256=fingerprint,
        manifest_file_sha256=_sha256_file_stable(manifest),
        rows_file_sha256=_sha256_file_stable(rows),
    )


def _resolve_destination(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _encode_numeric(value: object) -> object:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise ValueError(
            "first champion host numeric value must be int or float"
        )
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        raise ValueError(
            "first champion host float must be finite"
        )
    return {"$float": value.hex()}


def _decode_numeric(value: object, name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{name} boolean is forbidden")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(
            f"{name} raw JSON float is forbidden; tagged float is required"
        )
    if not isinstance(value, dict) or frozenset(value) != {"$float"}:
        raise ValueError(
            f"{name} must be an integer or exact tagged float"
        )
    raw = value["$float"]
    if not isinstance(raw, str):
        raise ValueError(f"{name} tagged float must be text")
    try:
        decoded = float.fromhex(raw)
    except ValueError as exc:
        raise ValueError(f"{name} tagged float is malformed") from exc
    if not math.isfinite(decoded):
        raise ValueError(f"{name} tagged float must be finite")
    return decoded


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            f"{label} must have exactly one trailing newline"
        )
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    if _canonical(value) != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


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


def _sha256_file_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source must be an existing regular file: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("source changed while fingerprinting")
    return digest.hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_non_empty(name: str, value: object) -> None:
    _text(value, name)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} must be positive and finite")


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            "expected release source SHA must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
