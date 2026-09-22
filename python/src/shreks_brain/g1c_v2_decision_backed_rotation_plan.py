from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import g1c_v2_paper_manifest_manager_installation_proof as install_proof
from shreks_brain import g1c_v2_paper_manifest_manager_status as manager_status
from shreks_brain import g1c_v2_paper_manifest_rotation_readiness as standard_readiness
from shreks_brain import g1c_v2_decision_backed_rotation_readiness as decision_readiness
from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    G1CV2DecisionBackedCandidateAuthorityError,
    decode_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    G1CV2RuntimeManifestTransitionBindingError,
    decode_g1c_v2_runtime_manifest_transition_binding,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


_SCHEMA_NAME = "shreks.g1c_v2_decision_backed_rotation_plan"
_SCHEMA_VERSION = 1
_READY_STATUS = "READY_FOR_TRUSTED_ADMIN_ROTATION_CEREMONY"
_ZERO_SHA256 = "0" * 64

_READINESS_KEYS = {
    "schema_name",
    "schema_version",
    "status",
    "release_source_sha",
    "release_directory",
    "wheel_relative_path",
    "wheel_sha256",
    "manager_sha256",
    "manager_destination",
    "installation_proof_fingerprint_sha256",
    "deploy_sudoers_sha256",
    "source_manifest_sha256",
    "source_runtime_manifest_fingerprint_sha256",
    "source_paper_run_id",
    "source_quote_asset_mint",
    "candidate_manifest_sha256",
    "candidate_runtime_manifest_fingerprint_sha256",
    "candidate_paper_run_id",
    "candidate_start_at_unix_ms",
    "candidate_quote_asset_mint",
    "candidate_quote_asset_decimals",
    "binding_fingerprint_sha256",
    "risk_control_revision",
    "risk_control_halt_new_entries",
    "risk_control_kill_switch_active",
    "services",
    "candidate_preflight_status",
    "runtime_env_contract",
    "service_lifecycle_unchanged",
    "readiness_fingerprint_sha256",
    "installation_authority",
    "manifest_rotation_authority",
    "scoring_authority",
    "paper_promotion_authority",
    "live_authority",
}


class DecisionBackedRotationPlanError(RuntimeError):
    """Raised when one protected PAPER rotation ceremony is not safe to plan."""


@dataclass(frozen=True, slots=True)
class DecisionBackedRotationPlanPaths:
    current_link: Path
    active_manifest_path: Path
    env_file: Path
    observer_database_path: Path
    evidence_path: Path
    risk_control_path: Path
    deploy_sudoers: Path
    manager_destination: Path
    rotation_evidence_root: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "active_manifest_path",
            "env_file",
            "observer_database_path",
            "evidence_path",
            "risk_control_path",
            "deploy_sudoers",
            "manager_destination",
            "rotation_evidence_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise DecisionBackedRotationPlanError(
                    f"{name} must be an absolute Path"
                )


def build_decision_backed_paper_manifest_rotation_plan(
    *,
    candidate_runtime_manifest_path: str | Path,
    transition_binding_path: str | Path,
    decision_backed_candidate_authority_path: str | Path,
    readiness_receipt_path: str | Path,
    expected_release_source_sha: str,
    paths: DecisionBackedRotationPlanPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_runner: install_proof.CommandRunner | None = None,
) -> dict[str, object]:
    if type(paths) is not DecisionBackedRotationPlanPaths:
        raise DecisionBackedRotationPlanError(
            "plan paths must be an exact DecisionBackedRotationPlanPaths"
        )
    if os.geteuid() != 0:
        raise DecisionBackedRotationPlanError(
            "decision-backed rotation planning requires root"
        )

    try:
        expected_sha = installer._validate_source_sha(
            expected_release_source_sha
        )
    except (
        installer.PaperManifestManagerInstallError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            "expected release source SHA is invalid"
        ) from error

    candidate_path = _resolve_existing_regular_file(
        candidate_runtime_manifest_path,
        label="candidate runtime manifest",
    )
    binding_path = _resolve_existing_regular_file(
        transition_binding_path,
        label="transition binding",
    )
    authority_path = _resolve_existing_regular_file(
        decision_backed_candidate_authority_path,
        label="decision-backed candidate authority",
    )
    readiness_path = _resolve_existing_regular_file(
        readiness_receipt_path,
        label="decision-backed rotation readiness receipt",
    )

    candidate_payload = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    binding_payload = _read_regular_file_stable(
        binding_path,
        label="transition binding",
    )
    authority_payload = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )
    readiness_payload = _read_regular_file_stable(
        readiness_path,
        label="decision-backed rotation readiness receipt",
    )

    try:
        candidate = decode_observer_paper_campaign_runtime_manifest(
            candidate_payload
        )
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise DecisionBackedRotationPlanError(
            f"candidate runtime manifest authentication failed: {error}"
        ) from error
    if (
        candidate.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        raise DecisionBackedRotationPlanError(
            "candidate runtime manifest must be canonical v2"
        )

    try:
        binding = decode_g1c_v2_runtime_manifest_transition_binding(
            binding_payload.decode("utf-8")
        )
    except (
        G1CV2RuntimeManifestTransitionBindingError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            f"transition binding authentication failed: {error}"
        ) from error

    try:
        authority = decode_g1c_v2_decision_backed_candidate_authority(
            authority_payload.decode("utf-8")
        )
    except (
        G1CV2DecisionBackedCandidateAuthorityError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            "decision-backed candidate authority authentication failed: "
            f"{error}"
        ) from error

    try:
        decision_readiness._require_candidate_matches_authority(
            candidate_payload=candidate_payload,
            candidate=candidate,
            authority=authority,
        )
        decision_readiness._require_binding_matches_authority(
            binding,
            authority,
        )
    except decision_readiness.G1CV2DecisionBackedRotationReadinessError as error:
        raise DecisionBackedRotationPlanError(
            f"decision-backed candidate or binding provenance is invalid: {error}"
        ) from error

    readiness = _decode_readiness_receipt(readiness_payload)
    try:
        decision_readiness._require_receipt_matches_authority(
            receipt=readiness,
            authority=authority,
            binding=binding,
            expected_release_source_sha=expected_sha,
        )
    except decision_readiness.G1CV2DecisionBackedRotationReadinessError as error:
        raise DecisionBackedRotationPlanError(
            f"readiness receipt does not match decision-backed authority: {error}"
        ) from error
    _require_readiness_semantics(readiness)

    runtime = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    status_paths = manager_status.PaperManifestManagerStatusPaths(
        current_link=paths.current_link,
        destination=paths.manager_destination,
    )
    status_before = _manager_status(
        expected_sha=expected_sha,
        paths=status_paths,
        runtime=runtime,
    )
    _require_status_matches_readiness(
        status=status_before,
        readiness=readiness,
        expected_sha=expected_sha,
    )

    readiness_paths = standard_readiness.PaperManifestRotationReadinessPaths(
        current_link=paths.current_link,
        env_file=paths.env_file,
        active_manifest_path=paths.active_manifest_path,
        observer_database_path=paths.observer_database_path,
        evidence_path=paths.evidence_path,
        risk_control_path=paths.risk_control_path,
        deploy_sudoers=paths.deploy_sudoers,
        manager_destination=paths.manager_destination,
    )

    try:
        standard_readiness._load_and_verify_inputs(
            active_manifest_path=paths.active_manifest_path,
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            expected_binding_fingerprint_sha256=binding[
                "binding_fingerprint_sha256"
            ],
        )
        standard_readiness._require_runtime_env_contract(readiness_paths)
    except (
        standard_readiness.PaperManifestRotationReadinessError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            f"protected rotation inputs are not currently ready: {error}"
        ) from error

    try:
        sudoers_before = install_proof._sudoers_observation(
            paths.deploy_sudoers
        )
    except (
        install_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            "deployment sudoers could not be observed safely"
        ) from error
    if (
        sudoers_before.get("sha256")
        != readiness["deploy_sudoers_sha256"]
    ):
        raise DecisionBackedRotationPlanError(
            "deployment sudoers changed since readiness proof"
        )

    risk_before = _risk_state(paths.risk_control_path)
    _require_risk_matches_readiness(risk_before, readiness)

    runner = (
        install_proof._default_runner
        if service_runner is None
        else service_runner
    )
    services_before = _services(runner)
    if services_before != readiness["services"]:
        raise DecisionBackedRotationPlanError(
            "protected service observations changed since readiness proof"
        )

    evidence_dir = (
        paths.rotation_evidence_root
        / str(binding["binding_fingerprint_sha256"])
    )
    _require_absent_path(
        evidence_dir,
        "rotation evidence directory",
    )

    candidate_after = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    binding_after = _read_regular_file_stable(
        binding_path,
        label="transition binding",
    )
    authority_after = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )
    readiness_after = _read_regular_file_stable(
        readiness_path,
        label="decision-backed rotation readiness receipt",
    )
    if candidate_after != candidate_payload:
        raise DecisionBackedRotationPlanError(
            "candidate runtime manifest changed during rotation planning"
        )
    if binding_after != binding_payload:
        raise DecisionBackedRotationPlanError(
            "transition binding changed during rotation planning"
        )
    if authority_after != authority_payload:
        raise DecisionBackedRotationPlanError(
            "decision-backed candidate authority changed during rotation planning"
        )
    if readiness_after != readiness_payload:
        raise DecisionBackedRotationPlanError(
            "readiness receipt changed during rotation planning"
        )

    status_after = _manager_status(
        expected_sha=expected_sha,
        paths=status_paths,
        runtime=runtime,
    )
    if status_after != status_before:
        raise DecisionBackedRotationPlanError(
            "release-bound manager status changed during rotation planning"
        )
    try:
        standard_readiness._require_runtime_env_contract(readiness_paths)
        sudoers_after = install_proof._sudoers_observation(
            paths.deploy_sudoers
        )
    except (
        standard_readiness.PaperManifestRotationReadinessError,
        install_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            "protected host state changed during rotation planning"
        ) from error
    if sudoers_after != sudoers_before:
        raise DecisionBackedRotationPlanError(
            "deployment sudoers changed during rotation planning"
        )

    risk_after = _risk_state(paths.risk_control_path)
    if _risk_identity(risk_after) != _risk_identity(risk_before):
        raise DecisionBackedRotationPlanError(
            "operator risk-control state changed during rotation planning"
        )
    services_after = _services(runner)
    if services_after != services_before:
        raise DecisionBackedRotationPlanError(
            "protected service observations changed during rotation planning"
        )
    _require_absent_path(
        evidence_dir,
        "rotation evidence directory",
    )

    document: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _READY_STATUS,
        "release_source_sha": expected_sha,
        "release_directory": status_before["release_directory"],
        "manager_destination": str(paths.manager_destination),
        "manager_sha256": status_before["expected_manager_sha256"],
        "authority_fingerprint_sha256": authority[
            "authority_fingerprint_sha256"
        ],
        "readiness_fingerprint_sha256": readiness[
            "readiness_fingerprint_sha256"
        ],
        "source_manifest_sha256": authority["source_manifest_sha256"],
        "source_runtime_manifest_fingerprint_sha256": authority[
            "source_runtime_manifest_fingerprint_sha256"
        ],
        "source_paper_run_id": authority["source_paper_run_id"],
        "candidate_manifest_sha256": authority["candidate_manifest_sha256"],
        "candidate_runtime_manifest_fingerprint_sha256": authority[
            "candidate_runtime_manifest_fingerprint_sha256"
        ],
        "candidate_paper_run_id": authority["candidate_paper_run_id"],
        "binding_fingerprint_sha256": binding[
            "binding_fingerprint_sha256"
        ],
        "rotation_evidence_directory": str(evidence_dir),
        "rotation_evidence_directory_status": "ABSENT",
        "steps": [
            {
                "name": "trusted_admin_rotate_protected_paper_manifest",
                "argv": [
                    str(paths.manager_destination),
                    "rotate",
                    str(candidate_path),
                    str(binding_path),
                    binding["binding_fingerprint_sha256"],
                    expected_sha,
                ],
                "requires_explicit_root_invocation": True,
                "executed_by_planner": False,
            }
        ],
        "stop_on_any_failure": True,
        "planning_authority": "READ_ONLY",
        "manifest_rotation_authority": "NOT_EXERCISED",
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


def _decode_readiness_receipt(payload: bytes) -> dict[str, object]:
    try:
        text = payload.decode("utf-8")
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        DecisionBackedRotationPlanError,
    ) as error:
        if isinstance(error, DecisionBackedRotationPlanError):
            raise
        raise DecisionBackedRotationPlanError(
            "readiness receipt is not valid canonical JSON"
        ) from error
    if not isinstance(document, dict) or _canonical(document) != payload:
        raise DecisionBackedRotationPlanError(
            "readiness receipt must be a canonical JSON object"
        )
    if set(document) != _READINESS_KEYS:
        raise DecisionBackedRotationPlanError(
            "readiness receipt has unknown or missing fields"
        )
    if (
        document.get("schema_name")
        != standard_readiness._SCHEMA_NAME
        or document.get("schema_version")
        != standard_readiness._SCHEMA_VERSION
    ):
        raise DecisionBackedRotationPlanError(
            "readiness receipt schema is unsupported"
        )
    if (
        document.get("readiness_fingerprint_sha256")
        != standard_readiness._fingerprint(
            document,
            "readiness_fingerprint_sha256",
        )
    ):
        raise DecisionBackedRotationPlanError(
            "readiness receipt fingerprint is invalid"
        )
    return document


def _require_readiness_semantics(
    readiness: dict[str, object],
) -> None:
    expected = {
        "status": "READY_EVIDENCE_ONLY",
        "candidate_preflight_status": "PASSED",
        "runtime_env_contract": "MATCHED",
        "service_lifecycle_unchanged": True,
        "installation_authority": "PROVEN",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    for field, value in expected.items():
        if readiness.get(field) != value:
            raise DecisionBackedRotationPlanError(
                f"readiness receipt {field} is not acceptable"
            )


def _require_status_matches_readiness(
    *,
    status: dict[str, object],
    readiness: dict[str, object],
    expected_sha: str,
) -> None:
    expected = {
        "status": "MATCHED_CURRENT_RELEASE",
        "release_source_sha": expected_sha,
        "release_directory": readiness["release_directory"],
        "wheel_relative_path": readiness["wheel_relative_path"],
        "wheel_sha256": readiness["wheel_sha256"],
        "expected_manager_sha256": readiness["manager_sha256"],
        "destination": readiness["manager_destination"],
        "observation_authority": "READ_ONLY",
        "installation_authority": "NOT_EXERCISED",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    for field, value in expected.items():
        if status.get(field) != value:
            raise DecisionBackedRotationPlanError(
                f"release-bound manager status {field} does not match readiness"
            )


def _manager_status(
    *,
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
        raise DecisionBackedRotationPlanError(
            "release-bound manager status could not be established"
        ) from error


def _risk_state(path: Path):
    try:
        return standard_readiness._load_risk_state(path)
    except (
        standard_readiness.PaperManifestRotationReadinessError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            "operator risk-control state could not be established"
        ) from error


def _risk_identity(state) -> tuple[object, object, object]:
    return (
        state.revision,
        state.halt_new_entries,
        state.kill_switch_active,
    )


def _require_risk_matches_readiness(
    state,
    readiness: dict[str, object],
) -> None:
    expected = (
        readiness["risk_control_revision"],
        readiness["risk_control_halt_new_entries"],
        readiness["risk_control_kill_switch_active"],
    )
    if _risk_identity(state) != expected:
        raise DecisionBackedRotationPlanError(
            "operator risk-control state changed since readiness proof"
        )


def _services(
    runner: install_proof.CommandRunner,
) -> list[dict[str, object]]:
    try:
        return standard_readiness._service_observations(runner)
    except (
        standard_readiness.PaperManifestRotationReadinessError,
        install_proof.PaperManifestManagerInstallationProofError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise DecisionBackedRotationPlanError(
            "protected service observations could not be established"
        ) from error


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise DecisionBackedRotationPlanError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise DecisionBackedRotationPlanError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise DecisionBackedRotationPlanError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise DecisionBackedRotationPlanError(
            f"{label} could not be read"
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != before.st_size:
        raise DecisionBackedRotationPlanError(
            f"{label} changed while being read"
        )
    return payload


def _require_absent_path(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise DecisionBackedRotationPlanError(
            f"{label} could not be inspected"
        ) from error
    raise DecisionBackedRotationPlanError(
        f"{label} must not already exist"
    )


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DecisionBackedRotationPlanError(
                "readiness receipt contains duplicate keys"
            )
        result[key] = value
    return result


def _reject_non_finite(value: str) -> object:
    raise DecisionBackedRotationPlanError(
        f"readiness receipt contains non-finite value: {value}"
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


def _production_paths() -> DecisionBackedRotationPlanPaths:
    return DecisionBackedRotationPlanPaths(
        current_link=Path("/opt/shreks/current"),
        active_manifest_path=Path("/etc/shreks/paper-campaign.json"),
        env_file=Path("/etc/shreks/shreks.env"),
        observer_database_path=Path("/var/lib/shreks/shreks.db"),
        evidence_path=Path("/var/lib/shreks/paper-evaluation-e11.json"),
        risk_control_path=Path("/var/lib/shreks/risk/operator-control.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path(
            "/usr/local/sbin/shreks-paper-manifest-manager"
        ),
        rotation_evidence_root=Path("/var/lib/shreks/manifest-rotations"),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-decision-backed-rotation-plan",
        description=(
            "Build a read-only trusted-administrator PAPER manifest rotation "
            "plan from exact decision-backed readiness evidence."
        ),
    )
    parser.add_argument("--candidate-runtime-manifest", required=True)
    parser.add_argument("--transition-binding", required=True)
    parser.add_argument(
        "--decision-backed-candidate-authority",
        required=True,
    )
    parser.add_argument("--readiness-receipt", required=True)
    parser.add_argument("--expected-release-source-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = build_decision_backed_paper_manifest_rotation_plan(
            candidate_runtime_manifest_path=args.candidate_runtime_manifest,
            transition_binding_path=args.transition_binding,
            decision_backed_candidate_authority_path=(
                args.decision_backed_candidate_authority
            ),
            readiness_receipt_path=args.readiness_receipt,
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        DecisionBackedRotationPlanError,
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
                    "manifest_rotation_authority": "NOT_EXERCISED",
                    "scoring_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1

    sys.stdout.buffer.write(_canonical(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
