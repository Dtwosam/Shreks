from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


FL9_V2_DISCOVERY_AUTHORITY_BINDING_SCHEMA_NAME = (
    "shreks.fl9_v2_discovery_authority_binding"
)
FL9_V2_DISCOVERY_AUTHORITY_BINDING_SCHEMA_VERSION = 1

_CONTROL_RESULT_SCHEMA_NAME = "shreks.fl9_v2_discovery_control_result"
_CONTROL_RESULT_SCHEMA_VERSION = 1
_DISCOVERY_SCHEMA_NAME = "shreks.fl9_v2_runtime_manifest_discovery"
_DISCOVERY_REQUEST_AUTHORITY_SCHEMA_VERSION = 2
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DiscoveryAuthorityBindingError(RuntimeError):
    """Raised when an FL9 V2 discovery result cannot be bound safely."""


def bind_fl9_v2_discovery_authority(
    *,
    discovery_result_path: str | Path,
    destination: str | Path,
    runtime_manifest_fingerprint_sha256: str | None = None,
) -> dict[str, object]:
    source = Path(discovery_result_path).expanduser().resolve()
    payload = _read_regular_file_stable(source, label="discovery result")
    document = _decode_canonical_json(payload, label="discovery result")
    _require_control_result_identity(document)

    status = document.get("status")
    if status != "FOUND_COMPATIBLE":
        raise DiscoveryAuthorityBindingError(
            "only FOUND_COMPATIBLE discovery results may be bound"
        )

    expected_release = document.get("expected_release_sha")
    observed_release = document.get("observed_release_sha")
    _require_source_sha("expected_release_sha", expected_release)
    _require_source_sha("observed_release_sha", observed_release)
    if expected_release != observed_release:
        raise DiscoveryAuthorityBindingError(
            "discovery result release binding does not match exactly"
        )

    request_id = document.get("request_id")
    if (
        not isinstance(request_id, str)
        or _REQUEST_ID_RE.fullmatch(request_id) is None
    ):
        raise DiscoveryAuthorityBindingError(
            "discovery result request_id is invalid"
        )

    authority_group_count = document.get("authority_group_count")
    authority_groups = document.get("authority_groups")
    if (
        authority_group_count != 1
        or not isinstance(authority_groups, list)
        or len(authority_groups) != 1
    ):
        raise DiscoveryAuthorityBindingError(
            "exactly one authenticated authority group is required"
        )
    authority_group = authority_groups[0]
    if not isinstance(authority_group, dict):
        raise DiscoveryAuthorityBindingError(
            "authority group provenance is invalid"
        )
    authority_group_fingerprint = authority_group.get(
        "authority_group_fingerprint_sha256"
    )
    _require_sha256(
        "authority_group_fingerprint_sha256",
        authority_group_fingerprint,
    )

    selected_request_fingerprint = document.get(
        "selected_request_fingerprint_sha256"
    )
    _require_sha256(
        "selected_request_fingerprint_sha256",
        selected_request_fingerprint,
    )

    report = document.get("discovery_report")
    if not isinstance(report, dict):
        raise DiscoveryAuthorityBindingError(
            "FOUND_COMPATIBLE result is missing discovery_report"
        )
    if report.get("schema_name") != _DISCOVERY_SCHEMA_NAME:
        raise DiscoveryAuthorityBindingError(
            "discovery_report schema_name is unsupported"
        )
    if (
        report.get("schema_version")
        != _DISCOVERY_REQUEST_AUTHORITY_SCHEMA_VERSION
    ):
        raise DiscoveryAuthorityBindingError(
            "discovery_report schema_version is unsupported"
        )
    if report.get("status") != "FOUND_COMPATIBLE":
        raise DiscoveryAuthorityBindingError(
            "nested discovery_report is not FOUND_COMPATIBLE"
        )

    authority = report.get("non_manifest_input_authority")
    if not isinstance(authority, dict):
        raise DiscoveryAuthorityBindingError(
            "discovery_report is missing non-manifest authority"
        )
    if authority.get("authority_kind") != "v2_host_request":
        raise DiscoveryAuthorityBindingError(
            "discovery_report authority kind is unsupported"
        )
    if (
        authority.get("request_fingerprint_sha256")
        != selected_request_fingerprint
    ):
        raise DiscoveryAuthorityBindingError(
            "selected request fingerprint does not match nested authority"
        )
    cohort_fingerprint = authority.get(
        "cohort_artifact_fingerprint_sha256"
    )
    try:
        _require_sha256(
            "cohort_artifact_fingerprint_sha256",
            cohort_fingerprint,
        )
    except DiscoveryAuthorityBindingError as error:
        raise DiscoveryAuthorityBindingError(
            "authenticated cohort artifact fingerprint is missing or invalid"
        ) from error

    cohort_quote_mint = report.get("cohort_quote_mint")
    if not isinstance(cohort_quote_mint, str) or not cohort_quote_mint:
        raise DiscoveryAuthorityBindingError(
            "discovery_report cohort quote mint is invalid"
        )

    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise DiscoveryAuthorityBindingError(
            "discovery_report candidates must be a list"
        )
    candidate_count = report.get("candidate_count")
    compatible_count = report.get("compatible_candidate_count")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count != len(candidates)
    ):
        raise DiscoveryAuthorityBindingError(
            "discovery_report candidate count is inconsistent"
        )
    compatible = [
        candidate
        for candidate in candidates
        if isinstance(candidate, dict)
        and candidate.get("compatibility") == "COMPATIBLE"
    ]
    if (
        isinstance(compatible_count, bool)
        or not isinstance(compatible_count, int)
        or compatible_count != len(compatible)
        or not compatible
    ):
        raise DiscoveryAuthorityBindingError(
            "discovery_report compatible candidate count is inconsistent"
        )

    selected = _select_compatible_candidate(
        compatible,
        requested_fingerprint=runtime_manifest_fingerprint_sha256,
    )
    _validate_selected_candidate(
        selected,
        cohort_quote_mint=cohort_quote_mint,
    )

    material: dict[str, object] = {
        "schema_name": FL9_V2_DISCOVERY_AUTHORITY_BINDING_SCHEMA_NAME,
        "schema_version": FL9_V2_DISCOVERY_AUTHORITY_BINDING_SCHEMA_VERSION,
        "request_id": request_id,
        "release_source_sha": expected_release,
        "cohort_artifact_fingerprint_sha256": cohort_fingerprint,
        "cohort_quote_mint": cohort_quote_mint,
        "authority_group_fingerprint_sha256": (
            authority_group_fingerprint
        ),
        "selected_request_fingerprint_sha256": (
            selected_request_fingerprint
        ),
        "discovery_result_sha256": hashlib.sha256(payload).hexdigest(),
        "runtime_manifest_source_kind": selected["source_kind"],
        "runtime_manifest_source_path": selected["source_path"],
        "backup_bundle_path": selected["backup_bundle_path"],
        "backup_created_at_unix_ms": selected[
            "backup_created_at_unix_ms"
        ],
        "runtime_manifest_fingerprint_sha256": selected[
            "runtime_manifest_fingerprint_sha256"
        ],
        "hydration_policy_fingerprint_sha256": selected[
            "hydration_policy_fingerprint_sha256"
        ],
        "regime_quote_asset_mint": selected[
            "regime_quote_asset_mint"
        ],
        "safety_probe_output_mint": selected[
            "safety_probe_output_mint"
        ],
        "quote_asset_mint": selected["quote_asset_mint"],
        "quote_asset_decimals": selected["quote_asset_decimals"],
        "quote_provider": selected["quote_provider"],
    }
    binding = {
        **material,
        "binding_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_binding_once(destination, binding)
    verified = decode_fl9_v2_discovery_authority_binding(
        Path(destination).expanduser().resolve().read_text(
            encoding="utf-8"
        )
    )
    if verified != binding:
        raise DiscoveryAuthorityBindingError(
            "written discovery authority binding did not round-trip"
        )
    return binding


def decode_fl9_v2_discovery_authority_binding(
    payload: str,
) -> dict[str, object]:
    if not isinstance(payload, str):
        raise DiscoveryAuthorityBindingError(
            "binding payload must be text"
        )
    try:
        document = _decode_canonical_text(
            payload,
            label="discovery authority binding",
        )
    except DiscoveryAuthorityBindingError:
        raise
    if document.get("schema_name") != (
        FL9_V2_DISCOVERY_AUTHORITY_BINDING_SCHEMA_NAME
    ):
        raise DiscoveryAuthorityBindingError(
            "binding schema_name is unsupported"
        )
    if document.get("schema_version") != (
        FL9_V2_DISCOVERY_AUTHORITY_BINDING_SCHEMA_VERSION
    ):
        raise DiscoveryAuthorityBindingError(
            "binding schema_version is unsupported"
        )

    expected_keys = {
        "schema_name",
        "schema_version",
        "request_id",
        "release_source_sha",
        "cohort_artifact_fingerprint_sha256",
        "cohort_quote_mint",
        "authority_group_fingerprint_sha256",
        "selected_request_fingerprint_sha256",
        "discovery_result_sha256",
        "runtime_manifest_source_kind",
        "runtime_manifest_source_path",
        "backup_bundle_path",
        "backup_created_at_unix_ms",
        "runtime_manifest_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
        "regime_quote_asset_mint",
        "safety_probe_output_mint",
        "quote_asset_mint",
        "quote_asset_decimals",
        "quote_provider",
        "binding_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise DiscoveryAuthorityBindingError(
            "binding has unknown or missing fields"
        )

    for name in (
        "cohort_artifact_fingerprint_sha256",
        "authority_group_fingerprint_sha256",
        "selected_request_fingerprint_sha256",
        "discovery_result_sha256",
        "runtime_manifest_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
        "binding_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))
    _require_source_sha(
        "release_source_sha",
        document.get("release_source_sha"),
    )
    request_id = document.get("request_id")
    if (
        not isinstance(request_id, str)
        or _REQUEST_ID_RE.fullmatch(request_id) is None
    ):
        raise DiscoveryAuthorityBindingError(
            "binding request_id is invalid"
        )

    claimed = document["binding_fingerprint_sha256"]
    material = dict(document)
    del material["binding_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise DiscoveryAuthorityBindingError(
            "binding fingerprint mismatch"
        )
    return document


def _require_control_result_identity(
    document: dict[str, object],
) -> None:
    if document.get("schema_name") != _CONTROL_RESULT_SCHEMA_NAME:
        raise DiscoveryAuthorityBindingError(
            "discovery result schema_name is unsupported"
        )
    if document.get("schema_version") != _CONTROL_RESULT_SCHEMA_VERSION:
        raise DiscoveryAuthorityBindingError(
            "discovery result schema_version is unsupported"
        )


def _select_compatible_candidate(
    candidates: list[dict[str, object]],
    *,
    requested_fingerprint: str | None,
) -> dict[str, object]:
    if requested_fingerprint is None:
        if len(candidates) != 1:
            raise DiscoveryAuthorityBindingError(
                "multiple compatible candidates require an explicit "
                "runtime-manifest fingerprint"
            )
        return candidates[0]

    _require_sha256(
        "runtime_manifest_fingerprint_sha256",
        requested_fingerprint,
    )
    matches = [
        candidate
        for candidate in candidates
        if candidate.get("runtime_manifest_fingerprint_sha256")
        == requested_fingerprint
    ]
    if len(matches) != 1:
        raise DiscoveryAuthorityBindingError(
            "explicit runtime-manifest fingerprint must identify exactly "
            "one compatible candidate"
        )
    return matches[0]


def _validate_selected_candidate(
    candidate: dict[str, object],
    *,
    cohort_quote_mint: str,
) -> None:
    if candidate.get("authentication") != "AUTHENTICATED":
        raise DiscoveryAuthorityBindingError(
            "selected runtime manifest is not authenticated"
        )
    if candidate.get("compatibility") != "COMPATIBLE":
        raise DiscoveryAuthorityBindingError(
            "selected runtime manifest is not compatible"
        )
    _require_sha256(
        "runtime_manifest_fingerprint_sha256",
        candidate.get("runtime_manifest_fingerprint_sha256"),
    )
    _require_sha256(
        "hydration_policy_fingerprint_sha256",
        candidate.get("hydration_policy_fingerprint_sha256"),
    )

    source_kind = candidate.get("source_kind")
    if source_kind not in {"active", "g8_backup"}:
        raise DiscoveryAuthorityBindingError(
            "selected runtime manifest source kind is unsupported"
        )
    source_path = candidate.get("source_path")
    if not isinstance(source_path, str) or not source_path:
        raise DiscoveryAuthorityBindingError(
            "selected runtime manifest source path is invalid"
        )
    backup_path = candidate.get("backup_bundle_path")
    if source_kind == "active":
        if backup_path is not None:
            raise DiscoveryAuthorityBindingError(
                "active runtime manifest must not claim backup provenance"
            )
    elif not isinstance(backup_path, str) or not backup_path:
        raise DiscoveryAuthorityBindingError(
            "backup runtime manifest must include bundle provenance"
        )

    for field in (
        "regime_quote_asset_mint",
        "safety_probe_output_mint",
        "quote_asset_mint",
    ):
        if candidate.get(field) != cohort_quote_mint:
            raise DiscoveryAuthorityBindingError(
                "selected candidate quote identity does not match frozen "
                "cohort quote mint"
            )
    decimals = candidate.get("quote_asset_decimals")
    if (
        isinstance(decimals, bool)
        or not isinstance(decimals, int)
        or decimals < 0
    ):
        raise DiscoveryAuthorityBindingError(
            "selected candidate quote decimals are invalid"
        )
    provider = candidate.get("quote_provider")
    if not isinstance(provider, str) or not provider:
        raise DiscoveryAuthorityBindingError(
            "selected candidate quote provider is invalid"
        )


def _write_binding_once(
    destination: str | Path,
    binding: dict[str, object],
) -> None:
    path = Path(destination).expanduser().resolve()
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "discovery authority binding destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise DiscoveryAuthorityBindingError(
            "binding destination parent must be a real directory"
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
                "discovery authority binding destination appeared during write"
            )
        temporary.rename(path)
        path.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise DiscoveryAuthorityBindingError(
            f"{label} must be an existing regular file"
        )
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise DiscoveryAuthorityBindingError(
            f"{label} could not be read"
        ) from error
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise DiscoveryAuthorityBindingError(
            f"{label} changed while being read"
        )
    return payload


def _decode_canonical_json(
    payload: bytes,
    *,
    label: str,
) -> dict[str, object]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiscoveryAuthorityBindingError(
            f"{label} is not UTF-8"
        ) from error
    return _decode_canonical_text(text, label=label)


def _decode_canonical_text(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise DiscoveryAuthorityBindingError(
            f"{label} must use canonical JSON with one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise DiscoveryAuthorityBindingError(
            f"{label} is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise DiscoveryAuthorityBindingError(
            f"{label} must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise DiscoveryAuthorityBindingError(
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


def _require_source_sha(name: str, value: object) -> None:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise DiscoveryAuthorityBindingError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DiscoveryAuthorityBindingError(
            f"{name} must be lowercase SHA-256 hex"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-discovery-authority-bind",
        description=(
            "Bind one authenticated FL9 V2 FOUND_COMPATIBLE discovery "
            "result to one exact runtime-manifest authority without "
            "granting scoring or promotion authority."
        ),
    )
    parser.add_argument("--discovery-result", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument(
        "--runtime-manifest-fingerprint",
        default=None,
    )
    args = parser.parse_args(argv)

    try:
        binding = bind_fl9_v2_discovery_authority(
            discovery_result_path=args.discovery_result,
            destination=args.destination,
            runtime_manifest_fingerprint_sha256=(
                args.runtime_manifest_fingerprint
            ),
        )
    except (
        DiscoveryAuthorityBindingError,
        FileExistsError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1

    sys.stdout.write(_canonical_json(binding))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
