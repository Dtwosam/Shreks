from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import g1c_v2_paper_manifest_manager_installation_proof as install_proof
from shreks_brain import g1c_v2_paper_manifest_rotation_readiness as readiness
from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    bind_g1c_v2_runtime_manifest_transition,
)
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
)
from shreks_brain.risk_control import initialize_operator_risk_control_state

from test_g1c_v2_runtime_manifest_transition_binding import _inputs


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANAGER_SOURCE = _REPO_ROOT / "deploy" / "release" / "paper_manifest_manager.py"
_RUNBOOK = _REPO_ROOT / "deploy" / "release" / "README.md"
_VERIFY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "verify-production-paper.yml"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
RELEASE_SHA = "f" * 40
WHEEL_RELATIVE_PATH = "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl"


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


class ServiceRunner:
    def __init__(self, *, drift_after_first_snapshot: bool = False):
        self.calls: list[tuple[str, ...]] = []
        self.drift_after_first_snapshot = drift_after_first_snapshot
        self.by_unit = {
            unit: {
                "ActiveState": "active",
                "SubState": "running",
                "NRestarts": "0",
                "MainPID": str(5000 + index),
                "ExecMainStatus": "0",
                "ActiveEnterTimestampMonotonic": str(1_000_000 + index),
            }
            for index, unit in enumerate(install_proof._UNITS)
        }

    def __call__(self, command: tuple[str, ...]) -> install_proof.HostCommandResult:
        self.calls.append(command)
        assert command[0:2] == ("systemctl", "show")
        assert command[2] in install_proof._UNITS
        if self.drift_after_first_snapshot and len(self.calls) == 4:
            self.by_unit[command[2]]["NRestarts"] = "1"
            self.by_unit[command[2]]["MainPID"] = "9999"
            self.by_unit[command[2]][
                "ActiveEnterTimestampMonotonic"
            ] = "2_000_000"
        fields = self.by_unit[command[2]]
        return install_proof.HostCommandResult(
            returncode=0,
            stdout="".join(
                f"{key}={fields[key]}\n"
                for key in install_proof._PROPERTIES
            ),
        )


class PreflightRunner:
    def __init__(self, *, fail: bool = False):
        self.paths: list[Path] = []
        self.fail = fail

    def __call__(self, config):
        self.paths.append(config.manifest_path)
        if self.fail:
            raise ObserverPaperCampaignRuntimeError("simulated preflight failure")
        return object()


class CycleAssemblyRunner:
    def __init__(self, *, fail: bool = False):
        self.calls: list[tuple[Path, int]] = []
        self.fail = fail

    def __call__(self, config, as_of_unix_ms: int):
        self.calls.append((config.manifest_path, as_of_unix_ms))
        if self.fail:
            raise ObserverPaperCampaignRuntimeError(
                "simulated next-cycle assembly failure"
            )
        return object()


def _write_release(
    tmp_path: Path,
) -> tuple[Path, Path, bytes]:
    release_dir = tmp_path / "opt" / "shreks" / "releases" / RELEASE_SHA
    wheel_path = release_dir / WHEEL_RELATIVE_PATH
    wheel_path.parent.mkdir(parents=True)
    manager_payload = _MANAGER_SOURCE.read_bytes()
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr(installer._MANAGER_MEMBER, manager_payload)
    wheel_payload = wheel_path.read_bytes()
    manifest = {
        "files": [
            {
                "path": WHEEL_RELATIVE_PATH,
                "sha256": hashlib.sha256(wheel_payload).hexdigest(),
                "size": len(wheel_payload),
            }
        ],
        "platform": "aarch64-unknown-linux-gnu",
        "schema_version": "g2-release-manifest-v1",
        "source_sha": RELEASE_SHA,
    }
    (release_dir / "RELEASE_MANIFEST.json").write_bytes(_canonical(manifest))

    runtime_python = release_dir / ".venv" / "bin" / "python"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime_python.chmod(0o755)

    current = tmp_path / "opt" / "shreks" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(release_dir)
    return current, runtime_python, manager_payload


def _write_runtime_env(paths: readiness.PaperManifestRotationReadinessPaths) -> None:
    paths.env_file.parent.mkdir(parents=True, exist_ok=True)
    paths.env_file.write_text(
        "\n".join(
            (
                f"SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH={paths.observer_database_path}",
                f"SHREKS_PAPER_CAMPAIGN_E11_PATH={paths.evidence_path}",
                f"SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH={paths.active_manifest_path}",
                "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS=60",
                "SHREKS_PAPER_CAMPAIGN_MAX_CYCLES=",
                f"SHREKS_RISK_CONTROL_STATE_PATH={paths.risk_control_path}",
                "",
            )
        ),
        encoding="utf-8",
    )


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    service_runner: ServiceRunner | None = None,
):
    (tmp_path / "inputs").mkdir()
    (
        source,
        source_path,
        source_bytes,
        candidate,
        candidate_path,
        candidate_bytes,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path / "inputs", monkeypatch)

    binding_path = tmp_path / "transition-binding.json"
    binding = bind_g1c_v2_runtime_manifest_transition(
        source_runtime_manifest_path=source_path,
        candidate_runtime_manifest_path=candidate_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        destination=binding_path,
    )

    current, runtime_python, manager_payload = _write_release(tmp_path)
    state = tmp_path / "var" / "lib" / "shreks"
    etc = tmp_path / "etc" / "shreks"
    destination = (
        tmp_path / "usr" / "local" / "sbin" / "shreks-paper-manifest-manager"
    )
    destination.parent.mkdir(parents=True)

    sudoers = tmp_path / "etc" / "sudoers.d" / "shreks-release-manager"
    sudoers.parent.mkdir(parents=True)
    sudoers.write_text(install_proof._SUDOERS_LINE + "\n", encoding="utf-8")
    sudoers.chmod(0o440)

    paths = readiness.PaperManifestRotationReadinessPaths(
        current_link=current,
        env_file=etc / "shreks.env",
        active_manifest_path=etc / "paper-campaign.json",
        observer_database_path=state / "shreks.db",
        evidence_path=state / "paper-evaluation-e11.json",
        risk_control_path=state / "risk" / "operator-control.json",
        deploy_sudoers=sudoers,
        manager_destination=destination,
    )
    paths.active_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    paths.active_manifest_path.write_bytes(source_bytes)
    paths.active_manifest_path.chmod(0o640)
    _write_runtime_env(paths)
    paths.risk_control_path.parent.mkdir(parents=True, exist_ok=True)
    initialize_operator_risk_control_state(
        paths.risk_control_path,
        observed_at_unix_ms=1_000,
    )

    monkeypatch.setattr(readiness.os, "geteuid", lambda: 0)
    monkeypatch.setattr(readiness, "_ROOT_UID", os.getuid())
    monkeypatch.setattr(readiness, "_ROOT_GID", os.getgid())
    monkeypatch.setattr(install_proof.os, "geteuid", lambda: 0)
    monkeypatch.setattr(install_proof, "_ROOT_UID", os.getuid())
    monkeypatch.setattr(install_proof, "_ROOT_GID", os.getgid())
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer, "_DESTINATION_UID", os.getuid())
    monkeypatch.setattr(installer, "_DESTINATION_GID", os.getgid())

    services = service_runner or ServiceRunner()
    proof_paths = install_proof.ProofPaths(
        current_link=current,
        campaign_manifest=paths.active_manifest_path,
        deploy_sudoers=sudoers,
        manager_destination=destination,
    )
    install_paths = installer.PaperManifestManagerInstallPaths(
        current_link=current,
        destination=destination,
    )
    before = install_proof.capture_preinstall_state(
        expected_release_source_sha=RELEASE_SHA,
        paths=proof_paths,
        runtime_executable=runtime_python,
        command_runner=services,
    )
    installer_receipt = installer.install_release_bound_paper_manifest_manager(
        expected_release_source_sha=RELEASE_SHA,
        paths=install_paths,
        runtime_executable=runtime_python,
    )
    installation_proof = install_proof.verify_postinstall_state(
        expected_release_source_sha=RELEASE_SHA,
        preinstall_payload=_canonical(before),
        installer_receipt_payload=_canonical(installer_receipt),
        paths=proof_paths,
        runtime_executable=runtime_python,
        command_runner=services,
    )
    services.calls.clear()

    return {
        "source": source,
        "source_bytes": source_bytes,
        "candidate": candidate,
        "candidate_path": candidate_path,
        "candidate_bytes": candidate_bytes,
        "binding": binding,
        "binding_path": binding_path,
        "paths": paths,
        "runtime_python": runtime_python,
        "manager_payload": manager_payload,
        "installation_proof": installation_proof,
        "services": services,
    }


def _prove(
    setup,
    preflight: PreflightRunner,
    cycle_assembly: CycleAssemblyRunner | None = None,
):
    cycle = CycleAssemblyRunner() if cycle_assembly is None else cycle_assembly
    return readiness.prove_paper_manifest_rotation_readiness(
        candidate_runtime_manifest_path=setup["candidate_path"],
        transition_binding_path=setup["binding_path"],
        installation_proof_payload=_canonical(setup["installation_proof"]),
        expected_binding_fingerprint_sha256=setup["binding"][
            "binding_fingerprint_sha256"
        ],
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime_python"],
        service_runner=setup["services"],
        preflight_runner=preflight,
        cycle_assembly_runner=cycle,
        clock_unix_ms=lambda: 1_234_567,
    )


def test_readiness_proves_exact_release_helper_binding_and_private_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)
    preflight = PreflightRunner()
    cycle_assembly = CycleAssemblyRunner()

    receipt = _prove(setup, preflight, cycle_assembly)

    assert receipt["status"] == "READY_EVIDENCE_ONLY"
    assert receipt["release_source_sha"] == RELEASE_SHA
    assert receipt["manager_sha256"] == hashlib.sha256(
        setup["manager_payload"]
    ).hexdigest()
    assert receipt["source_manifest_sha256"] == hashlib.sha256(
        setup["source_bytes"]
    ).hexdigest()
    assert receipt["candidate_manifest_sha256"] == hashlib.sha256(
        setup["candidate_bytes"]
    ).hexdigest()
    assert receipt["binding_fingerprint_sha256"] == setup["binding"][
        "binding_fingerprint_sha256"
    ]
    assert receipt["candidate_preflight_status"] == "PASSED"
    assert receipt["runtime_env_contract"] == "MATCHED"
    assert receipt["service_lifecycle_unchanged"] is True
    assert receipt["manifest_rotation_authority"] == "NOT_GRANTED"
    assert receipt["scoring_authority"] == "NOT_GRANTED"
    assert receipt["paper_promotion_authority"] == "BLOCKED"
    assert receipt["live_authority"] == "DISABLED"
    assert receipt["readiness_fingerprint_sha256"] != readiness._ZERO_SHA256

    assert len(preflight.paths) == 1
    assert preflight.paths[0] != setup["candidate_path"]
    assert preflight.paths[0].name == "candidate-paper-campaign.json"
    assert len(cycle_assembly.calls) == 1
    assert cycle_assembly.calls[0] == (preflight.paths[0], 1_234_567)
    assert not preflight.paths[0].exists()
    assert setup["paths"].active_manifest_path.read_bytes() == setup["source_bytes"]
    assert setup["candidate_path"].read_bytes() == setup["candidate_bytes"]
    assert all(call[0:2] == ("systemctl", "show") for call in setup["services"].calls)


def test_readiness_rejects_installed_helper_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)
    setup["paths"].manager_destination.chmod(0o755)
    setup["paths"].manager_destination.write_bytes(
        setup["manager_payload"] + b"\n# drift\n"
    )
    setup["paths"].manager_destination.chmod(0o755)

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="bytes do not match sealed release",
    ):
        _prove(setup, PreflightRunner())


def test_readiness_rejects_tampered_installation_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)
    setup["installation_proof"]["manager_sha256"] = "0" * 64

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="installation proof fingerprint is invalid",
    ):
        _prove(setup, PreflightRunner())


def test_readiness_rejects_active_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)
    setup["paths"].active_manifest_path.write_bytes(setup["candidate_bytes"])
    setup["paths"].active_manifest_path.chmod(0o640)

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="active source runtime manifest must be canonical v1",
    ):
        _prove(setup, PreflightRunner())


def test_readiness_rejects_runtime_env_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)
    setup["paths"].env_file.write_text(
        setup["paths"].env_file.read_text(encoding="utf-8").replace(
            str(setup["paths"].observer_database_path),
            str(tmp_path / "wrong.db"),
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH",
    ):
        _prove(setup, PreflightRunner())


def test_readiness_preflight_failure_does_not_mutate_protected_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="preflight rejected candidate readiness",
    ):
        _prove(setup, PreflightRunner(fail=True))

    assert setup["paths"].active_manifest_path.read_bytes() == setup["source_bytes"]
    assert setup["candidate_path"].read_bytes() == setup["candidate_bytes"]


def test_readiness_next_cycle_assembly_failure_does_not_mutate_protected_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup(tmp_path, monkeypatch)

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="preflight rejected candidate readiness",
    ):
        _prove(
            setup,
            PreflightRunner(),
            CycleAssemblyRunner(fail=True),
        )

    assert setup["paths"].active_manifest_path.read_bytes() == setup["source_bytes"]
    assert setup["candidate_path"].read_bytes() == setup["candidate_bytes"]


def test_readiness_rejects_service_lifecycle_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = ServiceRunner()
    setup = _setup(tmp_path, monkeypatch, service_runner=services)
    services.drift_after_first_snapshot = True
    services.calls.clear()

    with pytest.raises(
        readiness.PaperManifestRotationReadinessError,
        match="service lifecycle state changed",
    ):
        _prove(setup, PreflightRunner())


def test_rotation_readiness_authority_firewall_and_operator_contract() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_rotation_readiness.py"
    ).read_text(encoding="utf-8")
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for forbidden in (
        '"stop"',
        '"start"',
        '"restart"',
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
        "os.replace(",
        "os.link(",
        "rotate_paper_manifest(",
    ):
        assert forbidden not in source

    assert "READY_EVIDENCE_ONLY" in source
    assert "manifest_rotation_authority" in source
    assert "NOT_GRANTED" in source
    assert "TemporaryDirectory" in source
    assert "preflight_observer_paper_campaign_runtime" in source
    assert "preflight_observer_paper_campaign_next_cycle" in source
    assert (
        'shreks-g1c-v2-paper-manifest-rotation-readiness = '
        '"shreks_brain.g1c_v2_paper_manifest_rotation_readiness:main"'
    ) in pyproject
    assert "Prove protected PAPER manifest rotation readiness" in runbook
    assert "rotation-readiness.json" in runbook
    assert "does not authorize rotation" in runbook

    workflow = _VERIFY_WORKFLOW.read_text(encoding="utf-8")
    assert (
        'ROTATION_READINESS="/opt/shreks/current/.venv/bin/'
        'shreks-g1c-v2-paper-manifest-rotation-readiness"'
    ) in workflow
    assert 'test -f "$ROTATION_READINESS"' in workflow
    assert 'test ! -L "$ROTATION_READINESS"' in workflow
    assert 'test -x "$ROTATION_READINESS"' in workflow
    assert 'readlink -f "$ROTATION_READINESS"' in workflow
    assert "import shreks_brain.g1c_v2_paper_manifest_rotation_readiness as readiness" in workflow
    assert 'paper_manifest_rotation_readiness=present' in workflow
    assert 'paper_manifest_rotation_readiness_path=%s' in workflow
    assert 'paper_manifest_rotation_readiness_module=%s' in workflow
    assert "readiness.main(" not in workflow
    assert 'exec "$ROTATION_READINESS"' not in workflow
