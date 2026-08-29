#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
from typing import Callable
import uuid

from release_bundle import (
    ReleaseBundleError,
    ReleaseManifest,
    decode_release_manifest,
    validate_source_sha,
    verify_release_archive,
)


CommandRunner = Callable[[tuple[str, ...]], None]
RuntimeIdentity = tuple[int, Path, Path]
RuntimeIdentityReader = Callable[[str], RuntimeIdentity]

_SYSTEMD_UNIT_NAMES = (
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
    "shreks.target",
)
_RUNTIME_SERVICE_NAMES = (
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
)
_RUNTIME_STOP_ORDER = (
    "shreks-paper-campaign.service",
    "shreks-paper-evidence.service",
    "shreks-observe.service",
)
_NATIVE_RUNTIME_EXECUTABLES = {
    "shreks-observe.service": "target/release/shreks-observe",
    "shreks-paper-evidence.service": "target/release/shreks-paper-evidence",
}
_RUNTIME_BINARY_PATHS = (
    "target/release/shreks-observe",
    "target/release/shreks-paper-evidence",
)
_CONTROL_MANIFEST_PATH = "RELEASE_MANIFEST.json"
_HOST_PLATFORM_BY_MACHINE = {
    "x86_64": "x86_64-unknown-linux-gnu",
    "aarch64": "aarch64-unknown-linux-gnu",
}


class ReleaseManagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleasePaths:
    releases_dir: Path
    current_link: Path
    systemd_dir: Path


def _default_command_runner(command: tuple[str, ...]) -> None:
    subprocess.run(command, check=True)


def _default_runtime_identity_reader(unit_name: str) -> RuntimeIdentity:
    try:
        result = subprocess.run(
            ("systemctl", "show", unit_name, "-p", "MainPID", "--value"),
            check=True,
            capture_output=True,
            text=True,
        )
        pid = int(result.stdout.strip())
        if pid <= 0:
            raise ValueError("MainPID is not a running process")
        executable = Path(os.readlink(f"/proc/{pid}/exe"))
        cwd = Path(os.readlink(f"/proc/{pid}/cwd"))
        return pid, executable, cwd
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise ReleaseManagerError(
            f"unable to inspect runtime process for {unit_name}"
        ) from exc


def _host_release_platform() -> str:
    machine = os.uname().machine
    try:
        return _HOST_PLATFORM_BY_MACHINE[machine]
    except KeyError as exc:
        raise ReleaseManagerError(f"unsupported host architecture: {machine!r}") from exc


def _require_manifest_matches_host(manifest: ReleaseManifest) -> None:
    host_platform = _host_release_platform()
    if manifest.platform != host_platform:
        raise ReleaseManagerError(
            f"release platform {manifest.platform!r} does not match host platform {host_platform!r}"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path, context: str) -> ReleaseManifest:
    if path.is_symlink() or not path.is_file():
        raise ReleaseManagerError(f"{context} manifest is missing or not a regular file")
    try:
        return decode_release_manifest(path.read_bytes())
    except (OSError, ReleaseBundleError) as exc:
        raise ReleaseManagerError(f"{context} manifest verification failed") from exc


def _is_allowed_runtime_venv_symlink(venv_dir: Path, path: Path) -> bool:
    if path != venv_dir / "lib64":
        return False
    try:
        if os.readlink(path) != "lib":
            return False
    except OSError:
        return False
    lib_dir = venv_dir / "lib"
    return not lib_dir.is_symlink() and lib_dir.is_dir()


def _verify_runtime_venv(release_dir: Path) -> None:
    venv_dir = release_dir / ".venv"
    python = venv_dir / "bin" / "python"
    if venv_dir.is_symlink() or not venv_dir.is_dir():
        raise ReleaseManagerError("stored release virtualenv is missing or invalid")
    if python.is_symlink() or not python.is_file():
        raise ReleaseManagerError("stored release Python executable is missing or symlinked")

    for path in venv_dir.rglob("*"):
        if path.is_symlink() and not _is_allowed_runtime_venv_symlink(venv_dir, path):
            raise ReleaseManagerError("symlinks are not allowed inside stored release virtualenv")


def _verify_stored_release(release_dir: Path) -> ReleaseManifest:
    release_dir = Path(release_dir)
    if release_dir.is_symlink() or not release_dir.is_dir():
        raise ReleaseManagerError("stored release directory is missing or invalid")
    if stat.S_IMODE(release_dir.stat().st_mode) != 0o755:
        raise ReleaseManagerError("stored release directory permissions must be 0755")

    manifest = _load_manifest(release_dir / _CONTROL_MANIFEST_PATH, "stored release")
    _require_manifest_matches_host(manifest)
    if release_dir.name != manifest.source_sha:
        raise ReleaseManagerError("stored release directory does not match source SHA")

    expected = {entry.path: entry for entry in manifest.files}
    for relative, entry in expected.items():
        path = release_dir / relative
        if path.is_symlink() or not path.is_file():
            raise ReleaseManagerError(f"stored release payload missing: {relative}")
        if path.stat().st_size != entry.size or _sha256_file(path) != entry.sha256:
            raise ReleaseManagerError(f"stored release payload verification failed: {relative}")

    for path in release_dir.rglob("*"):
        relative = path.relative_to(release_dir).as_posix()
        if relative == _CONTROL_MANIFEST_PATH or relative in expected:
            continue
        if relative == ".venv" or relative.startswith(".venv/"):
            continue
        if path.is_dir() and not path.is_symlink():
            continue
        raise ReleaseManagerError(f"unexpected stored release file: {relative}")

    _verify_runtime_venv(release_dir)
    return manifest


def _extract_verified_archive(archive_path: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isreg():
                    raise ReleaseManagerError("verified archive contained a non-regular member")
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseManagerError("unable to read verified archive member")
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
                target.chmod(member.mode & 0o777)
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseManagerError("unable to extract verified release archive") from exc


def _find_wheel(release_dir: Path, manifest: ReleaseManifest) -> Path:
    wheels = [
        release_dir / entry.path
        for entry in manifest.files
        if entry.path.startswith("wheelhouse/") and entry.path.endswith(".whl")
    ]
    if len(wheels) != 1:
        raise ReleaseManagerError("stored release must contain exactly one Shreks wheel")
    return wheels[0]


def _load_staged_manifest(staging_dir: Path, expected_source_sha: str) -> ReleaseManifest:
    manifest = _load_manifest(staging_dir / _CONTROL_MANIFEST_PATH, "staged release")
    if manifest.source_sha != expected_source_sha:
        raise ReleaseManagerError("staged release source SHA mismatch")
    return manifest


def _verify_payloads_for_staging(staging_dir: Path, manifest: ReleaseManifest) -> None:
    expected = {entry.path: entry for entry in manifest.files}
    for relative, entry in expected.items():
        path = staging_dir / relative
        if path.is_symlink() or not path.is_file():
            raise ReleaseManagerError(f"staged payload missing: {relative}")
        if path.stat().st_size != entry.size or _sha256_file(path) != entry.sha256:
            raise ReleaseManagerError(f"staged payload verification failed: {relative}")

    actual = set()
    for path in staging_dir.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise ReleaseManagerError("staged release contains a non-regular file")
        actual.add(path.relative_to(staging_dir).as_posix())
    expected_with_control = set(expected) | {_CONTROL_MANIFEST_PATH}
    if actual != expected_with_control:
        raise ReleaseManagerError("staged release member set does not match manifest")


def _current_points_to(current_link: Path, release_dir: Path) -> bool:
    current_link = Path(current_link)
    if not current_link.is_symlink():
        return False
    try:
        return current_link.resolve(strict=False) == release_dir.resolve(strict=False)
    except OSError:
        return False


def _cleanup_incomplete_release(release_dir: Path, current_link: Path) -> None:
    if not release_dir.exists() and not release_dir.is_symlink():
        return
    if _current_points_to(current_link, release_dir):
        raise ReleaseManagerError("refusing to remove an incomplete release referenced by current")
    if release_dir.is_symlink():
        release_dir.unlink(missing_ok=True)
    else:
        shutil.rmtree(release_dir, ignore_errors=False)


def stage_release(
    archive_path: Path,
    checksum_path: Path,
    manifest_path: Path,
    paths: ReleasePaths,
    *,
    python_executable: str = "/usr/bin/python3",
    command_runner: CommandRunner = _default_command_runner,
) -> Path:
    try:
        manifest = verify_release_archive(archive_path, checksum_path, manifest_path)
    except (OSError, ReleaseBundleError) as exc:
        raise ReleaseManagerError("release bundle verification failed") from exc

    _require_manifest_matches_host(manifest)

    releases_dir = Path(paths.releases_dir)
    release_dir = releases_dir / manifest.source_sha
    releases_dir.mkdir(parents=True, exist_ok=True)
    releases_dir.chmod(0o755)

    if release_dir.exists() or release_dir.is_symlink():
        stored = _verify_stored_release(release_dir)
        if stored != manifest:
            raise ReleaseManagerError("existing release content does not match incoming manifest")
        return release_dir

    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".staging-{manifest.source_sha}-", dir=releases_dir)
    )
    payload_committed = False
    try:
        _extract_verified_archive(Path(archive_path), staging_dir)
        embedded = _load_staged_manifest(staging_dir, manifest.source_sha)
        if embedded != manifest:
            raise ReleaseManagerError("staged manifest does not match verified release manifest")
        _verify_payloads_for_staging(staging_dir, manifest)

        for relative in _RUNTIME_BINARY_PATHS:
            binary = staging_dir / relative
            binary.chmod(stat.S_IMODE(binary.stat().st_mode) | 0o755)

        if release_dir.exists() or release_dir.is_symlink():
            raise ReleaseManagerError("release directory appeared during staging")
        staging_dir.chmod(0o755)
        os.replace(staging_dir, release_dir)
        payload_committed = True

        venv_dir = release_dir / ".venv"
        command_runner((python_executable, "-m", "venv", "--copies", str(venv_dir)))
        wheel = _find_wheel(release_dir, manifest)
        command_runner(
            (
                str(venv_dir / "bin" / "python"),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            )
        )

        _verify_stored_release(release_dir)
        return release_dir
    except ReleaseManagerError:
        if payload_committed:
            _cleanup_incomplete_release(release_dir, paths.current_link)
        else:
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    except Exception as exc:
        try:
            if payload_committed:
                _cleanup_incomplete_release(release_dir, paths.current_link)
            else:
                shutil.rmtree(staging_dir, ignore_errors=True)
        except ReleaseManagerError:
            raise
        except OSError as cleanup_error:
            raise ReleaseManagerError("release staging failed and cleanup failed") from cleanup_error
        raise ReleaseManagerError("release staging failed") from exc


def _require_managed_release(release_dir: Path, paths: ReleasePaths) -> ReleaseManifest:
    release_dir = Path(release_dir)
    releases_dir = Path(paths.releases_dir)
    try:
        if release_dir.parent.resolve() != releases_dir.resolve():
            raise ReleaseManagerError("release directory is outside managed releases directory")
    except OSError as exc:
        raise ReleaseManagerError("unable to resolve managed release path") from exc
    return _verify_stored_release(release_dir)


def _current_release(paths: ReleasePaths) -> Path | None:
    current = Path(paths.current_link)
    if current.is_symlink():
        try:
            target = current.resolve(strict=True)
        except OSError as exc:
            raise ReleaseManagerError("current release symlink is broken") from exc
        _require_managed_release(target, paths)
        return target
    if current.exists():
        raise ReleaseManagerError("current release path must be absent or a symlink")
    return None


def _atomic_switch(current_link: Path, release_dir: Path) -> None:
    current_link = Path(current_link)
    current_link.parent.mkdir(parents=True, exist_ok=True)
    temporary = current_link.parent / f".{current_link.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.symlink_to(release_dir)
        os.replace(temporary, current_link)
    finally:
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink(missing_ok=True)


def _install_units(release_dir: Path, systemd_dir: Path) -> None:
    systemd_dir = Path(systemd_dir)
    systemd_dir.mkdir(parents=True, exist_ok=True)
    for name in _SYSTEMD_UNIT_NAMES:
        source = release_dir / "deploy" / "systemd" / name
        if source.is_symlink() or not source.is_file():
            raise ReleaseManagerError(f"release systemd unit missing: {name}")
        temporary = systemd_dir / f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copyfile(source, temporary)
            temporary.chmod(0o644)
            os.replace(temporary, systemd_dir / name)
        finally:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink(missing_ok=True)


def _systemctl(command_runner: CommandRunner, *args: str) -> None:
    command_runner(("systemctl", *args))


def _stop_runtime(command_runner: CommandRunner) -> None:
    _systemctl(command_runner, "stop", *_RUNTIME_STOP_ORDER)
    _systemctl(command_runner, "stop", "shreks.target")


def _require_runtime_processes_from_release(
    release_dir: Path,
    *,
    identity_reader: RuntimeIdentityReader = _default_runtime_identity_reader,
) -> None:
    release_dir = Path(release_dir)
    try:
        resolved_release = release_dir.resolve(strict=True)
    except OSError as exc:
        raise ReleaseManagerError("unable to resolve activated release directory") from exc

    for unit_name in _RUNTIME_SERVICE_NAMES:
        pid, executable, cwd = identity_reader(unit_name)
        if pid <= 0:
            raise ReleaseManagerError(f"{unit_name} has no running process")

        resolved_cwd = Path(cwd).resolve(strict=False)
        if resolved_cwd != resolved_release:
            raise ReleaseManagerError(
                f"{unit_name} process is not running from the activated release"
            )

        native_relative = _NATIVE_RUNTIME_EXECUTABLES.get(unit_name)
        if native_relative is not None:
            expected_executable = (release_dir / native_relative).resolve(strict=False)
            resolved_executable = Path(executable).resolve(strict=False)
            if resolved_executable != expected_executable:
                raise ReleaseManagerError(
                    f"{unit_name} executable does not match the activated release"
                )
        elif unit_name == "shreks-paper-campaign.service":
            expected_venv_bin = (release_dir / ".venv" / "bin").resolve(strict=False)
            resolved_executable = Path(executable).resolve(strict=False)
            if expected_venv_bin not in resolved_executable.parents:
                raise ReleaseManagerError(
                    f"{unit_name} executable is not from the activated release virtualenv"
                )


def _require_runtime_healthy(
    command_runner: CommandRunner,
    release_dir: Path | None = None,
) -> None:
    for unit_name in _SYSTEMD_UNIT_NAMES:
        _systemctl(command_runner, "is-active", "--quiet", unit_name)

    # Production activation always uses the default runner. Dependency-injected
    # runners are test harnesses and must not inspect the CI runner's real /proc/systemd.
    if release_dir is not None and command_runner is _default_command_runner:
        _require_runtime_processes_from_release(release_dir)


def _rollback_after_failure(
    previous: Path | None,
    failed_release: Path,
    paths: ReleasePaths,
    command_runner: CommandRunner,
) -> None:
    current = Path(paths.current_link)
    _stop_runtime(command_runner)

    if previous is None:
        if current.is_symlink():
            try:
                if current.resolve(strict=False) == failed_release.resolve():
                    current.unlink(missing_ok=True)
            except OSError:
                current.unlink(missing_ok=True)
        return

    _verify_stored_release(previous)
    _install_units(previous, paths.systemd_dir)
    _atomic_switch(current, previous)
    _systemctl(command_runner, "daemon-reload")
    _systemctl(command_runner, "start", "shreks.target")
    _require_runtime_healthy(command_runner, previous)


def activate_release(
    release_dir: Path,
    paths: ReleasePaths,
    *,
    command_runner: CommandRunner = _default_command_runner,
) -> None:
    release_dir = Path(release_dir)
    _require_managed_release(release_dir, paths)
    previous = _current_release(paths)
    same_release = previous is not None and previous.resolve() == release_dir.resolve()

    try:
        if previous is not None:
            _stop_runtime(command_runner)
        _install_units(release_dir, paths.systemd_dir)
        if not same_release:
            _atomic_switch(paths.current_link, release_dir)
        _systemctl(command_runner, "daemon-reload")
        _systemctl(command_runner, "start", "shreks.target")
        _require_runtime_healthy(command_runner, release_dir)
    except Exception as activation_error:
        try:
            _rollback_after_failure(previous, release_dir, paths, command_runner)
        except Exception as rollback_error:
            raise ReleaseManagerError("release activation failed and rollback failed") from rollback_error
        raise ReleaseManagerError("release activation failed; previous state restored") from activation_error


def activate_existing(
    source_sha: str,
    paths: ReleasePaths,
    *,
    command_runner: CommandRunner = _default_command_runner,
) -> None:
    source_sha = validate_source_sha(source_sha)
    release_dir = Path(paths.releases_dir) / source_sha
    _require_managed_release(release_dir, paths)
    activate_release(release_dir, paths, command_runner=command_runner)


def _production_paths() -> ReleasePaths:
    return ReleasePaths(
        releases_dir=Path("/opt/shreks/releases"),
        current_link=Path("/opt/shreks/current"),
        systemd_dir=Path("/etc/systemd/system"),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or activate verified Shreks releases")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install")
    install.add_argument("archive", type=Path)
    install.add_argument("checksum", type=Path)
    install.add_argument("manifest", type=Path)
    install.add_argument("--python", default="/usr/bin/python3")

    existing = subparsers.add_parser("activate-existing")
    existing.add_argument("source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = _production_paths()
    try:
        if args.command == "install":
            release_dir = stage_release(
                args.archive,
                args.checksum,
                args.manifest,
                paths,
                python_executable=args.python,
            )
            activate_release(release_dir, paths)
        else:
            activate_existing(args.source_sha, paths)
    except (ReleaseManagerError, ReleaseBundleError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
