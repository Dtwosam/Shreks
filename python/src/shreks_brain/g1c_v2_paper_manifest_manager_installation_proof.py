from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer

_PRE_SCHEMA = "shreks.g1c_v2_paper_manifest_manager_installation_prestate"
_PROOF_SCHEMA = "shreks.g1c_v2_paper_manifest_manager_installation_proof"
_SCHEMA_VERSION = 1
_ZERO_SHA256 = "0" * 64
_ROOT_UID = 0
_ROOT_GID = 0
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


class PaperManifestManagerInstallationProofError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProofPaths:
    current_link: Path
    campaign_manifest: Path
    deploy_sudoers: Path
    manager_destination: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link", "campaign_manifest", "deploy_sudoers", "manager_destination"
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise PaperManifestManagerInstallationProofError(
                    f"{name} must be an absolute Path"
                )


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]


def capture_preinstall_state(
    *, expected_release_source_sha: str, paths: ProofPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root(paths)
    material = _release_material(expected_release_source_sha, paths, runtime_executable)
    runner = _default_runner if command_runner is None else command_runner
    document: dict[str, object] = {
        "schema_name": _PRE_SCHEMA,
        "schema_version": _SCHEMA_VERSION,
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "manager_sha256": material["manager_sha256"],
        "campaign_manifest": _file_observation(
            paths.campaign_manifest, "protected PAPER campaign manifest", 0o640
        ),
        "deploy_sudoers": _sudoers_observation(paths.deploy_sudoers),
        "services": _service_observations(runner),
        "snapshot_fingerprint_sha256": _ZERO_SHA256,
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    document["snapshot_fingerprint_sha256"] = _fingerprint(
        document, "snapshot_fingerprint_sha256"
    )
    return document


def verify_postinstall_state(
    *, expected_release_source_sha: str, preinstall_payload: bytes,
    installer_receipt_payload: bytes, paths: ProofPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root(paths)
    material = _release_material(expected_release_source_sha, paths, runtime_executable)
    before = _decode_prestate(preinstall_payload)
    _require_release_fields(before, material, "preinstall snapshot")
    receipt = _decode_receipt(installer_receipt_payload)
    _require_receipt(receipt, material, paths)

    payload, meta = installer._read_regular_no_follow(
        paths.manager_destination, label="installed PAPER manifest manager"
    )
    if payload != material["manager_payload"]:
        raise PaperManifestManagerInstallationProofError(
            "installed PAPER manifest manager bytes do not match sealed release"
        )
    if (meta.st_uid, meta.st_gid, stat.S_IMODE(meta.st_mode)) != (
        _ROOT_UID, _ROOT_GID, 0o755
    ):
        raise PaperManifestManagerInstallationProofError(
            "installed PAPER manifest manager metadata is not exact"
        )

    campaign = _file_observation(
        paths.campaign_manifest, "protected PAPER campaign manifest", 0o640
    )
    if campaign != before["campaign_manifest"]:
        raise PaperManifestManagerInstallationProofError(
            "protected PAPER campaign manifest changed during helper installation window"
        )
    sudoers = _sudoers_observation(paths.deploy_sudoers)
    if sudoers != before["deploy_sudoers"]:
        raise PaperManifestManagerInstallationProofError(
            "deployment sudoers changed during helper installation window"
        )
    runner = _default_runner if command_runner is None else command_runner
    services = _service_observations(runner)
    if services != before["services"]:
        raise PaperManifestManagerInstallationProofError(
            "Shreks service lifecycle state changed during helper installation window"
        )

    result: dict[str, object] = {
        "schema_name": _PROOF_SCHEMA,
        "schema_version": _SCHEMA_VERSION,
        "status": "VERIFIED",
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "manager_sha256": material["manager_sha256"],
        "manager_destination": str(paths.manager_destination),
        "destination_uid": meta.st_uid,
        "destination_gid": meta.st_gid,
        "destination_mode": "0755",
        "preinstall_snapshot_fingerprint_sha256": before[
            "snapshot_fingerprint_sha256"
        ],
        "installer_receipt_sha256": hashlib.sha256(installer_receipt_payload).hexdigest(),
        "campaign_manifest_sha256": campaign["sha256"],
        "campaign_manifest_unchanged": True,
        "deploy_sudoers_sha256": sudoers["sha256"],
        "deploy_sudoers_unchanged": True,
        "service_lifecycle_unchanged": True,
        "proof_fingerprint_sha256": _ZERO_SHA256,
        "installation_authority": "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    result["proof_fingerprint_sha256"] = _fingerprint(
        result, "proof_fingerprint_sha256"
    )
    return result


def _require_root(paths: ProofPaths) -> None:
    if type(paths) is not ProofPaths:
        raise PaperManifestManagerInstallationProofError(
            "paths must be an exact ProofPaths"
        )
    if os.geteuid() != 0:
        raise PaperManifestManagerInstallationProofError(
            "PAPER manifest manager installation proof requires root"
        )


def _production_paths() -> ProofPaths:
    return ProofPaths(
        current_link=Path("/opt/shreks/current"),
        campaign_manifest=Path("/etc/shreks/paper-campaign.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
    )


def _release_material(expected_sha: str, paths: ProofPaths, runtime_executable) -> dict[str, object]:
    expected_sha = installer._validate_source_sha(expected_sha)
    release_dir = installer._require_current_release(paths.current_link, expected_sha)
    installer._require_release_runtime_executable(
        release_dir, Path(sys.executable if runtime_executable is None else runtime_executable)
    )
    manifest_payload, _ = installer._read_regular_no_follow(
        release_dir / "RELEASE_MANIFEST.json", label="current release manifest"
    )
    manifest = installer._decode_release_manifest(manifest_payload)
    if manifest.source_sha != expected_sha:
        raise PaperManifestManagerInstallationProofError(
            "current release manifest source SHA does not match expected release"
        )
    record = installer._require_single_wheel_record(manifest)
    wheel, _ = installer._read_regular_no_follow(
        release_dir / record.path, label="release wheel"
    )
    if len(wheel) != record.size or hashlib.sha256(wheel).hexdigest() != record.sha256:
        raise PaperManifestManagerInstallationProofError(
            "release wheel does not match release manifest"
        )
    manager = installer._extract_manager_payload(wheel)
    return {
        "release_source_sha": expected_sha,
        "release_directory": str(release_dir),
        "wheel_relative_path": record.path,
        "wheel_sha256": record.sha256,
        "manager_sha256": hashlib.sha256(manager).hexdigest(),
        "manager_payload": manager,
    }


def _file_observation(path: Path, label: str, mode: int) -> dict[str, object]:
    payload, meta = installer._read_regular_no_follow(path, label=label)
    actual_mode = stat.S_IMODE(meta.st_mode)
    if actual_mode != mode:
        raise PaperManifestManagerInstallationProofError(
            f"{label} mode is not {mode:04o}"
        )
    return {
        "path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload), "uid": meta.st_uid, "gid": meta.st_gid,
        "mode": f"{actual_mode:04o}",
    }


def _sudoers_observation(path: Path) -> dict[str, object]:
    payload, meta = installer._read_regular_no_follow(path, label="Shreks deployment sudoers")
    if (meta.st_uid, meta.st_gid, stat.S_IMODE(meta.st_mode)) != (
        _ROOT_UID, _ROOT_GID, 0o440
    ):
        raise PaperManifestManagerInstallationProofError(
            "Shreks deployment sudoers metadata is not exact"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PaperManifestManagerInstallationProofError(
            "Shreks deployment sudoers is not UTF-8"
        ) from error
    lines = tuple(
        line.strip() for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if lines != (_SUDOERS_LINE,):
        raise PaperManifestManagerInstallationProofError(
            "Shreks deployment sudoers authority is not the exact sealed command"
        )
    return {
        "path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload), "uid": meta.st_uid, "gid": meta.st_gid, "mode": "0440",
    }


def _service_observations(runner: CommandRunner) -> list[dict[str, object]]:
    values = [_service_observation(unit, runner) for unit in _UNITS]
    return sorted(values, key=lambda item: item["unit"])


def _service_observation(unit: str, runner: CommandRunner) -> dict[str, object]:
    result = runner((
        "systemctl", "show", unit,
        "--property=" + ",".join(_PROPERTIES), "--no-pager",
    ))
    if type(result) is not HostCommandResult or result.returncode != 0:
        raise PaperManifestManagerInstallationProofError(
            f"could not inspect service state for {unit}"
        )
    fields = _key_values(result.stdout)
    if set(fields) != set(_PROPERTIES):
        raise PaperManifestManagerInstallationProofError(
            f"service state fields are incomplete for {unit}"
        )
    numbers = {
        name: _non_negative_int(fields[name], name)
        for name in (
            "NRestarts", "MainPID", "ExecMainStatus", "ActiveEnterTimestampMonotonic"
        )
    }
    if (
        fields["ActiveState"] != "active" or fields["SubState"] != "running"
        or numbers["MainPID"] <= 0 or numbers["ExecMainStatus"] != 0
        or numbers["ActiveEnterTimestampMonotonic"] <= 0
    ):
        raise PaperManifestManagerInstallationProofError(
            f"service is not healthy for installation proof: {unit}"
        )
    return {
        "unit": unit, "active_state": fields["ActiveState"],
        "sub_state": fields["SubState"], "n_restarts": numbers["NRestarts"],
        "main_pid": numbers["MainPID"], "exec_main_status": numbers["ExecMainStatus"],
        "active_enter_timestamp_monotonic": numbers["ActiveEnterTimestampMonotonic"],
    }


def _key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key in result:
            raise PaperManifestManagerInstallationProofError(
                "systemd service state output is malformed"
            )
        result[key] = value
    return result


def _non_negative_int(value: str, label: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as error:
        raise PaperManifestManagerInstallationProofError(
            f"{label} is not an integer"
        ) from error
    if parsed < 0:
        raise PaperManifestManagerInstallationProofError(
            f"{label} must be non-negative"
        )
    return parsed


def _decode_prestate(payload: bytes) -> dict[str, object]:
    raw = _decode(payload, "preinstall snapshot")
    if raw.get("schema_name") != _PRE_SCHEMA or raw.get("schema_version") != 1:
        raise PaperManifestManagerInstallationProofError(
            "preinstall snapshot schema is unsupported"
        )
    if raw.get("snapshot_fingerprint_sha256") != _fingerprint(
        raw, "snapshot_fingerprint_sha256"
    ):
        raise PaperManifestManagerInstallationProofError(
            "preinstall snapshot fingerprint is invalid"
        )
    return raw


def _decode_receipt(payload: bytes) -> dict[str, object]:
    raw = _decode(payload, "installer receipt")
    if (
        raw.get("schema_name") != installer._RECEIPT_SCHEMA_NAME
        or raw.get("schema_version") != installer._RECEIPT_SCHEMA_VERSION
        or raw.get("status") not in ("INSTALLED", "ALREADY_INSTALLED")
    ):
        raise PaperManifestManagerInstallationProofError(
            "installer receipt schema or status is invalid"
        )
    return raw


def _decode(payload: bytes, label: str) -> dict[str, object]:
    try:
        raw = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaperManifestManagerInstallationProofError(
            f"{label} is not valid canonical JSON"
        ) from error
    if not isinstance(raw, dict) or _canonical(raw) != payload:
        raise PaperManifestManagerInstallationProofError(
            f"{label} must be a canonical JSON object"
        )
    return raw


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PaperManifestManagerInstallationProofError(
                "JSON objects must not contain duplicate keys"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise PaperManifestManagerInstallationProofError(
        f"non-finite JSON constant is not allowed: {value}"
    )


def _require_release_fields(document: dict[str, object], material: dict[str, object], label: str) -> None:
    for key in (
        "release_source_sha", "release_directory", "wheel_relative_path",
        "wheel_sha256", "manager_sha256",
    ):
        if document.get(key) != material[key]:
            raise PaperManifestManagerInstallationProofError(
                f"{label} does not match current sealed release: {key}"
            )


def _require_receipt(receipt: dict[str, object], material: dict[str, object], paths: ProofPaths) -> None:
    expected = {
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "wheel_member": installer._MANAGER_MEMBER,
        "manager_sha256": material["manager_sha256"],
        "destination": str(paths.manager_destination),
        "destination_uid": _ROOT_UID, "destination_gid": _ROOT_GID,
        "destination_mode": "0755",
        "installation_authority": "EXERCISED_EXACT_RELEASE_BOUND_HELPER_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED", "live_authority": "DISABLED",
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise PaperManifestManagerInstallationProofError(
                f"installer receipt does not match sealed installation: {key}"
            )


def _fingerprint(document: dict[str, object], field: str) -> str:
    copy = dict(document)
    copy[field] = _ZERO_SHA256
    return hashlib.sha256(_canonical(copy)).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _default_runner(command: tuple[str, ...]) -> HostCommandResult:
    allowed = (
        len(command) == 5 and command[0:2] == ("systemctl", "show")
        and command[2] in _UNITS
        and command[3] == "--property=" + ",".join(_PROPERTIES)
        and command[4] == "--no-pager"
    )
    if not allowed:
        raise PaperManifestManagerInstallationProofError(
            "installation proof system command is not allowlisted"
        )
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, shell=False
    )
    return HostCommandResult(completed.returncode, completed.stdout)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and verify read-only evidence around exact release-bound helper installation."
    )
    subs = parser.add_subparsers(dest="command", required=True)
    prepare = subs.add_parser("prepare")
    prepare.add_argument("expected_release_source_sha")
    verify = subs.add_parser("verify")
    verify.add_argument("expected_release_source_sha")
    verify.add_argument("preinstall_snapshot")
    verify.add_argument("installer_receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = capture_preinstall_state(
                expected_release_source_sha=args.expected_release_source_sha,
                paths=_production_paths(),
            )
        else:
            before, _ = installer._read_regular_no_follow(
                Path(args.preinstall_snapshot), label="preinstall snapshot"
            )
            receipt, _ = installer._read_regular_no_follow(
                Path(args.installer_receipt), label="installer receipt"
            )
            result = verify_postinstall_state(
                expected_release_source_sha=args.expected_release_source_sha,
                preinstall_payload=before,
                installer_receipt_payload=receipt,
                paths=_production_paths(),
            )
    except (
        PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError, TypeError, ValueError,
    ) as error:
        sys.stderr.buffer.write(_canonical({
            "schema_name": _PROOF_SCHEMA, "schema_version": 1, "status": "FAILED",
            "error_type": type(error).__name__,
            "manifest_rotation_authority": "NOT_GRANTED",
            "scoring_authority": "NOT_GRANTED",
            "paper_promotion_authority": "BLOCKED", "live_authority": "DISABLED",
        }))
        return 1
    sys.stdout.buffer.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
