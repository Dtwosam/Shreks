from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import g1c_v2_paper_manifest_manager_status as status


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANAGER_SOURCE = _REPO_ROOT / "deploy" / "release" / "paper_manifest_manager.py"
_VERIFY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "verify-production-paper.yml"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
RELEASE_SHA = "a" * 40
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

    destination = (
        tmp_path / "usr" / "local" / "sbin" / "shreks-paper-manifest-manager"
    )
    destination.parent.mkdir(parents=True)

    monkeypatch.setattr(status, "_DESTINATION_UID", os.getuid())
    monkeypatch.setattr(status, "_DESTINATION_GID", os.getgid())

    return {
        "runtime_python": runtime_python,
        "paths": status.PaperManifestManagerStatusPaths(
            current_link=current,
            destination=destination,
        ),
        "destination": destination,
        "manager_payload": manager_payload,
        "wheel_payload": wheel_payload,
    }


def _inspect(setup):
    return status.inspect_release_bound_paper_manifest_manager_status(
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime_python"],
    )


def test_status_reports_absent_without_mutating_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)

    result = _inspect(setup)

    assert result["status"] == "ABSENT"
    assert result["destination_present"] is False
    assert result["destination_type"] == "absent"
    assert result["destination_sha256"] is None
    assert result["bytes_match_current_release"] is None
    assert result["metadata_match_expected"] is None
    assert result["installation_authority"] == "NOT_EXERCISED"
    assert result["manifest_rotation_authority"] == "NOT_GRANTED"
    assert result["live_authority"] == "DISABLED"
    assert not setup["destination"].exists()


def test_status_reports_exact_current_release_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["destination"].write_bytes(setup["manager_payload"])
    setup["destination"].chmod(0o755)

    result = _inspect(setup)

    assert result["status"] == "MATCHED_CURRENT_RELEASE"
    assert result["destination_present"] is True
    assert result["destination_type"] == "regular"
    assert result["destination_sha256"] == hashlib.sha256(
        setup["manager_payload"]
    ).hexdigest()
    assert result["bytes_match_current_release"] is True
    assert result["metadata_match_expected"] is True


def test_status_reports_different_existing_bytes_without_replacing_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    drift = setup["manager_payload"] + b"\n# stale helper\n"
    setup["destination"].write_bytes(drift)
    setup["destination"].chmod(0o755)

    result = _inspect(setup)

    assert result["status"] == "PRESENT_DIFFERENT_BYTES"
    assert result["destination_sha256"] == hashlib.sha256(drift).hexdigest()
    assert result["bytes_match_current_release"] is False
    assert setup["destination"].read_bytes() == drift


def test_status_reports_metadata_mismatch_without_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["destination"].write_bytes(setup["manager_payload"])
    setup["destination"].chmod(0o700)

    result = _inspect(setup)

    assert result["status"] == "PRESENT_METADATA_MISMATCH"
    assert result["bytes_match_current_release"] is True
    assert result["metadata_match_expected"] is False
    assert result["destination_mode"] == "0700"
    assert setup["destination"].stat().st_mode & 0o777 == 0o700


def test_status_reports_symlink_as_unsafe_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    target = tmp_path / "manager-target"
    target.write_bytes(setup["manager_payload"])
    setup["destination"].symlink_to(target)

    result = _inspect(setup)

    assert result["status"] == "PRESENT_UNSAFE_TYPE"
    assert result["destination_type"] == "symlink"
    assert result["destination_sha256"] is None
    assert result["bytes_match_current_release"] is None
    assert setup["destination"].is_symlink()


def test_status_rejects_release_wheel_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    wheel_path = (
        setup["paths"].current_link.resolve() / WHEEL_RELATIVE_PATH
    )
    payload = bytearray(wheel_path.read_bytes())
    payload[-1] ^= 0x01
    wheel_path.write_bytes(payload)

    with pytest.raises(
        status.PaperManifestManagerStatusError,
        match="release wheel hash does not match release manifest",
    ):
        _inspect(setup)


def test_status_authority_firewall_and_production_verifier_contract() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_manager_status.py"
    ).read_text(encoding="utf-8")
    workflow = _VERIFY_WORKFLOW.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for forbidden in (
        "os.replace(",
        "os.link(",
        "chmod(",
        "chown(",
        "systemctl",
        "subprocess",
        " rotate ",
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    assert '"observation_authority": "READ_ONLY"' in source
    assert '"installation_authority": "NOT_EXERCISED"' in source
    assert '"manifest_rotation_authority": "NOT_GRANTED"' in source

    assert (
        'shreks-g1c-v2-paper-manifest-manager-status = '
        '"shreks_brain.g1c_v2_paper_manifest_manager_status:main"'
    ) in pyproject
    assert "shreks-g1c-v2-paper-manifest-manager-status" in workflow
    assert "paper_manifest_manager_status=" in workflow
    assert "paper_manifest_manager_status_json=" in workflow
