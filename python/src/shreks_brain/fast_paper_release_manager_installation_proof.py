from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Callable
import zipfile

from shreks_brain import g1c_v2_paper_manifest_manager_install as release_material


_SCHEMA_NAME = "shreks.fast_paper_release_manager_installation_proof"
_SCHEMA_VERSION = 1
_MANAGER_MEMBER = (
    "shreks_brain/_sealed_deploy_control/release_manager.py"
)
_BUNDLE_MEMBER = (
    "shreks_brain/_sealed_deploy_control/release_bundle.py"
)
_MANAGER_DESTINATION = Path("/usr/local/sbin/shreks-release-manager")
_BUNDLE_DESTINATION = Path("/usr/local/sbin/release_bundle.py")
_SUDOERS_PATH = Path("/etc/sudoers.d/shreks-release-manager")
_SUDOERS_LINE = (
    "shreks-deploy ALL=(root) NOPASSWD: "
    "/usr/local/sbin/shreks-release-manager install "
    "/var/tmp/shreks-release-*.tar.gz "
    "/var/tmp/shreks-release-*.tar.gz.sha256 "
    "/var/tmp/shreks-release-*.RELEASE_MANIFEST.json"
)
_ROOT_UID = 0
_ROOT_GID = 0
_EXECUTABLE_MODE = 0o755
_SUDOERS_MODE = 0o440
_RECEIPT_MODE = 0o600
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


class FastPaperReleaseManagerInstallationProofError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class InstallationProofPaths:
    current_link: Path
    manager_destination: Path
    bundle_destination: Path
    deploy_sudoers: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "manager_destination",
            "bundle_destination",
            "deploy_sudoers",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise FastPaperReleaseManagerInstallationProofError(
                    f"{name} must be an absolute Path"
                )


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]


def refresh_and_prove_fast_aware_release_manager(
    *,
    expected_release_source_sha: str,
    paths: InstallationProofPaths,
    receipt_path: str | Path,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root()
    expected_sha = release_material._validate_source_sha(
        expected_release_source_sha
    )
    runner = _default_runner if command_runner is None else command_runner
    receipt = Path(receipt_path).expanduser()
    _require_receipt_path(receipt)

    material = _release_material(
        expected_sha=expected_sha,
        paths=paths,
        runtime_executable=runtime_executable,
    )
    before_manager, before_manager_stat = release_material._read_regular_no_follow(
        paths.manager_destination,
        label="installed root release manager",
    )
    _require_executable_metadata(
        before_manager_stat,
        "installed root release manager",
    )
    if not before_manager.startswith(b"#!/usr/bin/env python3\n"):
        raise FastPaperReleaseManagerInstallationProofError(
            "installed root release manager is not the expected executable shape"
        )

    bundle_payload, bundle_stat = release_material._read_regular_no_follow(
        paths.bundle_destination,
        label="installed root release bundle companion",
    )
    _require_executable_metadata(
        bundle_stat,
        "installed root release bundle companion",
    )
    if bundle_payload != material["bundle_payload"]:
        raise FastPaperReleaseManagerInstallationProofError(
            "installed root release_bundle.py does not match exact sealed release"
        )

    sudoers_before = _sudoers_observation(paths.deploy_sudoers)
    services_before = _service_observations(runner)
    release_before = release_material._require_current_release(
        paths.current_link,
        expected_sha,
    )
    if release_before != material["release_directory_path"]:
        raise FastPaperReleaseManagerInstallationProofError(
            "current release changed before release-manager refresh"
        )

    target_manager = material["manager_payload"]
    target_manager_sha256 = material["manager_sha256"]
    old_manager_sha256 = hashlib.sha256(before_manager).hexdigest()
    replaced = old_manager_sha256 != target_manager_sha256

    if replaced:
        _replace_exact_existing(
            destination=paths.manager_destination,
            old_payload=before_manager,
            new_payload=target_manager,
        )

    try:
        release_after = release_material._require_current_release(
            paths.current_link,
            expected_sha,
        )
        if release_after != material["release_directory_path"]:
            raise FastPaperReleaseManagerInstallationProofError(
                "current release changed during release-manager refresh"
            )
        installed_manager, installed_stat = (
            release_material._read_regular_no_follow(
                paths.manager_destination,
                label="installed root release manager",
            )
        )
        _require_executable_metadata(
            installed_stat,
            "installed root release manager",
        )
        if installed_manager != target_manager:
            raise FastPaperReleaseManagerInstallationProofError(
                "installed release manager does not match exact sealed bytes"
            )
        installed_bundle, installed_bundle_stat = (
            release_material._read_regular_no_follow(
                paths.bundle_destination,
                label="installed root release bundle companion",
            )
        )
        _require_executable_metadata(
            installed_bundle_stat,
            "installed root release bundle companion",
        )
        if installed_bundle != material["bundle_payload"]:
            raise FastPaperReleaseManagerInstallationProofError(
                "installed release_bundle.py changed during release-manager refresh"
            )
        sudoers_after = _sudoers_observation(paths.deploy_sudoers)
        if sudoers_after != sudoers_before:
            raise FastPaperReleaseManagerInstallationProofError(
                "deployment sudoers changed during release-manager refresh"
            )
        services_after = _service_observations(runner)
        if services_after != services_before:
            raise FastPaperReleaseManagerInstallationProofError(
                "runtime service lifecycle changed during release-manager refresh"
            )
    except Exception as error:
        if replaced:
            try:
                _replace_exact_existing(
                    destination=paths.manager_destination,
                    old_payload=target_manager,
                    new_payload=before_manager,
                )
                restored, restored_stat = (
                    release_material._read_regular_no_follow(
                        paths.manager_destination,
                        label="restored root release manager",
                    )
                )
                _require_executable_metadata(
                    restored_stat,
                    "restored root release manager",
                )
                if restored != before_manager:
                    raise FastPaperReleaseManagerInstallationProofError(
                        "release-manager rollback bytes mismatch"
                    )
            except Exception as rollback_error:
                raise FastPaperReleaseManagerInstallationProofError(
                    "release-manager refresh failed and rollback failed"
                ) from rollback_error
        if isinstance(
            error,
            FastPaperReleaseManagerInstallationProofError,
        ):
            raise
        raise FastPaperReleaseManagerInstallationProofError(
            "release-manager refresh failed; prior helper restored"
        ) from error

    document: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": "VERIFIED",
        "release_source_sha": expected_sha,
        "release_directory": str(material["release_directory_path"]),
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "release_manager_wheel_member": _MANAGER_MEMBER,
        "release_manager_sha256": target_manager_sha256,
        "prior_release_manager_sha256": old_manager_sha256,
        "release_manager_replaced": replaced,
        "release_manager_destination": str(paths.manager_destination),
        "release_bundle_wheel_member": _BUNDLE_MEMBER,
        "release_bundle_sha256": material["bundle_sha256"],
        "release_bundle_destination": str(paths.bundle_destination),
        "deploy_sudoers_sha256": sudoers_after["sha256"],
        "deploy_sudoers_exact_rule": True,
        "service_lifecycle_unchanged": True,
        "installation_authority": (
            "EXERCISED_EXACT_RELEASE_BOUND_FAST_AWARE_MANAGER_ONLY"
            if replaced
            else "PROVEN_EXACT_RELEASE_BOUND_FAST_AWARE_MANAGER_ONLY"
        ),
        "physical_cutover_authority": "NOT_EXERCISED",
        "paper_execution_authority": "UNCHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    document["proof_fingerprint_sha256"] = _fingerprint(document)
    _write_receipt_no_replace(receipt, document)
    return document


def _release_material(
    *,
    expected_sha: str,
    paths: InstallationProofPaths,
    runtime_executable: str | os.PathLike[str] | None,
) -> dict[str, object]:
    release_dir = release_material._require_current_release(
        paths.current_link,
        expected_sha,
    )
    release_material._require_release_runtime_executable(
        release_dir,
        Path(
            sys.executable
            if runtime_executable is None
            else runtime_executable
        ),
    )
    manifest_payload, _ = release_material._read_regular_no_follow(
        release_dir / "RELEASE_MANIFEST.json",
        label="current release manifest",
    )
    manifest = release_material._decode_release_manifest(
        manifest_payload
    )
    if manifest.source_sha != expected_sha:
        raise FastPaperReleaseManagerInstallationProofError(
            "current release manifest source SHA mismatch"
        )
    wheel_record = release_material._require_single_wheel_record(manifest)
    wheel_path = release_dir / wheel_record.path
    wheel_payload, _ = release_material._read_regular_no_follow(
        wheel_path,
        label="current release wheel",
    )
    if len(wheel_payload) != wheel_record.size:
        raise FastPaperReleaseManagerInstallationProofError(
            "release wheel size mismatch"
        )
    wheel_sha256 = hashlib.sha256(wheel_payload).hexdigest()
    if wheel_sha256 != wheel_record.sha256:
        raise FastPaperReleaseManagerInstallationProofError(
            "release wheel SHA-256 mismatch"
        )
    manager_payload = _extract_unique_wheel_member(
        wheel_payload,
        _MANAGER_MEMBER,
        label="sealed release manager",
    )
    bundle_payload = _extract_unique_wheel_member(
        wheel_payload,
        _BUNDLE_MEMBER,
        label="sealed release bundle companion",
    )
    if not manager_payload.startswith(b"#!/usr/bin/env python3\n"):
        raise FastPaperReleaseManagerInstallationProofError(
            "sealed release manager has unexpected executable shape"
        )
    if not bundle_payload.startswith(b"#!/usr/bin/env python3\n"):
        raise FastPaperReleaseManagerInstallationProofError(
            "sealed release bundle companion has unexpected executable shape"
        )
    return {
        "release_directory_path": release_dir,
        "wheel_relative_path": wheel_record.path,
        "wheel_sha256": wheel_sha256,
        "manager_payload": manager_payload,
        "manager_sha256": hashlib.sha256(manager_payload).hexdigest(),
        "bundle_payload": bundle_payload,
        "bundle_sha256": hashlib.sha256(bundle_payload).hexdigest(),
    }


def _extract_unique_wheel_member(
    wheel_payload: bytes,
    member: str,
    *,
    label: str,
) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_payload), "r") as archive:
            matches = tuple(
                info
                for info in archive.infolist()
                if info.filename == member
            )
            if len(matches) != 1:
                raise FastPaperReleaseManagerInstallationProofError(
                    f"release wheel must contain exactly one {label}"
                )
            info = matches[0]
            if info.is_dir() or (info.flag_bits & 0x1):
                raise FastPaperReleaseManagerInstallationProofError(
                    f"{label} wheel member is unsafe"
                )
            return archive.read(info)
    except FastPaperReleaseManagerInstallationProofError:
        raise
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise FastPaperReleaseManagerInstallationProofError(
            "release wheel could not be read safely"
        ) from exc


def _sudoers_observation(path: Path) -> dict[str, object]:
    payload, metadata = release_material._read_regular_no_follow(
        path,
        label="deployment sudoers",
    )
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != _SUDOERS_MODE
    ):
        raise FastPaperReleaseManagerInstallationProofError(
            "deployment sudoers metadata is not root:root 0440"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastPaperReleaseManagerInstallationProofError(
            "deployment sudoers is not UTF-8"
        ) from exc
    effective = tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if effective != (_SUDOERS_LINE,):
        raise FastPaperReleaseManagerInstallationProofError(
            "deployment sudoers authority is not the exact historical command"
        )
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "mode": "0440",
    }


def _service_observations(
    runner: CommandRunner,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    values = []
    for unit in _UNITS:
        result = runner(
            (
                "systemctl",
                "show",
                unit,
                "--property=" + ",".join(_PROPERTIES),
                "--no-pager",
            )
        )
        if result.returncode != 0 or result.stderr.strip():
            raise FastPaperReleaseManagerInstallationProofError(
                f"unable to inspect runtime service: {unit}"
            )
        fields: dict[str, str] = {}
        for raw in result.stdout.splitlines():
            if not raw:
                continue
            if "=" not in raw:
                raise FastPaperReleaseManagerInstallationProofError(
                    "systemd observation is malformed"
                )
            key, value = raw.split("=", 1)
            if key in fields:
                raise FastPaperReleaseManagerInstallationProofError(
                    "systemd observation contains duplicate fields"
                )
            fields[key] = value
        if set(fields) != set(_PROPERTIES):
            raise FastPaperReleaseManagerInstallationProofError(
                "systemd observation has unknown or missing fields"
            )
        values.append((unit, tuple(sorted(fields.items()))))
    return tuple(values)


def _replace_exact_existing(
    *,
    destination: Path,
    old_payload: bytes,
    new_payload: bytes,
) -> None:
    _require_safe_parent(destination.parent)
    observed, metadata = release_material._read_regular_no_follow(
        destination,
        label="installed root release manager",
    )
    _require_executable_metadata(
        metadata,
        "installed root release manager",
    )
    if observed != old_payload:
        raise FastPaperReleaseManagerInstallationProofError(
            "installed release manager changed before replacement"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.refresh-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(new_payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), _ROOT_UID, _ROOT_GID)
            os.fchmod(handle.fileno(), _EXECUTABLE_MODE)
            os.fsync(handle.fileno())
        observed_again, metadata_again = (
            release_material._read_regular_no_follow(
                destination,
                label="installed root release manager",
            )
        )
        _require_executable_metadata(
            metadata_again,
            "installed root release manager",
        )
        if observed_again != old_payload:
            raise FastPaperReleaseManagerInstallationProofError(
                "installed release manager changed during replacement"
            )
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _require_executable_metadata(
    metadata: os.stat_result,
    label: str,
) -> None:
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != _EXECUTABLE_MODE
    ):
        raise FastPaperReleaseManagerInstallationProofError(
            f"{label} metadata is not root:root 0755"
        )


def _require_safe_parent(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise FastPaperReleaseManagerInstallationProofError(
            "release-manager destination parent is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise FastPaperReleaseManagerInstallationProofError(
            "release-manager destination parent metadata is unsafe"
        )


def _require_receipt_path(path: Path) -> None:
    if not path.is_absolute():
        raise FastPaperReleaseManagerInstallationProofError(
            "installation proof receipt path must be absolute"
        )
    if path.exists() or path.is_symlink():
        raise FastPaperReleaseManagerInstallationProofError(
            "installation proof receipt path must not already exist"
        )
    _require_safe_parent(path.parent)


def _write_receipt_no_replace(
    path: Path,
    document: dict[str, object],
) -> None:
    payload = (_canonical(document) + "\n").encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        _RECEIPT_MODE,
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


def _fingerprint(document: dict[str, object]) -> str:
    material = dict(document)
    material.pop("proof_fingerprint_sha256", None)
    return hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperReleaseManagerInstallationProofError(
            "Fast-aware release-manager installation proof requires root"
        )


def _default_runner(command: tuple[str, ...]) -> HostCommandResult:
    if (
        len(command) != 5
        or command[0:2] != ("systemctl", "show")
        or command[2] not in _UNITS
        or not command[3].startswith("--property=")
        or command[4] != "--no-pager"
    ):
        raise FastPaperReleaseManagerInstallationProofError(
            "installation proof command is outside the read-only allowlist"
        )
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise FastPaperReleaseManagerInstallationProofError(
            "installation proof host command failed"
        ) from exc
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _production_paths() -> InstallationProofPaths:
    return InstallationProofPaths(
        current_link=Path("/opt/shreks/current"),
        manager_destination=_MANAGER_DESTINATION,
        bundle_destination=_BUNDLE_DESTINATION,
        deploy_sudoers=_SUDOERS_PATH,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-release-manager-install-proof"
    )
    parser.add_argument("expected_release_source_sha")
    parser.add_argument("--receipt-path", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(
        sys.argv[1:] if argv is None else argv
    )
    try:
        result = refresh_and_prove_fast_aware_release_manager(
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
            receipt_path=args.receipt_path,
        )
    except Exception as exc:
        print(
            _canonical(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "installation_authority": "NOT_EXERCISED",
                    "physical_cutover_authority": "NOT_EXERCISED",
                    "paper_execution_authority": "UNCHANGED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
