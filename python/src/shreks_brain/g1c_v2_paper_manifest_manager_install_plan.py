from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import g1c_v2_paper_manifest_manager_installation_proof as proof
from shreks_brain import g1c_v2_paper_manifest_manager_status as manager_status


_SCHEMA_NAME = "shreks.g1c_v2_paper_manifest_manager_install_plan"
_SCHEMA_VERSION = 1
_ZERO_SHA256 = "0" * 64
_PROOF_MODULE = "shreks_brain.g1c_v2_paper_manifest_manager_installation_proof"
_INSTALL_MODULE = "shreks_brain.g1c_v2_paper_manifest_manager_install"


class PaperManifestManagerInstallPlanError(RuntimeError):
    """Raised when one first-install administrator ceremony is not ready to plan."""


@dataclass(frozen=True, slots=True)
class PaperManifestManagerInstallPlanPaths:
    current_link: Path
    campaign_manifest: Path
    deploy_sudoers: Path
    manager_destination: Path
    evidence_root: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "campaign_manifest",
            "deploy_sudoers",
            "manager_destination",
            "evidence_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise PaperManifestManagerInstallPlanError(
                    f"{name} must be an absolute Path"
                )


def build_release_bound_paper_manifest_manager_install_plan(
    *,
    expected_release_source_sha: str,
    paths: PaperManifestManagerInstallPlanPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: proof.CommandRunner | None = None,
) -> dict[str, object]:
    if type(paths) is not PaperManifestManagerInstallPlanPaths:
        raise PaperManifestManagerInstallPlanError(
            "plan paths must be an exact PaperManifestManagerInstallPlanPaths"
        )
    if os.geteuid() != 0:
        raise PaperManifestManagerInstallPlanError(
            "PAPER manifest manager install planning requires root"
        )

    try:
        expected_sha = installer._validate_source_sha(expected_release_source_sha)
    except (installer.PaperManifestManagerInstallError, TypeError, ValueError) as error:
        raise PaperManifestManagerInstallPlanError(
            "expected release source SHA is invalid"
        ) from error

    proof_paths = proof.ProofPaths(
        current_link=paths.current_link,
        campaign_manifest=paths.campaign_manifest,
        deploy_sudoers=paths.deploy_sudoers,
        manager_destination=paths.manager_destination,
    )
    status_paths = manager_status.PaperManifestManagerStatusPaths(
        current_link=paths.current_link,
        destination=paths.manager_destination,
    )

    runtime = Path(sys.executable if runtime_executable is None else runtime_executable)
    before_status = _helper_status(
        expected_sha,
        status_paths,
        runtime,
    )
    if before_status["status"] != "ABSENT":
        raise PaperManifestManagerInstallPlanError(
            "trusted-administrator first-install plan requires helper status ABSENT"
        )

    evidence_dir = paths.evidence_root / (
        f"shreks-paper-manifest-manager-install-{expected_sha}"
    )
    _require_absent_path(evidence_dir, "installation evidence directory")

    runner = proof._default_runner if command_runner is None else command_runner
    try:
        preflight = proof.capture_preinstall_state(
            expected_release_source_sha=expected_sha,
            paths=proof_paths,
            runtime_executable=runtime,
            command_runner=runner,
        )
    except (
        proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestManagerInstallPlanError(
            "installation proof preflight is not ready"
        ) from error

    after_status = _helper_status(
        expected_sha,
        status_paths,
        runtime,
    )
    if after_status != before_status:
        raise PaperManifestManagerInstallPlanError(
            "helper status changed during install-plan preflight"
        )
    _require_absent_path(evidence_dir, "installation evidence directory")

    release_dir = Path(str(before_status["release_directory"]))
    try:
        resolved_runtime = runtime.resolve(strict=True)
    except OSError as error:
        raise PaperManifestManagerInstallPlanError(
            "release runtime executable could not be resolved"
        ) from error
    expected_runtime = release_dir / ".venv" / "bin" / "python"
    if resolved_runtime != expected_runtime.resolve(strict=True):
        raise PaperManifestManagerInstallPlanError(
            "install plan runtime does not match exact current release"
        )

    pre_path = evidence_dir / "installation-proof-pre.json"
    receipt_path = evidence_dir / "installer-receipt.json"
    final_path = evidence_dir / "installation-proof.json"

    document: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": "READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY",
        "release_source_sha": expected_sha,
        "release_directory": str(release_dir),
        "runtime_python": str(resolved_runtime),
        "wheel_relative_path": before_status["wheel_relative_path"],
        "wheel_sha256": before_status["wheel_sha256"],
        "manager_sha256": before_status["expected_manager_sha256"],
        "manager_destination": str(paths.manager_destination),
        "helper_status": "ABSENT",
        "preflight_snapshot_fingerprint_sha256": preflight[
            "snapshot_fingerprint_sha256"
        ],
        "campaign_manifest_sha256": preflight["campaign_manifest"]["sha256"],
        "deploy_sudoers_sha256": preflight["deploy_sudoers"]["sha256"],
        "service_observations": preflight["services"],
        "evidence_directory": str(evidence_dir),
        "evidence_directory_mode": "0700",
        "required_umask": "0077",
        "installation_proof_pre_path": str(pre_path),
        "installer_receipt_path": str(receipt_path),
        "installation_proof_path": str(final_path),
        "steps": [
            {
                "name": "create_evidence_directory",
                "argv": [
                    "install",
                    "-d",
                    "-o",
                    "root",
                    "-g",
                    "root",
                    "-m",
                    "0700",
                    str(evidence_dir),
                ],
                "stdout_path": None,
            },
            {
                "name": "prepare_installation_proof",
                "argv": [
                    str(resolved_runtime),
                    "-m",
                    _PROOF_MODULE,
                    "prepare",
                    expected_sha,
                ],
                "stdout_path": str(pre_path),
            },
            {
                "name": "install_exact_release_bound_helper",
                "argv": [
                    str(resolved_runtime),
                    "-m",
                    _INSTALL_MODULE,
                    expected_sha,
                ],
                "stdout_path": str(receipt_path),
            },
            {
                "name": "verify_installation_proof",
                "argv": [
                    str(resolved_runtime),
                    "-m",
                    _PROOF_MODULE,
                    "verify",
                    expected_sha,
                    str(pre_path),
                    str(receipt_path),
                ],
                "stdout_path": str(final_path),
            },
        ],
        "stop_on_any_failure": True,
        "plan_preflight_is_not_installation_proof": True,
        "planning_authority": "READ_ONLY",
        "installation_authority": "NOT_EXERCISED",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
        "plan_fingerprint_sha256": _ZERO_SHA256,
    }
    document["plan_fingerprint_sha256"] = _fingerprint(
        document,
        "plan_fingerprint_sha256",
    )
    return document


def _helper_status(
    expected_sha: str,
    paths: manager_status.PaperManifestManagerStatusPaths,
    runtime: Path,
) -> dict[str, object]:
    try:
        return manager_status.inspect_release_bound_paper_manifest_manager_status(
            expected_release_source_sha=expected_sha,
            paths=paths,
            runtime_executable=runtime,
        )
    except (
        manager_status.PaperManifestManagerStatusError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestManagerInstallPlanError(
            "release-bound helper status could not be established"
        ) from error


def _require_absent_path(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise PaperManifestManagerInstallPlanError(
            f"{label} could not be inspected"
        ) from error
    raise PaperManifestManagerInstallPlanError(
        f"{label} must not already exist"
    )


def _fingerprint(document: dict[str, object], field: str) -> str:
    copy = dict(document)
    copy[field] = _ZERO_SHA256
    return hashlib.sha256(_canonical(copy)).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _production_paths() -> PaperManifestManagerInstallPlanPaths:
    return PaperManifestManagerInstallPlanPaths(
        current_link=Path("/opt/shreks/current"),
        campaign_manifest=Path("/etc/shreks/paper-campaign.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
        evidence_root=Path("/root"),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a read-only exact-release trusted-administrator first-install "
            "ceremony plan for the PAPER manifest manager helper."
        )
    )
    parser.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = build_release_bound_paper_manifest_manager_install_plan(
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        PaperManifestManagerInstallPlanError,
        proof.PaperManifestManagerInstallationProofError,
        manager_status.PaperManifestManagerStatusError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.buffer.write(
            _canonical(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "status": "NOT_READY",
                    "error_type": type(error).__name__,
                    "planning_authority": "READ_ONLY",
                    "installation_authority": "NOT_EXERCISED",
                    "manifest_rotation_authority": "NOT_GRANTED",
                    "scoring_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1
    sys.stdout.buffer.write(_canonical(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
