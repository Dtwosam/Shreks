from __future__ import annotations

import argparse
import json
from pathlib import Path

from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
    hydrate_fast_forecast_evaluation_contexts,
)
from shreks_brain.fast_proof_workspace import read_fast_proof_workspace
from shreks_brain.fast_validation import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
)
from shreks_brain.fl9_v2_cohort_acceptance import (
    read_fl9_v2_cohort_acceptance,
)
from shreks_brain.research.fast_training_economics import (
    read_fast_training_economics_overlay,
)

from .artifact import (
    read_fast_first_champion_v2_evidence,
    write_fast_first_champion_v2_evidence,
)
from .builder import build_fast_first_champion_v2
from .bundle import (
    _validate_cohort,
    build_fast_first_champion_v2_bundle,
)
from .host_request import (
    FastFirstChampionV2HostRequest,
    decode_fast_first_champion_v2_host_request,
)
from .models import FastFirstChampionV2Policy


FAST_FIRST_CHAMPION_V2_HOST_STATUS_SCHEMA_NAME = (
    "shreks.fast_first_champion_v2_host_status"
)
FAST_FIRST_CHAMPION_V2_HOST_STATUS_SCHEMA_VERSION = 1
_CONTEXT_POLICY_VERSION = (
    "fl9-v2-first-champion-context-hydration-v1"
)
_CONTEXT_FOLD_NAME = "fl9-v2-first-champion-v1"


def run_fast_first_champion_v2_host_request(
    request_path: str | Path,
):
    source = Path(request_path).expanduser().resolve()
    if source.is_symlink() or not source.is_file():
        raise ValueError(
            "V2 first-champion request path must be an existing regular file"
        )
    request_payload = source.read_text(encoding="utf-8")
    request = decode_fast_first_champion_v2_host_request(request_payload)
    base = source.parent

    proof_path = _resolve_directory(
        base,
        request.proof_workspace_path,
        "proof workspace",
    )
    database_path = _resolve_file(
        base,
        request.observer_database_path,
        "observer database",
    )
    cohort_path = _resolve_directory(
        base,
        request.cohort_artifact_path,
        "cohort artifact",
    )
    hydration_path = _resolve_file(
        base,
        request.hydration_policy_path,
        "hydration policy",
    )
    overlay_path = _resolve_directory(
        base,
        request.training_economics_overlay_path,
        "training economics overlay",
    )
    if {item.name for item in overlay_path.iterdir()} != {
        "manifest.json",
        "rows.jsonl",
    }:
        raise ValueError(
            "V2 training economics overlay must contain exactly "
            "manifest.json and rows.jsonl"
        )
    destination = _resolve_destination(base, request.destination_path)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "V2 first-champion evidence destination already exists"
        )

    # Release identity is checked before any cohort/target source is opened.
    proof = read_fast_proof_workspace(proof_path)
    if proof.manifest.release_source_sha != request.expected_release_source_sha:
        raise ValueError(
            "V2 first-champion release source mismatch"
        )

    cohort = read_fl9_v2_cohort_acceptance(cohort_path)
    policy = FastFirstChampionV2Policy()
    if (
        cohort.manifest.artifact_fingerprint_sha256
        != request.expected_cohort_artifact_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion physical cohort fingerprint mismatch"
        )
    _validate_cohort(cohort, policy)
    validation_policy = _frozen_context_validation_policy(
        cohort,
        policy,
    )

    overlay = read_fast_training_economics_overlay(overlay_path)
    if (
        overlay.manifest.manifest_fingerprint_sha256
        != request.expected_training_economics_overlay_manifest_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion training economics overlay fingerprint mismatch"
        )

    hydration_payload = hydration_path.read_text(encoding="utf-8")
    hydration_policy = decode_fast_forecast_context_hydration_policy(
        hydration_payload
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
            "V2 first-champion hydration policy fingerprint mismatch"
        )

    built_cohort, bundle = build_fast_first_champion_v2_bundle(
        cohort_path=cohort_path,
        feature_jsonl_path=proof_path / "features.jsonl",
        sqlite_path=database_path,
        future_path_label_version=request.future_path_label_version,
        training_economics_overlay_path=overlay_path,
        training_execution_cost_policy=(
            request.training_execution_cost_policy
        ),
        counterfactual_base_quantity=float(
            request.counterfactual_base_quantity
        ),
        policy=policy,
    )
    if (
        built_cohort.manifest.artifact_fingerprint_sha256
        != cohort.manifest.artifact_fingerprint_sha256
    ):
        raise ValueError(
            "V2 bundle builder cohort does not match authenticated cohort"
        )
    if (
        bundle.features.source_sha256
        != proof.manifest.feature_jsonl_sha256
        or bundle.features.logical_fingerprint_sha256
        != proof.manifest.feature_logical_fingerprint_sha256
    ):
        raise ValueError(
            "V2 training bundle feature source does not match proof workspace"
        )

    hydration = hydrate_fast_forecast_evaluation_contexts(
        bundle=bundle,
        observer_database_path=database_path,
        validation_policy=validation_policy,
        horizon_ms=policy.horizon_ms,
        hydration_policy=hydration_policy,
    )
    contexts = hydration.context_corpus.contexts

    build = build_fast_first_champion_v2(
        cohort=cohort,
        bundle=bundle,
        contexts=contexts,
        evaluation_policy=request.evaluation_policy,
        champion_version=request.champion_version,
        decision_reference=(
            "v2-first-champion-host-request:"
            f"{request.request_fingerprint_sha256}"
        ),
        reason=request.reason,
        model_version_prefix=request.model_version_prefix,
        training_policy_version=request.training_policy_version,
        policy=policy,
    )
    if (
        build.training_bundle_fingerprint_sha256
        != bundle.manifest.bundle_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion build bundle fingerprint mismatch"
        )

    artifact = write_fast_first_champion_v2_evidence(
        build,
        destination,
        policy=policy,
    )
    reopened = read_fast_first_champion_v2_evidence(destination)
    _validate_reopened(
        request=request,
        policy=policy,
        cohort=cohort,
        bundle=bundle,
        build=build,
        artifact=artifact,
        reopened=reopened,
    )

    if source.read_text(encoding="utf-8") != request_payload:
        raise ValueError(
            "V2 first-champion request source changed during execution"
        )
    if hydration_path.read_text(encoding="utf-8") != hydration_payload:
        raise ValueError(
            "V2 first-champion hydration source changed during execution"
        )
    proof_after = read_fast_proof_workspace(proof_path)
    cohort_after = read_fl9_v2_cohort_acceptance(cohort_path)
    overlay_after = read_fast_training_economics_overlay(overlay_path)
    if proof_after.manifest != proof.manifest:
        raise ValueError(
            "V2 first-champion proof workspace changed during execution"
        )
    if cohort_after.manifest != cohort.manifest:
        raise ValueError(
            "V2 first-champion cohort artifact changed during execution"
        )
    if overlay_after.manifest != overlay.manifest:
        raise ValueError(
            "V2 first-champion training economics overlay changed during execution"
        )

    return reopened


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-first-champion",
        description=(
            "Execute one canonical FL9 V2 first-champion production "
            "evidence request."
        ),
    )
    parser.add_argument("request")
    args = parser.parse_args(argv)

    source = Path(args.request).expanduser().resolve()
    request = decode_fast_first_champion_v2_host_request(
        source.read_text(encoding="utf-8")
    )
    artifact = run_fast_first_champion_v2_host_request(source)
    print(
        json.dumps(
            {
                "schema_name": (
                    FAST_FIRST_CHAMPION_V2_HOST_STATUS_SCHEMA_NAME
                ),
                "schema_version": (
                    FAST_FIRST_CHAMPION_V2_HOST_STATUS_SCHEMA_VERSION
                ),
                "status": "SUCCEEDED",
                "request_fingerprint_sha256": (
                    request.request_fingerprint_sha256
                ),
                "release_source_sha": request.expected_release_source_sha,
                "cohort_artifact_fingerprint_sha256": (
                    artifact.manifest.cohort_artifact_fingerprint_sha256
                ),
                "training_bundle_fingerprint_sha256": (
                    artifact.manifest.training_bundle_fingerprint_sha256
                ),
                "champion_fingerprint_sha256": (
                    artifact.manifest.champion_fingerprint_sha256
                ),
                "evidence_artifact_fingerprint_sha256": (
                    artifact.manifest.artifact_fingerprint_sha256
                ),
                "destination_path": str(artifact.path),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


def _frozen_context_validation_policy(
    cohort,
    policy: FastFirstChampionV2Policy,
) -> FastChronologicalValidationPolicy:
    manifest = cohort.manifest
    expected = (
        manifest.minimum_decision_observed_at_unix_ms,
        manifest.training_cut_unix_ms,
        manifest.validation_cut_unix_ms,
        manifest.test_end_unix_ms,
        manifest.selection_at_unix_ms,
        manifest.horizon_ms,
    )
    frozen = (
        policy.training_started_at_unix_ms,
        policy.training_ended_at_unix_ms,
        policy.validation_ended_at_unix_ms,
        policy.test_ended_at_unix_ms,
        policy.selection_at_unix_ms,
        policy.horizon_ms,
    )
    if expected != frozen:
        raise ValueError(
            "V2 cohort chronology does not match frozen first-champion policy"
        )
    return FastChronologicalValidationPolicy(
        version=_CONTEXT_POLICY_VERSION,
        folds=(
            FastChronologicalFold(
                name=_CONTEXT_FOLD_NAME,
                training_started_at_unix_ms=(
                    manifest.minimum_decision_observed_at_unix_ms
                ),
                training_ended_at_unix_ms=manifest.training_cut_unix_ms,
                validation_started_at_unix_ms=(
                    manifest.training_cut_unix_ms
                ),
                validation_ended_at_unix_ms=(
                    manifest.validation_cut_unix_ms
                ),
                test_started_at_unix_ms=manifest.validation_cut_unix_ms,
                test_ended_at_unix_ms=manifest.test_end_unix_ms,
            ),
        ),
    )


def _validate_reopened(
    *,
    request: FastFirstChampionV2HostRequest,
    policy: FastFirstChampionV2Policy,
    cohort,
    bundle,
    build,
    artifact,
    reopened,
) -> None:
    if reopened.manifest != artifact.manifest:
        raise ValueError(
            "V2 first-champion evidence manifest changed on readback"
        )
    if (
        reopened.manifest.cohort_artifact_fingerprint_sha256
        != request.expected_cohort_artifact_fingerprint_sha256
        or reopened.manifest.cohort_artifact_fingerprint_sha256
        != cohort.manifest.artifact_fingerprint_sha256
        or reopened.manifest.cohort_artifact_fingerprint_sha256
        != policy.expected_cohort_artifact_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion evidence cohort chain does not reconcile"
        )
    if (
        reopened.manifest.training_bundle_fingerprint_sha256
        != bundle.manifest.bundle_fingerprint_sha256
        or reopened.manifest.training_bundle_fingerprint_sha256
        != build.training_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion evidence bundle chain does not reconcile"
        )
    if (
        reopened.manifest.champion_fingerprint_sha256
        != build.champion.champion_fingerprint_sha256
        or reopened.champion.champion_fingerprint_sha256
        != build.champion.champion_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion evidence champion chain does not reconcile"
        )


def _resolve_directory(base: Path, value: str, label: str) -> Path:
    path = _resolve(base, value)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be an existing real directory")
    return path


def _resolve_file(base: Path, value: str, label: str) -> Path:
    path = _resolve(base, value)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be an existing regular file")
    return path


def _resolve_destination(base: Path, value: str) -> Path:
    path = _resolve(base, value)
    if path == Path("/") or path.name in ("", ".", ".."):
        raise ValueError("V2 evidence destination is unsafe")
    return path


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
