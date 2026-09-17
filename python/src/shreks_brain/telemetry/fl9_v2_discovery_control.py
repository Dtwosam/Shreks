from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import time
from typing import Final

from shreks_brain.fl9_v2_runtime_manifest_discovery import (
    AuthenticatedV2DiscoveryRequestAuthority,
    RuntimeManifestDiscoveryError,
    authenticate_fl9_v2_discovery_request_authority,
    discover_fl9_v2_runtime_manifests_from_v2_request_authority,
)


CONTROL_REQUEST_SCHEMA_NAME: Final = "shreks.fl9_v2_discovery_control_request"
CONTROL_REQUEST_SCHEMA_VERSION: Final = 1
CONTROL_RESULT_SCHEMA_NAME: Final = "shreks.fl9_v2_discovery_control_result"
CONTROL_RESULT_SCHEMA_VERSION: Final = 1
_MARKER_PREFIX: Final = "shreks-fl9-v2-discovery."
_MARKER_SUFFIX: Final = ".request"
_REQUEST_ID_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_SOURCE_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_MAX_MARKER_BYTES: Final = 4096
_MAX_REQUEST_AGE_MS: Final = 300_000
_MAX_FUTURE_SKEW_MS: Final = 30_000
_AUTHORITY_FILENAME: Final = "v2-first-champion-request.json"
_MAX_AUTHORITY_SEARCH_DEPTH: Final = 3
_MAX_AUTHORITY_DIRECTORIES: Final = 128
_MAX_AUTHORITY_CANDIDATES: Final = 64
_DEFAULT_COHORT = Path(
    "/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2"
)


class DiscoveryControlError(RuntimeError):
    """Raised when an FL9 V2 discovery control request cannot be trusted."""


def process_pending_fl9_v2_discovery_requests(
    *,
    marker_directory: Path = Path("/dev/shm"),
    receipt_root: Path = Path(
        "/var/lib/shreks/telemetry/fl9-v2-discovery-control"
    ),
    request_search_root: Path = Path("/var/lib/shreks"),
    cohort_path: Path = _DEFAULT_COHORT,
    active_runtime_manifest_path: Path = Path("/etc/shreks/paper-campaign.json"),
    backup_root: Path = Path("/var/lib/shreks/backups"),
    current_release_link: Path = Path("/opt/shreks/current"),
    expected_owner_uid: int | None = None,
    now_unix_ms: int | None = None,
    max_requests: int = 8,
) -> tuple[dict[str, object], ...]:
    if max_requests < 1:
        raise ValueError("max_requests must be positive")
    owner_uid = (
        pwd.getpwnam("shreks-deploy").pw_uid
        if expected_owner_uid is None
        else expected_owner_uid
    )
    now_ms = int(time.time() * 1000) if now_unix_ms is None else now_unix_ms
    if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
        raise ValueError("now_unix_ms must be a non-negative integer")

    directory = Path(marker_directory)
    if directory.is_symlink() or not directory.is_dir():
        return ()
    try:
        marker_paths = tuple(
            sorted(
                path
                for path in directory.iterdir()
                if path.name.startswith(_MARKER_PREFIX)
                and path.name.endswith(_MARKER_SUFFIX)
            )
        )[:max_requests]
    except OSError:
        return ()

    results: list[dict[str, object]] = []
    for marker_path in marker_paths:
        result, may_persist = _process_one_marker(
            marker_path=marker_path,
            receipt_root=Path(receipt_root),
            request_search_root=Path(request_search_root),
            cohort_path=Path(cohort_path),
            active_runtime_manifest_path=Path(active_runtime_manifest_path),
            backup_root=Path(backup_root),
            current_release_link=Path(current_release_link),
            expected_owner_uid=owner_uid,
            now_unix_ms=now_ms,
        )
        if may_persist:
            try:
                _write_receipt_once(Path(receipt_root), result)
            except DiscoveryControlError as error:
                result = _failure_result(
                    request_id=_request_id_from_marker_name(marker_path.name),
                    expected_release_sha=result.get("expected_release_sha"),
                    observed_release_sha=result.get("observed_release_sha"),
                    error_code="RECEIPT_WRITE_FAILED",
                    message=str(error),
                )
        results.append(result)
    return tuple(results)


def encode_fl9_v2_discovery_control_result(result: dict[str, object]) -> str:
    return _canonical_json(result)


def emit_fl9_v2_discovery_control_result(
    result: dict[str, object],
    *,
    stream=None,
) -> None:
    target = sys.stdout if stream is None else stream
    print(encode_fl9_v2_discovery_control_result(result), file=target)


def _process_one_marker(
    *,
    marker_path: Path,
    receipt_root: Path,
    request_search_root: Path,
    cohort_path: Path,
    active_runtime_manifest_path: Path,
    backup_root: Path,
    current_release_link: Path,
    expected_owner_uid: int,
    now_unix_ms: int,
) -> tuple[dict[str, object], bool]:
    fallback_request_id = _request_id_from_marker_name(marker_path.name)
    try:
        request = _read_control_request(
            marker_path,
            expected_owner_uid=expected_owner_uid,
        )
    except DiscoveryControlError as error:
        return (
            _failure_result(
                request_id=fallback_request_id,
                expected_release_sha=None,
                observed_release_sha=None,
                error_code="UNTRUSTED_MARKER",
                message=str(error),
            ),
            False,
        )

    request_id = request["request_id"]
    expected_release_sha = request["expected_release_sha"]
    try:
        observed_release_sha = _require_current_release_binding(
            current_release_link,
            expected_release_sha,
        )
    except DiscoveryControlError as error:
        return (
            _failure_result(
                request_id=request_id,
                expected_release_sha=expected_release_sha,
                observed_release_sha=None,
                error_code="RELEASE_BINDING_FAILED",
                message=str(error),
            ),
            True,
        )

    receipt = _read_existing_receipt(
        receipt_root,
        request_id=request_id,
        expected_release_sha=expected_release_sha,
    )
    if receipt is not None:
        return receipt, False

    created_at_unix_ms = request["created_at_unix_ms"]
    if created_at_unix_ms < now_unix_ms - _MAX_REQUEST_AGE_MS:
        return (
            _failure_result(
                request_id=request_id,
                expected_release_sha=expected_release_sha,
                observed_release_sha=observed_release_sha,
                error_code="STALE_REQUEST",
                message="control request is stale",
            ),
            True,
        )
    if created_at_unix_ms > now_unix_ms + _MAX_FUTURE_SKEW_MS:
        return (
            _failure_result(
                request_id=request_id,
                expected_release_sha=expected_release_sha,
                observed_release_sha=observed_release_sha,
                error_code="FUTURE_REQUEST",
                message="control request timestamp is too far in the future",
            ),
            True,
        )

    try:
        result = _resolve_and_discover(
            request_id=request_id,
            expected_release_sha=expected_release_sha,
            observed_release_sha=observed_release_sha,
            request_search_root=request_search_root,
            cohort_path=cohort_path,
            active_runtime_manifest_path=active_runtime_manifest_path,
            backup_root=backup_root,
        )
    except (DiscoveryControlError, RuntimeManifestDiscoveryError, OSError, TypeError, ValueError) as error:
        return (
            _failure_result(
                request_id=request_id,
                expected_release_sha=expected_release_sha,
                observed_release_sha=observed_release_sha,
                error_code="DISCOVERY_FAILED",
                message=str(error),
            ),
            True,
        )
    return result, True


def _read_control_request(path: Path, *, expected_owner_uid: int) -> dict[str, object]:
    request_id_from_name = _request_id_from_marker_name(path.name)
    if request_id_from_name is None:
        raise DiscoveryControlError("control marker filename is invalid")

    try:
        before = path.lstat()
    except OSError as error:
        raise DiscoveryControlError("control marker could not be inspected") from error
    if stat.S_ISLNK(before.st_mode):
        raise DiscoveryControlError("control marker must not be a symlink")
    if not stat.S_ISREG(before.st_mode):
        raise DiscoveryControlError("control marker must be a regular file")
    if stat.S_IMODE(before.st_mode) != 0o644:
        raise DiscoveryControlError("control marker mode must be 0644")
    if before.st_uid != expected_owner_uid:
        raise DiscoveryControlError("control marker owner is not shreks-deploy")
    if before.st_size < 2 or before.st_size > _MAX_MARKER_BYTES:
        raise DiscoveryControlError("control marker size is outside the allowed bound")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise DiscoveryControlError("control marker could not be opened safely") from error
    try:
        opened = os.fstat(fd)
        payload = os.read(fd, _MAX_MARKER_BYTES + 1)
        after = os.fstat(fd)
    except OSError as error:
        raise DiscoveryControlError("control marker could not be read safely") from error
    finally:
        os.close(fd)

    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_opened = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_opened or identity_opened != identity_after:
        raise DiscoveryControlError("control marker changed while being read")
    if len(payload) != before.st_size or len(payload) > _MAX_MARKER_BYTES:
        raise DiscoveryControlError("control marker size changed while being read")

    try:
        text = payload.decode("utf-8")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryControlError("control marker JSON is invalid") from error
    if not isinstance(document, dict):
        raise DiscoveryControlError("control marker must contain one JSON object")
    expected_keys = {
        "schema_name",
        "schema_version",
        "request_id",
        "expected_release_sha",
        "created_at_unix_ms",
    }
    if set(document) != expected_keys:
        raise DiscoveryControlError("control marker keys do not match the sealed schema")
    if text != _canonical_json(document) + "\n":
        raise DiscoveryControlError("control marker JSON is not canonical")
    if document["schema_name"] != CONTROL_REQUEST_SCHEMA_NAME:
        raise DiscoveryControlError("control marker schema_name is unsupported")
    if document["schema_version"] != CONTROL_REQUEST_SCHEMA_VERSION:
        raise DiscoveryControlError("control marker schema_version is unsupported")

    request_id = document["request_id"]
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise DiscoveryControlError("control request_id is invalid")
    if request_id != request_id_from_name:
        raise DiscoveryControlError("control request_id does not match marker filename")

    source_sha = document["expected_release_sha"]
    if not isinstance(source_sha, str) or _SOURCE_SHA_RE.fullmatch(source_sha) is None:
        raise DiscoveryControlError("expected release SHA is invalid")
    created_at = document["created_at_unix_ms"]
    if isinstance(created_at, bool) or not isinstance(created_at, int) or created_at < 0:
        raise DiscoveryControlError("created_at_unix_ms is invalid")
    return document


def _require_current_release_binding(current_link: Path, expected_sha: str) -> str:
    if not current_link.is_symlink():
        raise DiscoveryControlError("current release path is not a symlink")
    try:
        resolved = current_link.resolve(strict=True)
    except OSError as error:
        raise DiscoveryControlError("current release symlink could not be resolved") from error
    if resolved.name != expected_sha or resolved.parent.name != "releases":
        raise DiscoveryControlError("current release does not match expected release SHA")

    manifest_path = resolved / "RELEASE_MANIFEST.json"
    payload = _read_regular_file_stable(manifest_path, label="release manifest")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryControlError("release manifest JSON is invalid") from error
    if not isinstance(document, dict):
        raise DiscoveryControlError("release manifest is invalid")
    if document.get("schema_version") != "g2-release-manifest-v1":
        raise DiscoveryControlError("release manifest schema is invalid")
    if document.get("source_sha") != expected_sha:
        raise DiscoveryControlError("release manifest source SHA does not match expected release")
    return resolved.name


def _resolve_and_discover(
    *,
    request_id: str,
    expected_release_sha: str,
    observed_release_sha: str,
    request_search_root: Path,
    cohort_path: Path,
    active_runtime_manifest_path: Path,
    backup_root: Path,
) -> dict[str, object]:
    candidate_paths = _enumerate_authority_candidates(request_search_root)
    authenticated: list[AuthenticatedV2DiscoveryRequestAuthority] = []
    rejected_count = 0
    for path in candidate_paths:
        try:
            authority = authenticate_fl9_v2_discovery_request_authority(
                cohort_path=cohort_path,
                v2_host_request_authority_path=path,
            )
        except (RuntimeManifestDiscoveryError, OSError, TypeError, ValueError):
            rejected_count += 1
            continue
        authenticated.append(authority)

    groups: dict[str, list[AuthenticatedV2DiscoveryRequestAuthority]] = {}
    for authority in authenticated:
        fingerprint = _authority_group_fingerprint(authority)
        groups.setdefault(fingerprint, []).append(authority)

    group_provenance = [
        {
            "authority_group_fingerprint_sha256": fingerprint,
            "request_count": len(authorities),
            "request_paths": sorted(str(item.request_path) for item in authorities),
        }
        for fingerprint, authorities in sorted(groups.items())
    ]
    common = {
        "schema_name": CONTROL_RESULT_SCHEMA_NAME,
        "schema_version": CONTROL_RESULT_SCHEMA_VERSION,
        "request_id": request_id,
        "expected_release_sha": expected_release_sha,
        "observed_release_sha": observed_release_sha,
        "request_candidate_count": len(candidate_paths),
        "authenticated_authority_count": len(authenticated),
        "rejected_authority_count": rejected_count,
        "authority_group_count": len(groups),
        "authority_groups": group_provenance,
    }
    if not groups:
        return {**common, "status": "HOLD_NO_REQUEST_AUTHORITY"}
    if len(groups) != 1:
        return {**common, "status": "HOLD_AMBIGUOUS_REQUEST_AUTHORITY"}

    only_group = next(iter(groups.values()))
    selected = min(only_group, key=lambda item: str(item.request_path))
    report = discover_fl9_v2_runtime_manifests_from_v2_request_authority(
        cohort_path=cohort_path,
        active_runtime_manifest_path=active_runtime_manifest_path,
        backup_root=backup_root,
        v2_host_request_authority_path=selected.request_path,
    )
    status = report.get("status")
    if status not in {"FOUND_COMPATIBLE", "HOLD_NO_COMPATIBLE"}:
        raise DiscoveryControlError("runtime-manifest discovery returned an untrusted status")
    return {
        **common,
        "status": status,
        "selected_request_path": str(selected.request_path),
        "selected_request_fingerprint_sha256": selected.request_fingerprint_sha256,
        "discovery_report": report,
    }


def _enumerate_authority_candidates(root: Path) -> tuple[Path, ...]:
    if root.is_symlink() or not root.is_dir():
        raise DiscoveryControlError("historical request search root is not a real directory")
    candidates: set[Path] = set()
    root_candidate = root / _AUTHORITY_FILENAME
    if root_candidate.exists() or root_candidate.is_symlink():
        candidates.add(root_candidate)

    try:
        top_level = tuple(
            sorted(
                path
                for path in root.iterdir()
                if path.name.startswith("fl9-v2-")
                and not path.name.startswith(".")
                and path.is_dir()
                and not path.is_symlink()
            )
        )
    except OSError as error:
        raise DiscoveryControlError("historical request search root could not be listed") from error

    frontier: list[tuple[Path, int]] = [(path, 1) for path in top_level]
    visited = 0
    while frontier:
        directory, depth = frontier.pop(0)
        visited += 1
        if visited > _MAX_AUTHORITY_DIRECTORIES:
            raise DiscoveryControlError("historical request search exceeded directory bound")
        candidate = directory / _AUTHORITY_FILENAME
        if candidate.exists() or candidate.is_symlink():
            candidates.add(candidate)
            if len(candidates) > _MAX_AUTHORITY_CANDIDATES:
                raise DiscoveryControlError("historical request search exceeded candidate bound")
        if depth >= _MAX_AUTHORITY_SEARCH_DEPTH:
            continue
        try:
            children = tuple(
                sorted(
                    child
                    for child in directory.iterdir()
                    if not child.name.startswith(".")
                    and child.is_dir()
                    and not child.is_symlink()
                )
            )
        except OSError as error:
            raise DiscoveryControlError("historical request directory could not be listed") from error
        frontier.extend((child, depth + 1) for child in children)
    return tuple(sorted(candidates))


def _authority_group_fingerprint(
    authority: AuthenticatedV2DiscoveryRequestAuthority,
) -> str:
    payload = {
        "cohort_artifact_fingerprint_sha256": (
            authority.cohort_artifact_fingerprint_sha256
        ),
        "hydration_policy_version": authority.hydration_policy_version,
        "strategy_families": list(authority.strategy_families),
        "max_exit_quote_age_ms": authority.max_exit_quote_age_ms,
        "execution_cost_policy_version": authority.execution_cost_policy_version,
        "expected_round_trip_cost_bps": authority.expected_round_trip_cost_bps,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _read_existing_receipt(
    receipt_root: Path,
    *,
    request_id: str,
    expected_release_sha: str,
) -> dict[str, object] | None:
    path = receipt_root / f"{request_id}.json"
    if not path.exists() and not path.is_symlink():
        return None
    payload = _read_regular_file_stable(path, label="discovery control receipt")
    try:
        text = payload.decode("utf-8")
        result = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryControlError("stored discovery receipt is invalid") from error
    if not isinstance(result, dict) or text != _canonical_json(result) + "\n":
        raise DiscoveryControlError("stored discovery receipt is not canonical")
    if result.get("schema_name") != CONTROL_RESULT_SCHEMA_NAME:
        raise DiscoveryControlError("stored discovery receipt schema is invalid")
    if result.get("schema_version") != CONTROL_RESULT_SCHEMA_VERSION:
        raise DiscoveryControlError("stored discovery receipt schema version is invalid")
    if result.get("request_id") != request_id:
        raise DiscoveryControlError("stored discovery receipt request ID mismatch")
    if result.get("expected_release_sha") != expected_release_sha:
        raise DiscoveryControlError("stored discovery receipt release binding mismatch")
    return result


def _write_receipt_once(receipt_root: Path, result: dict[str, object]) -> None:
    request_id = result.get("request_id")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise DiscoveryControlError("result request ID is invalid for receipt")
    if receipt_root.is_symlink():
        raise DiscoveryControlError("receipt root must not be a symlink")
    try:
        receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as error:
        raise DiscoveryControlError("receipt root could not be created") from error
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise DiscoveryControlError("receipt root must be a real directory")

    destination = receipt_root / f"{request_id}.json"
    if destination.exists() or destination.is_symlink():
        existing = _read_existing_receipt(
            receipt_root,
            request_id=request_id,
            expected_release_sha=str(result.get("expected_release_sha")),
        )
        if existing != result:
            raise DiscoveryControlError("existing receipt conflicts with discovery result")
        return

    payload = (_canonical_json(result) + "\n").encode("utf-8")
    temporary = receipt_root / f".{request_id}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(fd)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DiscoveryControlError("discovery receipt could not be written atomically") from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise DiscoveryControlError(f"{label} must be an existing regular file")
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise DiscoveryControlError(f"{label} could not be read") from error
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise DiscoveryControlError(f"{label} changed while being read")
    return payload


def _failure_result(
    *,
    request_id: str | None,
    expected_release_sha: object,
    observed_release_sha: object,
    error_code: str,
    message: str,
) -> dict[str, object]:
    bounded = " ".join(str(message).split())[:240]
    return {
        "schema_name": CONTROL_RESULT_SCHEMA_NAME,
        "schema_version": CONTROL_RESULT_SCHEMA_VERSION,
        "request_id": request_id,
        "expected_release_sha": expected_release_sha,
        "observed_release_sha": observed_release_sha,
        "status": "FAILED",
        "error_code": error_code,
        "error": bounded,
    }


def _request_id_from_marker_name(name: str) -> str | None:
    if not name.startswith(_MARKER_PREFIX) or not name.endswith(_MARKER_SUFFIX):
        return None
    value = name[len(_MARKER_PREFIX) : -len(_MARKER_SUFFIX)]
    if _REQUEST_ID_RE.fullmatch(value) is None:
        return None
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
