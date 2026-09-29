from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Callable
import zipfile

from shreks_brain import g1c_v2_paper_manifest_manager_install as release_install


_SCHEMA_NAME = "shreks.fast_paper_root_release_manager_refresh"
_SCHEMA_VERSION = 1
_ROOT_UID = 0
_ROOT_GID = 0
_MANAGER_MEMBER = "shreks_brain/_sealed_deploy_control/release_manager.py"
_BUNDLE_MEMBER = "shreks_brain/_sealed_deploy_control/release_bundle.py"
_SUDOERS_LINE = (
    "shreks-deploy ALL=(root) NOPASSWD: "
    "/usr/local/sbin/shreks-release-manager install "
    "/var/tmp/shreks-release-*.tar.gz "
    "/var/tmp/shreks-release-*.tar.gz.sha256 "
    "/var/tmp/shreks-release-*.RELEASE_MANIFEST.json"
)
_UNITS = (
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
)
_PROPERTIES = (
    "ActiveState",
    "SubState",
    "NRestarts",
    "MainPID",
    "ExecMainStatus",
    "ActiveEnterTimestampMonotonic",
)
_REQUIRED_MANAGER_MARKERS = (
    b"activate_fast_release",
    b"shreks_brain.fast_paper_release_upgrade",
    b"legacy release activation is blocked after Fast PAPER cutover",
)


class FastPaperRootReleaseManagerRefreshError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RefreshPaths:
    current_link: Path
    deploy_sudoers: Path
    release_bundle_destination: Path
    release_manager_destination: Path
    receipt_root: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "deploy_sudoers",
            "release_bundle_destination",
            "release_manager_destination",
            "receipt_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]


def preflight_fast_paper_root_release_manager_refresh(
    *,
    expected_release_source_sha: str,
    paths: RefreshPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root(paths)
    material = _release_material(
        expected_release_source_sha,
        paths,
        runtime_executable,
    )
    _require_root_control_file(
        paths.release_bundle_destination,
        expected_payload=material["release_bundle_payload"],
        label="installed release bundle verifier",
    )
    installed_manager, metadata = _read_root_control_file(
        paths.release_manager_destination,
        label="installed release manager",
    )
    sudoers = _sudoers_observation(paths.deploy_sudoers)
    runner = _default_runner if command_runner is None else command_runner
    services = _service_observations(runner)
    manager_exact = installed_manager == material["release_manager_payload"]
    document = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": (
            "ALREADY_EXACT"
            if manager_exact
            else "READY_TO_REFRESH"
        ),
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "release_manager_sha256": material["release_manager_sha256"],
        "release_bundle_sha256": material["release_bundle_sha256"],
        "installed_manager_sha256": hashlib.sha256(
            installed_manager
        ).hexdigest(),
        "installed_manager_uid": metadata.st_uid,
        "installed_manager_gid": metadata.st_gid,
        "installed_manager_mode": "0755",
        "deploy_sudoers_sha256": sudoers["sha256"],
        "service_state_fingerprint_sha256": _service_fingerprint(services),
        "installation_authority": "NOT_EXERCISED",
        "sudo_authority_change": "FORBIDDEN",
        "service_control_authority": "READ_ONLY",
        "production_paper_cutover": "NOT_CHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize(document)


def install_fast_paper_root_release_manager_refresh(
    *,
    expected_release_source_sha: str,
    paths: RefreshPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root(paths)
    expected_sha = release_install._validate_source_sha(
        expected_release_source_sha
    )
    existing_receipt = _existing_receipt(paths, expected_sha)
    if existing_receipt is not None:
        material = _release_material(
            expected_sha,
            paths,
            runtime_executable,
        )
        _require_existing_receipt(
            existing_receipt,
            material=material,
            paths=paths,
        )
        _require_root_control_file(
            paths.release_bundle_destination,
            expected_payload=material["release_bundle_payload"],
            label="installed release bundle verifier",
        )
        _require_root_control_file(
            paths.release_manager_destination,
            expected_payload=material["release_manager_payload"],
            label="installed release manager",
        )
        _sudoers_observation(paths.deploy_sudoers)
        return existing_receipt

    material = _release_material(
        expected_sha,
        paths,
        runtime_executable,
    )
    _require_root_control_file(
        paths.release_bundle_destination,
        expected_payload=material["release_bundle_payload"],
        label="installed release bundle verifier",
    )
    prior_manager, prior_meta = _read_root_control_file(
        paths.release_manager_destination,
        label="installed release manager",
    )
    before_sudoers = _sudoers_observation(paths.deploy_sudoers)
    runner = _default_runner if command_runner is None else command_runner
    before_services = _service_observations(runner)

    changed = prior_manager != material["release_manager_payload"]
    if changed:
        _replace_root_control_file(
            paths.release_manager_destination,
            material["release_manager_payload"],
        )

    try:
        _require_root_control_file(
            paths.release_manager_destination,
            expected_payload=material["release_manager_payload"],
            label="installed release manager",
        )
        after_sudoers = _sudoers_observation(paths.deploy_sudoers)
        if after_sudoers != before_sudoers:
            raise FastPaperRootReleaseManagerRefreshError(
                "deployment sudoers changed during root release-manager refresh"
            )
        after_services = _service_observations(runner)
        if after_services != before_services:
            raise FastPaperRootReleaseManagerRefreshError(
                "runtime service lifecycle changed during root release-manager refresh"
            )
    except Exception as exc:
        if changed:
            try:
                _replace_file_atomically(
                    paths.release_manager_destination,
                    prior_manager,
                    uid=prior_meta.st_uid,
                    gid=prior_meta.st_gid,
                    mode=stat.S_IMODE(prior_meta.st_mode),
                )
            except Exception as rollback_exc:
                raise FastPaperRootReleaseManagerRefreshError(
                    "root release-manager refresh proof failed and rollback failed"
                ) from rollback_exc
        if isinstance(exc, FastPaperRootReleaseManagerRefreshError):
            raise
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh proof failed"
        ) from exc

    document = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": "REFRESHED" if changed else "ALREADY_EXACT",
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "release_manager_sha256": material["release_manager_sha256"],
        "release_bundle_sha256": material["release_bundle_sha256"],
        "manager_destination": str(paths.release_manager_destination),
        "release_bundle_destination": str(paths.release_bundle_destination),
        "destination_uid": _ROOT_UID,
        "destination_gid": _ROOT_GID,
        "destination_mode": "0755",
        "deploy_sudoers_sha256": before_sudoers["sha256"],
        "deploy_sudoers_unchanged": True,
        "service_state_fingerprint_sha256": _service_fingerprint(
            before_services
        ),
        "service_lifecycle_unchanged": True,
        "installation_authority": (
            "EXERCISED_EXACT_RELEASE_BOUND_DEPLOY_CONTROL_ONLY"
        ),
        "sudo_authority_change": "FORBIDDEN",
        "service_control_authority": "READ_ONLY",
        "production_paper_cutover": "NOT_CHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    receipt = _finalize(document)
    _write_receipt_no_replace(
        _receipt_path(paths, expected_sha),
        receipt,
    )
    return receipt


def _release_material(
    expected_sha: str,
    paths: RefreshPaths,
    runtime_executable: str | os.PathLike[str] | None,
) -> dict[str, object]:
    expected_sha = release_install._validate_source_sha(expected_sha)
    release_dir = release_install._require_current_release(
        paths.current_link,
        expected_sha,
    )
    executable = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    release_install._require_release_runtime_executable(
        release_dir,
        executable,
    )
    manifest_payload, _ = release_install._read_regular_no_follow(
        release_dir / "RELEASE_MANIFEST.json",
        label="current release manifest",
    )
    manifest = release_install._decode_release_manifest(manifest_payload)
    if manifest.source_sha != expected_sha:
        raise FastPaperRootReleaseManagerRefreshError(
            "current release manifest source SHA mismatch"
        )
    wheel_record = release_install._require_single_wheel_record(manifest)
    wheel_path = release_dir / wheel_record.path
    wheel_payload, _ = release_install._read_regular_no_follow(
        wheel_path,
        label="current release wheel",
    )
    if (
        len(wheel_payload) != wheel_record.size
        or hashlib.sha256(wheel_payload).hexdigest()
        != wheel_record.sha256
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            "current release wheel does not match release manifest"
        )
    manager, bundle = _sealed_control_payloads(wheel_path)
    for marker in _REQUIRED_MANAGER_MARKERS:
        if marker not in manager:
            raise FastPaperRootReleaseManagerRefreshError(
                "sealed release manager lacks Fast-aware dispatch marker"
            )
    return {
        "release_source_sha": expected_sha,
        "release_directory": str(release_dir),
        "wheel_relative_path": wheel_record.path,
        "wheel_sha256": wheel_record.sha256,
        "release_manager_sha256": hashlib.sha256(manager).hexdigest(),
        "release_bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "release_manager_payload": manager,
        "release_bundle_payload": bundle,
    }


def _sealed_control_payloads(wheel_path: Path) -> tuple[bytes, bytes]:
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            names = archive.namelist()
            if names.count(_MANAGER_MEMBER) != 1:
                raise FastPaperRootReleaseManagerRefreshError(
                    "sealed release wheel must contain one release-manager member"
                )
            if names.count(_BUNDLE_MEMBER) != 1:
                raise FastPaperRootReleaseManagerRefreshError(
                    "sealed release wheel must contain one release-bundle member"
                )
            return (
                archive.read(_MANAGER_MEMBER),
                archive.read(_BUNDLE_MEMBER),
            )
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise FastPaperRootReleaseManagerRefreshError(
            "sealed deployment-control wheel cannot be read"
        ) from exc


def _read_root_control_file(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, os.stat_result]:
    payload, metadata = release_install._read_regular_no_follow(
        path,
        label=label,
    )
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o755
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            f"{label} metadata must be root:root 0755"
        )
    return payload, metadata


def _require_root_control_file(
    path: Path,
    *,
    expected_payload: bytes,
    label: str,
) -> None:
    payload, _ = _read_root_control_file(path, label=label)
    if payload != expected_payload:
        raise FastPaperRootReleaseManagerRefreshError(
            f"{label} bytes do not match exact current sealed release"
        )


def _sudoers_observation(path: Path) -> dict[str, object]:
    payload, metadata = release_install._read_regular_no_follow(
        path,
        label="Shreks deployment sudoers",
    )
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o440
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            "deployment sudoers metadata must be root:root 0440"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastPaperRootReleaseManagerRefreshError(
            "deployment sudoers must be UTF-8"
        ) from exc
    lines = tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if lines != (_SUDOERS_LINE,):
        raise FastPaperRootReleaseManagerRefreshError(
            "deployment sudoers authority is not the exact narrow install command"
        )
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "mode": "0440",
    }


def _service_observations(
    runner: CommandRunner,
) -> tuple[dict[str, object], ...]:
    return tuple(
        sorted(
            (_service_observation(unit, runner) for unit in _UNITS),
            key=lambda item: str(item["unit"]),
        )
    )


def _service_observation(
    unit: str,
    runner: CommandRunner,
) -> dict[str, object]:
    result = runner(
        (
            "systemctl",
            "show",
            unit,
            "--property=" + ",".join(_PROPERTIES),
            "--no-pager",
        )
    )
    if (
        type(result) is not HostCommandResult
        or result.returncode != 0
        or result.stderr.strip()
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            f"could not inspect service state for {unit}"
        )
    fields = _key_values(result.stdout)
    if set(fields) != set(_PROPERTIES):
        raise FastPaperRootReleaseManagerRefreshError(
            f"service state fields are incomplete for {unit}"
        )
    numeric = {
        name: _non_negative_int(fields[name], name)
        for name in (
            "NRestarts",
            "MainPID",
            "ExecMainStatus",
            "ActiveEnterTimestampMonotonic",
        )
    }
    if (
        fields["ActiveState"] != "active"
        or fields["SubState"] != "running"
        or numeric["MainPID"] <= 0
        or numeric["ExecMainStatus"] != 0
        or numeric["ActiveEnterTimestampMonotonic"] <= 0
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            f"service is not healthy during root helper refresh: {unit}"
        )
    return {
        "unit": unit,
        "active_state": fields["ActiveState"],
        "sub_state": fields["SubState"],
        "n_restarts": numeric["NRestarts"],
        "main_pid": numeric["MainPID"],
        "exec_main_status": numeric["ExecMainStatus"],
        "active_enter_timestamp_monotonic": numeric[
            "ActiveEnterTimestampMonotonic"
        ],
    }


def _key_values(payload: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in payload.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise FastPaperRootReleaseManagerRefreshError(
                "service state output is malformed"
            )
        values[key] = value
    return values


def _non_negative_int(value: str, label: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise FastPaperRootReleaseManagerRefreshError(
            f"{label} is not an integer"
        ) from exc
    if parsed < 0:
        raise FastPaperRootReleaseManagerRefreshError(
            f"{label} must be non-negative"
        )
    return parsed


def _service_fingerprint(
    values: tuple[dict[str, object], ...],
) -> str:
    return hashlib.sha256(_canonical(values)).hexdigest()


def _replace_root_control_file(path: Path, payload: bytes) -> None:
    _replace_file_atomically(
        path,
        payload,
        uid=_ROOT_UID,
        gid=_ROOT_GID,
        mode=0o755,
    )


def _replace_file_atomically(
    destination: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> None:
    if destination.is_symlink():
        raise FastPaperRootReleaseManagerRefreshError(
            "root control destination must not be a symlink"
        )
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir():
        raise FastPaperRootReleaseManagerRefreshError(
            "root control destination parent is unsafe"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.refresh-",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), uid, gid)
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _require_root(paths: RefreshPaths) -> None:
    if type(paths) is not RefreshPaths:
        raise FastPaperRootReleaseManagerRefreshError(
            "paths must be exact RefreshPaths"
        )
    if os.geteuid() != 0:
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh requires root"
        )


def _production_paths() -> RefreshPaths:
    return RefreshPaths(
        current_link=Path("/opt/shreks/current"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        release_bundle_destination=Path(
            "/usr/local/sbin/release_bundle.py"
        ),
        release_manager_destination=Path(
            "/usr/local/sbin/shreks-release-manager"
        ),
        receipt_root=Path(
            "/root/shreks-fast-paper-release-manager-refresh"
        ),
    )


def _receipt_path(paths: RefreshPaths, release_sha: str) -> Path:
    return paths.receipt_root / f"refresh-{release_sha}.json"


def _existing_receipt(
    paths: RefreshPaths,
    release_sha: str,
) -> dict[str, object] | None:
    path = _receipt_path(paths, release_sha)
    if path.is_symlink():
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh receipt must not be a symlink"
        )
    if not path.exists():
        return None
    payload, metadata = release_install._read_regular_no_follow(
        path,
        label="root release-manager refresh receipt",
    )
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh receipt metadata is not exact"
        )
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh receipt is malformed"
        ) from exc
    if (
        not isinstance(document, dict)
        or payload != _canonical_line(document)
        or document.get("schema_name") != _SCHEMA_NAME
        or document.get("schema_version") != _SCHEMA_VERSION
        or document.get("receipt_fingerprint_sha256")
        != _fingerprint(document)
    ):
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh receipt is invalid"
        )
    return document


def _require_existing_receipt(
    receipt: dict[str, object],
    *,
    material: dict[str, object],
    paths: RefreshPaths,
) -> None:
    expected = {
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "release_manager_sha256": material["release_manager_sha256"],
        "release_bundle_sha256": material["release_bundle_sha256"],
        "manager_destination": str(paths.release_manager_destination),
        "release_bundle_destination": str(
            paths.release_bundle_destination
        ),
        "destination_uid": _ROOT_UID,
        "destination_gid": _ROOT_GID,
        "destination_mode": "0755",
        "deploy_sudoers_unchanged": True,
        "service_lifecycle_unchanged": True,
        "installation_authority": (
            "EXERCISED_EXACT_RELEASE_BOUND_DEPLOY_CONTROL_ONLY"
        ),
        "sudo_authority_change": "FORBIDDEN",
        "service_control_authority": "READ_ONLY",
        "production_paper_cutover": "NOT_CHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    for name, value in expected.items():
        if receipt.get(name) != value:
            raise FastPaperRootReleaseManagerRefreshError(
                f"existing root release-manager receipt mismatch: {name}"
            )


def _write_receipt_no_replace(
    path: Path,
    document: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists() or path.is_symlink():
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh receipt already exists"
        )
    payload = _canonical_line(document)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _finalize(document: dict[str, object]) -> dict[str, object]:
    return {
        **document,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(document)
        ).hexdigest(),
    }


def _fingerprint(document: dict[str, object]) -> str:
    material = dict(document)
    material.pop("receipt_fingerprint_sha256", None)
    return hashlib.sha256(_canonical(material)).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _reject_duplicates(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FastPaperRootReleaseManagerRefreshError(
                "JSON object contains duplicate keys"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise FastPaperRootReleaseManagerRefreshError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _default_runner(command: tuple[str, ...]) -> HostCommandResult:
    allowed = (
        len(command) == 5
        and command[0:2] == ("systemctl", "show")
        and command[2] in _UNITS
        and command[3] == "--property=" + ",".join(_PROPERTIES)
        and command[4] == "--no-pager"
    )
    if not allowed:
        raise FastPaperRootReleaseManagerRefreshError(
            "root release-manager refresh command is outside read-only allowlist"
        )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
    )
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-root-release-manager-refresh"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "install"):
        command = sub.add_parser(name)
        command.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(
        sys.argv[1:] if argv is None else argv
    )
    try:
        if args.command == "preflight":
            result = preflight_fast_paper_root_release_manager_refresh(
                expected_release_source_sha=args.expected_release_source_sha,
                paths=_production_paths(),
            )
        else:
            result = install_fast_paper_root_release_manager_refresh(
                expected_release_source_sha=args.expected_release_source_sha,
                paths=_production_paths(),
            )
    except Exception as exc:
        print(
            _canonical_line(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "sudo_authority_change": "FORBIDDEN",
                    "service_control_authority": "READ_ONLY",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ).decode("utf-8").rstrip(),
            file=sys.stderr,
        )
        return 1
    print(_canonical_line(result).decode("utf-8").rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
