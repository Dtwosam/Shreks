from __future__ import annotations

import os
from pathlib import Path

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install_plan as plan
from shreks_brain import g1c_v2_paper_manifest_manager_installation_proof as proof

from test_g1c_v2_paper_manifest_manager_installation_proof import (
    RELEASE_SHA,
    _layout,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNBOOK = _REPO_ROOT / "deploy" / "release" / "README.md"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"


def _paths(tmp_path: Path, setup) -> plan.PaperManifestManagerInstallPlanPaths:
    evidence_root = tmp_path / "root"
    evidence_root.mkdir()
    return plan.PaperManifestManagerInstallPlanPaths(
        current_link=setup["paths"].current_link,
        campaign_manifest=setup["paths"].campaign_manifest,
        deploy_sudoers=setup["paths"].deploy_sudoers,
        manager_destination=setup["paths"].manager_destination,
        evidence_root=evidence_root,
    )


def _build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setup, *, runner=None):
    monkeypatch.setattr(plan.os, "geteuid", lambda: 0)
    return plan.build_release_bound_paper_manifest_manager_install_plan(
        expected_release_source_sha=RELEASE_SHA,
        paths=_paths(tmp_path, setup),
        runtime_executable=setup["runtime_python"],
        command_runner=setup["runner"] if runner is None else runner,
    )


def test_install_plan_authenticates_absent_helper_and_emits_exact_read_only_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path / "layout", monkeypatch)

    document = _build(tmp_path, monkeypatch, setup)

    evidence_dir = (
        tmp_path
        / "root"
        / f"shreks-paper-manifest-manager-install-{RELEASE_SHA}"
    )
    assert document["status"] == "READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY"
    assert document["release_source_sha"] == RELEASE_SHA
    assert document["helper_status"] == "ABSENT"
    assert document["manager_destination"] == str(setup["destination"])
    assert document["preflight_snapshot_fingerprint_sha256"] != proof._ZERO_SHA256
    assert document["evidence_directory"] == str(evidence_dir)
    assert document["evidence_directory_mode"] == "0700"
    assert document["required_umask"] == "0077"
    assert document["stop_on_any_failure"] is True
    assert document["plan_preflight_is_not_installation_proof"] is True
    assert document["planning_authority"] == "READ_ONLY"
    assert document["installation_authority"] == "NOT_EXERCISED"
    assert document["manifest_rotation_authority"] == "NOT_GRANTED"
    assert document["scoring_authority"] == "NOT_GRANTED"
    assert document["paper_promotion_authority"] == "BLOCKED"
    assert document["live_authority"] == "DISABLED"
    assert document["plan_fingerprint_sha256"] == plan._fingerprint(
        document,
        "plan_fingerprint_sha256",
    )

    steps = document["steps"]
    assert [step["name"] for step in steps] == [
        "create_evidence_directory",
        "prepare_installation_proof",
        "install_exact_release_bound_helper",
        "verify_installation_proof",
    ]
    runtime = str(setup["runtime_python"].resolve())
    assert steps[1]["argv"] == [
        runtime,
        "-m",
        "shreks_brain.g1c_v2_paper_manifest_manager_installation_proof",
        "prepare",
        RELEASE_SHA,
    ]
    assert steps[2]["argv"] == [
        runtime,
        "-m",
        "shreks_brain.g1c_v2_paper_manifest_manager_install",
        RELEASE_SHA,
    ]
    assert steps[3]["argv"][0:5] == [
        runtime,
        "-m",
        "shreks_brain.g1c_v2_paper_manifest_manager_installation_proof",
        "verify",
        RELEASE_SHA,
    ]

    assert not setup["destination"].exists()
    assert not evidence_dir.exists()


def test_install_plan_rejects_any_existing_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path / "layout", monkeypatch)
    setup["destination"].write_bytes(setup["manager_payload"])
    setup["destination"].chmod(0o755)

    with pytest.raises(
        plan.PaperManifestManagerInstallPlanError,
        match="requires helper status ABSENT",
    ):
        _build(tmp_path, monkeypatch, setup)

    assert setup["destination"].read_bytes() == setup["manager_payload"]


def test_install_plan_rejects_existing_evidence_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path / "layout", monkeypatch)
    evidence_dir = (
        tmp_path
        / "root"
        / f"shreks-paper-manifest-manager-install-{RELEASE_SHA}"
    )
    evidence_dir.mkdir(parents=True)

    monkeypatch.setattr(plan.os, "geteuid", lambda: 0)
    with pytest.raises(
        plan.PaperManifestManagerInstallPlanError,
        match="evidence directory must not already exist",
    ):
        plan.build_release_bound_paper_manifest_manager_install_plan(
            expected_release_source_sha=RELEASE_SHA,
            paths=plan.PaperManifestManagerInstallPlanPaths(
                current_link=setup["paths"].current_link,
                campaign_manifest=setup["paths"].campaign_manifest,
                deploy_sudoers=setup["paths"].deploy_sudoers,
                manager_destination=setup["paths"].manager_destination,
                evidence_root=tmp_path / "root",
            ),
            runtime_executable=setup["runtime_python"],
            command_runner=setup["runner"],
        )


def test_install_plan_rejects_unhealthy_service_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path / "layout", monkeypatch)
    setup["service_state"]["shreks-paper-campaign.service"]["ActiveState"] = "inactive"

    with pytest.raises(
        plan.PaperManifestManagerInstallPlanError,
        match="installation proof preflight is not ready",
    ):
        _build(tmp_path, monkeypatch, setup)


def test_install_plan_rejects_helper_status_drift_during_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path / "layout", monkeypatch)
    calls = 0

    def drifting_runner(command: tuple[str, ...]) -> proof.HostCommandResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            setup["destination"].write_bytes(setup["manager_payload"])
            setup["destination"].chmod(0o755)
        return setup["runner"](command)

    with pytest.raises(
        plan.PaperManifestManagerInstallPlanError,
        match="helper status changed during install-plan preflight",
    ):
        _build(tmp_path, monkeypatch, setup, runner=drifting_runner)


def test_install_plan_requires_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path / "layout", monkeypatch)
    monkeypatch.setattr(plan.os, "geteuid", lambda: 1000)

    with pytest.raises(
        plan.PaperManifestManagerInstallPlanError,
        match="planning requires root",
    ):
        plan.build_release_bound_paper_manifest_manager_install_plan(
            expected_release_source_sha=RELEASE_SHA,
            paths=_paths(tmp_path, setup),
            runtime_executable=setup["runtime_python"],
            command_runner=setup["runner"],
        )


def test_install_plan_authority_firewall_and_operator_contract() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "g1c_v2_paper_manifest_manager_install_plan.py"
    ).read_text(encoding="utf-8")
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for forbidden in (
        "install_release_bound_paper_manifest_manager(",
        "verify_postinstall_state(",
        "os.replace(",
        "os.link(",
        ".mkdir(",
        ".write_bytes(",
        ".write_text(",
        "subprocess",
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
    ):
        assert forbidden not in source

    assert "proof.capture_preinstall_state(" in source
    assert '"helper_status": "ABSENT"' in source
    assert '"planning_authority": "READ_ONLY"' in source
    assert '"installation_authority": "NOT_EXERCISED"' in source
    assert '"manifest_rotation_authority": "NOT_GRANTED"' in source

    assert (
        'shreks-g1c-v2-paper-manifest-manager-install-plan = '
        '"shreks_brain.g1c_v2_paper_manifest_manager_install_plan:main"'
    ) in pyproject
    assert "Plan the trusted-admin helper installation ceremony read-only" in runbook
    assert "READY_FOR_TRUSTED_ADMIN_FIRST_INSTALL_CEREMONY" in runbook
    assert "does not create the evidence directory" in runbook
    assert "does not execute the installer" in runbook
