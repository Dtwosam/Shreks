from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

import pytest

from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    bind_g1c_v2_runtime_manifest_transition,
)
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    build_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.risk_control import initialize_operator_risk_control_state

from test_g1c_v2_runtime_manifest_transition_binding import _inputs
from test_g2_release_manager import _build_bundle


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_DIR = _REPO_ROOT / "deploy" / "release"
if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

_MANAGER_SPEC = importlib.util.spec_from_file_location(
    "shreks_g1c_paper_manifest_manager",
    _RELEASE_DIR / "paper_manifest_manager.py",
)
assert _MANAGER_SPEC is not None and _MANAGER_SPEC.loader is not None
manager = importlib.util.module_from_spec(_MANAGER_SPEC)
sys.modules[_MANAGER_SPEC.name] = manager
_MANAGER_SPEC.loader.exec_module(manager)


RELEASE_SHA = "c" * 40


class SystemctlRunner:
    def __init__(self, *, fail_first_health: bool = False):
        self.calls: list[tuple[str, ...]] = []
        self.fail_first_health = fail_first_health
        self.health_checks = 0

    def __call__(self, command: tuple[str, ...]) -> None:
        self.calls.append(command)
        if command == (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ):
            self.health_checks += 1
            if self.fail_first_health and self.health_checks == 1:
                raise RuntimeError("simulated candidate health failure")


class PreflightRunner:
    def __init__(self, *, fail_first: bool = False):
        self.paths: list[Path] = []
        self.fail_first = fail_first

    def __call__(self, config):
        self.paths.append(config.manifest_path)
        if self.fail_first and len(self.paths) == 1:
            raise ObserverPaperCampaignRuntimeError(
                "simulated candidate preflight failure"
            )
        return object()


def _rotation_paths(tmp_path: Path):
    etc = tmp_path / "etc" / "shreks"
    state = tmp_path / "var" / "lib" / "shreks"
    return manager.PaperManifestRotationPaths(
        current_link=tmp_path / "opt" / "shreks" / "current",
        env_file=etc / "shreks.env",
        active_manifest_path=etc / "paper-campaign.json",
        observer_database_path=state / "shreks.db",
        evidence_path=state / "paper-evaluation-e11.json",
        risk_control_path=state / "risk" / "operator-control.json",
        rotation_evidence_root=state / "manifest-rotations",
    )


def _write_runtime_env(paths) -> None:
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


def _write_current_release(tmp_path: Path, paths) -> Path:
    _archive, _checksum, release_manifest, _manifest = _build_bundle(
        tmp_path / "release-bundle",
        RELEASE_SHA,
        "rotation",
    )
    release_dir = paths.current_link.parent / "releases" / RELEASE_SHA
    release_dir.mkdir(parents=True)
    (release_dir / "RELEASE_MANIFEST.json").write_bytes(
        release_manifest.read_bytes()
    )
    runtime_python = release_dir / ".venv" / "bin" / "python"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime_python.chmod(0o755)
    paths.current_link.parent.mkdir(parents=True, exist_ok=True)
    paths.current_link.symlink_to(release_dir)
    return release_dir


def _safe_atomic_replace(path: Path, payload: bytes, metadata) -> None:
    temporary = path.parent / f".{path.name}.test.tmp"
    temporary.write_bytes(payload)
    temporary.chmod(metadata.mode)
    os.replace(temporary, path)


def _setup_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (
        source,
        source_path,
        source_bytes,
        candidate,
        candidate_path,
        candidate_bytes,
        cohort_path,
        request_path,
    ) = _inputs(tmp_path, monkeypatch)

    binding_path = tmp_path / "transition-binding.json"
    binding = bind_g1c_v2_runtime_manifest_transition(
        source_runtime_manifest_path=source_path,
        candidate_runtime_manifest_path=candidate_path,
        cohort_path=cohort_path,
        v2_host_request_authority_path=request_path,
        destination=binding_path,
    )

    paths = _rotation_paths(tmp_path)
    paths.active_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    paths.active_manifest_path.write_bytes(source_bytes)
    paths.active_manifest_path.chmod(0o640)
    _write_runtime_env(paths)
    paths.risk_control_path.parent.mkdir(parents=True, exist_ok=True)
    initialize_operator_risk_control_state(
        paths.risk_control_path,
        observed_at_unix_ms=1_000,
    )
    release_dir = _write_current_release(tmp_path, paths)

    monkeypatch.setattr(
        manager,
        "_atomic_replace_manifest",
        _safe_atomic_replace,
    )
    return {
        "source": source,
        "source_bytes": source_bytes,
        "candidate": candidate,
        "candidate_path": candidate_path,
        "candidate_bytes": candidate_bytes,
        "binding": binding,
        "binding_path": binding_path,
        "paths": paths,
        "release_dir": release_dir,
    }


def _identity_reader(release_dir: Path):
    return lambda _unit: (
        4242,
        release_dir / ".venv" / "bin" / "python",
        release_dir,
    )


def test_successful_rotation_preflights_private_copy_and_writes_activation_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_rotation(tmp_path, monkeypatch)
    runner = SystemctlRunner()
    preflight = PreflightRunner()

    receipt = manager.rotate_paper_manifest(
        candidate_runtime_manifest_path=setup["candidate_path"],
        transition_binding_path=setup["binding_path"],
        expected_binding_fingerprint_sha256=setup["binding"][
            "binding_fingerprint_sha256"
        ],
        expected_release_source_sha=RELEASE_SHA,
        paths=setup["paths"],
        command_runner=runner,
        runtime_identity_reader=_identity_reader(setup["release_dir"]),
        preflight_runner=preflight,
    )

    assert receipt["status"] == "ACTIVATED"
    assert receipt["scoring_authority"] == "NOT_GRANTED"
    assert receipt["paper_promotion_authority"] == "BLOCKED"
    assert receipt["live_authority"] == "DISABLED"
    assert setup["paths"].active_manifest_path.read_bytes() == setup["candidate_bytes"]
    assert stat.S_IMODE(setup["paths"].active_manifest_path.stat().st_mode) == 0o640

    evidence = (
        setup["paths"].rotation_evidence_root
        / setup["binding"]["binding_fingerprint_sha256"]
    )
    assert preflight.paths == [
        evidence / "candidate-paper-campaign.json",
        setup["paths"].active_manifest_path,
    ]
    assert runner.calls == [
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "start", "shreks-paper-campaign.service"),
        (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ),
    ]
    assert {
        path.name
        for path in evidence.iterdir()
    } == {
        "source-paper-campaign.json",
        "candidate-paper-campaign.json",
        "transition-binding.json",
        "prepared.json",
        "activated.json",
    }
    for path in evidence.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o700
    assert (
        evidence / "candidate-paper-campaign.json"
    ).read_bytes() == setup["candidate_bytes"]


def test_candidate_preflight_failure_restarts_source_without_replacing_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_rotation(tmp_path, monkeypatch)
    runner = SystemctlRunner()
    preflight = PreflightRunner(fail_first=True)

    with pytest.raises(
        manager.PaperManifestManagerError,
        match="source manifest restored",
    ):
        manager.rotate_paper_manifest(
            candidate_runtime_manifest_path=setup["candidate_path"],
            transition_binding_path=setup["binding_path"],
            expected_binding_fingerprint_sha256=setup["binding"][
                "binding_fingerprint_sha256"
            ],
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["paths"],
            command_runner=runner,
            runtime_identity_reader=_identity_reader(setup["release_dir"]),
            preflight_runner=preflight,
        )

    assert setup["paths"].active_manifest_path.read_bytes() == setup["source_bytes"]
    assert runner.calls == [
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "start", "shreks-paper-campaign.service"),
        (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ),
    ]
    evidence = (
        setup["paths"].rotation_evidence_root
        / setup["binding"]["binding_fingerprint_sha256"]
    )
    assert (evidence / "prepared.json").is_file()
    assert (evidence / "rolled-back.json").is_file()
    assert not (evidence / "activated.json").exists()


def test_candidate_activation_health_failure_restores_source_and_restarts_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_rotation(tmp_path, monkeypatch)
    runner = SystemctlRunner(fail_first_health=True)
    preflight = PreflightRunner()

    with pytest.raises(
        manager.PaperManifestManagerError,
        match="source manifest restored",
    ):
        manager.rotate_paper_manifest(
            candidate_runtime_manifest_path=setup["candidate_path"],
            transition_binding_path=setup["binding_path"],
            expected_binding_fingerprint_sha256=setup["binding"][
                "binding_fingerprint_sha256"
            ],
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["paths"],
            command_runner=runner,
            runtime_identity_reader=_identity_reader(setup["release_dir"]),
            preflight_runner=preflight,
        )

    assert setup["paths"].active_manifest_path.read_bytes() == setup["source_bytes"]
    assert preflight.paths[-1] == setup["paths"].active_manifest_path
    assert runner.calls == [
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "start", "shreks-paper-campaign.service"),
        (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ),
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "start", "shreks-paper-campaign.service"),
        (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ),
    ]


def test_candidate_runtime_identity_failure_stops_candidate_before_source_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_rotation(tmp_path, monkeypatch)
    runner = SystemctlRunner()
    preflight = PreflightRunner()
    identity_calls = 0

    def identity_reader(_unit):
        nonlocal identity_calls
        identity_calls += 1
        if identity_calls == 1:
            raise RuntimeError("simulated candidate identity failure")
        return (
            4243,
            setup["release_dir"] / ".venv" / "bin" / "python",
            setup["release_dir"],
        )

    with pytest.raises(
        manager.PaperManifestManagerError,
        match="source manifest restored",
    ):
        manager.rotate_paper_manifest(
            candidate_runtime_manifest_path=setup["candidate_path"],
            transition_binding_path=setup["binding_path"],
            expected_binding_fingerprint_sha256=setup["binding"][
                "binding_fingerprint_sha256"
            ],
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["paths"],
            command_runner=runner,
            runtime_identity_reader=identity_reader,
            preflight_runner=preflight,
        )

    assert setup["paths"].active_manifest_path.read_bytes() == setup["source_bytes"]
    assert runner.calls == [
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "start", "shreks-paper-campaign.service"),
        (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ),
        ("systemctl", "stop", "shreks-paper-campaign.service"),
        ("systemctl", "start", "shreks-paper-campaign.service"),
        (
            "systemctl",
            "is-active",
            "--quiet",
            "shreks-paper-campaign.service",
        ),
    ]
    assert identity_calls == 2


def test_active_manifest_mismatch_is_rejected_before_campaign_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_rotation(tmp_path, monkeypatch)
    source = setup["source"]
    drifted = build_observer_paper_campaign_runtime_manifest(
        paper_run_id=source.paper_run_id,
        candidate=source.candidate,
        initial_state=source.initial_state,
        policy_bundle=source.policy_bundle,
        risk_environment=source.risk_environment,
        selection_policy=source.selection_policy,
        recent_performance=source.recent_performance,
        global_risk_halt=not source.global_risk_halt,
    )
    setup["paths"].active_manifest_path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(drifted)
    )
    setup["paths"].active_manifest_path.chmod(0o640)
    runner = SystemctlRunner()

    with pytest.raises(
        manager.PaperManifestManagerError,
        match="transition binding .* does not match",
    ):
        manager.rotate_paper_manifest(
            candidate_runtime_manifest_path=setup["candidate_path"],
            transition_binding_path=setup["binding_path"],
            expected_binding_fingerprint_sha256=setup["binding"][
                "binding_fingerprint_sha256"
            ],
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["paths"],
            command_runner=runner,
            runtime_identity_reader=_identity_reader(setup["release_dir"]),
            preflight_runner=PreflightRunner(),
        )

    assert runner.calls == []
    assert not setup["paths"].rotation_evidence_root.exists()


def test_runtime_env_path_drift_is_rejected_before_campaign_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _setup_rotation(tmp_path, monkeypatch)
    setup["paths"].env_file.write_text(
        setup["paths"].env_file.read_text(encoding="utf-8").replace(
            str(setup["paths"].observer_database_path),
            str(tmp_path / "wrong.db"),
        ),
        encoding="utf-8",
    )
    runner = SystemctlRunner()

    with pytest.raises(
        manager.PaperManifestManagerError,
        match="SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH",
    ):
        manager.rotate_paper_manifest(
            candidate_runtime_manifest_path=setup["candidate_path"],
            transition_binding_path=setup["binding_path"],
            expected_binding_fingerprint_sha256=setup["binding"][
                "binding_fingerprint_sha256"
            ],
            expected_release_source_sha=RELEASE_SHA,
            paths=setup["paths"],
            command_runner=runner,
            runtime_identity_reader=_identity_reader(setup["release_dir"]),
            preflight_runner=PreflightRunner(),
        )

    assert runner.calls == []


def test_rotation_manager_is_manual_root_authority_and_does_not_widen_deploy_sudo() -> None:
    source = (_RELEASE_DIR / "paper_manifest_manager.py").read_text(
        encoding="utf-8"
    )
    runbook = (_RELEASE_DIR / "README.md").read_text(encoding="utf-8")
    build_script = (_RELEASE_DIR / "build_release.sh").read_text(encoding="utf-8")

    assert source.startswith("#!/opt/shreks/current/.venv/bin/python")
    assert "os.geteuid() != 0" in source
    assert "/etc/shreks/paper-campaign.json" in source
    assert "/var/lib/shreks/manifest-rotations" in source

    for forbidden in (
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    assert (
        "shreks-deploy ALL=(root) NOPASSWD: "
        "/usr/local/sbin/shreks-paper-manifest-manager"
    ) not in runbook
    assert (
        'cp deploy/release/paper_manifest_manager.py '
        '"$CONTROL_PACKAGE/paper_manifest_manager.py"'
    ) in build_script
    assert (
        "shreks_brain/_sealed_deploy_control/paper_manifest_manager.py"
        in build_script
    )
    assert (
        "shreks_brain/_sealed_deploy_control/paper_manifest_manager.py"
        in runbook
    )
