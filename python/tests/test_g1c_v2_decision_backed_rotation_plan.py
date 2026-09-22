from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.g1c_v2_decision_backed_rotation_plan as plan
from shreks_brain import g1c_v2_paper_manifest_rotation_readiness as readiness

from test_g1c_v2_decision_backed_rotation_readiness import (
    RELEASE_SHA,
    _inputs,
)


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


def _services() -> list[dict[str, object]]:
    return [
        {
            "unit": unit,
            "active_state": "active",
            "sub_state": "running",
            "n_restarts": 0,
            "main_pid": index + 100,
            "exec_main_status": 0,
            "active_enter_timestamp_monotonic": 1000 + index,
        }
        for index, unit in enumerate(
            (
                "shreks-observe.service",
                "shreks-paper-evidence.service",
                "shreks-paper-campaign.service",
            )
        )
    ]


def _readiness_receipt(authority, binding) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_name": "shreks.g1c_v2_paper_manifest_rotation_readiness",
        "schema_version": 1,
        "status": "READY_EVIDENCE_ONLY",
        "release_source_sha": RELEASE_SHA,
        "release_directory": f"/opt/shreks/releases/{RELEASE_SHA}",
        "wheel_relative_path": "python/shreks_brain-0.1.0-py3-none-any.whl",
        "wheel_sha256": "1" * 64,
        "manager_sha256": "2" * 64,
        "manager_destination": "/usr/local/sbin/shreks-paper-manifest-manager",
        "installation_proof_fingerprint_sha256": "3" * 64,
        "deploy_sudoers_sha256": "4" * 64,
        "source_manifest_sha256": authority["source_manifest_sha256"],
        "source_runtime_manifest_fingerprint_sha256": authority[
            "source_runtime_manifest_fingerprint_sha256"
        ],
        "source_paper_run_id": authority["source_paper_run_id"],
        "source_quote_asset_mint": authority["source_quote_asset_mint"],
        "candidate_manifest_sha256": authority["candidate_manifest_sha256"],
        "candidate_runtime_manifest_fingerprint_sha256": authority[
            "candidate_runtime_manifest_fingerprint_sha256"
        ],
        "candidate_paper_run_id": authority["candidate_paper_run_id"],
        "candidate_start_at_unix_ms": authority["candidate_start_at_unix_ms"],
        "candidate_quote_asset_mint": authority["candidate_quote_asset_mint"],
        "candidate_quote_asset_decimals": authority["candidate_quote_asset_decimals"],
        "binding_fingerprint_sha256": binding["binding_fingerprint_sha256"],
        "risk_control_revision": 7,
        "risk_control_halt_new_entries": False,
        "risk_control_kill_switch_active": False,
        "services": _services(),
        "candidate_preflight_status": "PASSED",
        "runtime_env_contract": "MATCHED",
        "service_lifecycle_unchanged": True,
        "readiness_fingerprint_sha256": "0" * 64,
        "installation_authority": "PROVEN",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    document["readiness_fingerprint_sha256"] = readiness._fingerprint(
        document,
        "readiness_fingerprint_sha256",
    )
    return document


def _host_patches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authority,
    binding,
    candidate_path: Path,
    binding_path: Path,
    receipt,
    evidence_dir: Path,
):
    status = {
        "status": "MATCHED_CURRENT_RELEASE",
        "release_source_sha": RELEASE_SHA,
        "release_directory": f"/opt/shreks/releases/{RELEASE_SHA}",
        "wheel_relative_path": receipt["wheel_relative_path"],
        "wheel_sha256": receipt["wheel_sha256"],
        "expected_manager_sha256": receipt["manager_sha256"],
        "destination": receipt["manager_destination"],
        "observation_authority": "READ_ONLY",
        "installation_authority": "NOT_EXERCISED",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    monkeypatch.setattr(plan.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        plan.manager_status,
        "inspect_release_bound_paper_manifest_manager_status",
        lambda **_kwargs: dict(status),
    )
    monkeypatch.setattr(
        plan.standard_readiness,
        "_load_and_verify_inputs",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        plan.standard_readiness,
        "_require_runtime_env_contract",
        lambda _paths: None,
    )
    monkeypatch.setattr(
        plan.install_proof,
        "_sudoers_observation",
        lambda _path: {"sha256": receipt["deploy_sudoers_sha256"]},
    )
    monkeypatch.setattr(
        plan.standard_readiness,
        "_load_risk_state",
        lambda _path: SimpleNamespace(
            revision=receipt["risk_control_revision"],
            halt_new_entries=receipt["risk_control_halt_new_entries"],
            kill_switch_active=receipt["risk_control_kill_switch_active"],
        ),
    )
    monkeypatch.setattr(
        plan.standard_readiness,
        "_service_observations",
        lambda _runner: list(receipt["services"]),
    )

    original_lstat = Path.lstat

    def _lstat(path: Path):
        if path == evidence_dir:
            raise FileNotFoundError(path)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", _lstat)


def test_plan_binds_exact_readiness_to_one_manual_rotation_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        _readiness_paths,
    ) = _inputs(tmp_path, monkeypatch)
    receipt = _readiness_receipt(authority, binding)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_bytes(_canonical(receipt))

    paths = plan.DecisionBackedRotationPlanPaths(
        current_link=Path("/opt/shreks/current"),
        active_manifest_path=Path("/etc/shreks/paper-campaign.json"),
        env_file=Path("/etc/shreks/shreks.env"),
        observer_database_path=Path("/var/lib/shreks/shreks.db"),
        evidence_path=Path("/var/lib/shreks/paper-evaluation-e11.json"),
        risk_control_path=Path("/var/lib/shreks/risk/operator-control.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
        rotation_evidence_root=Path("/var/lib/shreks/manifest-rotations"),
    )
    evidence_dir = paths.rotation_evidence_root / binding["binding_fingerprint_sha256"]
    _host_patches(
        monkeypatch,
        authority=authority,
        binding=binding,
        candidate_path=candidate_path,
        binding_path=binding_path,
        receipt=receipt,
        evidence_dir=evidence_dir,
    )

    before = {
        "candidate": candidate_path.read_bytes(),
        "binding": binding_path.read_bytes(),
        "authority": authority_path.read_bytes(),
        "readiness": readiness_path.read_bytes(),
    }
    document = plan.build_decision_backed_paper_manifest_rotation_plan(
        candidate_runtime_manifest_path=candidate_path,
        transition_binding_path=binding_path,
        decision_backed_candidate_authority_path=authority_path,
        readiness_receipt_path=readiness_path,
        expected_release_source_sha=RELEASE_SHA,
        paths=paths,
        runtime_executable=Path(
            f"/opt/shreks/releases/{RELEASE_SHA}/.venv/bin/python"
        ),
        service_runner=lambda _command: None,
    )

    assert document["status"] == "READY_FOR_TRUSTED_ADMIN_ROTATION_CEREMONY"
    assert document["release_source_sha"] == RELEASE_SHA
    assert document["authority_fingerprint_sha256"] == authority[
        "authority_fingerprint_sha256"
    ]
    assert document["readiness_fingerprint_sha256"] == receipt[
        "readiness_fingerprint_sha256"
    ]
    assert document["binding_fingerprint_sha256"] == binding[
        "binding_fingerprint_sha256"
    ]
    assert document["rotation_evidence_directory"] == str(evidence_dir)
    assert document["rotation_evidence_directory_status"] == "ABSENT"
    assert document["planning_authority"] == "READ_ONLY"
    assert document["manifest_rotation_authority"] == "NOT_EXERCISED"
    assert document["scoring_authority"] == "NOT_GRANTED"
    assert document["paper_promotion_authority"] == "BLOCKED"
    assert document["live_authority"] == "DISABLED"
    assert document["plan_fingerprint_sha256"] == plan._fingerprint(
        document,
        "plan_fingerprint_sha256",
    )

    steps = document["steps"]
    assert len(steps) == 1
    assert steps[0]["name"] == "trusted_admin_rotate_protected_paper_manifest"
    assert steps[0]["argv"] == [
        "/usr/local/sbin/shreks-paper-manifest-manager",
        "rotate",
        str(candidate_path.resolve()),
        str(binding_path.resolve()),
        binding["binding_fingerprint_sha256"],
        RELEASE_SHA,
    ]
    assert steps[0]["requires_explicit_root_invocation"] is True
    assert steps[0]["executed_by_planner"] is False

    assert candidate_path.read_bytes() == before["candidate"]
    assert binding_path.read_bytes() == before["binding"]
    assert authority_path.read_bytes() == before["authority"]
    assert readiness_path.read_bytes() == before["readiness"]


def test_plan_rejects_tampered_readiness_fingerprint_before_host_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        _readiness_paths,
    ) = _inputs(tmp_path, monkeypatch)
    receipt = _readiness_receipt(authority, binding)
    receipt["readiness_fingerprint_sha256"] = "0" * 64
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_bytes(_canonical(receipt))

    monkeypatch.setattr(plan.os, "geteuid", lambda: 0)
    with pytest.raises(
        plan.DecisionBackedRotationPlanError,
        match="readiness.*fingerprint",
    ):
        plan.build_decision_backed_paper_manifest_rotation_plan(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            decision_backed_candidate_authority_path=authority_path,
            readiness_receipt_path=readiness_path,
            expected_release_source_sha=RELEASE_SHA,
            paths=plan._production_paths(),
        )


def test_plan_rejects_existing_rotation_evidence_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        _readiness_paths,
    ) = _inputs(tmp_path, monkeypatch)
    receipt = _readiness_receipt(authority, binding)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_bytes(_canonical(receipt))
    paths = plan.DecisionBackedRotationPlanPaths(
        current_link=Path("/opt/shreks/current"),
        active_manifest_path=Path("/etc/shreks/paper-campaign.json"),
        env_file=Path("/etc/shreks/shreks.env"),
        observer_database_path=Path("/var/lib/shreks/shreks.db"),
        evidence_path=Path("/var/lib/shreks/paper-evaluation-e11.json"),
        risk_control_path=Path("/var/lib/shreks/risk/operator-control.json"),
        deploy_sudoers=Path("/etc/sudoers.d/shreks-release-manager"),
        manager_destination=Path("/usr/local/sbin/shreks-paper-manifest-manager"),
        rotation_evidence_root=tmp_path / "rotations",
    )
    evidence_dir = paths.rotation_evidence_root / binding["binding_fingerprint_sha256"]
    evidence_dir.mkdir(parents=True)
    _host_patches(
        monkeypatch,
        authority=authority,
        binding=binding,
        candidate_path=candidate_path,
        binding_path=binding_path,
        receipt=receipt,
        evidence_dir=tmp_path / "different-never-matched",
    )

    with pytest.raises(
        plan.DecisionBackedRotationPlanError,
        match="rotation evidence directory.*must not already exist",
    ):
        plan.build_decision_backed_paper_manifest_rotation_plan(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            decision_backed_candidate_authority_path=authority_path,
            readiness_receipt_path=readiness_path,
            expected_release_source_sha=RELEASE_SHA,
            paths=paths,
            runtime_executable=Path(
                f"/opt/shreks/releases/{RELEASE_SHA}/.venv/bin/python"
            ),
            service_runner=lambda _command: None,
        )


def test_plan_rejects_service_state_drift_from_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        authority_path,
        authority,
        candidate_path,
        _candidate,
        binding_path,
        binding,
        _readiness_paths,
    ) = _inputs(tmp_path, monkeypatch)
    receipt = _readiness_receipt(authority, binding)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_bytes(_canonical(receipt))
    paths = plan._production_paths()
    evidence_dir = paths.rotation_evidence_root / binding["binding_fingerprint_sha256"]
    _host_patches(
        monkeypatch,
        authority=authority,
        binding=binding,
        candidate_path=candidate_path,
        binding_path=binding_path,
        receipt=receipt,
        evidence_dir=evidence_dir,
    )
    monkeypatch.setattr(
        plan.standard_readiness,
        "_service_observations",
        lambda _runner: [
            {**value, "main_pid": 999999}
            for value in receipt["services"]
        ],
    )

    with pytest.raises(
        plan.DecisionBackedRotationPlanError,
        match="service.*changed|services.*readiness",
    ):
        plan.build_decision_backed_paper_manifest_rotation_plan(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            decision_backed_candidate_authority_path=authority_path,
            readiness_receipt_path=readiness_path,
            expected_release_source_sha=RELEASE_SHA,
            paths=paths,
            runtime_executable=Path(
                f"/opt/shreks/releases/{RELEASE_SHA}/.venv/bin/python"
            ),
            service_runner=lambda _command: None,
        )


def test_rotation_plan_cli_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "shreks_brain"
        / "g1c_v2_decision_backed_rotation_plan.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-decision-backed-rotation-plan = '
        '"shreks_brain.g1c_v2_decision_backed_rotation_plan:main"'
        in pyproject
    )
    for required in (
        "--candidate-runtime-manifest",
        "--transition-binding",
        "--decision-backed-candidate-authority",
        "--readiness-receipt",
        "--expected-release-source-sha",
    ):
        assert required in source

    for forbidden_argument in (
        "--expected-binding-fingerprint",
        "--paper-run-id",
        "--start-at-unix-ms",
        "--quote-asset-mint",
        "--quote-asset-decimals",
        "--entry-input-amount",
        "--candidate-value-decision",
    ):
        assert forbidden_argument not in source

    for forbidden_runtime_surface in (
        "subprocess",
        "os.replace(",
        "os.link(",
        ".write_bytes(",
        ".write_text(",
        ".mkdir(",
        "systemctl stop",
        "systemctl start",
        "systemctl restart",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden_runtime_surface not in source

    assert '"planning_authority": "READ_ONLY"' in source
    assert '"manifest_rotation_authority": "NOT_EXERCISED"' in source
    assert '"executed_by_planner": False' in source
