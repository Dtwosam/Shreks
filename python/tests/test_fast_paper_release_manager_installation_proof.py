from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

import shreks_brain.fast_paper_release_manager_installation_proof as proof


_RELEASE_SHA = "a" * 40
_WHEEL_RELATIVE = "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl"
_REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = tmp_path / "opt" / "shreks" / "releases" / _RELEASE_SHA
    wheel = release / _WHEEL_RELATIVE
    wheel.parent.mkdir(parents=True)
    manager_payload = (
        _REPO_ROOT / "deploy" / "release" / "release_manager.py"
    ).read_bytes()
    bundle_payload = (
        _REPO_ROOT / "deploy" / "release" / "release_bundle.py"
    ).read_bytes()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(proof._MANAGER_MEMBER, manager_payload)
        archive.writestr(proof._BUNDLE_MEMBER, bundle_payload)
    wheel_payload = wheel.read_bytes()
    manifest = {
        "files": [
            {
                "path": _WHEEL_RELATIVE,
                "sha256": hashlib.sha256(wheel_payload).hexdigest(),
                "size": len(wheel_payload),
            }
        ],
        "platform": "aarch64-unknown-linux-gnu",
        "schema_version": "g2-release-manifest-v1",
        "source_sha": _RELEASE_SHA,
    }
    (release / "RELEASE_MANIFEST.json").write_bytes(
        _canonical(manifest)
    )
    runtime_python = release / ".venv" / "bin" / "python"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime_python.chmod(0o755)

    current = tmp_path / "opt" / "shreks" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(release)

    root_bin = tmp_path / "usr" / "local" / "sbin"
    root_bin.mkdir(parents=True)
    root_bin.chmod(0o755)
    manager = root_bin / "shreks-release-manager"
    prior_manager = (
        b"#!/usr/bin/env python3\n"
        b"# prior root release manager\n"
    )
    manager.write_bytes(prior_manager)
    manager.chmod(0o755)
    bundle = root_bin / "release_bundle.py"
    bundle.write_bytes(bundle_payload)
    bundle.chmod(0o755)

    sudoers = tmp_path / "etc" / "sudoers.d" / "shreks-release-manager"
    sudoers.parent.mkdir(parents=True)
    sudoers.write_text(proof._SUDOERS_LINE + "\n", encoding="utf-8")
    sudoers.chmod(0o440)

    receipts = tmp_path / "root" / "proofs"
    receipts.mkdir(parents=True)
    receipts.chmod(0o700)
    receipt = receipts / "release-manager-installation-proof.json"

    monkeypatch.setattr(proof.os, "geteuid", lambda: 0)
    monkeypatch.setattr(proof, "_ROOT_UID", os.getuid())
    monkeypatch.setattr(proof, "_ROOT_GID", os.getgid())
    monkeypatch.setattr(proof.os, "fchown", lambda *_args: None)

    states = {
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
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        fields = states[command[2]]
        return proof.HostCommandResult(
            0,
            "".join(
                f"{name}={fields[name]}\n"
                for name in proof._PROPERTIES
            ),
            "",
        )

    paths = proof.InstallationProofPaths(
        current_link=current,
        manager_destination=manager,
        bundle_destination=bundle,
        deploy_sudoers=sudoers,
    )
    return {
        "release": release,
        "runtime_python": runtime_python,
        "paths": paths,
        "manager": manager,
        "prior_manager": prior_manager,
        "manager_payload": manager_payload,
        "bundle": bundle,
        "bundle_payload": bundle_payload,
        "sudoers": sudoers,
        "receipt": receipt,
        "states": states,
        "runner": runner,
        "calls": calls,
    }


def test_refresh_replaces_only_manager_and_proves_exact_control_plane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)

    result = proof.refresh_and_prove_fast_aware_release_manager(
        expected_release_source_sha=_RELEASE_SHA,
        paths=setup["paths"],
        receipt_path=setup["receipt"],
        runtime_executable=setup["runtime_python"],
        command_runner=setup["runner"],
    )

    assert result["status"] == "VERIFIED"
    assert result["release_source_sha"] == _RELEASE_SHA
    assert result["release_manager_replaced"] is True
    assert result["release_manager_sha256"] == hashlib.sha256(
        setup["manager_payload"]
    ).hexdigest()
    assert result["release_bundle_sha256"] == hashlib.sha256(
        setup["bundle_payload"]
    ).hexdigest()
    assert result["deploy_sudoers_exact_rule"] is True
    assert result["service_lifecycle_unchanged"] is True
    assert result["physical_cutover_authority"] == "NOT_EXERCISED"
    assert result["paper_execution_authority"] == "UNCHANGED"
    assert result["signing_submission_authority"] == "NOT_GRANTED"
    assert result["live_authority"] == "DISABLED"
    assert setup["manager"].read_bytes() == setup["manager_payload"]
    assert setup["bundle"].read_bytes() == setup["bundle_payload"]
    assert setup["sudoers"].read_text(encoding="utf-8") == (
        proof._SUDOERS_LINE + "\n"
    )
    assert setup["receipt"].is_file()
    assert stat.S_IMODE(setup["receipt"].stat().st_mode) == 0o600
    stored = json.loads(
        setup["receipt"].read_text(encoding="utf-8")
    )
    assert stored == result
    assert stored["proof_fingerprint_sha256"] == proof._fingerprint(stored)
    assert len(setup["calls"]) == len(proof._UNITS) * 2


def test_exact_manager_is_proof_only_and_not_rewritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["manager"].write_bytes(setup["manager_payload"])
    setup["manager"].chmod(0o755)
    before = setup["manager"].stat()

    result = proof.refresh_and_prove_fast_aware_release_manager(
        expected_release_source_sha=_RELEASE_SHA,
        paths=setup["paths"],
        receipt_path=setup["receipt"],
        runtime_executable=setup["runtime_python"],
        command_runner=setup["runner"],
    )

    after = setup["manager"].stat()
    assert result["release_manager_replaced"] is False
    assert result["installation_authority"] == (
        "PROVEN_EXACT_RELEASE_BOUND_FAST_AWARE_MANAGER_ONLY"
    )
    assert after.st_ino == before.st_ino


def test_stale_release_bundle_fails_before_manager_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["bundle"].write_bytes(b"#!/usr/bin/env python3\n# stale\n")
    setup["bundle"].chmod(0o755)

    with pytest.raises(
        proof.FastPaperReleaseManagerInstallationProofError,
        match="release_bundle.py",
    ):
        proof.refresh_and_prove_fast_aware_release_manager(
            expected_release_source_sha=_RELEASE_SHA,
            paths=setup["paths"],
            receipt_path=setup["receipt"],
            runtime_executable=setup["runtime_python"],
            command_runner=setup["runner"],
        )

    assert setup["manager"].read_bytes() == setup["prior_manager"]
    assert not setup["receipt"].exists()


def test_sudoers_widening_fails_before_manager_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["sudoers"].chmod(0o640)
    setup["sudoers"].write_text(
        proof._SUDOERS_LINE
        + "\nshreks-deploy ALL=(root) NOPASSWD: /bin/sh\n",
        encoding="utf-8",
    )
    setup["sudoers"].chmod(0o440)

    with pytest.raises(
        proof.FastPaperReleaseManagerInstallationProofError,
        match="exact historical command",
    ):
        proof.refresh_and_prove_fast_aware_release_manager(
            expected_release_source_sha=_RELEASE_SHA,
            paths=setup["paths"],
            receipt_path=setup["receipt"],
            runtime_executable=setup["runtime_python"],
            command_runner=setup["runner"],
        )

    assert setup["manager"].read_bytes() == setup["prior_manager"]


def test_service_lifecycle_drift_rolls_back_prior_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    base_runner = setup["runner"]
    call_count = {"value": 0}

    def drifting_runner(command: tuple[str, ...]):
        call_count["value"] += 1
        if call_count["value"] == len(proof._UNITS) + 1:
            setup["states"][proof._UNITS[0]]["NRestarts"] = "1"
            setup["states"][proof._UNITS[0]]["MainPID"] = "9999"
        return base_runner(command)

    with pytest.raises(
        proof.FastPaperReleaseManagerInstallationProofError,
        match="service lifecycle changed",
    ):
        proof.refresh_and_prove_fast_aware_release_manager(
            expected_release_source_sha=_RELEASE_SHA,
            paths=setup["paths"],
            receipt_path=setup["receipt"],
            runtime_executable=setup["runtime_python"],
            command_runner=drifting_runner,
        )

    assert setup["manager"].read_bytes() == setup["prior_manager"]
    assert not setup["receipt"].exists()


def test_command_runner_is_read_only_systemd_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        proof.subprocess,
        "run",
        lambda command, **_kwargs: type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )(),
    )
    for forbidden in (
        ("systemctl", "start", "shreks-paper-campaign.service"),
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "restart", "shreks-paper-campaign.service"),
        ("systemctl", "show", "other.service", "--property=x", "--no-pager"),
    ):
        with pytest.raises(
            proof.FastPaperReleaseManagerInstallationProofError,
            match="allowlist",
        ):
            proof._default_runner(forbidden)


def test_installation_proof_source_has_no_paper_cutover_or_live_authority() -> None:
    source = Path(proof.__file__).read_text(encoding="utf-8")

    for required in (
        proof._MANAGER_MEMBER,
        proof._BUNDLE_MEMBER,
        "/usr/local/sbin/shreks-release-manager install ",
        "/var/tmp/shreks-release-*.RELEASE_MANIFEST.json",
        "EXERCISED_EXACT_RELEASE_BOUND_FAST_AWARE_MANAGER_ONLY",
        "physical_cutover_authority",
        "paper_execution_authority",
        "live_authority",
    ):
        assert required in source

    for forbidden in (
        '"start"',
        '"stop"',
        '"restart"',
        "systemctl daemon-reload",
        "fast_paper_physical_cutover",
        "activate_fast_release",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "score_candidate",
        "decide_entry",
    ):
        assert forbidden not in source
