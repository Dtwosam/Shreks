from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.fast_first_champion_v2.host_request import (
    decode_fast_first_champion_v2_host_request,
)
from shreks_brain.fl9_v2_discovery_backed_request_preparation import (
    DiscoveryBackedRequestPreparationError,
    decode_discovery_backed_request_preparation,
)


FL9_V2_SCORING_AUTHORITY_SCHEMA_NAME = "shreks.fl9_v2_scoring_authority"
FL9_V2_SCORING_AUTHORITY_SCHEMA_VERSION = 1

_AUTHORIZE = "AUTHORIZE_ONE_SCORING_RUN"
_REJECT = "REJECT_SCORING_RUN"
_VALID_DECISIONS = {_AUTHORIZE, _REJECT}
_AUTHORIZED_STATUS = "SCORING_AUTHORIZED"
_REJECTED_STATUS = "SCORING_REJECTED"
_SINGLE_RUN_AUTHORITY = "EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN"
_SCORING_EVIDENCE_ONLY = "SCORING_EVIDENCE_ONLY"
_EXECUTION_SCOPE = "ONE_REQUEST_ONE_DESTINATION"
_PREPARATION_AUTHORITY = "DISCOVERY_BOUND_REQUEST_ONLY"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FL9V2ScoringAuthorityError(ValueError):
    """Raised when a V2 scoring authority decision cannot be bound safely."""


def decide_fl9_v2_scoring_authority(
    *,
    request_preparation_path: str | Path,
    decision: str,
    decision_reason: str,
    destination: str | Path,
) -> dict[str, object]:
    preparation_path = _resolve_existing_regular_file(
        request_preparation_path,
        label="request preparation receipt",
    )
    preparation_payload = _read_regular_file_stable(
        preparation_path,
        label="request preparation receipt",
    )
    try:
        preparation = decode_discovery_backed_request_preparation(
            preparation_payload.decode("utf-8")
        )
    except (
        DiscoveryBackedRequestPreparationError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise FL9V2ScoringAuthorityError(
            f"preparation receipt authentication failed: {error}"
        ) from error

    if decision not in _VALID_DECISIONS:
        raise FL9V2ScoringAuthorityError(
            "scoring authority decision is unsupported"
        )
    _require_non_empty_text("decision_reason", decision_reason)

    request_path = _request_path_from_preparation(preparation)
    request_payload = _read_regular_file_stable(
        request_path,
        label="prepared V2 request",
    )
    request_sha256 = hashlib.sha256(request_payload).hexdigest()
    if request_sha256 != preparation.get("request_sha256"):
        raise FL9V2ScoringAuthorityError(
            "prepared V2 request SHA-256 does not match preparation receipt"
        )

    try:
        request = decode_fast_first_champion_v2_host_request(
            request_payload.decode("utf-8")
        )
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise FL9V2ScoringAuthorityError(
            f"prepared V2 request authentication failed: {error}"
        ) from error

    _require_request_matches_preparation(
        request=request,
        preparation=preparation,
    )

    if _read_regular_file_stable(
        preparation_path,
        label="request preparation receipt",
    ) != preparation_payload:
        raise FL9V2ScoringAuthorityError(
            "request preparation receipt changed while decision was derived"
        )
    if _read_regular_file_stable(
        request_path,
        label="prepared V2 request",
    ) != request_payload:
        raise FL9V2ScoringAuthorityError(
            "prepared V2 request changed while decision was derived"
        )

    if decision == _AUTHORIZE:
        status = _AUTHORIZED_STATUS
        scoring_authority = _SINGLE_RUN_AUTHORITY
        model_fitting_authority = _SINGLE_RUN_AUTHORITY
        champion_publication_authority = _SCORING_EVIDENCE_ONLY
    else:
        status = _REJECTED_STATUS
        scoring_authority = _NOT_GRANTED
        model_fitting_authority = _NOT_GRANTED
        champion_publication_authority = _NOT_GRANTED

    material: dict[str, object] = {
        "schema_name": FL9_V2_SCORING_AUTHORITY_SCHEMA_NAME,
        "schema_version": FL9_V2_SCORING_AUTHORITY_SCHEMA_VERSION,
        "status": status,
        "decision": decision,
        "decision_reason": decision_reason,
        "source_preparation_sha256": hashlib.sha256(
            preparation_payload
        ).hexdigest(),
        "preparation_fingerprint_sha256": preparation[
            "preparation_fingerprint_sha256"
        ],
        "discovery_binding_fingerprint_sha256": preparation[
            "discovery_binding_fingerprint_sha256"
        ],
        "discovery_result_sha256": preparation["discovery_result_sha256"],
        "release_source_sha": preparation["release_source_sha"],
        "cohort_artifact_fingerprint_sha256": preparation[
            "cohort_artifact_fingerprint_sha256"
        ],
        "hydration_policy_fingerprint_sha256": preparation[
            "hydration_policy_fingerprint_sha256"
        ],
        "runtime_manifest_fingerprint_sha256": preparation[
            "runtime_manifest_fingerprint_sha256"
        ],
        "quote_asset_mint": preparation["quote_asset_mint"],
        "quote_asset_decimals": preparation["quote_asset_decimals"],
        "quote_provider": preparation["quote_provider"],
        "request_sha256": request_sha256,
        "request_fingerprint_sha256": preparation[
            "request_fingerprint_sha256"
        ],
        "request_path": str(request_path),
        "evidence_destination": preparation["evidence_destination"],
        "request_preparation_authority": _PREPARATION_AUTHORITY,
        "execution_scope": _EXECUTION_SCOPE,
        "scoring_authority": scoring_authority,
        "model_fitting_authority": model_fitting_authority,
        "champion_publication_authority": (
            champion_publication_authority
        ),
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    result = {
        **material,
        "authority_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_once(destination, result)
    written = Path(destination).expanduser().resolve()
    verified = decode_fl9_v2_scoring_authority(
        written.read_text(encoding="utf-8")
    )
    if verified != result:
        raise FL9V2ScoringAuthorityError(
            "written scoring authority did not round-trip"
        )
    return result


def decode_fl9_v2_scoring_authority(
    payload: str,
) -> dict[str, object]:
    document = _decode_canonical_text(
        payload,
        label="FL9 V2 scoring authority",
    )
    expected_keys = {
        "schema_name",
        "schema_version",
        "status",
        "decision",
        "decision_reason",
        "source_preparation_sha256",
        "preparation_fingerprint_sha256",
        "discovery_binding_fingerprint_sha256",
        "discovery_result_sha256",
        "release_source_sha",
        "cohort_artifact_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
        "runtime_manifest_fingerprint_sha256",
        "quote_asset_mint",
        "quote_asset_decimals",
        "quote_provider",
        "request_sha256",
        "request_fingerprint_sha256",
        "request_path",
        "evidence_destination",
        "request_preparation_authority",
        "execution_scope",
        "scoring_authority",
        "model_fitting_authority",
        "champion_publication_authority",
        "paper_promotion_authority",
        "live_authority",
        "authority_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise FL9V2ScoringAuthorityError(
            "scoring authority has unknown or missing fields"
        )
    if (
        document.get("schema_name")
        != FL9_V2_SCORING_AUTHORITY_SCHEMA_NAME
        or document.get("schema_version")
        != FL9_V2_SCORING_AUTHORITY_SCHEMA_VERSION
    ):
        raise FL9V2ScoringAuthorityError(
            "scoring authority schema is unsupported"
        )

    for name in (
        "source_preparation_sha256",
        "preparation_fingerprint_sha256",
        "discovery_binding_fingerprint_sha256",
        "discovery_result_sha256",
        "cohort_artifact_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
        "runtime_manifest_fingerprint_sha256",
        "request_sha256",
        "request_fingerprint_sha256",
        "authority_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))
    _require_source_sha(
        "release_source_sha",
        document.get("release_source_sha"),
    )
    for name in (
        "decision_reason",
        "quote_asset_mint",
        "quote_provider",
        "request_path",
        "evidence_destination",
    ):
        _require_non_empty_text(name, document.get(name))
    _require_non_negative_int(
        "quote_asset_decimals",
        document.get("quote_asset_decimals"),
    )
    if not Path(str(document["request_path"])).is_absolute():
        raise FL9V2ScoringAuthorityError(
            "request_path must be absolute"
        )
    if not Path(str(document["evidence_destination"])).is_absolute():
        raise FL9V2ScoringAuthorityError(
            "evidence_destination must be absolute"
        )
    if document.get("request_preparation_authority") != _PREPARATION_AUTHORITY:
        raise FL9V2ScoringAuthorityError(
            "scoring authority preparation provenance is unsupported"
        )
    if document.get("execution_scope") != _EXECUTION_SCOPE:
        raise FL9V2ScoringAuthorityError(
            "scoring authority execution scope is unsupported"
        )
    if document.get("paper_promotion_authority") != _BLOCKED:
        raise FL9V2ScoringAuthorityError(
            "scoring authority cannot grant PAPER promotion"
        )
    if document.get("live_authority") != _DISABLED:
        raise FL9V2ScoringAuthorityError(
            "scoring authority cannot enable LIVE"
        )

    decision = document.get("decision")
    status = document.get("status")
    scoring_authority = document.get("scoring_authority")
    model_fitting_authority = document.get("model_fitting_authority")
    champion_publication_authority = document.get(
        "champion_publication_authority"
    )

    if decision == _AUTHORIZE:
        if status != _AUTHORIZED_STATUS:
            raise FL9V2ScoringAuthorityError(
                "authorized scoring decision status is inconsistent"
            )
        if scoring_authority != _SINGLE_RUN_AUTHORITY:
            raise FL9V2ScoringAuthorityError(
                "authorized scoring authority is inconsistent"
            )
        if model_fitting_authority != _SINGLE_RUN_AUTHORITY:
            raise FL9V2ScoringAuthorityError(
                "authorized model-fitting authority is inconsistent"
            )
        if champion_publication_authority != _SCORING_EVIDENCE_ONLY:
            raise FL9V2ScoringAuthorityError(
                "authorized champion publication authority is inconsistent"
            )
    elif decision == _REJECT:
        if status != _REJECTED_STATUS:
            raise FL9V2ScoringAuthorityError(
                "rejected scoring decision status is inconsistent"
            )
        if (
            scoring_authority != _NOT_GRANTED
            or model_fitting_authority != _NOT_GRANTED
            or champion_publication_authority != _NOT_GRANTED
        ):
            raise FL9V2ScoringAuthorityError(
                "rejected scoring decision must grant no downstream authority"
            )
    else:
        raise FL9V2ScoringAuthorityError(
            "scoring authority decision is unsupported"
        )

    claimed = document["authority_fingerprint_sha256"]
    material = dict(document)
    del material["authority_fingerprint_sha256"]
    if claimed != _sha256_canonical(material):
        raise FL9V2ScoringAuthorityError(
            "scoring authority fingerprint mismatch"
        )
    return document


def _request_path_from_preparation(
    preparation: dict[str, object],
) -> Path:
    raw = preparation.get("request_path")
    if not isinstance(raw, str) or not raw:
        raise FL9V2ScoringAuthorityError(
            "preparation receipt request_path is invalid"
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise FL9V2ScoringAuthorityError(
            "preparation receipt request_path must be absolute"
        )
    return _resolve_existing_regular_file(
        path,
        label="prepared V2 request",
    )


def _require_request_matches_preparation(
    *,
    request,
    preparation: dict[str, object],
) -> None:
    expected = {
        "request_fingerprint_sha256": preparation[
            "request_fingerprint_sha256"
        ],
        "expected_release_source_sha": preparation[
            "release_source_sha"
        ],
        "expected_cohort_artifact_fingerprint_sha256": preparation[
            "cohort_artifact_fingerprint_sha256"
        ],
        "expected_hydration_policy_fingerprint_sha256": preparation[
            "hydration_policy_fingerprint_sha256"
        ],
        "destination_path": preparation["evidence_destination"],
    }
    for field, value in expected.items():
        if getattr(request, field) != value:
            raise FL9V2ScoringAuthorityError(
                f"prepared V2 request {field} does not match preparation receipt"
            )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise FL9V2ScoringAuthorityError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise FL9V2ScoringAuthorityError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise FL9V2ScoringAuthorityError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(
    path: Path,
    *,
    label: str,
) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise FL9V2ScoringAuthorityError(
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
        raise FL9V2ScoringAuthorityError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(
    destination: str | Path,
    document: dict[str, object],
) -> None:
    path = Path(destination).expanduser().resolve()
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "scoring authority destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise FL9V2ScoringAuthorityError(
            "scoring authority destination parent must be a real directory"
        )

    payload = _canonical(document).encode("utf-8")
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
                "scoring authority destination appeared during write"
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
    if not isinstance(payload, str):
        raise FL9V2ScoringAuthorityError(
            f"{label} payload must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise FL9V2ScoringAuthorityError(
            f"{label} must use canonical JSON with one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise FL9V2ScoringAuthorityError(
            f"{label} is not valid canonical JSON"
        ) from error
    if not isinstance(document, dict) or _canonical(document) != payload:
        raise FL9V2ScoringAuthorityError(
            f"{label} is not canonical JSON"
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
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FL9V2ScoringAuthorityError(
            f"{name} must be non-empty text"
        )


def _require_source_sha(name: str, value: object) -> None:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FL9V2ScoringAuthorityError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FL9V2ScoringAuthorityError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FL9V2ScoringAuthorityError(
            f"{name} must be a non-negative integer"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-scoring-authority-decide",
        description=(
            "Record one explicit discovery-backed FL9 V2 scoring authority "
            "decision without executing scoring or changing PAPER/LIVE state."
        ),
    )
    parser.add_argument("--request-preparation", required=True)
    parser.add_argument(
        "--decision",
        required=True,
        choices=sorted(_VALID_DECISIONS),
    )
    parser.add_argument("--decision-reason", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        result = decide_fl9_v2_scoring_authority(
            request_preparation_path=args.request_preparation,
            decision=args.decision,
            decision_reason=args.decision_reason,
            destination=args.destination,
        )
    except (
        FL9V2ScoringAuthorityError,
        FileExistsError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1

    sys.stdout.write(_canonical(result))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
