from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANAGER_SOURCE = _REPO_ROOT / "deploy" / "release" / "paper_manifest_manager.py"
_RUNBOOK = _REPO_ROOT / "deploy" / "release" / "README.md"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
RELEASE_SHA = "d" * 40
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


def _release_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    duplicate_manager_member: bool = False,
):
    release_dir = tmp_path / "opt" / "shreks" / "releases" / RELEASE_SHA
    wheel_path = release_dir / WHEEL_RELATIVE_PATH
    wheel_path.parent.mkdir(parents=True)

    manager_payload = _MANAGER_SOURCE.read_bytes()
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr(installer._MANAGER_MEMBER, manager_payload)
        if duplicate_manager_member:
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

    destination = tmp_path / "usr" / "local" / "sbin" / "shreks-paper-manifest-manager"
    destination.parent.mkdir(parents=True)

    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer, "_DESTINATION_UID", os.getuid())
    monkeypatch.setattr(installer, "_DESTINATION_GID", os.getgid())

    paths = installer.PaperManifestManagerInstallPaths(
        current_link=current,
        destination=destination,
    )
    return {
        "release_dir": release_dir,
        "wheel_path": wheel_path,
        "runtime_python": runtime_python,
        "current": current,
        "destination": destination,
        "paths": paths,
        "manager_payload": manager_payload,
    }


def _install(setup):
    return installer.install_release_bound_paper_manifest_manager(
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime_python"],
    )


def test_installs_exact_manifest_hashed_wheel_member_without_replacement_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(tmp_path, monkeypatch)

    receipt = _install(setup)

    assert receipt["status"] == "INSTALLED"
    assert receipt["release_source_sha"] == RELEASE_SHA
    assert receipt["wheel_relative_path"] == WHEEL_RELATIVE_PATH
    assert receipt["wheel_member"] == installer._MANAGER_MEMBER
    assert receipt["manager_sha256"] == hashlib.sha256(
        setup["manager_payload"]
    ).hexdigest()
    assert receipt["installation_authority"] == (
        "EXERCISED_EXACT_RELEASE_BOUND_HELPER_ONLY"
    )
    assert receipt["manifest_rotation_authority"] == "NOT_GRANTED"
    assert receipt["scoring_authority"] == "NOT_GRANTED"
    assert receipt["paper_promotion_authority"] == "BLOCKED"
    assert receipt["live_authority"] == "DISABLED"

    assert setup["destination"].read_bytes() == setup["manager_payload"]
    metadata = setup["destination"].stat()
    assert stat.S_IMODE(metadata.st_mode) == 0o755
    assert metadata.st_uid == os.getuid()
    assert metadata.st_gid == os.getgid()


def test_exact_existing_helper_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(tmp_path, monkeypatch)

    first = _install(setup)
    first_inode = setup["destination"].stat().st_ino
    second = _install(setup)

    assert first["status"] == "INSTALLED"
    assert second["status"] == "ALREADY_INSTALLED"
    assert setup["destination"].stat().st_ino == first_inode
    assert setup["destination"].read_bytes() == setup["manager_payload"]


def test_different_existing_helper_fails_closed_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(tmp_path, monkeypatch)
    setup["destination"].write_bytes(b"different-root-helper\n")
    setup["destination"].chmod(0o755)
    before = setup["destination"].read_bytes()

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match="different bytes",
    ):
        _install(setup)

    assert setup["destination"].read_bytes() == before


def test_tampered_release_wheel_is_rejected_before_destination_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(tmp_path, monkeypatch)
    wheel_payload = bytearray(setup["wheel_path"].read_bytes())
    wheel_payload[-1] ^= 0x01
    setup["wheel_path"].write_bytes(wheel_payload)

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match="hash does not match",
    ):
        _install(setup)

    assert not setup["destination"].exists()


def test_duplicate_sealed_manager_member_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(
        tmp_path,
        monkeypatch,
        duplicate_manager_member=True,
    )

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match="exactly one sealed PAPER manifest manager",
    ):
        _install(setup)

    assert not setup["destination"].exists()


def test_installer_must_execute_from_exact_current_release_virtualenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(tmp_path, monkeypatch)
    outside = tmp_path / "outside-python"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match="exact current release virtualenv",
    ):
        installer.install_release_bound_paper_manifest_manager(
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["paths"],
            runtime_executable=outside,
        )

    assert not setup["destination"].exists()


def test_non_root_installation_is_rejected_before_release_or_destination_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(installer.os, "geteuid", lambda: 1234)
    paths = installer.PaperManifestManagerInstallPaths(
        current_link=(tmp_path / "opt" / "shreks" / "current").resolve(),
        destination=(
            tmp_path / "usr" / "local" / "sbin" / "shreks-paper-manifest-manager"
        ).resolve(),
    )

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match="requires root",
    ):
        installer.install_release_bound_paper_manifest_manager(
            expected_release_source_sha=RELEASE_SHA,
            paths=paths,
        )


def test_world_writable_destination_parent_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _release_layout(tmp_path, monkeypatch)
    setup["destination"].parent.chmod(0o777)

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match="destination parent is unsafe",
    ):
        _install(setup)

    assert not setup["destination"].exists()


def test_installer_authority_firewall_and_release_local_cli_contract() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_manager_install.py"
    ).read_text(encoding="utf-8")
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for forbidden in (
        "/etc/shreks",
        "/var/lib/shreks",
        "paper-campaign.json",
        "systemctl",
        "subprocess",
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
        "/etc/sudoers",
    ):
        assert forbidden not in source

    assert "/usr/local/sbin/shreks-paper-manifest-manager" in source
    assert "os.link(" in source
    assert "follow_symlinks=False" in source
    assert "EXERCISED_EXACT_RELEASE_BOUND_HELPER_ONLY" in source

    assert (
        'shreks-g1c-v2-paper-manifest-manager-install = '
        '"shreks_brain.g1c_v2_paper_manifest_manager_install:main"'
    ) in pyproject

    assert "Install the sealed PAPER manifest manager helper" in runbook
    assert (
        '.venv/bin/shreks-g1c-v2-paper-manifest-manager-install" "$CURRENT_SHA"'
        in runbook
    )
    assert "does not stop or restart any Shreks service" in runbook
    assert "does not replace a different existing helper" in runbook

    recovery_start = runbook.index("## Recover or update sealed deployment control scripts")
    recovery_end = runbook.index("## Install the sealed PAPER manifest manager helper")
    recovery = runbook[recovery_start:recovery_end]
    assert "paper_manifest_manager.py" not in recovery
    assert "/usr/local/sbin/shreks-paper-manifest-manager" not in recovery

    bootstrap_end = runbook.index("## GitHub `production-paper` environment")
    bootstrap = runbook[:bootstrap_end]
    assert (
        "deploy/release/paper_manifest_manager.py "
        "/usr/local/sbin/shreks-paper-manifest-manager"
    ) not in bootstrap

    assert (
        "shreks-deploy ALL=(root) NOPASSWD: "
        "/usr/local/sbin/shreks-paper-manifest-manager"
    ) not in runbook
