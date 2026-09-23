from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.fl9_v2_runtime_manifest_discovery import (
    RuntimeManifestDiscoveryError,
    assess_fl9_v2_runtime_manifest_candidate_from_v2_request_authority,
)
from shreks_brain.g1c_v2_entry_sizing_proposal import (
    G1CV2EntrySizingProposalError,
    decode_g1c_v2_entry_sizing_proposal,
)
from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    G1CV2RuntimeManifestCandidateAuthoringError,
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)


_SCHEMA_NAME = "shreks.g1c_v2_candidate_value_preflight"
_SCHEMA_VERSION = 1
_STATUS = "READY_FOR_EXPLICIT_CANDIDATE_VALUE_DECISION"
_PREFLIGHT_AUTHORITY = "EVIDENCE_ONLY"
_COMPATIBLE = "COMPATIBLE"
_REVIEW_AUTHORITY = "MULTI_REFERENCE_REVIEW"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class G1CV2CandidateValuePreflightError(ValueError):
    """Raised when an evidence-only candidate-value preflight cannot be trusted."""


def preflight_g1c_v2_candidate_value(
    *,
    source_runtime_manifest_path: str | Path,
    sizing_proposal_path: str | Path,
    cohort_path: str | Path,
    v2_host_request_authority_path: str | Path,
    paper_run_id: str,
    start_at_unix_ms: int,
    destination: str | Path,
) -> dict[str, object]:
    source_path = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    proposal_path = _resolve_existing_regular_file(
        sizing_proposal_path,
        label="review-backed sizing proposal",
    )
    cohort = _resolve_existing_directory(cohort_path, label="frozen V2 cohort")
    request_path = _resolve_existing_regular_file(
        v2_host_request_authority_path,
        label="V2 host request authority",
    )
    destination_path = _resolve_new_destination(destination)

    _require_non_empty_text("paper_run_id", paper_run_id)
    _require_non_negative_int("start_at_unix_ms", start_at_unix_ms)

    source_payload = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    proposal_payload = _read_regular_file_stable(
        proposal_path,
        label="review-backed sizing proposal",
    )

    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2CandidateValuePreflightError(
            f"source runtime manifest authentication failed: {error}"
        ) from error

    try:
        proposal = decode_g1c_v2_entry_sizing_proposal(
            proposal_payload.decode("utf-8")
        )
    except (
        G1CV2EntrySizingProposalError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2CandidateValuePreflightError(
            f"sizing proposal authentication failed: {error}"
        ) from error

    _require_review_backed_proposal(proposal)
    source_sha256 = hashlib.sha256(source_payload).hexdigest()
    if proposal["source_manifest_sha256"] != source_sha256:
        raise G1CV2CandidateValuePreflightError(
            "sizing proposal source manifest SHA does not match supplied source"
        )
    if (
        proposal["source_runtime_manifest_fingerprint_sha256"]
        != source.manifest_fingerprint_sha256
    ):
        raise G1CV2CandidateValuePreflightError(
            "sizing proposal source fingerprint does not match supplied source"
        )
    if proposal["source_paper_run_id"] != source.paper_run_id:
        raise G1CV2CandidateValuePreflightError(
            "sizing proposal source paper_run_id does not match supplied source"
        )

    try:
        candidate = author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=source_path,
            paper_run_id=paper_run_id,
            start_at_unix_ms=start_at_unix_ms,
            quote_asset_mint=str(proposal["target_quote_mint"]),
            quote_asset_decimals=int(proposal["target_quote_decimals"]),
            entry_input_amount=int(proposal["proposed_entry_input_amount"]),
        )
        candidate_payload = encode_observer_paper_campaign_runtime_manifest(candidate)
    except (
        G1CV2RuntimeManifestCandidateAuthoringError,
        ObserverPaperCampaignRuntimeManifestError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2CandidateValuePreflightError(
            f"hypothetical candidate derivation failed: {error}"
        ) from error

    try:
        with tempfile.TemporaryDirectory(
            prefix="shreks-g1c-v2-candidate-preflight-"
        ) as temporary_directory:
            candidate_path = Path(temporary_directory) / "candidate.json"
            candidate_path.write_bytes(candidate_payload)
            candidate_path.chmod(0o600)
            assessment = assess_fl9_v2_runtime_manifest_candidate_from_v2_request_authority(
                cohort_path=cohort,
                runtime_manifest_path=candidate_path,
                v2_host_request_authority_path=request_path,
            )
    except (
        RuntimeManifestDiscoveryError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2CandidateValuePreflightError(
            f"canonical candidate compatibility assessment failed: {error}"
        ) from error

    candidate_document = assessment.get("candidate")
    authority_document = assessment.get("non_manifest_input_authority")
    if not isinstance(candidate_document, dict):
        raise G1CV2CandidateValuePreflightError(
            "canonical candidate assessment is missing candidate evidence"
        )
    if not isinstance(authority_document, dict):
        raise G1CV2CandidateValuePreflightError(
            "canonical candidate assessment is missing request authority"
        )
    if (
        assessment.get("status") != _COMPATIBLE
        or candidate_document.get("compatibility") != _COMPATIBLE
    ):
        raise G1CV2CandidateValuePreflightError(
            "hypothetical candidate is not COMPATIBLE with frozen V2 authority"
        )

    cohort_quote_mint = assessment.get("cohort_quote_mint")
    if cohort_quote_mint != proposal["target_quote_mint"]:
        raise G1CV2CandidateValuePreflightError(
            "canonical cohort quote mint does not match sizing proposal"
        )
    if candidate_document.get("runtime_manifest_fingerprint_sha256") != (
        candidate.manifest_fingerprint_sha256
    ):
        raise G1CV2CandidateValuePreflightError(
            "canonical assessment changed hypothetical candidate fingerprint"
        )

    source_after = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    proposal_after = _read_regular_file_stable(
        proposal_path,
        label="review-backed sizing proposal",
    )
    if source_after != source_payload:
        raise G1CV2CandidateValuePreflightError(
            "source runtime manifest changed during preflight"
        )
    if proposal_after != proposal_payload:
        raise G1CV2CandidateValuePreflightError(
            "sizing proposal changed during preflight"
        )

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "preflight_authority": _PREFLIGHT_AUTHORITY,
        "source_manifest_sha256": source_sha256,
        "source_runtime_manifest_fingerprint_sha256": (
            source.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": source.paper_run_id,
        "source_proposal_sha256": hashlib.sha256(proposal_payload).hexdigest(),
        "proposal_fingerprint_sha256": proposal["proposal_fingerprint_sha256"],
        "quote_evidence_authority": proposal["quote_evidence_authority"],
        "quote_evidence_fingerprint_sha256": (
            proposal["quote_evidence_fingerprint_sha256"]
        ),
        "quote_evidence_observed_at_unix_ms": (
            proposal["quote_evidence_observed_at_unix_ms"]
        ),
        "candidate_paper_run_id": paper_run_id,
        "candidate_start_at_unix_ms": start_at_unix_ms,
        "target_quote_mint": proposal["target_quote_mint"],
        "target_quote_decimals": proposal["target_quote_decimals"],
        "proposed_entry_input_amount": proposal["proposed_entry_input_amount"],
        "candidate_manifest_sha256": hashlib.sha256(candidate_payload).hexdigest(),
        "candidate_runtime_manifest_fingerprint_sha256": (
            candidate.manifest_fingerprint_sha256
        ),
        "candidate_compatibility": _COMPATIBLE,
        "cohort_quote_mint": cohort_quote_mint,
        "cohort_artifact_fingerprint_sha256": authority_document[
            "cohort_artifact_fingerprint_sha256"
        ],
        "request_fingerprint_sha256": authority_document[
            "request_fingerprint_sha256"
        ],
        "request_release_source_sha": authority_document[
            "request_release_source_sha"
        ],
        "request_hydration_policy_fingerprint_sha256": authority_document[
            "hydration_policy_fingerprint_sha256"
        ],
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    receipt = {
        **material,
        "preflight_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_once(destination_path, receipt)
    verified = decode_g1c_v2_candidate_value_preflight(
        destination_path.read_text(encoding="utf-8")
    )
    if verified != receipt:
        raise G1CV2CandidateValuePreflightError(
            "written candidate-value preflight did not round-trip"
        )
    return receipt


def decode_g1c_v2_candidate_value_preflight(payload: str) -> dict[str, object]:
    document = _decode_canonical_text(payload)
    expected_keys = {
        "schema_name",
        "schema_version",
        "status",
        "preflight_authority",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "source_proposal_sha256",
        "proposal_fingerprint_sha256",
        "quote_evidence_authority",
        "quote_evidence_fingerprint_sha256",
        "quote_evidence_observed_at_unix_ms",
        "candidate_paper_run_id",
        "candidate_start_at_unix_ms",
        "target_quote_mint",
        "target_quote_decimals",
        "proposed_entry_input_amount",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "candidate_compatibility",
        "cohort_quote_mint",
        "cohort_artifact_fingerprint_sha256",
        "request_fingerprint_sha256",
        "request_release_source_sha",
        "request_hydration_policy_fingerprint_sha256",
        "candidate_value_authority",
        "candidate_authoring_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "preflight_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight has unknown or missing fields"
        )

    static = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "preflight_authority": _PREFLIGHT_AUTHORITY,
        "quote_evidence_authority": _REVIEW_AUTHORITY,
        "candidate_compatibility": _COMPATIBLE,
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in static.items():
        if document.get(name) != expected:
            raise G1CV2CandidateValuePreflightError(
                f"candidate-value preflight {name} is unsupported"
            )

    for name in (
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_proposal_sha256",
        "proposal_fingerprint_sha256",
        "quote_evidence_fingerprint_sha256",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "cohort_artifact_fingerprint_sha256",
        "request_fingerprint_sha256",
        "request_hydration_policy_fingerprint_sha256",
        "preflight_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))

    _require_source_sha(
        "request_release_source_sha",
        document.get("request_release_source_sha"),
    )
    for name in (
        "source_paper_run_id",
        "candidate_paper_run_id",
        "target_quote_mint",
        "cohort_quote_mint",
    ):
        _require_non_empty_text(name, document.get(name))
    if document["target_quote_mint"] != document["cohort_quote_mint"]:
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight target/cohort quote mint mismatch"
        )
    _require_non_negative_int(
        "quote_evidence_observed_at_unix_ms",
        document.get("quote_evidence_observed_at_unix_ms"),
    )
    _require_non_negative_int(
        "candidate_start_at_unix_ms",
        document.get("candidate_start_at_unix_ms"),
    )
    _require_decimals(
        "target_quote_decimals",
        document.get("target_quote_decimals"),
    )
    _require_positive_u64(
        "proposed_entry_input_amount",
        document.get("proposed_entry_input_amount"),
    )

    claimed = document["preflight_fingerprint_sha256"]
    material = dict(document)
    del material["preflight_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight fingerprint mismatch"
        )
    return document


def _require_review_backed_proposal(proposal: dict[str, object]) -> None:
    required = {
        "status": "PROPOSAL_EVIDENCE_ONLY",
        "quote_evidence_authority": _REVIEW_AUTHORITY,
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in required.items():
        if proposal.get(name) != expected:
            raise G1CV2CandidateValuePreflightError(
                f"sizing proposal {name} must remain {expected}"
            )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2CandidateValuePreflightError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2CandidateValuePreflightError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2CandidateValuePreflightError(
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
        raise G1CV2CandidateValuePreflightError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_dir():
        raise G1CV2CandidateValuePreflightError(
            f"{label} must be an existing real directory"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2CandidateValuePreflightError(
            f"{label} could not be resolved"
        ) from error


def _resolve_new_destination(raw_path: str | Path) -> Path:
    try:
        path = Path(raw_path).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "candidate-value preflight destination already exists"
        )
    return path


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2CandidateValuePreflightError(
            f"{label} could not be read"
        ) from error
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or len(payload) != before.st_size:
        raise G1CV2CandidateValuePreflightError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight parent must be a real directory"
        )
    payload = _canonical_json(value).encode("utf-8")
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
                "candidate-value preflight destination appeared during write"
            )
        temporary.rename(path)
        path.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _decode_canonical_text(payload: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight must have one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2CandidateValuePreflightError(
            "candidate-value preflight must use canonical JSON"
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
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise G1CV2CandidateValuePreflightError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_source_sha(name: str, value: object) -> None:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise G1CV2CandidateValuePreflightError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2CandidateValuePreflightError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2CandidateValuePreflightError(
            f"{name} must be a non-negative integer"
        )


def _require_decimals(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 255
    ):
        raise G1CV2CandidateValuePreflightError(
            f"{name} must be an integer within [0, 255]"
        )


def _require_positive_u64(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > 2**64 - 1
    ):
        raise G1CV2CandidateValuePreflightError(
            f"{name} must be a positive u64 amount"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-candidate-value-preflight",
        description=(
            "Prove that one authenticated review-backed sizing proposal would "
            "derive an exact FL9 V2-compatible candidate before any explicit "
            "candidate-value decision or candidate authority is granted."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--sizing-proposal", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--v2-host-request-authority", required=True)
    parser.add_argument("--paper-run-id", required=True)
    parser.add_argument("--start-at-unix-ms", required=True, type=int)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        receipt = preflight_g1c_v2_candidate_value(
            source_runtime_manifest_path=args.source_runtime_manifest,
            sizing_proposal_path=args.sizing_proposal,
            cohort_path=args.cohort,
            v2_host_request_authority_path=args.v2_host_request_authority,
            paper_run_id=args.paper_run_id,
            start_at_unix_ms=args.start_at_unix_ms,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2CandidateValuePreflightError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            _canonical_json({"status": "FAILED", "error": str(error)}),
            end="",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(_canonical_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
