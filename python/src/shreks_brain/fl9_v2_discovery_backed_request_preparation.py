from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPolicy
from shreks_brain.fast_first_champion_v2 import host_request as request_module
from shreks_brain.fast_first_champion_v2.host_request import (
    decode_fast_first_champion_v2_host_request,
    write_fast_first_champion_v2_host_request_from_sources,
)
from shreks_brain.fast_proof_workspace import read_fast_proof_workspace
from shreks_brain.fl9_v2_cohort_acceptance import (
    read_fl9_v2_cohort_acceptance,
)
from shreks_brain.fl9_v2_discovery_authority_binding import (
    DiscoveryAuthorityBindingError,
    decode_fl9_v2_discovery_authority_binding,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


_SCHEMA_NAME = "shreks.fl9_v2_discovery_backed_request_preparation"
_SCHEMA_VERSION = 1
_REQUEST_PREPARATION_AUTHORITY = "DISCOVERY_BOUND_REQUEST_ONLY"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"


class DiscoveryBackedRequestPreparationError(RuntimeError):
    """Raised when a discovery-backed V2 request cannot be prepared safely."""


def prepare_discovery_backed_v2_request(
    *,
    discovery_authority_binding_path: str | Path,
    proof_workspace_path: str | Path,
    observer_database_path: str | Path,
    cohort_artifact_path: str | Path,
    hydration_policy_path: str | Path,
    training_economics_overlay_path: str | Path,
    training_execution_cost_policy_path: str | Path,
    request_destination: str | Path,
    evidence_destination: str | Path,
    preparation_destination: str | Path,
    future_path_label_version: int,
    counterfactual_base_quantity: float | int,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    model_version_prefix: str,
    training_policy_version: str,
    reason: str,
) -> dict[str, object]:
    binding_path = _resolve_existing_regular_file(
        discovery_authority_binding_path,
        label="discovery authority binding",
    )
    hydration_path = _resolve_existing_regular_file(
        hydration_policy_path,
        label="hydration policy",
    )
    proof_path = _resolve_existing_directory(
        proof_workspace_path,
        label="proof workspace",
    )
    cohort_path = _resolve_existing_directory(
        cohort_artifact_path,
        label="frozen V2 cohort",
    )
    database_path = _resolve_existing_regular_file(
        observer_database_path,
        label="observer database",
    )
    overlay_path = _resolve_existing_directory(
        training_economics_overlay_path,
        label="training economics overlay",
    )
    cost_path = _resolve_existing_regular_file(
        training_execution_cost_policy_path,
        label="training execution cost policy",
    )

    request_path = _resolve_new_destination(
        request_destination,
        label="V2 request destination",
    )
    preparation_path = _resolve_new_destination(
        preparation_destination,
        label="preparation receipt destination",
    )
    evidence_path = Path(evidence_destination).expanduser().resolve()
    if evidence_path.exists() or evidence_path.is_symlink():
        raise FileExistsError("V2 evidence destination already exists")
    if (
        request_path in {preparation_path, evidence_path}
        or preparation_path == evidence_path
    ):
        raise DiscoveryBackedRequestPreparationError(
            "request, evidence, and preparation destinations must be different"
        )

    binding_payload = _read_regular_file_stable(
        binding_path,
        label="discovery authority binding",
    )
    try:
        binding = decode_fl9_v2_discovery_authority_binding(
            binding_payload.decode("utf-8")
        )
    except (
        DiscoveryAuthorityBindingError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"discovery authority binding authentication failed: {error}"
        ) from error

    runtime_path = _runtime_manifest_path_from_binding(binding)
    runtime_payload = _read_regular_file_stable(
        runtime_path,
        label="selected runtime manifest",
    )
    try:
        runtime_manifest = decode_observer_paper_campaign_runtime_manifest(
            runtime_payload
        )
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise DiscoveryBackedRequestPreparationError(
            f"selected runtime manifest authentication failed: {error}"
        ) from error
    _require_runtime_manifest_matches_binding(
        runtime_manifest=runtime_manifest,
        binding=binding,
    )

    hydration_payload = _read_regular_file_stable(
        hydration_path,
        label="hydration policy",
    )
    try:
        hydration_policy = decode_fast_forecast_context_hydration_policy(
            hydration_payload.decode("utf-8")
        )
        hydration_fingerprint = (
            fast_forecast_context_hydration_policy_fingerprint_sha256(
                hydration_policy
            )
        )
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"hydration policy authentication failed: {error}"
        ) from error
    if (
        hydration_fingerprint
        != binding["hydration_policy_fingerprint_sha256"]
    ):
        raise DiscoveryBackedRequestPreparationError(
            "hydration policy fingerprint does not match discovery authority"
        )

    try:
        proof = read_fast_proof_workspace(proof_path)
        cohort = read_fl9_v2_cohort_acceptance(cohort_path)
    except (OSError, TypeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"request source authentication failed: {error}"
        ) from error
    if proof.manifest.release_source_sha != binding["release_source_sha"]:
        raise DiscoveryBackedRequestPreparationError(
            "proof workspace release does not match discovery authority"
        )
    if (
        cohort.manifest.artifact_fingerprint_sha256
        != binding["cohort_artifact_fingerprint_sha256"]
    ):
        raise DiscoveryBackedRequestPreparationError(
            "frozen cohort fingerprint does not match discovery authority"
        )

    proof_manifest_before = proof.manifest
    cohort_manifest_before = cohort.manifest

    wrote_request = False
    try:
        result = write_fast_first_champion_v2_host_request_from_sources(
            proof_workspace_path=proof_path,
            observer_database_path=database_path,
            cohort_artifact_path=cohort_path,
            hydration_policy_path=hydration_path,
            training_economics_overlay_path=overlay_path,
            training_execution_cost_policy_path=cost_path,
            request_destination=request_path,
            evidence_destination=evidence_path,
            future_path_label_version=future_path_label_version,
            counterfactual_base_quantity=counterfactual_base_quantity,
            evaluation_policy=evaluation_policy,
            champion_version=champion_version,
            model_version_prefix=model_version_prefix,
            training_policy_version=training_policy_version,
            reason=reason,
        )
        wrote_request = True
        if result.path != request_path:
            raise DiscoveryBackedRequestPreparationError(
                "canonical request writer returned an unexpected destination"
            )
        request_payload = _read_regular_file_stable(
            request_path,
            label="prepared V2 request",
        )
        try:
            request = decode_fast_first_champion_v2_host_request(
                request_payload.decode("utf-8")
            )
        except (UnicodeDecodeError, TypeError, ValueError) as error:
            raise DiscoveryBackedRequestPreparationError(
                f"prepared V2 request authentication failed: {error}"
            ) from error

        _require_request_matches_binding(
            request=request,
            binding=binding,
            evidence_path=evidence_path,
        )

        if _read_regular_file_stable(
            binding_path,
            label="discovery authority binding",
        ) != binding_payload:
            raise DiscoveryBackedRequestPreparationError(
                "discovery authority binding changed during request preparation"
            )
        if _read_regular_file_stable(
            runtime_path,
            label="selected runtime manifest",
        ) != runtime_payload:
            raise DiscoveryBackedRequestPreparationError(
                "selected runtime manifest changed during request preparation"
            )
        if _read_regular_file_stable(
            hydration_path,
            label="hydration policy",
        ) != hydration_payload:
            raise DiscoveryBackedRequestPreparationError(
                "hydration policy changed during request preparation"
            )

        try:
            proof_after = read_fast_proof_workspace(proof_path)
            cohort_after = read_fl9_v2_cohort_acceptance(cohort_path)
        except (OSError, TypeError, ValueError) as error:
            raise DiscoveryBackedRequestPreparationError(
                f"request source reauthentication failed: {error}"
            ) from error
        if proof_after.manifest != proof_manifest_before:
            raise DiscoveryBackedRequestPreparationError(
                "proof workspace changed during request preparation"
            )
        if cohort_after.manifest != cohort_manifest_before:
            raise DiscoveryBackedRequestPreparationError(
                "frozen cohort changed during request preparation"
            )

        material: dict[str, object] = {
            "schema_name": _SCHEMA_NAME,
            "schema_version": _SCHEMA_VERSION,
            "discovery_binding_sha256": hashlib.sha256(
                binding_payload
            ).hexdigest(),
            "discovery_binding_fingerprint_sha256": binding[
                "binding_fingerprint_sha256"
            ],
            "discovery_result_sha256": binding["discovery_result_sha256"],
            "release_source_sha": binding["release_source_sha"],
            "cohort_artifact_fingerprint_sha256": binding[
                "cohort_artifact_fingerprint_sha256"
            ],
            "hydration_policy_fingerprint_sha256": binding[
                "hydration_policy_fingerprint_sha256"
            ],
            "runtime_manifest_source_kind": binding[
                "runtime_manifest_source_kind"
            ],
            "runtime_manifest_source_path": str(runtime_path),
            "runtime_manifest_fingerprint_sha256": binding[
                "runtime_manifest_fingerprint_sha256"
            ],
            "quote_asset_mint": binding["quote_asset_mint"],
            "quote_asset_decimals": binding["quote_asset_decimals"],
            "quote_provider": binding["quote_provider"],
            "request_sha256": hashlib.sha256(request_payload).hexdigest(),
            "request_fingerprint_sha256": request.request_fingerprint_sha256,
            "request_path": str(request_path),
            "evidence_destination": str(evidence_path),
            "request_preparation_authority": (
                _REQUEST_PREPARATION_AUTHORITY
            ),
            "scoring_authority": "NOT_GRANTED",
            "champion_publication_authority": "NOT_GRANTED",
            "paper_promotion_authority": "BLOCKED",
            "live_authority": "DISABLED",
        }
        receipt = {
            **material,
            "preparation_fingerprint_sha256": _sha256_canonical(material),
        }
        _write_once(preparation_path, receipt)
        written = _read_regular_file_stable(
            preparation_path,
            label="preparation receipt",
        )
        verified = decode_discovery_backed_request_preparation(
            written.decode("utf-8")
        )
        if verified != receipt:
            raise DiscoveryBackedRequestPreparationError(
                "written preparation receipt did not round-trip"
            )
        return receipt
    except Exception:
        if wrote_request:
            try:
                request_path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            preparation_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def decode_discovery_backed_request_preparation(
    payload: str,
) -> dict[str, object]:
    document = _decode_canonical_text(
        payload,
        label="discovery-backed request preparation",
    )
    expected_keys = {
        "schema_name",
        "schema_version",
        "discovery_binding_sha256",
        "discovery_binding_fingerprint_sha256",
        "discovery_result_sha256",
        "release_source_sha",
        "cohort_artifact_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
        "runtime_manifest_source_kind",
        "runtime_manifest_source_path",
        "runtime_manifest_fingerprint_sha256",
        "quote_asset_mint",
        "quote_asset_decimals",
        "quote_provider",
        "request_sha256",
        "request_fingerprint_sha256",
        "request_path",
        "evidence_destination",
        "request_preparation_authority",
        "scoring_authority",
        "champion_publication_authority",
        "paper_promotion_authority",
        "live_authority",
        "preparation_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise DiscoveryBackedRequestPreparationError(
            "preparation receipt has unknown or missing fields"
        )
    if (
        document["schema_name"] != _SCHEMA_NAME
        or document["schema_version"] != _SCHEMA_VERSION
    ):
        raise DiscoveryBackedRequestPreparationError(
            "preparation receipt schema is unsupported"
        )
    authority = {
        "request_preparation_authority": _REQUEST_PREPARATION_AUTHORITY,
        "scoring_authority": _NOT_GRANTED,
        "champion_publication_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for field, expected in authority.items():
        if document.get(field) != expected:
            raise DiscoveryBackedRequestPreparationError(
                f"preparation receipt {field} is not allowed"
            )
    claimed = document["preparation_fingerprint_sha256"]
    material = dict(document)
    del material["preparation_fingerprint_sha256"]
    if claimed != _sha256_canonical(material):
        raise DiscoveryBackedRequestPreparationError(
            "preparation receipt fingerprint mismatch"
        )
    return document


def _runtime_manifest_path_from_binding(
    binding: dict[str, object],
) -> Path:
    raw = binding.get("runtime_manifest_source_path")
    if not isinstance(raw, str) or not raw:
        raise DiscoveryBackedRequestPreparationError(
            "discovery authority runtime manifest path is invalid"
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise DiscoveryBackedRequestPreparationError(
            "discovery authority runtime manifest path must be absolute"
        )
    return _resolve_existing_regular_file(
        path,
        label="selected runtime manifest",
    )


def _require_runtime_manifest_matches_binding(
    *,
    runtime_manifest,
    binding: dict[str, object],
) -> None:
    if (
        runtime_manifest.manifest_fingerprint_sha256
        != binding["runtime_manifest_fingerprint_sha256"]
    ):
        raise DiscoveryBackedRequestPreparationError(
            "runtime manifest fingerprint does not match discovery authority"
        )
    quote_asset = runtime_manifest.policy_bundle.quote_asset
    if quote_asset.mint != binding["quote_asset_mint"]:
        raise DiscoveryBackedRequestPreparationError(
            "runtime manifest quote mint does not match discovery authority"
        )
    if quote_asset.decimals != binding["quote_asset_decimals"]:
        raise DiscoveryBackedRequestPreparationError(
            "runtime manifest quote decimals do not match discovery authority"
        )


def _require_request_matches_binding(
    *,
    request,
    binding: dict[str, object],
    evidence_path: Path,
) -> None:
    expected = {
        "expected_release_source_sha": binding["release_source_sha"],
        "expected_cohort_artifact_fingerprint_sha256": binding[
            "cohort_artifact_fingerprint_sha256"
        ],
        "expected_hydration_policy_fingerprint_sha256": binding[
            "hydration_policy_fingerprint_sha256"
        ],
        "destination_path": str(evidence_path),
    }
    for field, value in expected.items():
        if getattr(request, field) != value:
            raise DiscoveryBackedRequestPreparationError(
                f"prepared V2 request {field} does not match discovery authority"
            )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise DiscoveryBackedRequestPreparationError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} could not be resolved"
        ) from error


def _resolve_existing_directory(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_dir():
        raise DiscoveryBackedRequestPreparationError(
            f"{label} must be an existing real directory"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} could not be resolved"
        ) from error


def _resolve_new_destination(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"{label} already exists")
    return path


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} could not be read"
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != before.st_size:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(
    destination: Path,
    document: dict[str, object],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise DiscoveryBackedRequestPreparationError(
            "preparation receipt parent must be a real directory"
        )
    payload = _canonical(document).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                "preparation receipt destination appeared during write"
            )
        temporary.rename(destination)
        destination.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _decode_canonical_text(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} is not valid canonical JSON"
        ) from error
    if not isinstance(document, dict) or _canonical(document) != payload:
        raise DiscoveryBackedRequestPreparationError(
            f"{label} must be a canonical JSON object"
        )
    return document


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON value is forbidden: {value}")


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


def _evaluation_policy_from_path(
    path: str | Path,
) -> FastForecastEvaluationPolicy:
    source = _resolve_existing_regular_file(
        path,
        label="evaluation policy",
    )
    payload = _read_regular_file_stable(source, label="evaluation policy")
    try:
        document = _decode_canonical_text(
            payload.decode("utf-8"),
            label="evaluation policy",
        )
        return request_module._decode_evaluation_policy(document)
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise DiscoveryBackedRequestPreparationError(
            f"evaluation policy is invalid: {error}"
        ) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-discovery-backed-request-prepare",
        description=(
            "Prepare one canonical FL9 V2 host request plus an immutable "
            "discovery-bound provenance receipt without executing the request."
        ),
    )
    parser.add_argument("--discovery-authority-binding", required=True)
    parser.add_argument("--proof-workspace", required=True)
    parser.add_argument("--observer-database", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--hydration-policy", required=True)
    parser.add_argument("--training-economics-overlay", required=True)
    parser.add_argument("--training-execution-cost-policy", required=True)
    parser.add_argument("--request-destination", required=True)
    parser.add_argument("--evidence-destination", required=True)
    parser.add_argument("--preparation-destination", required=True)
    parser.add_argument("--evaluation-policy", required=True)
    parser.add_argument("--future-path-label-version", required=True, type=int)
    parser.add_argument(
        "--counterfactual-base-quantity",
        required=True,
        type=float,
    )
    parser.add_argument("--champion-version", required=True)
    parser.add_argument("--model-version-prefix", required=True)
    parser.add_argument("--training-policy-version", required=True)
    parser.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = prepare_discovery_backed_v2_request(
            discovery_authority_binding_path=(
                args.discovery_authority_binding
            ),
            proof_workspace_path=args.proof_workspace,
            observer_database_path=args.observer_database,
            cohort_artifact_path=args.cohort,
            hydration_policy_path=args.hydration_policy,
            training_economics_overlay_path=(
                args.training_economics_overlay
            ),
            training_execution_cost_policy_path=(
                args.training_execution_cost_policy
            ),
            request_destination=args.request_destination,
            evidence_destination=args.evidence_destination,
            preparation_destination=args.preparation_destination,
            future_path_label_version=args.future_path_label_version,
            counterfactual_base_quantity=args.counterfactual_base_quantity,
            evaluation_policy=_evaluation_policy_from_path(
                args.evaluation_policy
            ),
            champion_version=args.champion_version,
            model_version_prefix=args.model_version_prefix,
            training_policy_version=args.training_policy_version,
            reason=args.reason,
        )
    except (
        DiscoveryBackedRequestPreparationError,
        DiscoveryAuthorityBindingError,
        FileExistsError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.write(
            _canonical(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "scoring_authority": "NOT_GRANTED",
                    "champion_publication_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1

    sys.stdout.write(_canonical(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
