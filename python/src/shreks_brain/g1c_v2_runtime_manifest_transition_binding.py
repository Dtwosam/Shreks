from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from shreks_brain.fl9_v2_runtime_manifest_candidate_assessment import (
    FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_NAME,
    FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_VERSION,
    RuntimeManifestCandidateAssessmentError,
    assess_fl9_v2_runtime_manifest_candidate,
)
from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    G1CV2RuntimeManifestCandidateAuthoringError,
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    ObserverPaperCampaignRuntimeManifestError,
    ObserverPaperQuoteUsdValuationMode,
    decode_observer_paper_campaign_runtime_manifest,
)


G1C_V2_RUNTIME_MANIFEST_TRANSITION_BINDING_SCHEMA_NAME = (
    "shreks.g1c_v2_runtime_manifest_transition_binding"
)
G1C_V2_RUNTIME_MANIFEST_TRANSITION_BINDING_SCHEMA_VERSION = 1

_TRANSITION_KIND = "new_run_quote_asset_rotation"
_TRANSITION_STATUS = "BOUND_COMPATIBLE_CANDIDATE"
_NOT_GRANTED = "NOT_GRANTED"
_PAPER_PROMOTION_BLOCKED = "BLOCKED"
_LIVE_DISABLED = "DISABLED"
_SHA256_LENGTH = 64
_SOURCE_SHA_LENGTH = 40


class G1CV2RuntimeManifestTransitionBindingError(RuntimeError):
    """Raised when a G1C v2 transition candidate cannot be bound safely."""


def bind_g1c_v2_runtime_manifest_transition(
    *,
    source_runtime_manifest_path: str | Path,
    candidate_runtime_manifest_path: str | Path,
    cohort_path: str | Path,
    v2_host_request_authority_path: str | Path,
    destination: str | Path,
) -> dict[str, object]:
    source_path = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    candidate_path = _resolve_existing_regular_file(
        candidate_runtime_manifest_path,
        label="candidate runtime manifest",
    )
    if source_path == candidate_path:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "source and candidate runtime manifests must be different files"
        )

    source_payload = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    candidate_payload = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
        candidate = decode_observer_paper_campaign_runtime_manifest(
            candidate_payload
        )
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"runtime manifest authentication failed: {error}"
        ) from error

    if (
        source.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition source must be canonical runtime-manifest v1 authority"
        )
    if (
        candidate.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition candidate must be canonical runtime-manifest v2"
        )

    _require_exact_authoring_derivation(
        source_path=source_path,
        candidate=candidate,
    )

    try:
        assessment = assess_fl9_v2_runtime_manifest_candidate(
            cohort_path=cohort_path,
            runtime_manifest_path=candidate_path,
            v2_host_request_authority_path=v2_host_request_authority_path,
        )
    except RuntimeManifestCandidateAssessmentError as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"candidate assessment failed: {error}"
        ) from error

    candidate_report, authority = _require_compatible_assessment(
        assessment,
        candidate_path=candidate_path,
        candidate=candidate,
    )

    source_bundle = source.policy_bundle
    candidate_bundle = candidate.policy_bundle
    if source.paper_run_id == candidate.paper_run_id:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition candidate must use a different paper_run_id"
        )
    if source_bundle.quote_asset.mint == candidate_bundle.quote_asset.mint:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition candidate must use a different quote asset"
        )

    assessment_payload = _canonical_json(assessment).encode("utf-8")
    material: dict[str, object] = {
        "schema_name": G1C_V2_RUNTIME_MANIFEST_TRANSITION_BINDING_SCHEMA_NAME,
        "schema_version": (
            G1C_V2_RUNTIME_MANIFEST_TRANSITION_BINDING_SCHEMA_VERSION
        ),
        "transition_kind": _TRANSITION_KIND,
        "transition_status": _TRANSITION_STATUS,
        "source_manifest_sha256": hashlib.sha256(source_payload).hexdigest(),
        "source_runtime_manifest_fingerprint_sha256": (
            source.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": source.paper_run_id,
        "source_quote_asset_mint": source_bundle.quote_asset.mint,
        "candidate_manifest_sha256": (
            hashlib.sha256(candidate_payload).hexdigest()
        ),
        "candidate_runtime_manifest_fingerprint_sha256": (
            candidate.manifest_fingerprint_sha256
        ),
        "candidate_paper_run_id": candidate.paper_run_id,
        "candidate_start_at_unix_ms": (
            candidate.initial_state.last_cycle_at_unix_ms
        ),
        "candidate_quote_asset_mint": candidate_bundle.quote_asset.mint,
        "candidate_quote_asset_decimals": (
            candidate_bundle.quote_asset.decimals
        ),
        "candidate_quote_usd_valuation_mode": (
            candidate.quote_usd_valuation_policy.mode.value
        ),
        "candidate_hydration_policy_fingerprint_sha256": (
            candidate_report["hydration_policy_fingerprint_sha256"]
        ),
        "cohort_artifact_fingerprint_sha256": (
            authority["cohort_artifact_fingerprint_sha256"]
        ),
        "cohort_quote_mint": assessment["cohort_quote_mint"],
        "request_fingerprint_sha256": (
            authority["request_fingerprint_sha256"]
        ),
        "request_release_source_sha": authority["request_release_source_sha"],
        "request_hydration_policy_fingerprint_sha256": (
            authority["hydration_policy_fingerprint_sha256"]
        ),
        "assessment_sha256": hashlib.sha256(assessment_payload).hexdigest(),
        "installation_authority": _NOT_GRANTED,
        "activation_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _PAPER_PROMOTION_BLOCKED,
        "live_authority": _LIVE_DISABLED,
    }
    binding = {
        **material,
        "binding_fingerprint_sha256": _sha256_canonical(material),
    }

    _write_binding_once(destination, binding)
    written = Path(destination).expanduser().resolve()
    verified = decode_g1c_v2_runtime_manifest_transition_binding(
        written.read_text(encoding="utf-8")
    )
    if verified != binding:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "written transition binding did not round-trip"
        )
    return binding


def decode_g1c_v2_runtime_manifest_transition_binding(
    payload: str,
) -> dict[str, object]:
    if not isinstance(payload, str):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding payload must be text"
        )
    document = _decode_canonical_text(
        payload,
        label="transition binding",
    )
    expected_keys = {
        "schema_name",
        "schema_version",
        "transition_kind",
        "transition_status",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "candidate_paper_run_id",
        "candidate_start_at_unix_ms",
        "candidate_quote_asset_mint",
        "candidate_quote_asset_decimals",
        "candidate_quote_usd_valuation_mode",
        "candidate_hydration_policy_fingerprint_sha256",
        "cohort_artifact_fingerprint_sha256",
        "cohort_quote_mint",
        "request_fingerprint_sha256",
        "request_release_source_sha",
        "request_hydration_policy_fingerprint_sha256",
        "assessment_sha256",
        "installation_authority",
        "activation_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "binding_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding has unknown or missing fields"
        )

    if document["schema_name"] != (
        G1C_V2_RUNTIME_MANIFEST_TRANSITION_BINDING_SCHEMA_NAME
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding schema_name is unsupported"
        )
    if document["schema_version"] != (
        G1C_V2_RUNTIME_MANIFEST_TRANSITION_BINDING_SCHEMA_VERSION
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding schema_version is unsupported"
        )
    if document["transition_kind"] != _TRANSITION_KIND:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding kind is unsupported"
        )
    if document["transition_status"] != _TRANSITION_STATUS:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding status is unsupported"
        )
    if document["candidate_quote_usd_valuation_mode"] != (
        ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO.value
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding must preserve exact-market-ratio valuation"
        )

    for name in (
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "candidate_hydration_policy_fingerprint_sha256",
        "cohort_artifact_fingerprint_sha256",
        "request_fingerprint_sha256",
        "request_hydration_policy_fingerprint_sha256",
        "assessment_sha256",
        "binding_fingerprint_sha256",
    ):
        _require_lower_hex(name, document[name], _SHA256_LENGTH)
    _require_lower_hex(
        "request_release_source_sha",
        document["request_release_source_sha"],
        _SOURCE_SHA_LENGTH,
    )

    for name in (
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_paper_run_id",
        "candidate_quote_asset_mint",
        "cohort_quote_mint",
    ):
        value = document[name]
        if not isinstance(value, str) or not value.strip():
            raise G1CV2RuntimeManifestTransitionBindingError(
                f"{name} must be a non-empty string"
            )

    if document["source_paper_run_id"] == document["candidate_paper_run_id"]:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "source and candidate paper_run_id must differ"
        )
    if (
        document["source_quote_asset_mint"]
        == document["candidate_quote_asset_mint"]
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "source and candidate quote assets must differ"
        )
    if document["candidate_quote_asset_mint"] != document["cohort_quote_mint"]:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate quote asset must match frozen cohort quote mint"
        )

    start_at = document["candidate_start_at_unix_ms"]
    if isinstance(start_at, bool) or not isinstance(start_at, int) or start_at < 0:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate_start_at_unix_ms must be a non-negative integer"
        )
    decimals = document["candidate_quote_asset_decimals"]
    if (
        isinstance(decimals, bool)
        or not isinstance(decimals, int)
        or decimals < 0
        or decimals > 255
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate_quote_asset_decimals must be within [0, 255]"
        )

    expected_authority = {
        "installation_authority": _NOT_GRANTED,
        "activation_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _PAPER_PROMOTION_BLOCKED,
        "live_authority": _LIVE_DISABLED,
    }
    for name, expected in expected_authority.items():
        if document[name] != expected:
            raise G1CV2RuntimeManifestTransitionBindingError(
                f"{name} is not allowed by this binding"
            )

    claimed = document["binding_fingerprint_sha256"]
    material = dict(document)
    del material["binding_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding fingerprint mismatch"
        )
    return document


def _require_exact_authoring_derivation(
    *,
    source_path: Path,
    candidate,
) -> None:
    bundle = candidate.policy_bundle
    try:
        expected = author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=source_path,
            paper_run_id=candidate.paper_run_id,
            start_at_unix_ms=candidate.initial_state.last_cycle_at_unix_ms,
            quote_asset_mint=bundle.quote_asset.mint,
            quote_asset_decimals=bundle.quote_asset.decimals,
            entry_input_amount=bundle.entry_quote_identity.input_amount,
        )
    except (
        G1CV2RuntimeManifestCandidateAuthoringError,
        ObserverPaperCampaignRuntimeManifestError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"candidate cannot be reproduced by canonical authoring: {error}"
        ) from error
    if expected != candidate:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate is not the exact canonical new-run derivation of source"
        )


def _require_compatible_assessment(
    assessment: dict[str, object],
    *,
    candidate_path: Path,
    candidate,
) -> tuple[dict[str, object], dict[str, object]]:
    if assessment.get("schema_name") != (
        FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_NAME
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment schema_name is unsupported"
        )
    if assessment.get("schema_version") != (
        FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_VERSION
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment schema_version is unsupported"
        )
    if assessment.get("status") != "COMPATIBLE":
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment is not COMPATIBLE"
        )

    report = assessment.get("candidate")
    if not isinstance(report, dict):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment is missing candidate provenance"
        )
    if report.get("authentication") != "AUTHENTICATED":
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment did not authenticate the manifest"
        )
    if report.get("compatibility") != "COMPATIBLE":
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment compatibility is inconsistent"
        )
    if report.get("source_kind") != "candidate":
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment source kind is unsupported"
        )
    if report.get("source_path") != str(candidate_path):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment source path changed"
        )
    if report.get("runtime_manifest_fingerprint_sha256") != (
        candidate.manifest_fingerprint_sha256
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment manifest fingerprint mismatch"
        )
    if report.get("paper_run_id") != candidate.paper_run_id:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment paper_run_id mismatch"
        )
    if report.get("runtime_manifest_schema_version") != (
        OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment schema version mismatch"
        )
    if report.get("quote_usd_valuation_mode") != (
        ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO.value
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment valuation mode mismatch"
        )

    bundle = candidate.policy_bundle
    quote_mint = bundle.quote_asset.mint
    if assessment.get("cohort_quote_mint") != quote_mint:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate quote asset does not match frozen cohort"
        )
    for name, expected in (
        ("quote_asset_mint", quote_mint),
        ("quote_asset_decimals", bundle.quote_asset.decimals),
        ("regime_quote_asset_mint", quote_mint),
        ("safety_probe_output_mint", quote_mint),
        ("quote_provider", bundle.entry_quote_identity.provider),
    ):
        if report.get(name) != expected:
            raise G1CV2RuntimeManifestTransitionBindingError(
                f"candidate assessment {name} mismatch"
            )

    authority = assessment.get("non_manifest_input_authority")
    if not isinstance(authority, dict):
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment is missing request authority"
        )
    if authority.get("authority_kind") != "v2_host_request":
        raise G1CV2RuntimeManifestTransitionBindingError(
            "candidate assessment request authority kind is unsupported"
        )
    for name in (
        "request_fingerprint_sha256",
        "cohort_artifact_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
    ):
        _require_lower_hex(name, authority.get(name), _SHA256_LENGTH)
    _require_lower_hex(
        "request_release_source_sha",
        authority.get("request_release_source_sha"),
        _SOURCE_SHA_LENGTH,
    )
    hydration_fingerprint = report.get(
        "hydration_policy_fingerprint_sha256"
    )
    _require_lower_hex(
        "candidate hydration policy fingerprint",
        hydration_fingerprint,
        _SHA256_LENGTH,
    )
    return report, authority


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} must be an existing regular non-symlink file"
        )
    return path.resolve()


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
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
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} changed while being read"
        )
    return payload


def _write_binding_once(
    destination: str | Path,
    binding: dict[str, object],
) -> None:
    try:
        path = Path(destination).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "transition binding destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2RuntimeManifestTransitionBindingError(
            "transition binding destination parent must be a real directory"
        )

    payload = _canonical_json(binding).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if path.exists() or path.is_symlink():
            raise FileExistsError(
                "transition binding destination appeared during write"
            )
        temporary.rename(path)
        path.chmod(0o600)
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
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} must use canonical JSON with one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{label} must use canonical JSON"
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


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical_json(value: object) -> str:
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
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _require_lower_hex(name: str, value: object, length: int) -> None:
    if (
        not isinstance(value, str)
        or len(value) != length
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise G1CV2RuntimeManifestTransitionBindingError(
            f"{name} must be {length} lowercase hex characters"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-runtime-manifest-transition-bind",
        description=(
            "Bind one exact canonical G1C v2 new-run candidate to its v1 "
            "source and one COMPATIBLE FL9 V2 assessment without granting "
            "installation, activation, rotation, scoring, promotion, or LIVE "
            "authority."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--candidate-runtime-manifest", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--v2-host-request-authority", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        binding = bind_g1c_v2_runtime_manifest_transition(
            source_runtime_manifest_path=args.source_runtime_manifest,
            candidate_runtime_manifest_path=args.candidate_runtime_manifest,
            cohort_path=args.cohort,
            v2_host_request_authority_path=args.v2_host_request_authority,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2RuntimeManifestTransitionBindingError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            _canonical_json(
                {
                    "status": "FAILED",
                    "error": str(error),
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(_canonical_json(binding))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
