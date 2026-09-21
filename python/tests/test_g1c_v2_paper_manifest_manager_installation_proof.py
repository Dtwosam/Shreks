from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import g1c_v2_paper_manifest_manager_installation_proof as proof


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANAGER_SOURCE = _REPO_ROOT / "deploy" / "release" / "paper_manifest_manager.py"
_RUNBOOK = _REPO_ROOT / "deploy" / "release" / "README.md"
_VERIFY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "verify-production-paper.yml"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
RELEASE_SHA = "e" * 40
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


def _layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    campaign = tmp_path / "etc" / "shreks" / "paper-campaign.json"
    campaign.parent.mkdir(parents=True)
    campaign.write_bytes(b'{"paper":"source"}\n')
    campaign.chmod(0o640)

    sudoers = tmp_path / "etc" / "sudoers.d" / "shreks-release-manager"
    sudoers.parent.mkdir(parents=True)
    sudoers.write_text(proof._SUDOERS_LINE + "\n", encoding="utf-8")
    sudoers.chmod(0o440)

    destination = tmp_path / "usr" / "local" / "sbin" / "shreks-paper-manifest-manager"
    destination.parent.mkdir(parents=True)

    monkeypatch.setattr(proof.os, "geteuid", lambda: 0)
    monkeypatch.setattr(proof, "_ROOT_UID", os.getuid())
    monkeypatch.setattr(proof, "_ROOT_GID", os.getgid())
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer, "_DESTINATION_UID", os.getuid())
    monkeypatch.setattr(installer, "_DESTINATION_GID", os.getgid())

    service_state = {
        unit: {
            "ActiveState": "active",
            "SubState": "running",
            "NRestarts": "0",
            "MainPID": str(4100 + index),
            "ExecMainStatus": "0",
            "ActiveEnterTimestampMonotonic": str(900000 + index),
        }
        for index, unit in enumerate(proof._UNITS)
    }

    def runner(command: tuple[str, ...]) -> proof.HostCommandResult:
        assert command[0:2] == ("systemctl", "show")
        fields = service_state[command[2]]
        payload = "".join(
            f"{key}={fields[key]}\n" for key in proof._PROPERTIES
        )
        return proof.HostCommandResult(returncode=0, stdout=payload)

    paths = proof.ProofPaths(
        current_link=current,
        campaign_manifest=campaign,
        deploy_sudoers=sudoers,
        manager_destination=destination,
    )
    install_paths = installer.PaperManifestManagerInstallPaths(
        current_link=current,
        destination=destination,
    )
    return {
        "runtime_python": runtime_python,
        "paths": paths,
        "install_paths": install_paths,
        "campaign": campaign,
        "sudoers": sudoers,
        "destination": destination,
        "manager_payload": manager_payload,
        "service_state": service_state,
        "runner": runner,
    }


def _prepare(setup) -> dict[str, object]:
    return proof.capture_preinstall_state(
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime_python"],
        command_runner=setup["runner"],
    )


def _install(setup) -> dict[str, object]:
    return installer.install_release_bound_paper_manifest_manager(
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["install_paths"],
        runtime_executable=setup["runtime_python"],
    )


def _verify(setup, before, receipt) -> dict[str, object]:
    return proof.verify_postinstall_state(
        expected_release_source_sha=RELEASE_SHA,
        preinstall_payload=_canonical(before),
        installer_receipt_payload=_canonical(receipt),
        paths=setup["paths"],
        runtime_executable=setup["runtime_python"],
        command_runner=setup["runner"],
    )


def test_prepare_install_verify_proves_exact_helper_without_runtime_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    before = _prepare(setup)
    receipt = _install(setup)
    result = _verify(setup, before, receipt)

    assert before["snapshot_fingerprint_sha256"] != proof._ZERO_SHA256
    assert receipt["status"] == "INSTALLED"
    assert result["status"] == "VERIFIED"
    assert result["release_source_sha"] == RELEASE_SHA
    assert result["manager_sha256"] == hashlib.sha256(
        setup["manager_payload"]
    ).hexdigest()
    assert result["campaign_manifest_unchanged"] is True
    assert result["deploy_sudoers_unchanged"] is True
    assert result["service_lifecycle_unchanged"] is True
    assert result["installation_authority"] == (
        "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY"
    )
    assert result["manifest_rotation_authority"] == "NOT_GRANTED"
    assert result["scoring_authority"] == "NOT_GRANTED"
    assert result["paper_promotion_authority"] == "BLOCKED"
    assert result["live_authority"] == "DISABLED"
    assert result["proof_fingerprint_sha256"] != proof._ZERO_SHA256

    metadata = setup["destination"].stat()
    assert setup["destination"].read_bytes() == setup["manager_payload"]
    assert stat.S_IMODE(metadata.st_mode) == 0o755


def test_campaign_manifest_drift_fails_postinstall_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    before = _prepare(setup)
    receipt = _install(setup)
    setup["campaign"].write_bytes(b'{"paper":"drift"}\n')
    setup["campaign"].chmod(0o640)

    with pytest.raises(
        proof.PaperManifestManagerInstallationProofError,
        match="campaign manifest changed",
    ):
        _verify(setup, before, receipt)


def test_service_restart_or_pid_drift_fails_postinstall_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    before = _prepare(setup)
    receipt = _install(setup)
    unit = "shreks-paper-campaign.service"
    setup["service_state"][unit]["NRestarts"] = "1"
    setup["service_state"][unit]["MainPID"] = "9999"
    setup["service_state"][unit]["ActiveEnterTimestampMonotonic"] = "999999"

    with pytest.raises(
        proof.PaperManifestManagerInstallationProofError,
        match="service lifecycle state changed",
    ):
        _verify(setup, before, receipt)


def test_sudoers_widening_fails_postinstall_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    before = _prepare(setup)
    receipt = _install(setup)
    setup["sudoers"].chmod(0o640)
    setup["sudoers"].write_text(
        proof._SUDOERS_LINE
        + "\nshreks-deploy ALL=(root) NOPASSWD: "
        + "/usr/local/sbin/shreks-paper-manifest-manager\n",
        encoding="utf-8",
    )
    setup["sudoers"].chmod(0o440)

    with pytest.raises(
        proof.PaperManifestManagerInstallationProofError,
        match="sudoers authority is not the exact sealed command",
    ):
        _verify(setup, before, receipt)


def test_receipt_mismatch_fails_postinstall_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    before = _prepare(setup)
    receipt = _install(setup)
    receipt["manager_sha256"] = "0" * 64

    with pytest.raises(
        proof.PaperManifestManagerInstallationProofError,
        match="installer receipt does not match sealed installation: manager_sha256",
    ):
        _verify(setup, before, receipt)


def test_tampered_preinstall_snapshot_fingerprint_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    before = _prepare(setup)
    receipt = _install(setup)
    before["campaign_manifest"]["sha256"] = "f" * 64

    with pytest.raises(
        proof.PaperManifestManagerInstallationProofError,
        match="snapshot fingerprint is invalid",
    ):
        _verify(setup, before, receipt)


def test_installation_proof_authority_firewall_and_operator_contract() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_manager_installation_proof.py"
    ).read_text(encoding="utf-8")
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for forbidden in (
        '"stop"',
        '"start"',
        '"restart"',
        " rotate ",
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
        "os.replace(",
        "os.link(",
    ):
        assert forbidden not in source

    assert '("systemctl", "show")' in source
    assert "shreks-paper-manifest-manager" in source
    assert "paper-campaign.json" in source
    assert "shreks-release-manager" in source
    assert "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY" in source

    assert (
        'shreks-g1c-v2-paper-manifest-manager-install-proof = '
        '"shreks_brain.g1c_v2_paper_manifest_manager_installation_proof:main"'
    ) in pyproject
    assert "Prepare and verify the helper-installation proof" in runbook
    assert "installation-proof-pre.json" in runbook
    assert "installation-proof.json" in runbook
    assert "does not invoke the manifest manager" in runbook
    workflow = _VERIFY_WORKFLOW.read_text(encoding="utf-8")
    assert (
        'INSTALLER="/opt/shreks/current/.venv/bin/'
        'shreks-g1c-v2-paper-manifest-manager-install"'
    ) in workflow
    assert (
        'INSTALL_PROOF="/opt/shreks/current/.venv/bin/'
        'shreks-g1c-v2-paper-manifest-manager-install-proof"'
    ) in workflow
    assert 'test -f "$INSTALLER"' in workflow
    assert 'test ! -L "$INSTALLER"' in workflow
    assert 'test -x "$INSTALLER"' in workflow
    assert 'readlink -f "$INSTALLER"' in workflow
    assert 'test -f "$INSTALL_PROOF"' in workflow
    assert 'test ! -L "$INSTALL_PROOF"' in workflow
    assert 'test -x "$INSTALL_PROOF"' in workflow
    assert 'readlink -f "$INSTALL_PROOF"' in workflow
    assert "import shreks_brain.g1c_v2_paper_manifest_manager_install as installer" in workflow
    assert (
        "import shreks_brain.g1c_v2_paper_manifest_manager_installation_proof "
        "as installation_proof"
    ) in workflow
    assert "paper_manifest_manager_installer=present" in workflow
    assert "paper_manifest_manager_installation_proof=present" in workflow
    assert "paper_manifest_manager_installer_path=%s" in workflow
    assert "paper_manifest_manager_installation_proof_path=%s" in workflow
    assert "paper_manifest_manager_installer_module=%s" in workflow
    assert "paper_manifest_manager_installation_proof_module=%s" in workflow
    assert 'exec "$INSTALLER"' not in workflow
    assert 'exec "$INSTALL_PROOF"' not in workflow
