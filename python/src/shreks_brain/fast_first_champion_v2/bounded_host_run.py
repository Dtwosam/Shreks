from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
    hydrate_fast_forecast_evaluation_contexts,
)
from shreks_brain.fl9_v2_cohort_acceptance import (
    read_fl9_v2_cohort_acceptance,
)
from shreks_brain.research.fast_training_economics import (
    validate_fast_training_economics_overlay,
)

from .artifact import (
    read_fast_first_champion_v2_evidence,
    write_fast_first_champion_v2_evidence,
)
from .bounded_bundle import build_fast_first_champion_v2_bundle
from .bounded_inputs import read_fast_proof_workspace_manifest_bounded
from .builder import build_fast_first_champion_v2
from .host_request import (
    decode_fast_first_champion_v2_host_request,
)
from .host_run import (
    FAST_FIRST_CHAMPION_V2_HOST_STATUS_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_V2_HOST_STATUS_SCHEMA_VERSION,
    _database_data_version,
    _frozen_context_validation_policy,
    _open_database_change_sentinel,
    _require_database_quiesced,
    _resolve_destination,
    _resolve_directory,
    _resolve_file,
    _validate_cohort,
    _validate_reopened,
    _verify_deployed_release_identity,
)
from .hydration_policy import (
    require_fast_first_champion_v2_hydration_policy_matches_identities,
)
from .models import FastFirstChampionV2Policy


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

    _verify_deployed_release_identity(
        request.expected_release_source_sha
    )

    proof_manifest = read_fast_proof_workspace_manifest_bounded(proof_path)
    if proof_manifest.release_source_sha != request.expected_release_source_sha:
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

    overlay_manifest = validate_fast_training_economics_overlay(overlay_path)
    if (
        overlay_manifest.manifest_fingerprint_sha256
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
    require_fast_first_champion_v2_hydration_policy_matches_identities(
        hydration_policy=hydration_policy,
        accepted_decision_identities=(
            accepted.decision_identity
            for accepted in cohort.accepted_decisions
        ),
    )

    _require_database_quiesced()
    sentinel = _open_database_change_sentinel(database_path)
    try:
        data_version_before = _database_data_version(sentinel)

        built_cohort, bundle = build_fast_first_champion_v2_bundle(
            cohort=cohort,
            proof_manifest=proof_manifest,
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
        if bundle.features.source_sha256 != proof_manifest.feature_jsonl_sha256:
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

        _require_database_quiesced()
        data_version_after = _database_data_version(sentinel)
        if data_version_after != data_version_before:
            raise ValueError(
                "V2 observer database changed during bundle/context "
                "evidence reads"
            )
    finally:
        sentinel.close()

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

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.host-staging-",
            dir=destination.parent,
        )
    )
    staged_destination = staging_root / "evidence"
    try:
        artifact = write_fast_first_champion_v2_evidence(
            build,
            staged_destination,
            policy=policy,
        )
        reopened = read_fast_first_champion_v2_evidence(
            staged_destination
        )
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
        proof_after = read_fast_proof_workspace_manifest_bounded(proof_path)
        cohort_after = read_fl9_v2_cohort_acceptance(cohort_path)
        overlay_after = validate_fast_training_economics_overlay(overlay_path)
        if proof_after != proof_manifest:
            raise ValueError(
                "V2 first-champion proof workspace changed during execution"
            )
        if cohort_after.manifest != cohort.manifest:
            raise ValueError(
                "V2 first-champion cohort artifact changed during execution"
            )
        if overlay_after != overlay_manifest:
            raise ValueError(
                "V2 first-champion training economics overlay changed during execution"
            )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                "V2 first-champion evidence destination appeared during execution"
            )

        staged_destination.rename(destination)
        final = read_fast_first_champion_v2_evidence(destination)
        if final.manifest != reopened.manifest:
            raise ValueError(
                "published V2 first-champion evidence changed after atomic move"
            )
        return final
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)


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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
