from __future__ import annotations

from pathlib import Path

from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPolicy
from shreks_brain.fl9_v2_cohort_acceptance import (
    read_fl9_v2_cohort_acceptance,
)

from .host_request import (
    FastFirstChampionV2HostRequestWriteResult,
    write_fast_first_champion_v2_host_request_from_sources,
)
from .hydration_policy import (
    require_fast_first_champion_v2_hydration_policy_matches_identities,
)


def write_quote_bound_fast_first_champion_v2_host_request_from_sources(
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
    """Write a V2 request only after cohort/hydration quote compatibility."""
    cohort_path = _existing_directory(cohort_artifact_path, "cohort artifact")
    hydration_path = _existing_file(hydration_policy_path, "hydration policy")
    request_path = Path(request_destination).expanduser().resolve()

    cohort = read_fl9_v2_cohort_acceptance(cohort_path)
    hydration_payload = _read_text_stable(hydration_path, "hydration policy")
    hydration_policy = decode_fast_forecast_context_hydration_policy(
        hydration_payload
    )
    accepted_identities = tuple(
        value.decision_identity for value in cohort.accepted_decisions
    )
    require_fast_first_champion_v2_hydration_policy_matches_identities(
        hydration_policy=hydration_policy,
        accepted_decision_identities=accepted_identities,
    )

    result = write_fast_first_champion_v2_host_request_from_sources(
        proof_workspace_path=proof_workspace_path,
        observer_database_path=observer_database_path,
        cohort_artifact_path=cohort_path,
        hydration_policy_path=hydration_path,
        training_economics_overlay_path=training_economics_overlay_path,
        training_execution_cost_policy_path=training_execution_cost_policy_path,
        request_destination=request_path,
        evidence_destination=evidence_destination,
        future_path_label_version=future_path_label_version,
        counterfactual_base_quantity=counterfactual_base_quantity,
        evaluation_policy=evaluation_policy,
        champion_version=champion_version,
        model_version_prefix=model_version_prefix,
        training_policy_version=training_policy_version,
        reason=reason,
    )

    try:
        if _read_text_stable(hydration_path, "hydration policy") != hydration_payload:
            raise ValueError(
                "hydration policy source changed across V2 quote-binding guard"
            )
        cohort_after = read_fl9_v2_cohort_acceptance(cohort_path)
        if cohort_after.manifest != cohort.manifest:
            raise ValueError(
                "cohort artifact source changed across V2 quote-binding guard"
            )
    except Exception:
        request_path.unlink(missing_ok=True)
        raise

    return result


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
