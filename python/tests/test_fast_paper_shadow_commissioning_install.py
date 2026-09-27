from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain.fast_paper_shadow_commissioning_assets import (
    FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES,
    stage_fast_paper_shadow_commissioning_package,
)
import shreks_brain.fast_paper_shadow_commissioning_install as commissioning


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
_RELEASE_MANAGER = _REPO_ROOT / "deploy" / "release" / "release_manager.py"
_TARGET = _REPO_ROOT / "deploy" / "systemd" / "shreks.target"

_SOURCE_SHA = "a" * 40
_PLATFORM = "x86_64-unknown-linux-gnu"


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
    ).encode()


def _layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    releases = tmp_path / "opt" / "shreks" / "releases"
    release = releases / _SOURCE_SHA
    release.mkdir(parents=True)
    current = tmp_path / "opt" / "shreks" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(release)

    venv_python = release / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    venv_python.chmod(0o755)

    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    unit = assets_root / "shreks-fast-paper-shadow.service"
    env = assets_root / "shreks-fast-paper-shadow.env.example"
    unit.write_text(
        """[Unit]
Description=Shreks learned Fast Lane PAPER shadow service
After=network-online.target shreks-observe.service shreks-paper-evidence.service
Wants=network-online.target shreks-observe.service shreks-paper-evidence.service
RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current

[Service]
Type=simple
User=shreks
Group=shreks
WorkingDirectory=/opt/shreks/current
EnvironmentFile=/etc/shreks/fast-paper-shadow.env
ExecStartPre=/opt/shreks/current/.venv/bin/python -m shreks_brain.fast_paper_runtime.shadow_supervisor --preflight
ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.fast_paper_runtime.shadow_supervisor
PrivateNetwork=true
ReadWritePaths=/var/lib/shreks/fast-paper-shadow
""",
        encoding="utf-8",
    )
    env.write_text("SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS=2.0\n", encoding="utf-8")

    package = tmp_path / "package"
    stage_fast_paper_shadow_commissioning_package(
        source_sha=_SOURCE_SHA,
        platform=_PLATFORM,
        assets={unit.name: unit, env.name: env},
        destination=package,
    )

    wheel = release / "wheelhouse" / "shreks_brain-0.1.0-py3-none-any.whl"
    wheel.parent.mkdir()
    prefix = "shreks_brain/_sealed_fast_paper_shadow_commissioning/"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in sorted(package.iterdir()):
            archive.write(path, f"{prefix}{path.name}")

    manifest = {
        "files": [
            {
                "path": "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl",
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "size": wheel.stat().st_size,
            }
        ],
        "platform": _PLATFORM,
        "schema_version": "g2-release-manifest-v1",
        "source_sha": _SOURCE_SHA,
    }
    (release / "RELEASE_MANIFEST.json").write_bytes(_canonical(manifest))

    systemd = tmp_path / "etc" / "systemd" / "system"
    systemd.mkdir(parents=True)
    destination = systemd / "shreks-fast-paper-shadow.service"

    monkeypatch.setattr(commissioning.os, "geteuid", lambda: 0)
    monkeypatch.setattr(commissioning, "_DESTINATION_UID", os.getuid())
    monkeypatch.setattr(commissioning, "_DESTINATION_GID", os.getgid())

    paths = commissioning.FastPaperShadowCommissioningInstallPaths(
        current_link=current,
        unit_destination=destination,
    )
    return {
        "release": release,
        "current": current,
        "python": venv_python,
        "wheel": wheel,
        "unit": unit,
        "env": env,
        "systemd": systemd,
        "destination": destination,
        "paths": paths,
    }


def _preflight(setup: dict[str, object]) -> dict[str, object]:
    return commissioning.preflight_release_bound_fast_paper_shadow_unit(
        expected_release_source_sha=_SOURCE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["python"],
    )


def _install(setup: dict[str, object]) -> dict[str, object]:
    return commissioning.install_release_bound_fast_paper_shadow_unit(
        expected_release_source_sha=_SOURCE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["python"],
    )


def test_preflight_authenticates_exact_release_and_reports_absent_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    result = _preflight(setup)

    assert result["status"] == "READY_TO_INSTALL"
    assert result["release_source_sha"] == _SOURCE_SHA
    assert result["release_dir"] == str(setup["release"].resolve())
    assert result["wheel_sha256"] == hashlib.sha256(
        setup["wheel"].read_bytes()
    ).hexdigest()
    assert result["unit_sha256"] == hashlib.sha256(
        setup["unit"].read_bytes()
    ).hexdigest()
    assert result["service_activation_authority"] == "NOT_GRANTED"
    assert result["paper_cutover_authority"] == "NOT_GRANTED"
    assert result["signing_submission_authority"] == "NOT_GRANTED"
    assert result["live_authority"] == "DISABLED"
    assert isinstance(result["receipt_fingerprint_sha256"], str)


def test_install_publishes_exact_root_owned_unit_without_activation_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)

    receipt = _install(setup)
    assert receipt["status"] == "INSTALLED"
    destination = setup["destination"]
    assert destination.read_bytes() == setup["unit"].read_bytes()
    metadata = destination.stat()
    assert metadata.st_uid == commissioning._DESTINATION_UID
    assert metadata.st_gid == commissioning._DESTINATION_GID
    assert stat.S_IMODE(metadata.st_mode) == 0o644

    preflight = _preflight(setup)
    assert preflight["status"] == "READY_ALREADY_INSTALLED"

    again = _install(setup)
    assert again["status"] == "ALREADY_INSTALLED"
    assert again["unit_sha256"] == receipt["unit_sha256"]


def test_wrong_release_runtime_or_tampered_wheel_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)

    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="release",
    ):
        commissioning.preflight_release_bound_fast_paper_shadow_unit(
            expected_release_source_sha="b" * 40,
            paths=setup["paths"],
            runtime_executable=setup["python"],
        )

    wrong_python = tmp_path / "python"
    wrong_python.write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="virtualenv",
    ):
        commissioning.preflight_release_bound_fast_paper_shadow_unit(
            expected_release_source_sha=_SOURCE_SHA,
            paths=setup["paths"],
            runtime_executable=wrong_python,
        )

    setup["wheel"].write_bytes(setup["wheel"].read_bytes() + b"tamper")
    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="wheel",
    ):
        _preflight(setup)


def test_existing_divergent_symlink_or_wrong_metadata_destination_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    destination = setup["destination"]

    destination.write_bytes(b"wrong")
    destination.chmod(0o644)
    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="different bytes",
    ):
        _preflight(setup)

    destination.unlink()
    other = tmp_path / "other"
    other.write_bytes(setup["unit"].read_bytes())
    destination.symlink_to(other)
    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="non-symlink|regular",
    ):
        _preflight(setup)

    destination.unlink()
    destination.write_bytes(setup["unit"].read_bytes())
    destination.chmod(0o600)
    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="metadata",
    ):
        _preflight(setup)


def test_unsafe_unit_shape_inside_authenticated_package_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    unit = setup["unit"]
    unit.write_text(
        unit.read_text(encoding="utf-8") + "\n[Install]\nWantedBy=shreks.target\n",
        encoding="utf-8",
    )

    package = tmp_path / "unsafe-package"
    stage_fast_paper_shadow_commissioning_package(
        source_sha=_SOURCE_SHA,
        platform=_PLATFORM,
        assets={
            FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES[0]: unit,
            FAST_PAPER_SHADOW_COMMISSIONING_ASSET_NAMES[1]: setup["env"],
        },
        destination=package,
    )
    wheel = setup["wheel"]
    prefix = "shreks_brain/_sealed_fast_paper_shadow_commissioning/"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in sorted(package.iterdir()):
            archive.write(path, f"{prefix}{path.name}")

    manifest_path = setup["release"] / "RELEASE_MANIFEST.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["files"][0]["size"] = wheel.stat().st_size
    raw["files"][0]["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    manifest_path.write_bytes(_canonical(raw))

    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="unit safety",
    ):
        _preflight(setup)


def test_current_release_change_before_publish_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    original = commissioning._require_current_release
    calls = 0

    def switch_on_publish_check(current_link: Path, expected_sha: str) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            setup["current"].unlink()
            other = setup["release"].parent / ("b" * 40)
            other.mkdir()
            setup["current"].symlink_to(other)
        return original(current_link, expected_sha)

    monkeypatch.setattr(
        commissioning,
        "_require_current_release",
        switch_on_publish_check,
    )
    with pytest.raises(
        commissioning.FastPaperShadowCommissioningInstallError,
        match="release",
    ):
        _install(setup)
    assert not setup["destination"].exists()


def test_commissioning_installer_authority_firewall_and_operator_contract() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "fast_paper_shadow_commissioning_install.py"
    ).read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")
    release_manager = _RELEASE_MANAGER.read_text(encoding="utf-8")
    target = _TARGET.read_text(encoding="utf-8")

    for forbidden in (
        "subprocess",
        "systemctl",
        "daemon-reload",
        " enable ",
        " start ",
        " restart ",
        " stop ",
        "shreks_brain.scoring",
        "score_candidate",
        "requests.",
        "httpx",
        "wallet",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    assert (
        'shreks-fast-paper-shadow-commissioning = '
        '"shreks_brain.fast_paper_shadow_commissioning_install:main"'
    ) in pyproject
    assert "shreks-fast-paper-shadow.service" not in release_manager
    assert "shreks-fast-paper-shadow.service" not in target
