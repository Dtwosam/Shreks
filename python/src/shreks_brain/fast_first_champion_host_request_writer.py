from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
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
from shreks_brain.fast_first_champion_host_run import (
    FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK,
    FastFirstChampionHostRequest,
    build_fast_first_champion_host_request,
    encode_fast_first_champion_host_request,
)
from shreks_brain.fast_proof_workspace import read_fast_proof_workspace


FAST_FIRST_CHAMPION_HOST_REQUEST_WRITER_VERSION = 1
FAST_FIRST_CHAMPION_HOST_REQUEST_WRITE_STATUS_SCHEMA_NAME = (
    "shreks.fast_first_champion_host_request_write_status"
)
FAST_FIRST_CHAMPION_HOST_REQUEST_WRITE_STATUS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FastFirstChampionHostRequestWriteResult:
    path: Path
    request_fingerprint_sha256: str
    release_source_sha: str
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
            "hydration_policy_fingerprint_sha256",
            self.hydration_policy_fingerprint_sha256,
        )


def write_fast_first_champion_host_request_from_sources(
    *,
    proof_workspace_path: str | Path,
    observer_database_path: str | Path,
    hydration_policy_path: str | Path,
    request_destination: str | Path,
    host_run_destination: str | Path,
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
) -> FastFirstChampionHostRequestWriteResult:
    proof_path = Path(proof_workspace_path).expanduser().resolve()
    if proof_path.is_symlink() or not proof_path.is_dir():
        raise ValueError(
            "proof workspace path must be an existing real directory"
        )
    database_path = Path(observer_database_path).expanduser().resolve()
    if database_path.is_symlink() or not database_path.is_file():
        raise ValueError(
            "observer database path must be an existing regular file"
        )
    policy_path = Path(hydration_policy_path).expanduser().resolve()
    if policy_path.is_symlink() or not policy_path.is_file():
        raise ValueError(
            "hydration policy path must be an existing regular file"
        )

    request_path = Path(request_destination).expanduser().resolve()
    if request_path.exists() or request_path.is_symlink():
        raise FileExistsError(
            "first champion host request destination already exists"
        )
    host_destination = _resolve_output_path(
        request_path.parent,
        host_run_destination,
    )
    if host_destination.exists() or host_destination.is_symlink():
        raise FileExistsError(
            "first champion host run destination already exists"
        )
    if host_destination == request_path:
        raise ValueError(
            "request destination and host run destination must differ"
        )

    if type(evaluation_policy) is not FastForecastEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact FastForecastEvaluationPolicy"
        )
    if (
        evaluation_policy.partition
        is not FastForecastEvaluationPartition.TEST
    ):
        raise ValueError(
            "first champion host request writer requires TEST evaluation"
        )

    proof_workspace = read_fast_proof_workspace(proof_path)
    policy_payload = _read_text_stable(policy_path)
    hydration_policy = (
        decode_fast_forecast_context_hydration_policy(
            policy_payload
        )
    )
    hydration_fingerprint = (
        fast_forecast_context_hydration_policy_fingerprint_sha256(
            hydration_policy
        )
    )

    request = build_fast_first_champion_host_request(
        proof_workspace_path=str(proof_path),
        observer_database_path=str(database_path),
        hydration_policy_path=str(policy_path),
        destination_path=str(host_destination),
        expected_release_source_sha=(
            proof_workspace.manifest.release_source_sha
        ),
        expected_hydration_policy_fingerprint_sha256=(
            hydration_fingerprint
        ),
        selection_clock=FAST_FIRST_CHAMPION_HOST_SELECTION_CLOCK,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        horizon_ms=horizon_ms,
        minimum_raw_rows_per_partition=(
            minimum_raw_rows_per_partition
        ),
        minimum_test_scored_observations=(
            minimum_test_scored_observations
        ),
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
    )
    payload = encode_fast_first_champion_host_request(request).encode(
        "utf-8"
    )

    request_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{request_path.name}.tmp-",
        dir=request_path.parent,
    )
    staging = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        staging.chmod(0o600)

        if _read_text_stable(policy_path) != policy_payload:
            raise ValueError(
                "hydration policy source changed during request creation"
            )
        proof_after = read_fast_proof_workspace(proof_path)
        if proof_after.manifest != proof_workspace.manifest:
            raise ValueError(
                "proof workspace source changed during request creation"
            )
        if database_path.is_symlink() or not database_path.is_file():
            raise ValueError(
                "observer database source changed during request creation"
            )
        if staging.read_bytes() != payload:
            raise ValueError(
                "staged first champion host request bytes changed"
            )
        if request_path.exists() or request_path.is_symlink():
            raise FileExistsError(
                "first champion host request destination appeared during write"
            )
        if host_destination.exists() or host_destination.is_symlink():
            raise FileExistsError(
                "first champion host run destination appeared during request write"
            )
        staging.rename(request_path)
    except Exception:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return FastFirstChampionHostRequestWriteResult(
        path=request_path,
        request_fingerprint_sha256=(
            request.request_fingerprint_sha256
        ),
        release_source_sha=(
            proof_workspace.manifest.release_source_sha
        ),
        hydration_policy_fingerprint_sha256=(
            hydration_fingerprint
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-first-champion-request",
        description=(
            "Write one canonical FL9 first-champion host request from "
            "authenticated proof-workspace and hydration-policy sources."
        ),
    )
    parser.add_argument("--proof-workspace", required=True)
    parser.add_argument("--observer-database", required=True)
    parser.add_argument("--hydration-policy", required=True)
    parser.add_argument("--request-destination", required=True)
    parser.add_argument("--host-run-destination", required=True)
    parser.add_argument(
        "--future-path-label-version",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--counterfactual-base-quantity",
        required=True,
        type=float,
    )
    parser.add_argument("--horizon-ms", required=True, type=int)
    parser.add_argument(
        "--minimum-raw-rows-per-partition",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--minimum-test-scored-observations",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--evaluation-policy-version",
        required=True,
    )
    parser.add_argument(
        "--probability-bucket-count",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--liquidity-capacity-quote-boundary",
        action="append",
        required=True,
        type=float,
        dest="liquidity_boundaries",
    )
    parser.add_argument(
        "--round-trip-cost-bps-boundary",
        action="append",
        required=True,
        type=float,
        dest="cost_boundaries",
    )
    parser.add_argument(
        "--binary-log-loss-clip-epsilon",
        required=True,
        type=float,
    )
    parser.add_argument("--champion-version", required=True)
    parser.add_argument("--model-version-prefix", required=True)
    parser.add_argument("--training-policy-version", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    evaluation_policy = FastForecastEvaluationPolicy(
        version=args.evaluation_policy_version,
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=args.probability_bucket_count,
        liquidity_capacity_quote_boundaries=tuple(
            args.liquidity_boundaries
        ),
        round_trip_cost_bps_boundaries=tuple(
            args.cost_boundaries
        ),
        binary_log_loss_clip_epsilon=(
            args.binary_log_loss_clip_epsilon
        ),
    )
    result = write_fast_first_champion_host_request_from_sources(
        proof_workspace_path=args.proof_workspace,
        observer_database_path=args.observer_database,
        hydration_policy_path=args.hydration_policy,
        request_destination=args.request_destination,
        host_run_destination=args.host_run_destination,
        future_path_label_version=args.future_path_label_version,
        counterfactual_base_quantity=(
            args.counterfactual_base_quantity
        ),
        horizon_ms=args.horizon_ms,
        minimum_raw_rows_per_partition=(
            args.minimum_raw_rows_per_partition
        ),
        minimum_test_scored_observations=(
            args.minimum_test_scored_observations
        ),
        evaluation_policy=evaluation_policy,
        champion_version=args.champion_version,
        model_version_prefix=args.model_version_prefix,
        training_policy_version=args.training_policy_version,
        reason=args.reason,
    )
    print(
        json.dumps(
            {
                "schema_name": (
                    FAST_FIRST_CHAMPION_HOST_REQUEST_WRITE_STATUS_SCHEMA_NAME
                ),
                "schema_version": (
                    FAST_FIRST_CHAMPION_HOST_REQUEST_WRITE_STATUS_SCHEMA_VERSION
                ),
                "status": "SUCCEEDED",
                "path": str(result.path),
                "request_fingerprint_sha256": (
                    result.request_fingerprint_sha256
                ),
                "release_source_sha": result.release_source_sha,
                "hydration_policy_fingerprint_sha256": (
                    result.hydration_policy_fingerprint_sha256
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


def _resolve_output_path(
    base: Path,
    value: str | Path,
) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _read_text_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "hydration policy source must remain a regular file"
        )
    before = path.stat()
    payload = path.read_text(encoding="utf-8")
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(
            "hydration policy source changed while reading"
        )
    return payload


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise ValueError(
            "release_source_sha must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise ValueError(
            f"{name} must be lowercase SHA-256 hex"
        )
