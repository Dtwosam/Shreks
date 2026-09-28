from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import tempfile
from typing import Mapping

from .fast_paper_authoritative_cutover_baseline import (
    read_fast_paper_authoritative_cutover_baseline_receipt,
)
from .fast_paper_authoritative_cutover_config import (
    encode_fast_paper_authoritative_cutover_environment,
    read_fast_paper_authoritative_cutover_environment,
    validate_fast_paper_authoritative_cutover_environment,
)
from .fast_paper_runtime.authoritative_runtime import (
    bootstrap_fast_paper_authoritative_runtime,
)
from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow_execution_input import (
    read_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_buy_writer_policy import (
    read_fast_paper_shadow_buy_writer_policy,
    verify_fast_paper_shadow_buy_writer_policy_bindings,
)
from .fast_paper_runtime.shadow_service import (
    read_fast_paper_shadow_service_policy,
)


_SCHEMA_VERSION = 1
_ROOT_UID = 0
_ROOT_GID = 0
_CONFIG_MODE = 0o640
_STATE_DIR_MODE = 0o700
_SERVICE_NAME = "shreks"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class FastPaperAuthoritativeHostPrepareError(RuntimeError):
    pass


def preflight_fast_paper_authoritative_host_config(
    *,
    expected_release_source_sha: str,
    candidate_env_path: str | Path,
    current_link: str | Path,
    config_destination: str | Path,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    expected_sha = _require_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        Path(current_link),
        expected_sha,
        runtime_executable,
    )
    env, manifest = _authenticate_candidate_environment(
        Path(candidate_env_path),
        expected_sha=expected_sha,
    )
    canonical = encode_fast_paper_authoritative_cutover_environment(
        env
    ).encode("utf-8")
    destination = Path(config_destination)
    _require_safe_config_parent(destination, service_gid=service_gid)
    installed = _inspect_config_destination(
        destination,
        expected_payload=canonical,
        service_gid=service_gid,
    )
    return _receipt(
        schema_name="shreks.fast_paper_authoritative_host_config_preflight",
        state=(
            "READY_CONFIG_ALREADY_INSTALLED"
            if installed
            else "READY_TO_INSTALL_CONFIG"
        ),
        expected_sha=expected_sha,
        release_dir=release_dir,
        service_gid=service_gid,
        extra={
            "config_sha256": hashlib.sha256(canonical).hexdigest(),
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
        },
    )


def install_fast_paper_authoritative_host_config(
    *,
    expected_release_source_sha: str,
    candidate_env_path: str | Path,
    current_link: str | Path,
    config_destination: str | Path,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    expected_sha = _require_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        Path(current_link),
        expected_sha,
        runtime_executable,
    )
    env, manifest = _authenticate_candidate_environment(
        Path(candidate_env_path),
        expected_sha=expected_sha,
    )
    canonical = encode_fast_paper_authoritative_cutover_environment(
        env
    ).encode("utf-8")
    destination = Path(config_destination)
    _require_safe_config_parent(destination, service_gid=service_gid)
    if _inspect_config_destination(
        destination,
        expected_payload=canonical,
        service_gid=service_gid,
    ):
        state = "CONFIG_ALREADY_INSTALLED"
    else:
        if _require_current_release(Path(current_link), expected_sha) != release_dir:
            raise FastPaperAuthoritativeHostPrepareError(
                "current release changed before authoritative config publication"
            )
        _publish_config_no_replace(
            destination,
            canonical,
            service_gid=service_gid,
        )
        _require_config_destination(
            destination,
            expected_payload=canonical,
            service_gid=service_gid,
        )
        state = "CONFIG_INSTALLED"
    return _receipt(
        schema_name="shreks.fast_paper_authoritative_host_config_installation",
        state=state,
        expected_sha=expected_sha,
        release_dir=release_dir,
        service_gid=service_gid,
        extra={
            "config_sha256": hashlib.sha256(canonical).hexdigest(),
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
        },
    )


def provision_fast_paper_authoritative_host_roots(
    *,
    expected_release_source_sha: str,
    current_link: str | Path,
    config_destination: str | Path,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    expected_sha = _require_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        Path(current_link),
        expected_sha,
        runtime_executable,
    )
    env, config, manifest = _read_installed_config(
        Path(config_destination),
        expected_sha=expected_sha,
        service_gid=service_gid,
    )
    directories = _runtime_state_directories(config)
    created = 0
    root = directories[0].parent
    if root.is_symlink():
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative state root must not be a symlink"
        )
    if not root.exists():
        os.mkdir(root, _STATE_DIR_MODE)
        os.chown(root, service_uid, service_gid)
        os.chmod(root, _STATE_DIR_MODE)
        _fsync_directory(root.parent)
        created += 1
    _require_path_metadata(
        root,
        label="authoritative state root",
        expected_kind="directory",
        expected_uid=service_uid,
        expected_gid=service_gid,
        expected_mode=_STATE_DIR_MODE,
    )
    for directory in directories:
        if directory.is_symlink():
            raise FastPaperAuthoritativeHostPrepareError(
                "authoritative source directory must not be a symlink"
            )
        if not directory.exists():
            os.mkdir(directory, _STATE_DIR_MODE)
            os.chown(directory, service_uid, service_gid)
            os.chmod(directory, _STATE_DIR_MODE)
            created += 1
        _require_path_metadata(
            directory,
            label="authoritative source directory",
            expected_kind="directory",
            expected_uid=service_uid,
            expected_gid=service_gid,
            expected_mode=_STATE_DIR_MODE,
        )
    _fsync_directory(root)
    return _receipt(
        schema_name="shreks.fast_paper_authoritative_host_roots",
        state="ROOTS_CREATED" if created else "ROOTS_VERIFIED",
        expected_sha=expected_sha,
        release_dir=release_dir,
        service_gid=service_gid,
        extra={
            "service_uid": service_uid,
            "config_sha256": hashlib.sha256(
                encode_fast_paper_authoritative_cutover_environment(env).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
            "directories_created": created,
        },
    )


def preflight_fast_paper_authoritative_host(
    *,
    expected_release_source_sha: str,
    current_link: str | Path,
    config_destination: str | Path,
    baseline_receipt_path: str | Path,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    expected_sha = _require_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        Path(current_link),
        expected_sha,
        runtime_executable,
    )
    env, config, manifest = _read_installed_config(
        Path(config_destination),
        expected_sha=expected_sha,
        service_gid=service_gid,
    )
    for directory in _runtime_state_directories(config):
        _require_path_metadata(
            directory,
            label="authoritative source directory",
            expected_kind="directory",
            expected_uid=service_uid,
            expected_gid=service_gid,
            expected_mode=_STATE_DIR_MODE,
        )

    for authority in _authority_paths_from_config(config):
        _require_path_metadata(
            authority,
            label="authoritative protected authority file",
            expected_kind="file",
            expected_uid=_ROOT_UID,
            expected_gid=service_gid,
            expected_mode=_CONFIG_MODE,
        )
    if config.decision_config.checkpoint_path is None:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative decision checkpoint path is missing"
        )
    _require_path_metadata(
        config.decision_config.checkpoint_path,
        label="authoritative decision baseline checkpoint",
        expected_kind="file",
        expected_uid=service_uid,
        expected_gid=service_gid,
        expected_mode=0o600,
    )

    if (
        config.cutover_authorization_path.exists()
        or config.cutover_authorization_path.is_symlink()
    ):
        raise FastPaperAuthoritativeHostPrepareError(
            "production cutover authorization must not exist during host preparation"
        )

    baseline = _authenticate_baseline_receipt(
        Path(baseline_receipt_path),
        manifest=manifest,
        decision_checkpoint_path=(
            config.decision_config.checkpoint_path
        ),
    )
    service_policy = read_fast_paper_shadow_service_policy(
        config.decision_config.policy_path
    )
    writer_policy = read_fast_paper_shadow_buy_writer_policy(
        config.buy_writer_policy_path
    )
    verify_fast_paper_shadow_buy_writer_policy_bindings(
        manifest,
        service_policy,
        writer_policy,
    )
    try:
        bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
    except Exception as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative runtime bootstrap failed closed"
        ) from exc
    if (
        bootstrap.execution_bootstrap.runtime_state.market_positions
        or bootstrap.execution_bootstrap.checkpoint.state.pending_buy
        is not None
    ):
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative runtime must remain economically pristine before cutover"
        )
    canonical_env = encode_fast_paper_authoritative_cutover_environment(env)
    return _receipt(
        schema_name="shreks.fast_paper_authoritative_host_preflight",
        state="READY_FOR_PROTECTED_PAPER_CUTOVER_REVIEW",
        expected_sha=expected_sha,
        release_dir=release_dir,
        service_gid=service_gid,
        extra={
            "service_uid": service_uid,
            "config_sha256": hashlib.sha256(
                canonical_env.encode("utf-8")
            ).hexdigest(),
            "manifest_fingerprint_sha256": (
                manifest.manifest_fingerprint_sha256
            ),
            "buy_writer_policy_fingerprint_sha256": (
                writer_policy.policy_fingerprint_sha256
            ),
            "decision_state_fingerprint_sha256": (
                baseline["decision_state_fingerprint_sha256"]
            ),
            "baseline_receipt_fingerprint_sha256": (
                baseline["receipt_fingerprint_sha256"]
            ),
            "fast_run_id": (
                bootstrap.execution_bootstrap.binding.fast_run_id
            ),
            "paper_checkpoint_sequence": (
                bootstrap.execution_bootstrap.checkpoint.sequence
            ),
        },
    )


def _authenticate_candidate_environment(
    candidate: Path,
    *,
    expected_sha: str,
):
    try:
        env = read_fast_paper_authoritative_cutover_environment(candidate)
        manifest = read_fast_paper_runtime_manifest(
            env["SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"]
        )
        verify_fast_paper_runtime_bindings(manifest)
        if manifest.release_source_sha != expected_sha:
            raise ValueError(
                "runtime manifest release source SHA does not match active release"
            )
        validate_fast_paper_authoritative_cutover_environment(
            env,
            manifest,
            authoritative_database_path=(
                manifest.observer_database_path
            ),
        )
        service_policy = read_fast_paper_shadow_service_policy(
            env["SHREKS_FAST_PAPER_SERVICE_POLICY_PATH"]
        )
        read_fast_paper_shadow_execution_policy(
            manifest,
            env[
                "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_POLICY_PATH"
            ],
        )
        writer_policy = read_fast_paper_shadow_buy_writer_policy(
            env["SHREKS_FAST_PAPER_AUTHORITATIVE_BUY_WRITER_POLICY_PATH"]
        )
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            manifest,
            service_policy,
            writer_policy,
        )
    except Exception as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative host candidate environment authentication failed"
        ) from exc
    return env, manifest


def _read_installed_config(
    destination: Path,
    *,
    expected_sha: str,
    service_gid: int,
):
    payload, metadata = _read_regular_no_follow(
        destination,
        label="installed authoritative host config",
    )
    _require_config_metadata(metadata, service_gid=service_gid)
    try:
        text = payload.decode("utf-8")
        temporary = destination.parent / (
            f".{destination.name}.validate-{os.getpid()}"
        )
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("temporary validation path already exists")
        temporary.write_text(text, encoding="utf-8")
        try:
            env = read_fast_paper_authoritative_cutover_environment(temporary)
        finally:
            temporary.unlink(missing_ok=True)
        if (
            encode_fast_paper_authoritative_cutover_environment(env).encode(
                "utf-8"
            )
            != payload
        ):
            raise ValueError(
                "installed authoritative host config is not canonical"
            )
        manifest = read_fast_paper_runtime_manifest(
            env["SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"]
        )
        verify_fast_paper_runtime_bindings(manifest)
        if manifest.release_source_sha != expected_sha:
            raise ValueError(
                "installed runtime manifest release identity mismatch"
            )
        config = validate_fast_paper_authoritative_cutover_environment(
            env,
            manifest,
            authoritative_database_path=manifest.observer_database_path,
        )
    except Exception as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "installed authoritative host config authentication failed"
        ) from exc
    return env, config, manifest


def _authenticate_baseline_receipt(
    path: Path,
    *,
    manifest,
    decision_checkpoint_path: Path | None,
) -> dict[str, object]:
    if decision_checkpoint_path is None:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative decision checkpoint path is missing"
        )
    try:
        receipt = read_fast_paper_authoritative_cutover_baseline_receipt(path)
        state = read_fast_paper_runtime_state(decision_checkpoint_path)
    except Exception as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative cutover baseline authentication failed"
        ) from exc
    if (
        receipt["release_source_sha"] != manifest.release_source_sha
        or receipt["manifest_fingerprint_sha256"]
        != manifest.manifest_fingerprint_sha256
        or receipt["authoritative_checkpoint_path"]
        != str(decision_checkpoint_path.resolve(strict=True))
        or receipt["decision_state_fingerprint_sha256"]
        != state.state_fingerprint_sha256
        or receipt["decision_cursor_sequence"]
        != (
            None
            if state.cursor is None
            else state.cursor.decision_sequence
        )
    ):
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative cutover baseline identity mismatch"
        )
    shadow_path = Path(receipt["shadow_checkpoint_path"])
    if shadow_path.is_symlink() or not shadow_path.is_file():
        raise FastPaperAuthoritativeHostPrepareError(
            "baseline shadow checkpoint is unavailable"
        )
    if hashlib.sha256(shadow_path.read_bytes()).hexdigest() != receipt[
        "shadow_checkpoint_file_sha256"
    ]:
        raise FastPaperAuthoritativeHostPrepareError(
            "baseline shadow checkpoint changed after provisioning"
        )
    if decision_checkpoint_path.read_bytes() != shadow_path.read_bytes():
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative baseline no longer equals shadow checkpoint"
        )
    return receipt


def _authority_paths_from_config(config) -> tuple[Path, ...]:
    return (
        config.decision_config.manifest_path,
        config.decision_config.policy_path,
        config.execution_config.execution_policy_path,
        config.buy_writer_policy_path,
    )


def _runtime_state_directories(config) -> tuple[Path, ...]:
    values = (
        config.decision_config.evidence_directory,
        config.execution_config.source_directory,
        config.buy_authority_source_directory,
        config.quote_usd_source_directory,
        config.reduction_source_directory,
        config.pending_buy_retry_source_directory,
    )
    resolved = tuple(Path(value).resolve(strict=False) for value in values)
    if len(set(resolved)) != len(resolved):
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative source directories must be distinct"
        )
    return resolved


def _require_current_release(current_link: Path, expected_sha: str) -> Path:
    if not current_link.is_symlink():
        raise FastPaperAuthoritativeHostPrepareError(
            "current release must be an existing symlink"
        )
    try:
        release_dir = current_link.resolve(strict=True)
    except OSError as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "current release symlink could not be resolved"
        ) from exc
    if not release_dir.is_dir() or release_dir.name != expected_sha:
        raise FastPaperAuthoritativeHostPrepareError(
            "current release does not match expected source SHA"
        )
    return release_dir


def _require_release_runtime(
    current_link: Path,
    expected_sha: str,
    runtime_executable: str | os.PathLike[str] | None,
) -> Path:
    release_dir = _require_current_release(current_link, expected_sha)
    executable = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    try:
        if executable.is_symlink():
            raise FastPaperAuthoritativeHostPrepareError(
                "host preparation runtime executable must not be a symlink"
            )
        resolved = executable.resolve(strict=True)
        expected_bin = (release_dir / ".venv" / "bin").resolve(strict=True)
    except OSError as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "host preparation runtime executable could not be resolved"
        ) from exc
    if not resolved.is_file() or resolved.parent != expected_bin:
        raise FastPaperAuthoritativeHostPrepareError(
            "host preparation must execute from exact current release virtualenv"
        )
    return release_dir


def _require_safe_config_parent(
    destination: Path,
    *,
    service_gid: int,
) -> None:
    try:
        metadata = destination.parent.lstat()
    except OSError as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative config parent is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != _ROOT_UID
        or metadata.st_gid not in (_ROOT_GID, service_gid)
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative config parent metadata is unsafe"
        )


def _inspect_config_destination(
    destination: Path,
    *,
    expected_payload: bytes,
    service_gid: int,
) -> bool:
    try:
        payload, metadata = _read_regular_no_follow(
            destination,
            label="authoritative host config destination",
        )
    except FastPaperAuthoritativeHostPrepareError:
        if not destination.exists() and not destination.is_symlink():
            return False
        raise
    if payload != expected_payload:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative host config already exists with different bytes"
        )
    _require_config_metadata(metadata, service_gid=service_gid)
    return True


def _require_config_destination(
    destination: Path,
    *,
    expected_payload: bytes,
    service_gid: int,
) -> None:
    payload, metadata = _read_regular_no_follow(
        destination,
        label="installed authoritative host config",
    )
    if payload != expected_payload:
        raise FastPaperAuthoritativeHostPrepareError(
            "installed authoritative config bytes do not match candidate"
        )
    _require_config_metadata(metadata, service_gid=service_gid)


def _require_config_metadata(
    metadata: os.stat_result,
    *,
    service_gid: int,
) -> None:
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != service_gid
        or stat.S_IMODE(metadata.st_mode) != _CONFIG_MODE
    ):
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative host config metadata is not exact"
        )


def _publish_config_no_replace(
    destination: Path,
    payload: bytes,
    *,
    service_gid: int,
) -> None:
    _require_safe_config_parent(destination, service_gid=service_gid)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.install-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), _ROOT_UID, service_gid)
            os.fchmod(handle.fileno(), _CONFIG_MODE)
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
            linked = True
        except FileExistsError as exc:
            raise FastPaperAuthoritativeHostPrepareError(
                "authoritative host config appeared during publication"
            ) from exc
        temporary.unlink()
        _fsync_directory(destination.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        if linked:
            try:
                _fsync_directory(destination.parent)
            except Exception:
                pass
        raise


def _read_regular_no_follow(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, os.stat_result]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            f"{label} must be an existing regular non-symlink file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise FastPaperAuthoritativeHostPrepareError(
                f"{label} must be a regular file"
            )
        payload = b""
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            payload += chunk
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(payload) != before.st_size
        ):
            raise FastPaperAuthoritativeHostPrepareError(
                f"{label} changed while being read"
            )
        return payload, after
    finally:
        os.close(descriptor)


def _require_path_metadata(
    path: Path,
    *,
    label: str,
    expected_kind: str,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int,
) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            f"{label} is unavailable"
        ) from exc
    kind_ok = (
        stat.S_ISDIR(metadata.st_mode)
        if expected_kind == "directory"
        else stat.S_ISREG(metadata.st_mode)
    )
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not kind_ok
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
        or stat.S_IMODE(metadata.st_mode) != expected_mode
    ):
        raise FastPaperAuthoritativeHostPrepareError(
            f"{label} metadata is not exact"
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


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperAuthoritativeHostPrepareError(
            "authoritative host preparation requires root"
        )


def _resolve_service_identity() -> tuple[int, int]:
    try:
        account = pwd.getpwnam(_SERVICE_NAME)
        group = grp.getgrnam(_SERVICE_NAME)
    except KeyError as exc:
        raise FastPaperAuthoritativeHostPrepareError(
            "shreks service identity is unavailable"
        ) from exc
    if account.pw_gid != group.gr_gid:
        raise FastPaperAuthoritativeHostPrepareError(
            "shreks service identity is inconsistent"
        )
    return account.pw_uid, group.gr_gid


def _require_source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperAuthoritativeHostPrepareError(
            "expected release SHA must be exactly 40 lowercase hex"
        )
    return value


def _receipt(
    *,
    schema_name: str,
    state: str,
    expected_sha: str,
    release_dir: Path,
    service_gid: int,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    material: dict[str, object] = {
        "schema_name": schema_name,
        "schema_version": _SCHEMA_VERSION,
        "state": state,
        "release_source_sha": expected_sha,
        "release_dir": str(release_dir),
        "service_gid": service_gid,
        "production_paper_cutover": "NOT_GRANTED",
        "service_control_authority": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    if extra is not None:
        material.update(dict(extra))
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _production_paths() -> tuple[Path, Path]:
    return (
        Path("/opt/shreks/current"),
        Path("/etc/shreks/fast-paper-authoritative.env"),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-authoritative-host-prepare"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("config-preflight", "install-config"):
        sub = commands.add_parser(command)
        sub.add_argument("expected_release_source_sha")
        sub.add_argument("candidate_env")
    sub = commands.add_parser("provision-roots")
    sub.add_argument("expected_release_source_sha")
    sub = commands.add_parser("host-preflight")
    sub.add_argument("expected_release_source_sha")
    sub.add_argument("baseline_receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    current_link, config_destination = _production_paths()
    service_uid, service_gid = _resolve_service_identity()
    common = {
        "expected_release_source_sha": args.expected_release_source_sha,
        "current_link": current_link,
        "config_destination": config_destination,
        "service_gid": service_gid,
    }
    try:
        if args.command == "config-preflight":
            result = preflight_fast_paper_authoritative_host_config(
                candidate_env_path=args.candidate_env,
                **common,
            )
        elif args.command == "install-config":
            result = install_fast_paper_authoritative_host_config(
                candidate_env_path=args.candidate_env,
                **common,
            )
        elif args.command == "provision-roots":
            result = provision_fast_paper_authoritative_host_roots(
                service_uid=service_uid,
                **common,
            )
        elif args.command == "host-preflight":
            result = preflight_fast_paper_authoritative_host(
                baseline_receipt_path=args.baseline_receipt,
                service_uid=service_uid,
                **common,
            )
        else:
            raise AssertionError("unreachable authoritative host command")
    except Exception as exc:
        print(
            _canonical(
                {
                    "schema_name": (
                        "shreks.fast_paper_authoritative_host_prepare_failure"
                    ),
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "production_paper_cutover": "NOT_GRANTED",
                    "service_control_authority": "NOT_GRANTED",
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
