from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import g1c_v2_paper_manifest_manager_installation_proof as install_proof
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


_SCHEMA_NAME = "shreks.g1c_v2_paper_manifest_rotation_readiness"
_SCHEMA_VERSION = 1
_ZERO_SHA256 = "0" * 64
_ROOT_UID = 0
_ROOT_GID = 0
_SHA256_LENGTH = 64

_ENV_KEYS = {
    "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": "observer_database_path",
    "SHREKS_PAPER_CAMPAIGN_E11_PATH": "evidence_path",
    "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": "active_manifest_path",
    "SHREKS_RISK_CONTROL_STATE_PATH": "risk_control_path",
}


class PaperManifestRotationReadinessError(RuntimeError):
    """Raised when one protected PAPER rotation is not ready to request."""


@dataclass(frozen=True, slots=True)
class PaperManifestRotationReadinessPaths:
    current_link: Path
    env_file: Path
    active_manifest_path: Path
    observer_database_path: Path
    evidence_path: Path
    risk_control_path: Path
    deploy_sudoers: Path
    manager_destination: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "env_file",
            "active_manifest_path",
            "observer_database_path",
            "evidence_path",
            "risk_control_path",
            "deploy_sudoers",
            "manager_destination",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise PaperManifestRotationReadinessError(
                    f"{name} must be an absolute Path"
                )


@dataclass(frozen=True, slots=True)
class _Inputs:
    source_payload: bytes
    source_manifest: ObserverPaperCampaignRuntimeManifest
    candidate_payload: bytes
    candidate_manifest: ObserverPaperCampaignRuntimeManifest
    binding_payload: bytes
    binding: dict[str, object]
    candidate_path: Path
    binding_path: Path


PreflightRunner = Callable[[ObserverPaperCampaignRuntimeConfig], object]


def prove_paper_manifest_rotation_readiness(
    *,
    candidate_runtime_manifest_path: str | Path,
    transition_binding_path: str | Path,
    installation_proof_payload: bytes,
    expected_binding_fingerprint_sha256: str,
    expected_release_source_sha: str,
    paths: PaperManifestRotationReadinessPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_runner: install_proof.CommandRunner | None = None,
    preflight_runner: PreflightRunner | None = None,
) -> dict[str, object]:
    if type(paths) is not PaperManifestRotationReadinessPaths:
        raise PaperManifestRotationReadinessError(
            "readiness paths must be an exact PaperManifestRotationReadinessPaths"
        )
    if os.geteuid() != 0:
        raise PaperManifestRotationReadinessError(
            "PAPER manifest rotation readiness proof requires root"
        )

    expected_binding = _require_lower_hex(
        "expected_binding_fingerprint_sha256",
        expected_binding_fingerprint_sha256,
        _SHA256_LENGTH,
    )
    try:
        expected_release = installer._validate_source_sha(expected_release_source_sha)
    except (installer.PaperManifestManagerInstallError, TypeError, ValueError) as error:
        raise PaperManifestRotationReadinessError(
            "expected release source SHA is invalid"
        ) from error

    proof_paths = install_proof.ProofPaths(
        current_link=paths.current_link,
        campaign_manifest=paths.active_manifest_path,
        deploy_sudoers=paths.deploy_sudoers,
        manager_destination=paths.manager_destination,
    )
    try:
        material = install_proof._release_material(
            expected_release,
            proof_paths,
            runtime_executable,
        )
    except (
        install_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestRotationReadinessError(
            "current immutable release could not be authenticated"
        ) from error

    installation_proof = _require_installation_proof(
        installation_proof_payload,
        material=material,
        paths=paths,
    )
    _require_installed_manager(material, paths)
    sudoers = _require_current_sudoers(
        paths.deploy_sudoers,
        installation_proof=installation_proof,
    )
    _require_runtime_env_contract(paths)
    inputs = _load_and_verify_inputs(
        active_manifest_path=paths.active_manifest_path,
        candidate_runtime_manifest_path=candidate_runtime_manifest_path,
        transition_binding_path=transition_binding_path,
        expected_binding_fingerprint_sha256=expected_binding,
    )

    risk_before = _load_risk_state(paths.risk_control_path)
    runner = install_proof._default_runner if service_runner is None else service_runner
    services_before = _service_observations(runner)
    preflight = _default_preflight_runner if preflight_runner is None else preflight_runner
    _preflight_private_candidate(
        paths=paths,
        candidate_payload=inputs.candidate_payload,
        preflight_runner=preflight,
    )

    # Re-prove every mutable external input after preflight so this receipt
    # describes one stable readiness window rather than only an initial read.
    try:
        material_after = install_proof._release_material(
            expected_release,
            proof_paths,
            runtime_executable,
        )
    except (
        install_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestRotationReadinessError(
            "current immutable release changed during readiness proof"
        ) from error
    if _material_identity(material_after) != _material_identity(material):
        raise PaperManifestRotationReadinessError(
            "current immutable release changed during readiness proof"
        )
    _require_installed_manager(material, paths)
    sudoers_after = _require_current_sudoers(
        paths.deploy_sudoers,
        installation_proof=installation_proof,
    )
    if sudoers_after != sudoers:
        raise PaperManifestRotationReadinessError(
            "deployment sudoers changed during readiness proof"
        )
    _require_runtime_env_contract(paths)
    _require_payload_unchanged(
        paths.active_manifest_path,
        inputs.source_payload,
        label="active source runtime manifest",
    )
    _require_payload_unchanged(
        inputs.candidate_path,
        inputs.candidate_payload,
        label="candidate runtime manifest",
    )
    _require_payload_unchanged(
        inputs.binding_path,
        inputs.binding_payload,
        label="transition binding",
    )
    risk_after = _load_risk_state(paths.risk_control_path)
    if risk_after != risk_before:
        raise PaperManifestRotationReadinessError(
            "operator risk-control state changed during readiness proof"
        )
    services_after = _service_observations(runner)
    if services_after != services_before:
        raise PaperManifestRotationReadinessError(
            "Shreks service lifecycle state changed during readiness proof"
        )

    source = inputs.source_manifest
    candidate = inputs.candidate_manifest
    receipt: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": "READY_EVIDENCE_ONLY",
        "release_source_sha": expected_release,
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "manager_sha256": material["manager_sha256"],
        "manager_destination": str(paths.manager_destination),
        "installation_proof_fingerprint_sha256": installation_proof[
            "proof_fingerprint_sha256"
        ],
        "deploy_sudoers_sha256": sudoers["sha256"],
        "source_manifest_sha256": hashlib.sha256(inputs.source_payload).hexdigest(),
        "source_runtime_manifest_fingerprint_sha256": (
            source.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": source.paper_run_id,
        "source_quote_asset_mint": source.policy_bundle.quote_asset.mint,
        "candidate_manifest_sha256": hashlib.sha256(
            inputs.candidate_payload
        ).hexdigest(),
        "candidate_runtime_manifest_fingerprint_sha256": (
            candidate.manifest_fingerprint_sha256
        ),
        "candidate_paper_run_id": candidate.paper_run_id,
        "candidate_start_at_unix_ms": candidate.initial_state.last_cycle_at_unix_ms,
        "candidate_quote_asset_mint": candidate.policy_bundle.quote_asset.mint,
        "candidate_quote_asset_decimals": candidate.policy_bundle.quote_asset.decimals,
        "binding_fingerprint_sha256": inputs.binding[
            "binding_fingerprint_sha256"
        ],
        "risk_control_revision": risk_before.revision,
        "risk_control_halt_new_entries": risk_before.halt_new_entries,
        "risk_control_kill_switch_active": risk_before.kill_switch_active,
        "services": services_before,
        "candidate_preflight_status": "PASSED",
        "runtime_env_contract": "MATCHED",
        "service_lifecycle_unchanged": True,
        "readiness_fingerprint_sha256": _ZERO_SHA256,
        "installation_authority": "PROVEN",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    receipt["readiness_fingerprint_sha256"] = _fingerprint(
        receipt,
        "readiness_fingerprint_sha256",
    )
    return receipt


def _production_paths() -> PaperManifestRotationReadinessPaths:
    return PaperManifestRotationReadinessPaths(
        current_link=Path("/opt/shreks/current"),
        env_file=Path("/etc/shreks/shreks.env"),
        active_manifest_path=Path("/etc/shreks/paper-campaign.json"),
        observer_database_path=Path("/var/lib/shreks/shreks.db"),
        evidence_path=Path("/var/lib/shreks/paper-evaluation-e11.json"),
        risk_control_path=Path("/var/lib/shreks/risk/operator-control.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
    )


def _require_installation_proof(
    payload: bytes,
    *,
    material: dict[str, object],
    paths: PaperManifestRotationReadinessPaths,
) -> dict[str, object]:
    try:
        document = install_proof._decode(payload, "helper installation proof")
    except install_proof.PaperManifestManagerInstallationProofError as error:
        raise PaperManifestRotationReadinessError(
            "helper installation proof is not trusted canonical JSON"
        ) from error
    if (
        document.get("schema_name") != install_proof._PROOF_SCHEMA
        or document.get("schema_version") != install_proof._SCHEMA_VERSION
        or document.get("status") != "VERIFIED"
    ):
        raise PaperManifestRotationReadinessError(
            "helper installation proof schema or status is invalid"
        )
    if document.get("proof_fingerprint_sha256") != install_proof._fingerprint(
        document,
        "proof_fingerprint_sha256",
    ):
        raise PaperManifestRotationReadinessError(
            "helper installation proof fingerprint is invalid"
        )
    expected = {
        "release_source_sha": material["release_source_sha"],
        "release_directory": material["release_directory"],
        "wheel_relative_path": material["wheel_relative_path"],
        "wheel_sha256": material["wheel_sha256"],
        "manager_sha256": material["manager_sha256"],
        "manager_destination": str(paths.manager_destination),
        "destination_uid": _ROOT_UID,
        "destination_gid": _ROOT_GID,
        "destination_mode": "0755",
        "campaign_manifest_unchanged": True,
        "deploy_sudoers_unchanged": True,
        "service_lifecycle_unchanged": True,
        "installation_authority": "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise PaperManifestRotationReadinessError(
                f"helper installation proof does not match current authority: {key}"
            )
    return document


def _require_installed_manager(
    material: dict[str, object],
    paths: PaperManifestRotationReadinessPaths,
) -> None:
    try:
        payload, metadata = installer._read_regular_no_follow(
            paths.manager_destination,
            label="installed PAPER manifest manager",
        )
    except installer.PaperManifestManagerInstallError as error:
        raise PaperManifestRotationReadinessError(
            "installed PAPER manifest manager is unavailable or unsafe"
        ) from error
    if payload != material["manager_payload"]:
        raise PaperManifestRotationReadinessError(
            "installed PAPER manifest manager bytes do not match sealed release"
        )
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != _ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o755
    ):
        raise PaperManifestRotationReadinessError(
            "installed PAPER manifest manager metadata is not exact"
        )


def _require_current_sudoers(
    path: Path,
    *,
    installation_proof: dict[str, object],
) -> dict[str, object]:
    try:
        observed = install_proof._sudoers_observation(path)
    except (
        install_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
    ) as error:
        raise PaperManifestRotationReadinessError(
            "deployment sudoers no longer matches the sealed narrow authority"
        ) from error
    if observed["sha256"] != installation_proof.get("deploy_sudoers_sha256"):
        raise PaperManifestRotationReadinessError(
            "deployment sudoers changed since helper installation proof"
        )
    return observed


def _require_runtime_env_contract(
    paths: PaperManifestRotationReadinessPaths,
) -> None:
    try:
        payload, _ = installer._read_regular_no_follow(
            paths.env_file,
            label="runtime environment file",
        )
        text = payload.decode("utf-8")
    except (
        installer.PaperManifestManagerInstallError,
        UnicodeDecodeError,
    ) as error:
        raise PaperManifestRotationReadinessError(
            "runtime environment file is not safely readable UTF-8"
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
            raise PaperManifestRotationReadinessError(
                f"runtime environment contains duplicate {key}"
            )
        observed[key] = value.strip()
    for key, expected in required.items():
        if observed.get(key) != expected:
            raise PaperManifestRotationReadinessError(
                f"runtime environment {key} does not match protected rotation path"
            )


def _load_and_verify_inputs(
    *,
    active_manifest_path: Path,
    candidate_runtime_manifest_path: str | Path,
    transition_binding_path: str | Path,
    expected_binding_fingerprint_sha256: str,
) -> _Inputs:
    source_path = _regular_path(active_manifest_path, "active source runtime manifest")
    candidate_path = _regular_path(
        candidate_runtime_manifest_path,
        "candidate runtime manifest",
    )
    binding_path = _regular_path(transition_binding_path, "transition binding")
    if candidate_path == source_path:
        raise PaperManifestRotationReadinessError(
            "candidate runtime manifest must not be the active manifest path"
        )

    source_payload, source_meta = _stable_read(source_path, "active source runtime manifest")
    if stat.S_IMODE(source_meta.st_mode) != 0o640:
        raise PaperManifestRotationReadinessError(
            "active runtime manifest permissions must be 0640"
        )
    candidate_payload, _ = _stable_read(candidate_path, "candidate runtime manifest")
    binding_payload, _ = _stable_read(binding_path, "transition binding")

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
        raise PaperManifestRotationReadinessError(
            "rotation source, candidate, or binding authentication failed"
        ) from error

    if source.schema_version != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION:
        raise PaperManifestRotationReadinessError(
            "active source runtime manifest must be canonical v1 authority"
        )
    if candidate.schema_version != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2:
        raise PaperManifestRotationReadinessError(
            "candidate runtime manifest must be canonical v2"
        )
    if binding["binding_fingerprint_sha256"] != expected_binding_fingerprint_sha256:
        raise PaperManifestRotationReadinessError(
            "transition binding fingerprint does not match explicit operator evidence"
        )

    checks = (
        ("source_manifest_sha256", hashlib.sha256(source_payload).hexdigest()),
        (
            "source_runtime_manifest_fingerprint_sha256",
            source.manifest_fingerprint_sha256,
        ),
        ("source_paper_run_id", source.paper_run_id),
        ("source_quote_asset_mint", source.policy_bundle.quote_asset.mint),
        ("candidate_manifest_sha256", hashlib.sha256(candidate_payload).hexdigest()),
        (
            "candidate_runtime_manifest_fingerprint_sha256",
            candidate.manifest_fingerprint_sha256,
        ),
        ("candidate_paper_run_id", candidate.paper_run_id),
        ("candidate_start_at_unix_ms", candidate.initial_state.last_cycle_at_unix_ms),
        ("candidate_quote_asset_mint", candidate.policy_bundle.quote_asset.mint),
        ("candidate_quote_asset_decimals", candidate.policy_bundle.quote_asset.decimals),
    )
    for name, expected in checks:
        if binding.get(name) != expected:
            raise PaperManifestRotationReadinessError(
                f"transition binding {name} does not match protected rotation input"
            )

    return _Inputs(
        source_payload=source_payload,
        source_manifest=source,
        candidate_payload=candidate_payload,
        candidate_manifest=candidate,
        binding_payload=binding_payload,
        binding=binding,
        candidate_path=candidate_path,
        binding_path=binding_path,
    )


def _regular_path(raw_path: str | Path, label: str) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise PaperManifestRotationReadinessError(f"{label} path is invalid") from error
    if path.is_symlink() or not path.is_file():
        raise PaperManifestRotationReadinessError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve()
    except OSError as error:
        raise PaperManifestRotationReadinessError(
            f"{label} could not be resolved"
        ) from error


def _stable_read(path: Path, label: str) -> tuple[bytes, os.stat_result]:
    try:
        return installer._read_regular_no_follow(path, label=label)
    except installer.PaperManifestManagerInstallError as error:
        raise PaperManifestRotationReadinessError(
            f"{label} could not be read stably"
        ) from error


def _require_payload_unchanged(path: Path, expected: bytes, *, label: str) -> None:
    payload, _ = _stable_read(path, label)
    if payload != expected:
        raise PaperManifestRotationReadinessError(
            f"{label} changed during readiness proof"
        )


def _load_risk_state(path: Path):
    try:
        return load_operator_risk_control_state(path)
    except (RiskControlStateError, OSError, TypeError, ValueError) as error:
        raise PaperManifestRotationReadinessError(
            "operator risk-control state is not readable and valid"
        ) from error


def _service_observations(
    runner: install_proof.CommandRunner,
) -> list[dict[str, object]]:
    try:
        return install_proof._service_observations(runner)
    except install_proof.PaperManifestManagerInstallationProofError as error:
        raise PaperManifestRotationReadinessError(
            "protected PAPER runtime services are not healthy"
        ) from error


def _default_preflight_runner(
    config: ObserverPaperCampaignRuntimeConfig,
) -> object:
    return preflight_observer_paper_campaign_runtime(
        config,
        status_sink=lambda _line: None,
    )


def _preflight_private_candidate(
    *,
    paths: PaperManifestRotationReadinessPaths,
    candidate_payload: bytes,
    preflight_runner: PreflightRunner,
) -> None:
    try:
        with tempfile.TemporaryDirectory(
            prefix="shreks-g1c-v2-rotation-readiness-"
        ) as raw_dir:
            private_dir = Path(raw_dir)
            private_dir.chmod(0o700)
            candidate = private_dir / "candidate-paper-campaign.json"
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(candidate_payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            config = ObserverPaperCampaignRuntimeConfig(
                observer_database_path=paths.observer_database_path,
                evidence_path=paths.evidence_path,
                manifest_path=candidate,
                cycle_interval_seconds=1.0,
                max_cycles=1,
                risk_control_path=paths.risk_control_path,
            )
            preflight_runner(config)
    except (
        ObserverPaperCampaignRuntimeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestRotationReadinessError(
            "PAPER runtime preflight rejected candidate readiness"
        ) from error


def _material_identity(material: dict[str, object]) -> tuple[object, ...]:
    return (
        material["release_source_sha"],
        material["release_directory"],
        material["wheel_relative_path"],
        material["wheel_sha256"],
        material["manager_sha256"],
    )


def _require_lower_hex(name: str, value: object, length: int) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperManifestRotationReadinessError(
            f"{name} must be {length} lowercase hex characters"
        )
    return value


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


def _fingerprint(document: dict[str, object], field: str) -> str:
    copied = dict(document)
    copied[field] = _ZERO_SHA256
    return hashlib.sha256(_canonical(copied)).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prove read-only readiness evidence for one separately authorized "
            "protected PAPER runtime-manifest rotation."
        )
    )
    parser.add_argument("candidate_runtime_manifest", type=Path)
    parser.add_argument("transition_binding", type=Path)
    parser.add_argument("installation_proof", type=Path)
    parser.add_argument("expected_binding_fingerprint_sha256")
    parser.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        proof_payload, _ = installer._read_regular_no_follow(
            args.installation_proof,
            label="helper installation proof",
        )
        receipt = prove_paper_manifest_rotation_readiness(
            candidate_runtime_manifest_path=args.candidate_runtime_manifest,
            transition_binding_path=args.transition_binding,
            installation_proof_payload=proof_payload,
            expected_binding_fingerprint_sha256=(
                args.expected_binding_fingerprint_sha256
            ),
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        PaperManifestRotationReadinessError,
        install_proof.PaperManifestManagerInstallationProofError,
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
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "manifest_rotation_authority": "NOT_GRANTED",
                    "scoring_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1
    sys.stdout.buffer.write(_canonical(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
