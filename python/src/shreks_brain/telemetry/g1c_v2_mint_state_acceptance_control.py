from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import stat
import time
from typing import Final

from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfigError,
    load_observer_paper_campaign_runtime_config,
)
from shreks_brain.telemetry.fl9_v2_discovery_control import (
    DiscoveryControlError,
    _read_exchange_result,
    _require_current_release_binding,
    _resolve_marker_directory,
)

from .g1c_v2_mint_state_acceptance import (
    MintStateAcceptanceError,
    analyze_mint_state_acceptance,
)


CONTROL_REQUEST_SCHEMA_NAME: Final = (
    "shreks.g1c_v2_mint_state_acceptance_control_request"
)
CONTROL_REQUEST_SCHEMA_VERSION: Final = 1
CONTROL_RESULT_SCHEMA_NAME: Final = (
    "shreks.g1c_v2_mint_state_acceptance_control_result"
)
CONTROL_RESULT_SCHEMA_VERSION: Final = 1
_MARKER_PREFIX: Final = "shreks-g1c-v2-mint-state-acceptance."
_MARKER_SUFFIX: Final = ".request"
_RESULT_EXCHANGE_SUFFIX: Final = ".result.d"
_RESULT_FILENAME: Final = "result.json"
_RESULT_EXCHANGE_MODE: Final = 0o733
_RESULT_FILE_MODE: Final = 0o644
_MAX_MARKER_BYTES: Final = 4096
_MAX_RESULT_BYTES: Final = 65_536
_MAX_REQUEST_AGE_MS: Final = 300_000
_MAX_FUTURE_SKEW_MS: Final = 30_000
_MAX_WINDOW_MS: Final = 240 * 60_000
_REQUEST_ID_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_SOURCE_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")


class MintStateAcceptanceControlError(RuntimeError):
    """Raised when a mint-state acceptance control exchange is unsafe."""


def process_pending_mint_state_acceptance_requests(
    *,
    marker_directory: Path = Path("/dev/shm"),
    database_path: Path | None = None,
    manifest_path: Path | None = None,
    current_release_link: Path = Path("/opt/shreks/current"),
    expected_owner_uid: int | None = None,
    expected_marker_directory_owner_uid: int = 0,
    evidence_cycle_interval_ms: int | None = None,
    now_unix_ms: int | None = None,
    max_requests: int = 4,
) -> tuple[dict[str, object], ...]:
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests < 1:
        raise ValueError("max_requests must be a positive integer")
    now_ms = int(time.time() * 1000) if now_unix_ms is None else now_unix_ms
    if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
        raise ValueError("now_unix_ms must be a non-negative integer")
    directory = _resolve_marker_directory(
        Path(marker_directory),
        expected_owner_uid=expected_marker_directory_owner_uid,
    )
    if directory is None:
        return ()
    try:
        markers = tuple(
            sorted(
                path
                for path in directory.iterdir()
                if path.name.startswith(_MARKER_PREFIX)
                and path.name.endswith(_MARKER_SUFFIX)
            )
        )[:max_requests]
    except OSError:
        return ()
    if not markers:
        return ()

    resolved_database_path = database_path
    resolved_manifest_path = manifest_path
    if resolved_database_path is None or resolved_manifest_path is None:
        try:
            runtime_config = load_observer_paper_campaign_runtime_config()
        except ObserverPaperCampaignRuntimeConfigError as error:
            raise MintStateAcceptanceControlError(
                "PAPER campaign runtime authority is unavailable"
            ) from error
        if resolved_database_path is None:
            resolved_database_path = runtime_config.observer_database_path
        if resolved_manifest_path is None:
            resolved_manifest_path = runtime_config.manifest_path

    interval_ms = (
        _evidence_cycle_interval_ms_from_environment()
        if evidence_cycle_interval_ms is None
        else evidence_cycle_interval_ms
    )
    if (
        isinstance(interval_ms, bool)
        or not isinstance(interval_ms, int)
        or interval_ms <= 0
    ):
        raise ValueError("evidence_cycle_interval_ms must be positive")

    owner_uid = (
        pwd.getpwnam("shreks-deploy").pw_uid
        if expected_owner_uid is None
        else expected_owner_uid
    )
    if isinstance(owner_uid, bool) or not isinstance(owner_uid, int) or owner_uid < 0:
        raise ValueError("expected_owner_uid must be a non-negative integer")

    return tuple(
        _process_one_request(
            path,
            database_path=Path(resolved_database_path),
            manifest_path=Path(resolved_manifest_path),
            current_release_link=Path(current_release_link),
            expected_owner_uid=owner_uid,
            evidence_cycle_interval_ms=interval_ms,
            now_unix_ms=now_ms,
        )
        for path in markers
    )


def publish_mint_state_acceptance_control_result(
    result: dict[str, object],
    *,
    marker_directory: Path = Path("/dev/shm"),
    expected_exchange_owner_uid: int | None = None,
) -> bool:
    request_id = result.get("request_id")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        return False
    exchange_owner_uid = (
        pwd.getpwnam("shreks-deploy").pw_uid
        if expected_exchange_owner_uid is None
        else expected_exchange_owner_uid
    )
    if (
        isinstance(exchange_owner_uid, bool)
        or not isinstance(exchange_owner_uid, int)
        or exchange_owner_uid < 0
    ):
        raise ValueError("expected_exchange_owner_uid must be non-negative")

    exchange = (
        Path(marker_directory)
        / f"{_MARKER_PREFIX}{request_id}{_RESULT_EXCHANGE_SUFFIX}"
    )
    try:
        metadata = exchange.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise MintStateAcceptanceControlError(
            "result exchange could not be inspected"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MintStateAcceptanceControlError(
            "result exchange must be a real directory"
        )
    if metadata.st_uid != exchange_owner_uid:
        raise MintStateAcceptanceControlError(
            "result exchange owner is untrusted"
        )
    if stat.S_IMODE(metadata.st_mode) != _RESULT_EXCHANGE_MODE:
        raise MintStateAcceptanceControlError(
            "result exchange mode must be 0733"
        )

    payload = (_canonical_json(result) + "\n").encode("utf-8")
    if len(payload) > _MAX_RESULT_BYTES:
        raise MintStateAcceptanceControlError(
            "acceptance result exceeds size bound"
        )
    destination = exchange / _RESULT_FILENAME
    if destination.exists() or destination.is_symlink():
        existing = _read_exchange_result(
            destination,
            expected_owner_uid=os.getuid(),
        )
        if existing != payload:
            raise MintStateAcceptanceControlError(
                "existing acceptance result conflicts"
            )
        return True

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(destination, flags, 0o600)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError("short write")
                offset += written
            os.fsync(fd)
            os.fchmod(fd, _RESULT_FILE_MODE)
        finally:
            os.close(fd)
    except OSError as error:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise MintStateAcceptanceControlError(
            "acceptance result could not be published safely"
        ) from error

    if _read_exchange_result(
        destination,
        expected_owner_uid=os.getuid(),
    ) != payload:
        raise MintStateAcceptanceControlError(
            "published acceptance result verification failed"
        )
    return True


def emit_mint_state_acceptance_control_result(
    result: dict[str, object],
    *,
    stream=None,
) -> None:
    import sys

    target = sys.stdout if stream is None else stream
    print(_canonical_json(result), file=target)


def _process_one_request(
    marker_path: Path,
    *,
    database_path: Path,
    manifest_path: Path,
    current_release_link: Path,
    expected_owner_uid: int,
    evidence_cycle_interval_ms: int,
    now_unix_ms: int,
) -> dict[str, object]:
    fallback_id = _request_id_from_name(marker_path.name)
    try:
        request = _read_request(
            marker_path,
            expected_owner_uid=expected_owner_uid,
        )
    except MintStateAcceptanceControlError:
        return _failure_result(
            request_id=fallback_id,
            expected_release_sha=None,
            observed_release_sha=None,
            error_code="UNTRUSTED_MARKER",
            message="mint-state acceptance request is untrusted",
        )

    request_id = request["request_id"]
    expected_release_sha = request["expected_release_sha"]
    try:
        observed_release_sha = _require_current_release_binding(
            current_release_link,
            expected_release_sha,
        )
    except DiscoveryControlError:
        return _failure_result(
            request_id=request_id,
            expected_release_sha=expected_release_sha,
            observed_release_sha=None,
            error_code="RELEASE_BINDING_FAILED",
            message="mint-state acceptance release binding failed",
        )

    created_at = request["created_at_unix_ms"]
    if created_at < now_unix_ms - _MAX_REQUEST_AGE_MS:
        return _failure_result(
            request_id=request_id,
            expected_release_sha=expected_release_sha,
            observed_release_sha=observed_release_sha,
            error_code="STALE_REQUEST",
            message="mint-state acceptance request is stale",
        )
    if created_at > now_unix_ms + _MAX_FUTURE_SKEW_MS:
        return _failure_result(
            request_id=request_id,
            expected_release_sha=expected_release_sha,
            observed_release_sha=observed_release_sha,
            error_code="FUTURE_REQUEST",
            message="mint-state acceptance request is future-dated",
        )

    try:
        analysis = analyze_mint_state_acceptance(
            database_path,
            manifest_path,
            window_start_unix_ms=request["window_start_unix_ms"],
            window_end_unix_ms=request["window_end_unix_ms"],
            evidence_cycle_interval_ms=evidence_cycle_interval_ms,
        )
    except (MintStateAcceptanceError, OSError, TypeError, ValueError):
        return _failure_result(
            request_id=request_id,
            expected_release_sha=expected_release_sha,
            observed_release_sha=observed_release_sha,
            error_code="ANALYSIS_FAILED",
            message="mint-state acceptance analysis failed closed",
        )

    return {
        "schema_name": CONTROL_RESULT_SCHEMA_NAME,
        "schema_version": CONTROL_RESULT_SCHEMA_VERSION,
        "request_id": request_id,
        "expected_release_sha": expected_release_sha,
        "observed_release_sha": observed_release_sha,
        "status": analysis["status"],
        "analysis": analysis,
        "observation_authority": "READ_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }


def _read_request(
    path: Path,
    *,
    expected_owner_uid: int,
) -> dict[str, object]:
    request_id_from_name = _request_id_from_name(path.name)
    if request_id_from_name is None:
        raise MintStateAcceptanceControlError("invalid marker filename")
    try:
        before = path.lstat()
    except OSError as error:
        raise MintStateAcceptanceControlError(
            "marker could not be inspected"
        ) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise MintStateAcceptanceControlError(
            "marker must be a regular non-symlink file"
        )
    if before.st_uid != expected_owner_uid:
        raise MintStateAcceptanceControlError("marker owner is untrusted")
    if stat.S_IMODE(before.st_mode) != 0o644:
        raise MintStateAcceptanceControlError("marker mode must be 0644")
    if before.st_size < 2 or before.st_size > _MAX_MARKER_BYTES:
        raise MintStateAcceptanceControlError("marker size is invalid")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            payload = os.read(fd, _MAX_MARKER_BYTES + 1)
            after = os.fstat(fd)
        finally:
            os.close(fd)
    except OSError as error:
        raise MintStateAcceptanceControlError(
            "marker could not be read safely"
        ) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    if identity != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ) or identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise MintStateAcceptanceControlError(
            "marker changed while being read"
        )
    if len(payload) != before.st_size:
        raise MintStateAcceptanceControlError(
            "marker size changed while being read"
        )
    try:
        text = payload.decode("utf-8")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MintStateAcceptanceControlError(
            "marker JSON is invalid"
        ) from error
    if not isinstance(document, dict):
        raise MintStateAcceptanceControlError(
            "marker must contain one object"
        )
    required = {
        "schema_name",
        "schema_version",
        "request_id",
        "expected_release_sha",
        "created_at_unix_ms",
        "window_start_unix_ms",
        "window_end_unix_ms",
    }
    if set(document) != required:
        raise MintStateAcceptanceControlError(
            "marker keys do not match schema"
        )
    if text != _canonical_json(document) + "\n":
        raise MintStateAcceptanceControlError(
            "marker JSON is not canonical"
        )
    if document["schema_name"] != CONTROL_REQUEST_SCHEMA_NAME:
        raise MintStateAcceptanceControlError(
            "marker schema_name is unsupported"
        )
    if document["schema_version"] != CONTROL_REQUEST_SCHEMA_VERSION:
        raise MintStateAcceptanceControlError(
            "marker schema_version is unsupported"
        )
    request_id = document["request_id"]
    if (
        not isinstance(request_id, str)
        or _REQUEST_ID_RE.fullmatch(request_id) is None
        or request_id != request_id_from_name
    ):
        raise MintStateAcceptanceControlError(
            "marker request_id is invalid"
        )
    source_sha = document["expected_release_sha"]
    if (
        not isinstance(source_sha, str)
        or _SOURCE_SHA_RE.fullmatch(source_sha) is None
    ):
        raise MintStateAcceptanceControlError(
            "expected release SHA is invalid"
        )
    for key in (
        "created_at_unix_ms",
        "window_start_unix_ms",
        "window_end_unix_ms",
    ):
        value = document[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MintStateAcceptanceControlError(
                f"{key} must be a non-negative integer"
            )
    if document["window_end_unix_ms"] < document["window_start_unix_ms"]:
        raise MintStateAcceptanceControlError(
            "acceptance window is reversed"
        )
    if (
        document["window_end_unix_ms"] - document["window_start_unix_ms"]
        > _MAX_WINDOW_MS
    ):
        raise MintStateAcceptanceControlError(
            "acceptance window exceeds maximum"
        )
    if document["window_end_unix_ms"] > document["created_at_unix_ms"]:
        raise MintStateAcceptanceControlError(
            "acceptance window ends after request creation"
        )
    return document


def _request_id_from_name(name: str) -> str | None:
    if not name.startswith(_MARKER_PREFIX) or not name.endswith(_MARKER_SUFFIX):
        return None
    value = name[len(_MARKER_PREFIX) : -len(_MARKER_SUFFIX)]
    if _REQUEST_ID_RE.fullmatch(value) is None:
        return None
    return value


def _evidence_cycle_interval_ms_from_environment() -> int:
    raw = os.environ.get("SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS")
    if raw is None or re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise MintStateAcceptanceControlError(
            "PAPER evidence interval is unavailable"
        )
    seconds = int(raw)
    if seconds > (2**63 - 1) // 1000:
        raise MintStateAcceptanceControlError(
            "PAPER evidence interval is too large"
        )
    return seconds * 1000


def _failure_result(
    *,
    request_id: str | None,
    expected_release_sha: str | None,
    observed_release_sha: str | None,
    error_code: str,
    message: str,
) -> dict[str, object]:
    return {
        "schema_name": CONTROL_RESULT_SCHEMA_NAME,
        "schema_version": CONTROL_RESULT_SCHEMA_VERSION,
        "request_id": request_id,
        "expected_release_sha": expected_release_sha,
        "observed_release_sha": observed_release_sha,
        "status": "FAILED",
        "error": {
            "code": error_code,
            "message": message,
        },
        "observation_authority": "READ_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
