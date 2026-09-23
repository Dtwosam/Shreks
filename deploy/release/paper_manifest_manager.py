#!/opt/shreks/current/.venv/bin/python

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

if __package__:
    from .release_bundle import (
        ReleaseBundleError,
        decode_release_manifest,
        validate_source_sha,
    )
    from .release_manager import (
        ReleaseManagerError,
        _default_runtime_identity_reader,
    )
else:
    _LOCAL_CONTROL_DIR = Path(__file__).resolve().parent
    _LOCAL_RELEASE_BUNDLE = _LOCAL_CONTROL_DIR / "release_bundle.py"
    _LOCAL_RELEASE_MANAGER = _LOCAL_CONTROL_DIR / "release_manager.py"
    if (
        _LOCAL_RELEASE_BUNDLE.is_file()
        and not _LOCAL_RELEASE_BUNDLE.is_symlink()
        and _LOCAL_RELEASE_MANAGER.is_file()
        and not _LOCAL_RELEASE_MANAGER.is_symlink()
    ):
        from release_bundle import (
            ReleaseBundleError,
            decode_release_manifest,
            validate_source_sha,
        )
        from release_manager import (
            ReleaseManagerError,
            _default_runtime_identity_reader,
        )
    else:
        from shreks_brain._sealed_deploy_control.release_bundle import (
            ReleaseBundleError,
            decode_release_manifest,
            validate_source_sha,
        )
        from shreks_brain._sealed_deploy_control.release_manager import (
            ReleaseManagerError,
            _default_runtime_identity_reader,
        )

from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    G1CV2RuntimeManifestTransitionBindingError,
    decode_g1c_v2_runtime_manifest_transition_binding,
)
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
    preflight_observer_paper_campaign_runtime,
)
from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    ObserverPaperCampaignRuntimeManifest,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.risk_control import (
    RiskControlStateError,
    load_operator_risk_control_state,
)


CommandRunner = Callable[[tuple[str, ...]], None]
RuntimeIdentity = tuple[int, Path, Path]
RuntimeIdentityReader = Callable[[str], RuntimeIdentity]
PreflightRunner = Callable[[ObserverPaperCampaignRuntimeConfig], object]

_CAMPAIGN_SERVICE = "shreks-paper-campaign.service"
_CONTROL_MANIFEST_PATH = "RELEASE_MANIFEST.json"
_ROTATION_RECEIPT_SCHEMA_NAME = "shreks.g1c_v2_paper_manifest_rotation"
_ROTATION_RECEIPT_SCHEMA_VERSION = 1
_SHA256_LENGTH = 64

_ENV_KEYS = {
    "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": "observer_database_path",
    "SHREKS_PAPER_CAMPAIGN_E11_PATH": "evidence_path",
    "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": "active_manifest_path",
    "SHREKS_RISK_CONTROL_STATE_PATH": "risk_control_path",
}


class PaperManifestManagerError(RuntimeError):
    """Raised when a protected PAPER manifest rotation cannot be proven safe."""


@dataclass(frozen=True, slots=True)
class PaperManifestRotationPaths:
    current_link: Path
    env_file: Path
    active_manifest_path: Path
    observer_database_path: Path
    evidence_path: Path
    risk_control_path: Path
    rotation_evidence_root: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "env_file",
            "active_manifest_path",
            "observer_database_path",
            "evidence_path",
            "risk_control_path",
            "rotation_evidence_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise PaperManifestManagerError(
                    f"{name} must be an absolute Path"
                )


@dataclass(frozen=True, slots=True)
class _ManifestInputs:
    source_payload: bytes
    source_manifest: ObserverPaperCampaignRuntimeManifest
    candidate_payload: bytes
    candidate_manifest: ObserverPaperCampaignRuntimeManifest
    binding_payload: bytes
    binding: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ManifestMetadata:
    mode: int
    uid: int
    gid: int


def _default_command_runner(command: tuple[str, ...]) -> None:
    subprocess.run(command, check=True)


def _default_preflight_runner(
    config: ObserverPaperCampaignRuntimeConfig,
) -> object:
    return preflight_observer_paper_campaign_runtime(
        config,
        status_sink=lambda _line: None,
    )


def _production_paths() -> PaperManifestRotationPaths:
    return PaperManifestRotationPaths(
        current_link=Path("/opt/shreks/current"),
        env_file=Path("/etc/shreks/shreks.env"),
        active_manifest_path=Path("/etc/shreks/paper-campaign.json"),
        observer_database_path=Path("/var/lib/shreks/shreks.db"),
        evidence_path=Path("/var/lib/shreks/paper-evaluation-e11.json"),
        risk_control_path=Path("/var/lib/shreks/risk/operator-control.json"),
        rotation_evidence_root=Path("/var/lib/shreks/manifest-rotations"),
    )


def rotate_paper_manifest(
    *,
    candidate_runtime_manifest_path: str | Path,
    transition_binding_path: str | Path,
    expected_binding_fingerprint_sha256: str,
    expected_release_source_sha: str,
    paths: PaperManifestRotationPaths,
    command_runner: CommandRunner = _default_command_runner,
    runtime_identity_reader: RuntimeIdentityReader = _default_runtime_identity_reader,
    preflight_runner: PreflightRunner = _default_preflight_runner,
) -> dict[str, object]:
    if type(paths) is not PaperManifestRotationPaths:
        raise PaperManifestManagerError(
            "rotation paths must be an exact PaperManifestRotationPaths"
        )
    expected_binding = _require_lower_hex(
        "expected_binding_fingerprint_sha256",
        expected_binding_fingerprint_sha256,
        _SHA256_LENGTH,
    )
    try:
        expected_release = validate_source_sha(expected_release_source_sha)
    except (ReleaseBundleError, TypeError, ValueError) as error:
        raise PaperManifestManagerError(
            "expected release source SHA is invalid"
        ) from error

    _require_runtime_env_contract(paths)
    release_dir = _require_current_release(paths.current_link, expected_release)
    metadata = _require_active_manifest_metadata(paths.active_manifest_path)
    inputs = _load_and_verify_inputs(
        active_manifest_path=paths.active_manifest_path,
        candidate_runtime_manifest_path=candidate_runtime_manifest_path,
        transition_binding_path=transition_binding_path,
        expected_binding_fingerprint_sha256=expected_binding,
    )
    try:
        load_operator_risk_control_state(paths.risk_control_path)
    except (RiskControlStateError, OSError, TypeError, ValueError) as error:
        raise PaperManifestManagerError(
            "operator risk-control state is not readable and valid"
        ) from error

    rotation_dir: Path | None = None
    source_replaced = False
    campaign_stopped = False
    try:
        _systemctl(command_runner, "stop", _CAMPAIGN_SERVICE)
        campaign_stopped = True

        rotation_dir = _prepare_rotation_evidence(
            paths=paths,
            inputs=inputs,
            release_source_sha=expected_release,
        )
        _preflight_manifest(
            paths=paths,
            manifest_path=rotation_dir / "candidate-paper-campaign.json",
            preflight_runner=preflight_runner,
        )

        _atomic_replace_manifest(
            paths.active_manifest_path,
            inputs.candidate_payload,
            metadata,
        )
        source_replaced = True

        _preflight_manifest(
            paths=paths,
            manifest_path=paths.active_manifest_path,
            preflight_runner=preflight_runner,
        )
        _systemctl(command_runner, "start", _CAMPAIGN_SERVICE)
        _require_campaign_healthy(
            command_runner,
            runtime_identity_reader,
            release_dir,
        )
        _require_active_payload(
            paths.active_manifest_path,
            inputs.candidate_payload,
            label="candidate",
        )

        receipt = _rotation_receipt(
            status="ACTIVATED",
            release_source_sha=expected_release,
            inputs=inputs,
        )
        _write_private_once(rotation_dir / "activated.json", _canonical_json(receipt))
        return receipt
    except Exception as rotation_error:
        if not campaign_stopped:
            if isinstance(rotation_error, PaperManifestManagerError):
                raise
            raise PaperManifestManagerError(
                "PAPER manifest rotation failed before campaign quiesce"
            ) from rotation_error

        try:
            if source_replaced:
                _atomic_replace_manifest(
                    paths.active_manifest_path,
                    inputs.source_payload,
                    metadata,
                )
            else:
                _require_active_payload(
                    paths.active_manifest_path,
                    inputs.source_payload,
                    label="source",
                )
            _preflight_manifest(
                paths=paths,
                manifest_path=paths.active_manifest_path,
                preflight_runner=preflight_runner,
            )
            _systemctl(command_runner, "start", _CAMPAIGN_SERVICE)
            _require_campaign_healthy(
                command_runner,
                runtime_identity_reader,
                release_dir,
            )
            _require_active_payload(
                paths.active_manifest_path,
                inputs.source_payload,
                label="source",
            )
            if rotation_dir is not None:
                rollback = _rotation_receipt(
                    status="ROLLED_BACK",
                    release_source_sha=expected_release,
                    inputs=inputs,
                )
                rollback["failure_type"] = type(rotation_error).__name__
                _write_private_once(
                    rotation_dir / "rolled-back.json",
                    _canonical_json(rollback),
                )
        except Exception as rollback_error:
            raise PaperManifestManagerError(
                "PAPER manifest rotation failed and rollback failed"
            ) from rollback_error
        raise PaperManifestManagerError(
            "PAPER manifest rotation failed; source manifest restored"
        ) from rotation_error


def _load_and_verify_inputs(
    *,
    active_manifest_path: Path,
    candidate_runtime_manifest_path: str | Path,
    transition_binding_path: str | Path,
    expected_binding_fingerprint_sha256: str,
) -> _ManifestInputs:
    source_path = _resolve_regular_file(
        active_manifest_path,
        label="active source runtime manifest",
    )
    candidate_path = _resolve_regular_file(
        candidate_runtime_manifest_path,
        label="candidate runtime manifest",
    )
    binding_path = _resolve_regular_file(
        transition_binding_path,
        label="transition binding",
    )
    if candidate_path == source_path:
        raise PaperManifestManagerError(
            "candidate runtime manifest must not be the active manifest path"
        )

    source_payload = _read_stable(source_path, label="active source runtime manifest")
    candidate_payload = _read_stable(candidate_path, label="candidate runtime manifest")
    binding_payload = _read_stable(binding_path, label="transition binding")
    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
        candidate = decode_observer_paper_campaign_runtime_manifest(candidate_payload)
        binding = decode_g1c_v2_runtime_manifest_transition_binding(
            binding_payload.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        G1CV2RuntimeManifestTransitionBindingError,
        ObserverPaperCampaignRuntimeManifestError,
    ) as error:
        raise PaperManifestManagerError(
            "rotation source, candidate, or binding authentication failed"
        ) from error

    if source.schema_version != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION:
        raise PaperManifestManagerError(
            "active source runtime manifest must be canonical v1 authority"
        )
    if (
        candidate.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        raise PaperManifestManagerError(
            "candidate runtime manifest must be canonical v2"
        )
    if binding["binding_fingerprint_sha256"] != expected_binding_fingerprint_sha256:
        raise PaperManifestManagerError(
            "transition binding fingerprint does not match explicit operator authority"
        )

    source_sha = hashlib.sha256(source_payload).hexdigest()
    candidate_sha = hashlib.sha256(candidate_payload).hexdigest()
    checks = (
        ("source_manifest_sha256", source_sha),
        (
            "source_runtime_manifest_fingerprint_sha256",
            source.manifest_fingerprint_sha256,
        ),
        ("source_paper_run_id", source.paper_run_id),
        ("source_quote_asset_mint", source.policy_bundle.quote_asset.mint),
        ("candidate_manifest_sha256", candidate_sha),
        (
            "candidate_runtime_manifest_fingerprint_sha256",
            candidate.manifest_fingerprint_sha256,
        ),
        ("candidate_paper_run_id", candidate.paper_run_id),
        (
            "candidate_start_at_unix_ms",
            candidate.initial_state.last_cycle_at_unix_ms,
        ),
        (
            "candidate_quote_asset_mint",
            candidate.policy_bundle.quote_asset.mint,
        ),
        (
            "candidate_quote_asset_decimals",
            candidate.policy_bundle.quote_asset.decimals,
        ),
    )
    for name, expected in checks:
        if binding.get(name) != expected:
            raise PaperManifestManagerError(
                f"transition binding {name} does not match protected rotation input"
            )

    return _ManifestInputs(
        source_payload=source_payload,
        source_manifest=source,
        candidate_payload=candidate_payload,
        candidate_manifest=candidate,
        binding_payload=binding_payload,
        binding=binding,
    )


def _require_runtime_env_contract(paths: PaperManifestRotationPaths) -> None:
    env_path = _resolve_regular_file(paths.env_file, label="runtime environment file")
    payload = _read_stable(env_path, label="runtime environment file")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PaperManifestManagerError(
            "runtime environment file is not UTF-8"
        ) from error

    required = {
        key: str(getattr(paths, field))
        for key, field in _ENV_KEYS.items()
    }
    observed: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in required:
            continue
        if key in observed:
            raise PaperManifestManagerError(
                f"runtime environment contains duplicate {key}"
            )
        observed[key] = value.strip()

    for key, expected in required.items():
        if observed.get(key) != expected:
            raise PaperManifestManagerError(
                f"runtime environment {key} does not match protected rotation path"
            )


def _require_current_release(current_link: Path, expected_source_sha: str) -> Path:
    if not current_link.is_symlink():
        raise PaperManifestManagerError(
            "current release must be an existing symlink"
        )
    try:
        release_dir = current_link.resolve(strict=True)
    except OSError as error:
        raise PaperManifestManagerError(
            "current release symlink could not be resolved"
        ) from error
    if release_dir.name != expected_source_sha:
        raise PaperManifestManagerError(
            "current release directory does not match expected source SHA"
        )

    control_path = release_dir / _CONTROL_MANIFEST_PATH
    payload = _read_stable(
        _resolve_regular_file(control_path, label="current release manifest"),
        label="current release manifest",
    )
    try:
        manifest = decode_release_manifest(payload)
    except (ReleaseBundleError, TypeError, ValueError) as error:
        raise PaperManifestManagerError(
            "current release manifest verification failed"
        ) from error
    if manifest.source_sha != expected_source_sha:
        raise PaperManifestManagerError(
            "current release manifest source SHA mismatch"
        )

    runtime_python = release_dir / ".venv" / "bin" / "python"
    if runtime_python.is_symlink() or not runtime_python.is_file():
        raise PaperManifestManagerError(
            "current release Python executable is missing or symlinked"
        )
    return release_dir


def _require_active_manifest_metadata(path: Path) -> _ManifestMetadata:
    resolved = _resolve_regular_file(path, label="active runtime manifest")
    try:
        metadata = resolved.stat()
    except OSError as error:
        raise PaperManifestManagerError(
            "active runtime manifest metadata could not be read"
        ) from error
    mode = stat.S_IMODE(metadata.st_mode)
    if mode != 0o640:
        raise PaperManifestManagerError(
            "active runtime manifest permissions must be 0640"
        )
    return _ManifestMetadata(mode=mode, uid=metadata.st_uid, gid=metadata.st_gid)


def _prepare_rotation_evidence(
    *,
    paths: PaperManifestRotationPaths,
    inputs: _ManifestInputs,
    release_source_sha: str,
) -> Path:
    root = paths.rotation_evidence_root
    if root.exists() or root.is_symlink():
        if root.is_symlink() or not root.is_dir():
            raise PaperManifestManagerError(
                "rotation evidence root must be a real directory"
            )
    else:
        try:
            root.mkdir(parents=True, mode=0o700)
        except OSError as error:
            raise PaperManifestManagerError(
                "rotation evidence root could not be created"
            ) from error
    try:
        root.chmod(0o700)
    except OSError as error:
        raise PaperManifestManagerError(
            "rotation evidence root permissions could not be enforced"
        ) from error

    binding_fingerprint = str(inputs.binding["binding_fingerprint_sha256"])
    destination = root / binding_fingerprint
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as error:
        raise PaperManifestManagerError(
            "this transition binding already has rotation evidence"
        ) from error
    except OSError as error:
        raise PaperManifestManagerError(
            "rotation evidence directory could not be created"
        ) from error

    _write_private_once(destination / "source-paper-campaign.json", inputs.source_payload)
    _write_private_once(
        destination / "candidate-paper-campaign.json",
        inputs.candidate_payload,
    )
    _write_private_once(
        destination / "transition-binding.json",
        inputs.binding_payload,
    )
    prepared = _rotation_receipt(
        status="PREPARED",
        release_source_sha=release_source_sha,
        inputs=inputs,
    )
    _write_private_once(destination / "prepared.json", _canonical_json(prepared))
    return destination


def _preflight_manifest(
    *,
    paths: PaperManifestRotationPaths,
    manifest_path: Path,
    preflight_runner: PreflightRunner,
) -> None:
    config = ObserverPaperCampaignRuntimeConfig(
        observer_database_path=paths.observer_database_path,
        evidence_path=paths.evidence_path,
        manifest_path=manifest_path,
        cycle_interval_seconds=1.0,
        max_cycles=1,
        risk_control_path=paths.risk_control_path,
    )
    try:
        preflight_runner(config)
    except (
        ObserverPaperCampaignRuntimeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestManagerError(
            "PAPER runtime preflight rejected manifest rotation"
        ) from error


def _atomic_replace_manifest(
    destination: Path,
    payload: bytes,
    metadata: _ManifestMetadata,
) -> None:
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir():
        raise PaperManifestManagerError(
            "active runtime manifest parent is unsafe"
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.rotation-",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), metadata.mode)
            os.fchown(handle.fileno(), metadata.uid, metadata.gid)
        os.replace(temporary, destination)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _require_campaign_healthy(
    command_runner: CommandRunner,
    runtime_identity_reader: RuntimeIdentityReader,
    release_dir: Path,
) -> None:
    _systemctl(command_runner, "is-active", "--quiet", _CAMPAIGN_SERVICE)
    try:
        pid, executable, cwd = runtime_identity_reader(_CAMPAIGN_SERVICE)
    except (ReleaseManagerError, OSError, TypeError, ValueError) as error:
        raise PaperManifestManagerError(
            "campaign runtime process identity could not be verified"
        ) from error
    if pid <= 0:
        raise PaperManifestManagerError(
            "campaign runtime has no running process"
        )
    resolved_release = release_dir.resolve(strict=True)
    if Path(cwd).resolve(strict=False) != resolved_release:
        raise PaperManifestManagerError(
            "campaign runtime working directory does not match current release"
        )
    expected_venv_bin = (release_dir / ".venv" / "bin").resolve(strict=False)
    resolved_executable = Path(executable).resolve(strict=False)
    if expected_venv_bin not in resolved_executable.parents:
        raise PaperManifestManagerError(
            "campaign runtime executable is not from current release virtualenv"
        )


def _require_active_payload(path: Path, expected: bytes, *, label: str) -> None:
    actual = _read_stable(
        _resolve_regular_file(path, label="active runtime manifest"),
        label="active runtime manifest",
    )
    if actual != expected:
        raise PaperManifestManagerError(
            f"active runtime manifest does not match {label} bytes"
        )


def _rotation_receipt(
    *,
    status: str,
    release_source_sha: str,
    inputs: _ManifestInputs,
) -> dict[str, object]:
    return {
        "schema_name": _ROTATION_RECEIPT_SCHEMA_NAME,
        "schema_version": _ROTATION_RECEIPT_SCHEMA_VERSION,
        "status": status,
        "release_source_sha": release_source_sha,
        "binding_fingerprint_sha256": inputs.binding[
            "binding_fingerprint_sha256"
        ],
        "source_runtime_manifest_fingerprint_sha256": (
            inputs.source_manifest.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": inputs.source_manifest.paper_run_id,
        "candidate_runtime_manifest_fingerprint_sha256": (
            inputs.candidate_manifest.manifest_fingerprint_sha256
        ),
        "candidate_paper_run_id": inputs.candidate_manifest.paper_run_id,
        "candidate_quote_asset_mint": (
            inputs.candidate_manifest.policy_bundle.quote_asset.mint
        ),
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }


def _systemctl(command_runner: CommandRunner, *args: str) -> None:
    try:
        command_runner(("systemctl", *args))
    except Exception as error:
        raise PaperManifestManagerError(
            f"systemctl {' '.join(args)} failed"
        ) from error


def _resolve_regular_file(raw_path: str | Path, *, label: str) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise PaperManifestManagerError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise PaperManifestManagerError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve()
    except OSError as error:
        raise PaperManifestManagerError(
            f"{label} could not be resolved"
        ) from error


def _read_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise PaperManifestManagerError(
            f"{label} could not be read"
        ) from error
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(payload) != before.st_size
    ):
        raise PaperManifestManagerError(
            f"{label} changed while being read"
        )
    return payload


def _write_private_once(path: Path, payload: bytes | str) -> None:
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o600)
    except FileExistsError:
        raise
    except OSError as error:
        raise PaperManifestManagerError(
            "rotation evidence could not be written"
        ) from error


def _require_lower_hex(name: str, value: object, length: int) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperManifestManagerError(
            f"{name} must be {length} lowercase hex characters"
        )
    return value


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Perform one explicit protected PAPER runtime-manifest rotation "
            "with preflight, rollback evidence, and fail-closed recovery."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    rotate = subparsers.add_parser("rotate")
    rotate.add_argument("candidate_runtime_manifest", type=Path)
    rotate.add_argument("transition_binding", type=Path)
    rotate.add_argument("expected_binding_fingerprint_sha256")
    rotate.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        return 1
    args = _build_parser().parse_args(argv)
    try:
        if args.command != "rotate":
            return 2
        receipt = rotate_paper_manifest(
            candidate_runtime_manifest_path=args.candidate_runtime_manifest,
            transition_binding_path=args.transition_binding,
            expected_binding_fingerprint_sha256=(
                args.expected_binding_fingerprint_sha256
            ),
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        FileExistsError,
        PaperManifestManagerError,
        ReleaseBundleError,
        OSError,
        TypeError,
        ValueError,
    ):
        return 1
    sys.stdout.write(_canonical_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
