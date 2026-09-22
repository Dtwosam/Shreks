from __future__ import annotations

from pathlib import Path
import stat

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
import shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh as refresh

from test_g1c_v2_paper_manifest_manager_installation_proof import (
    RELEASE_SHA,
    _layout,
)


def _refresh(setup):
    return refresh.refresh_release_bound_paper_manifest_manager_installation_proof(
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime_python"],
        command_runner=setup["runner"],
    )


def test_refresh_proves_exact_already_installed_helper_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["destination"].write_bytes(setup["manager_payload"])
    setup["destination"].chmod(0o755)

    before = setup["destination"].stat()
    before_bytes = setup["destination"].read_bytes()

    proof = _refresh(setup)

    after = setup["destination"].stat()
    assert proof["status"] == "VERIFIED"
    assert proof["release_source_sha"] == RELEASE_SHA
    assert proof["manager_destination"] == str(setup["destination"])
    assert proof["installation_authority"] == (
        "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY"
    )
    assert proof["manifest_rotation_authority"] == "NOT_GRANTED"
    assert proof["scoring_authority"] == "NOT_GRANTED"
    assert proof["paper_promotion_authority"] == "BLOCKED"
    assert proof["live_authority"] == "DISABLED"

    assert setup["destination"].read_bytes() == before_bytes
    assert after.st_ino == before.st_ino
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
    assert stat.S_IMODE(after.st_mode) == 0o755


def test_refresh_rejects_absent_helper_without_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)

    with pytest.raises(
        refresh.PaperManifestManagerInstallationProofRefreshError,
        match="already installed|absent|refresh",
    ):
        _refresh(setup)

    assert not setup["destination"].exists()


def test_refresh_rejects_different_helper_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    different = setup["manager_payload"] + b"\n# drift\n"
    setup["destination"].write_bytes(different)
    setup["destination"].chmod(0o755)

    with pytest.raises(
        refresh.PaperManifestManagerInstallationProofRefreshError,
        match="different bytes|already installed|refresh",
    ):
        _refresh(setup)

    assert setup["destination"].read_bytes() == different


def test_refresh_rejects_metadata_mismatch_without_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    setup["destination"].write_bytes(setup["manager_payload"])
    setup["destination"].chmod(0o700)

    with pytest.raises(
        refresh.PaperManifestManagerInstallationProofRefreshError,
        match="metadata|already installed|refresh",
    ):
        _refresh(setup)

    assert stat.S_IMODE(setup["destination"].stat().st_mode) == 0o700


def test_require_already_installed_mode_never_publishes_absent_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    called = False

    def _forbidden_publish(*_args, **_kwargs):
        nonlocal called
        called = True
        pytest.fail("publication must be unreachable in proof-refresh mode")

    monkeypatch.setattr(installer, "_publish_no_replace", _forbidden_publish)

    with pytest.raises(
        installer.PaperManifestManagerInstallError,
        match=r"already.*installed",
    ):
        installer.install_release_bound_paper_manifest_manager(
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["install_paths"],
            runtime_executable=setup["runtime_python"],
            require_already_installed=True,
        )

    assert called is False
    assert not setup["destination"].exists()


def test_refresh_cli_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_manager_installation_proof_refresh.py"
    ).read_text(encoding="utf-8")
    installer_source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_manager_install.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-paper-manifest-manager-install-proof-refresh = '
        '"shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh:main"'
        in pyproject
    )
    assert "expected_release_source_sha" in source
    assert "require_already_installed=True" in source
    assert 'receipt["status"] != "ALREADY_INSTALLED"' in source

    for forbidden in (
        "_publish_no_replace",
        "os.link(",
        "os.replace(",
        "chmod(",
        "chown(",
        'systemctl", "stop',
        'systemctl", "start',
        'systemctl", "restart',
        " rotate ",
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    assert "require_already_installed: bool = False" in installer_source
    assert "if require_already_installed:" in installer_source
    assert "must already be installed for proof refresh" in installer_source
