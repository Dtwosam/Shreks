from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.g1c_v2_candidate_value_decision import (
    G1CV2CandidateValueDecisionError,
    decode_g1c_v2_candidate_value_decision,
)
from shreks_brain.g1c_v2_runtime_manifest_candidate_authority import (
    G1CV2RuntimeManifestCandidateAuthorityError,
    bind_g1c_v2_runtime_manifest_candidate_authority,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


_SCHEMA_NAME = "shreks.g1c_v2_decision_backed_candidate_authority"
_SCHEMA_VERSION = 1
_AUTHORITY_KIND = "approved_candidate_value_decision"
_AUTHORITY_STATUS = "BOUND_EXACT_CANONICAL_CANDIDATE"
_APPROVED_STATUS = "CANDIDATE_VALUE_APPROVED"
_ALLOWED_DECISIONS = {"ACCEPT_PROPOSAL", "REPLACE_PROPOSAL"}
_REQUIRED_VALUE_AUTHORITY = "EXPLICIT_PRODUCTION_DECISION_BOUND"
_REQUIRED_EVIDENCE_AUTHORITY = "MULTI_REFERENCE_REVIEW"
_AUTHORING_AUTHORITY = "DECISION_BACKED_INPUTS_BOUND"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_U64 = 2**64 - 1


class G1CV2DecisionBackedCandidateAuthorityError(RuntimeError):
    """Raised when an approved candidate-value decision cannot be bound safely."""


def bind_g1c_v2_decision_backed_candidate_authority(
    *,
    source_runtime_manifest_path: str | Path,
    cohort_path: str | Path,
    v2_host_request_authority_path: str | Path,
    candidate_value_decision_path: str | Path,
    paper_run_id: str,
    start_at_unix_ms: int,
    destination: str | Path,
) -> dict[str, object]:
    source_path = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    decision_path = _resolve_existing_regular_file(
        candidate_value_decision_path,
        label="candidate value decision",
    )
    source_payload = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    decision_payload = _read_regular_file_stable(
        decision_path,
        label="candidate value decision",
    )

    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"source runtime manifest authentication failed: {error}"
        ) from error
    try:
        decision = decode_g1c_v2_candidate_value_decision(
            decision_payload.decode("utf-8")
        )
    except (
        G1CV2CandidateValueDecisionError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"candidate value decision authentication failed: {error}"
        ) from error

    _require_approved_decision(decision)
    source_sha256 = hashlib.sha256(source_payload).hexdigest()
    if source_sha256 != decision["source_manifest_sha256"]:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision source manifest SHA does not match supplied source"
        )
    if (
        source.manifest_fingerprint_sha256
        != decision["source_runtime_manifest_fingerprint_sha256"]
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision source manifest fingerprint does not match supplied source"
        )
    if source.paper_run_id != decision["source_paper_run_id"]:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision source paper_run_id does not match supplied source"
        )

    selected_amount = decision["selected_entry_input_amount"]
    _require_positive_u64("selected_entry_input_amount", selected_amount)

    with tempfile.TemporaryDirectory(
        prefix="shreks-g1c-v2-decision-backed-authority-"
    ) as temporary_directory:
        derived_path = Path(temporary_directory) / "candidate-authority.json"
        try:
            derived = bind_g1c_v2_runtime_manifest_candidate_authority(
                source_runtime_manifest_path=source_path,
                cohort_path=cohort_path,
                v2_host_request_authority_path=v2_host_request_authority_path,
                paper_run_id=paper_run_id,
                start_at_unix_ms=start_at_unix_ms,
                quote_asset_mint=decision["target_quote_mint"],
                quote_asset_decimals=decision["target_quote_decimals"],
                entry_input_amount=selected_amount,
                destination=derived_path,
            )
        except (
            G1CV2RuntimeManifestCandidateAuthorityError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise G1CV2DecisionBackedCandidateAuthorityError(
                f"decision-backed candidate authority derivation failed: {error}"
            ) from error

    source_after = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    decision_after = _read_regular_file_stable(
        decision_path,
        label="candidate value decision",
    )
    if source_after != source_payload:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "source runtime manifest changed while decision-backed authority was derived"
        )
    if decision_after != decision_payload:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision changed while authority was derived"
        )

    if derived["candidate_quote_asset_mint"] != decision["target_quote_mint"]:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "derived candidate quote mint does not match approved decision"
        )
    if (
        derived["candidate_quote_asset_decimals"]
        != decision["target_quote_decimals"]
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "derived candidate quote decimals do not match approved decision"
        )
    if derived["candidate_entry_input_amount"] != selected_amount:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "derived candidate entry amount does not match approved decision"
        )

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "authority_kind": _AUTHORITY_KIND,
        "authority_status": _AUTHORITY_STATUS,
        "candidate_value_decision_sha256": hashlib.sha256(
            decision_payload
        ).hexdigest(),
        "candidate_value_decision_fingerprint_sha256": decision[
            "decision_fingerprint_sha256"
        ],
        "candidate_value_decision_status": decision["status"],
        "candidate_value_decision_kind": decision["decision"],
        "candidate_value_decision_reason": decision["decision_reason"],
        "candidate_value_authority": decision["candidate_value_authority"],
        "quote_evidence_fingerprint_sha256": decision[
            "quote_evidence_fingerprint_sha256"
        ],
        "quote_evidence_observed_at_unix_ms": decision[
            "quote_evidence_observed_at_unix_ms"
        ],
        "quote_evidence_authority": decision["quote_evidence_authority"],
        "decision_target_quote_mint": decision["target_quote_mint"],
        "decision_target_quote_decimals": decision["target_quote_decimals"],
        "decision_selected_entry_input_amount": selected_amount,
        "source_manifest_sha256": derived["source_manifest_sha256"],
        "source_runtime_manifest_fingerprint_sha256": derived[
            "source_runtime_manifest_fingerprint_sha256"
        ],
        "source_paper_run_id": derived["source_paper_run_id"],
        "source_quote_asset_mint": derived["source_quote_asset_mint"],
        "candidate_manifest_sha256": derived["candidate_manifest_sha256"],
        "candidate_runtime_manifest_fingerprint_sha256": derived[
            "candidate_runtime_manifest_fingerprint_sha256"
        ],
        "candidate_paper_run_id": derived["candidate_paper_run_id"],
        "candidate_start_at_unix_ms": derived["candidate_start_at_unix_ms"],
        "candidate_quote_asset_mint": derived["candidate_quote_asset_mint"],
        "candidate_quote_asset_decimals": derived[
            "candidate_quote_asset_decimals"
        ],
        "candidate_entry_input_amount": derived["candidate_entry_input_amount"],
        "candidate_quote_usd_valuation_mode": derived[
            "candidate_quote_usd_valuation_mode"
        ],
        "cohort_artifact_fingerprint_sha256": derived[
            "cohort_artifact_fingerprint_sha256"
        ],
        "cohort_quote_mint": derived["cohort_quote_mint"],
        "request_fingerprint_sha256": derived["request_fingerprint_sha256"],
        "request_release_source_sha": derived["request_release_source_sha"],
        "request_hydration_policy_fingerprint_sha256": derived[
            "request_hydration_policy_fingerprint_sha256"
        ],
        "derived_candidate_authority_fingerprint_sha256": derived[
            "authority_fingerprint_sha256"
        ],
        "candidate_authoring_authority": _AUTHORING_AUTHORITY,
        "installation_authority": _NOT_GRANTED,
        "activation_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    authority = {
        **material,
        "authority_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_once(destination, authority)
    written = Path(destination).expanduser().resolve()
    verified = decode_g1c_v2_decision_backed_candidate_authority(
        written.read_text(encoding="utf-8")
    )
    if verified != authority:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "written decision-backed candidate authority did not round-trip"
        )
    return authority


def decode_g1c_v2_decision_backed_candidate_authority(
    payload: str,
) -> dict[str, object]:
    document = _decode_canonical_text(payload)
    expected_keys = {
        "schema_name",
        "schema_version",
        "authority_kind",
        "authority_status",
        "candidate_value_decision_sha256",
        "candidate_value_decision_fingerprint_sha256",
        "candidate_value_decision_status",
        "candidate_value_decision_kind",
        "candidate_value_decision_reason",
        "candidate_value_authority",
        "quote_evidence_fingerprint_sha256",
        "quote_evidence_observed_at_unix_ms",
        "quote_evidence_authority",
        "decision_target_quote_mint",
        "decision_target_quote_decimals",
        "decision_selected_entry_input_amount",
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
        "candidate_entry_input_amount",
        "candidate_quote_usd_valuation_mode",
        "cohort_artifact_fingerprint_sha256",
        "cohort_quote_mint",
        "request_fingerprint_sha256",
        "request_release_source_sha",
        "request_hydration_policy_fingerprint_sha256",
        "derived_candidate_authority_fingerprint_sha256",
        "candidate_authoring_authority",
        "installation_authority",
        "activation_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "authority_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority has unknown or missing fields"
        )

    static = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "authority_kind": _AUTHORITY_KIND,
        "authority_status": _AUTHORITY_STATUS,
        "candidate_value_decision_status": _APPROVED_STATUS,
        "candidate_value_authority": _REQUIRED_VALUE_AUTHORITY,
        "quote_evidence_authority": _REQUIRED_EVIDENCE_AUTHORITY,
        "candidate_authoring_authority": _AUTHORING_AUTHORITY,
        "installation_authority": _NOT_GRANTED,
        "activation_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in static.items():
        if document.get(name) != expected:
            raise G1CV2DecisionBackedCandidateAuthorityError(
                f"decision-backed candidate authority {name} is unsupported"
            )
    if document.get("candidate_value_decision_kind") not in _ALLOWED_DECISIONS:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed authority requires accepted or replaced decision"
        )
    _require_non_empty_text(
        "candidate_value_decision_reason",
        document.get("candidate_value_decision_reason"),
    )

    for name in (
        "candidate_value_decision_sha256",
        "candidate_value_decision_fingerprint_sha256",
        "quote_evidence_fingerprint_sha256",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "cohort_artifact_fingerprint_sha256",
        "request_fingerprint_sha256",
        "request_hydration_policy_fingerprint_sha256",
        "derived_candidate_authority_fingerprint_sha256",
        "authority_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))
    _require_source_sha(
        "request_release_source_sha",
        document.get("request_release_source_sha"),
    )

    for name in (
        "decision_target_quote_mint",
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_paper_run_id",
        "candidate_quote_asset_mint",
        "cohort_quote_mint",
    ):
        _require_non_empty_text(name, document.get(name))
    _require_decimals(
        "decision_target_quote_decimals",
        document.get("decision_target_quote_decimals"),
    )
    _require_decimals(
        "candidate_quote_asset_decimals",
        document.get("candidate_quote_asset_decimals"),
    )
    _require_positive_u64(
        "decision_selected_entry_input_amount",
        document.get("decision_selected_entry_input_amount"),
    )
    _require_positive_u64(
        "candidate_entry_input_amount",
        document.get("candidate_entry_input_amount"),
    )
    _require_non_negative_int(
        "quote_evidence_observed_at_unix_ms",
        document.get("quote_evidence_observed_at_unix_ms"),
    )
    _require_non_negative_int(
        "candidate_start_at_unix_ms",
        document.get("candidate_start_at_unix_ms"),
    )

    if (
        document["decision_target_quote_mint"]
        != document["candidate_quote_asset_mint"]
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision quote mint does not match candidate"
        )
    if (
        document["decision_target_quote_decimals"]
        != document["candidate_quote_asset_decimals"]
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision quote decimals do not match candidate"
        )
    if (
        document["decision_selected_entry_input_amount"]
        != document["candidate_entry_input_amount"]
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision entry amount does not match candidate"
        )
    if document["candidate_quote_asset_mint"] != document["cohort_quote_mint"]:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate quote mint must equal frozen cohort quote mint"
        )
    if document["source_paper_run_id"] == document["candidate_paper_run_id"]:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate paper_run_id must differ from source"
        )

    claimed = document["authority_fingerprint_sha256"]
    material = dict(document)
    del material["authority_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority fingerprint mismatch"
        )
    return document


def _require_approved_decision(decision: dict[str, object]) -> None:
    if decision.get("status") != _APPROVED_STATUS:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision must be approved"
        )
    if decision.get("decision") not in _ALLOWED_DECISIONS:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision must accept or replace the proposal"
        )
    if decision.get("candidate_value_authority") != _REQUIRED_VALUE_AUTHORITY:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision lacks explicit production value authority"
        )
    if decision.get("quote_evidence_authority") != _REQUIRED_EVIDENCE_AUTHORITY:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "candidate value decision lacks MULTI_REFERENCE_REVIEW provenance"
        )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
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
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(destination: str | Path, value: dict[str, object]) -> None:
    try:
        path = Path(destination).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "decision-backed candidate authority destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority parent must be a real directory"
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
                "decision-backed candidate authority destination appeared during write"
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
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority must have one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            "decision-backed candidate authority must use canonical JSON"
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


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_source_sha(name: str, value: object) -> None:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{name} must be a non-negative integer"
        )


def _require_decimals(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 255
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{name} must be an integer within [0, 255]"
        )


def _require_positive_u64(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > _MAX_U64
    ):
        raise G1CV2DecisionBackedCandidateAuthorityError(
            f"{name} must be a positive u64 amount"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-decision-backed-candidate-authority-bind",
        description=(
            "Bind an approved candidate-value decision plus explicit new-run "
            "identity/time to exact authenticated G1C v2 candidate authority."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--v2-host-request-authority", required=True)
    parser.add_argument("--candidate-value-decision", required=True)
    parser.add_argument("--paper-run-id", required=True)
    parser.add_argument("--start-at-unix-ms", required=True, type=int)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        authority = bind_g1c_v2_decision_backed_candidate_authority(
            source_runtime_manifest_path=args.source_runtime_manifest,
            cohort_path=args.cohort,
            v2_host_request_authority_path=args.v2_host_request_authority,
            candidate_value_decision_path=args.candidate_value_decision,
            paper_run_id=args.paper_run_id,
            start_at_unix_ms=args.start_at_unix_ms,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2DecisionBackedCandidateAuthorityError,
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
    sys.stdout.write(_canonical_json(authority))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
