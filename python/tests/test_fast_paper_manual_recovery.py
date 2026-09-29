from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_manual_recovery as recovery
from shreks_brain.paper_validation import AccountingValidationStatus


_RELEASE_SHA = "a" * 40
_SOURCE_RELEASE_SHA = "b" * 40
_RUN_ID = "fast-final-run-1"
_HANDOFF_FP = "c" * 64


def _fingerprinted(
    material: dict[str, object],
    field: str,
) -> dict[str, object]:
    return {
        **material,
        field: hashlib.sha256(
            recovery._canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(
        recovery._canonical(document) + "\n",
        encoding="utf-8",
    )


def _cutover_revocation() -> dict[str, object]:
    return _fingerprinted(
        {
            "schema_name": (
                "shreks.fast_paper_cutover_authorization_revocation"
            ),
            "schema_version": 1,
            "state": "REVOKED_MANUAL_RECOVERY",
            "release_source_sha": _RELEASE_SHA,
            "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
            "service_control_authority": (
                "EXERCISED_BY_PROTECTED_CEREMONY"
            ),
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
            "error_type": "RuntimeError",
        },
        "revocation_fingerprint_sha256",
    )


def _cutover_failure() -> dict[str, object]:
    return _fingerprinted(
        {
            "schema_name": "shreks.fast_paper_physical_cutover_failure",
            "schema_version": 1,
            "state": "MANUAL_RECOVERY_REQUIRED",
            "release_source_sha": _RELEASE_SHA,
            "authoritative_state_changed": False,
            "legacy_unit_restored": False,
            "legacy_service_restarted": False,
            "fast_unit_retained": True,
            "final_fast_config_retained": True,
            "authorization_revoked": True,
            "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
            "service_control_authority": (
                "EXERCISED_BY_PROTECTED_CEREMONY"
            ),
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
            "error_type": "RuntimeError",
        },
        "receipt_fingerprint_sha256",
    )


def _release_revocation() -> dict[str, object]:
    return _fingerprinted(
        {
            "schema_name": (
                "shreks.fast_paper_release_authorization_revocation"
            ),
            "schema_version": 1,
            "state": "REVOKED_MANUAL_RECOVERY",
            "target_release_source_sha": _RELEASE_SHA,
            "target_fast_run_id": _RUN_ID,
            "release_handoff_fingerprint_sha256": _HANDOFF_FP,
            "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
            "error_type": "RuntimeError",
        },
        "receipt_fingerprint_sha256",
    )


def _release_failure() -> dict[str, object]:
    return _fingerprinted(
        {
            "schema_name": "shreks.fast_paper_release_upgrade_failure",
            "schema_version": 1,
            "state": "MANUAL_RECOVERY_REQUIRED",
            "source_release_source_sha": _SOURCE_RELEASE_SHA,
            "target_release_source_sha": _RELEASE_SHA,
            "target_fast_run_id": _RUN_ID,
            "target_start_attempted": True,
            "legacy_score_runtime_restored": False,
            "source_fast_runtime_restarted": False,
            "production_paper_cutover": "STOPPED_MANUAL_RECOVERY",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
            "error_type": "RuntimeError",
        },
        "receipt_fingerprint_sha256",
    )


def _runner(active_unit: str | None = None):
    calls: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...]) -> recovery.HostCommandResult:
        calls.append(command)
        unit = command[2]
        active = unit == active_unit
        return recovery.HostCommandResult(
            0,
            (
                f"ActiveState={'active' if active else 'inactive'}\n"
                f"SubState={'running' if active else 'dead'}\n"
                f"MainPID={123 if active else 0}\n"
            ),
            "",
        )

    run.calls = calls
    return run


def _bootstrap(
    *,
    decision_sequence: int | None = 42,
    execution_sequence: int | None = None,
    pending_buy: bool = False,
    checkpoint_sequence: int = 0,
    open_position_ids: tuple[str, ...] = (),
):
    positions = tuple(
        SimpleNamespace(
            position_id=position_id,
            state=__import__(
                "shreks_brain.paper",
                fromlist=["PaperPositionState"],
            ).PaperPositionState.OPEN,
        )
        for position_id in open_position_ids
    )
    ledger = SimpleNamespace(positions=positions)
    checkpoint = SimpleNamespace(
        sequence=checkpoint_sequence,
        payload_sha256="1" * 64,
        state=SimpleNamespace(
            pending_buy=object() if pending_buy else None,
            ledger=ledger,
        ),
    )
    runtime_state = SimpleNamespace(
        state_fingerprint_sha256="2" * 64,
        last_processed_source_sequence=execution_sequence,
        market_positions=tuple(
            SimpleNamespace(position_id=value)
            for value in open_position_ids
        ),
    )
    cursor = (
        None
        if decision_sequence is None
        else SimpleNamespace(decision_sequence=decision_sequence)
    )
    return SimpleNamespace(
        decision_bootstrap=SimpleNamespace(
            manifest=SimpleNamespace(
                release_source_sha=_RELEASE_SHA,
                manifest_fingerprint_sha256="3" * 64,
            ),
            state=SimpleNamespace(
                cursor=cursor,
                state_fingerprint_sha256="4" * 64,
            ),
        ),
        execution_bootstrap=SimpleNamespace(
            binding=SimpleNamespace(
                fast_run_id=_RUN_ID,
                binding_fingerprint_sha256="5" * 64,
            ),
            execution_policy=SimpleNamespace(
                policy_fingerprint_sha256="6" * 64,
            ),
            runtime_state=runtime_state,
            checkpoint=checkpoint,
        ),
    )


def _config(tmp_path: Path):
    decision = tmp_path / "decision"
    decision.mkdir()
    checkpoint = decision / "runtime-state.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"db")
    return SimpleNamespace(
        decision_config=SimpleNamespace(
            evidence_directory=decision,
            checkpoint_path=checkpoint,
        ),
        execution_config=SimpleNamespace(database_path=database),
    )


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bootstrap,
):
    config = _config(tmp_path)
    monkeypatch.setattr(recovery, "_require_root", lambda: None)
    monkeypatch.setattr(
        recovery,
        "read_fast_paper_authoritative_cutover_environment",
        lambda _path: {"SEALED": "ENV"},
    )
    monkeypatch.setattr(
        recovery,
        "load_fast_paper_authoritative_runtime_config",
        lambda _env: config,
    )
    monkeypatch.setattr(
        recovery,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: bootstrap,
    )
    open_count = len(
        bootstrap.execution_bootstrap.runtime_state.market_positions
    )
    monkeypatch.setattr(
        recovery,
        "validate_fast_paper_accounting",
        lambda _state: SimpleNamespace(
            status=AccountingValidationStatus.RECONCILED,
            open_position_count=open_count,
        ),
    )
    return config


def _current_link(tmp_path: Path) -> Path:
    release = tmp_path / _RELEASE_SHA
    release.mkdir()
    current = tmp_path / "current"
    current.symlink_to(release)
    return current


def test_cutover_manual_recovery_clean_baseline_is_ready_for_planning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_path = tmp_path / "revocation.json"
    failure_path = tmp_path / "failure.json"
    _write(revocation_path, _cutover_revocation())
    _write(failure_path, _cutover_failure())
    bootstrap = _bootstrap(
        decision_sequence=42,
        execution_sequence=None,
        checkpoint_sequence=0,
    )
    _patch_runtime(monkeypatch, tmp_path, bootstrap)
    runner = _runner()

    result = recovery.assess_fast_paper_manual_recovery(
        authoritative_runtime_env_path=tmp_path / "env",
        production_authorization_path=revocation_path,
        failure_receipt_path=failure_path,
        current_link=_current_link(tmp_path),
        command_runner=runner,
    )

    assert result["state"] == "READY_FOR_FAST_RECOVERY_PLANNING"
    assert result["failure_family"] == "PHYSICAL_CUTOVER"
    assert result["decision_cursor_sequence"] == 42
    assert result["execution_cursor_sequence"] is None
    assert result["pending_buy"] is False
    assert result["accounting"] == "RECONCILED"
    assert result["recovery_restart_authority"] == "NOT_GRANTED"
    assert result["service_control_authority"] == "READ_ONLY"
    assert result["live_authority"] == "DISABLED"
    assert runner.calls == [
        recovery._show_command(recovery._PAPER_UNIT),
        recovery._show_command(recovery._SHADOW_UNIT),
    ]


def test_cutover_manual_recovery_with_durable_pending_work_requires_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_path = tmp_path / "revocation.json"
    failure_path = tmp_path / "failure.json"
    _write(revocation_path, _cutover_revocation())
    _write(failure_path, _cutover_failure())
    bootstrap = _bootstrap(
        decision_sequence=43,
        execution_sequence=None,
        checkpoint_sequence=0,
    )
    config = _patch_runtime(monkeypatch, tmp_path, bootstrap)
    (config.decision_config.evidence_directory / "shadow-43.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    result = recovery.assess_fast_paper_manual_recovery(
        authoritative_runtime_env_path=tmp_path / "env",
        production_authorization_path=revocation_path,
        failure_receipt_path=failure_path,
        current_link=_current_link(tmp_path),
        command_runner=_runner(),
    )

    assert result["state"] == "RECOVERY_RECONCILIATION_REQUIRED"
    assert result["decision_evidence_count"] == 1


def test_release_upgrade_recovery_authenticates_handoff_and_open_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_path = tmp_path / "revocation.json"
    failure_path = tmp_path / "failure.json"
    _write(revocation_path, _release_revocation())
    _write(failure_path, _release_failure())
    bootstrap = _bootstrap(
        decision_sequence=7,
        execution_sequence=7,
        checkpoint_sequence=3,
        open_position_ids=("position-1",),
    )
    _patch_runtime(monkeypatch, tmp_path, bootstrap)
    observed = {}
    monkeypatch.setattr(
        recovery,
        "load_fast_paper_authoritative_release_handoff",
        lambda database, *, target_fast_run_id: (
            observed.update(
                database=database,
                target_fast_run_id=target_fast_run_id,
            )
            or SimpleNamespace(
                handoff_fingerprint_sha256=_HANDOFF_FP,
                target_release_source_sha=_RELEASE_SHA,
                source_release_source_sha=_SOURCE_RELEASE_SHA,
            )
        ),
    )
    runner = _runner()

    result = recovery.assess_fast_paper_manual_recovery(
        authoritative_runtime_env_path=tmp_path / "env",
        production_authorization_path=revocation_path,
        failure_receipt_path=failure_path,
        current_link=_current_link(tmp_path),
        command_runner=runner,
    )

    assert result["state"] == "READY_FOR_FAST_RECOVERY_PLANNING"
    assert result["failure_family"] == "RELEASE_UPGRADE"
    assert result["release_handoff_fingerprint_sha256"] == _HANDOFF_FP
    assert result["open_position_count"] == 1
    assert result["mapped_open_position_count"] == 1
    assert observed["target_fast_run_id"] == _RUN_ID
    assert runner.calls == [
        recovery._show_command(recovery._PAPER_UNIT),
        recovery._show_command(recovery._EVIDENCE_UNIT),
        recovery._show_command(recovery._OBSERVE_UNIT),
        recovery._show_command(recovery._TARGET_UNIT),
    ]


def test_manual_recovery_rejects_active_paper_writer_before_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_path = tmp_path / "revocation.json"
    failure_path = tmp_path / "failure.json"
    _write(revocation_path, _cutover_revocation())
    _write(failure_path, _cutover_failure())
    monkeypatch.setattr(recovery, "_require_root", lambda: None)
    monkeypatch.setattr(
        recovery,
        "read_fast_paper_authoritative_cutover_environment",
        lambda _path: pytest.fail(
            "active writer must fail before authoritative bootstrap"
        ),
    )

    with pytest.raises(
        recovery.FastPaperManualRecoveryError,
        match="inactive/dead",
    ):
        recovery.assess_fast_paper_manual_recovery(
            authoritative_runtime_env_path=tmp_path / "env",
            production_authorization_path=revocation_path,
            failure_receipt_path=failure_path,
            current_link=_current_link(tmp_path),
            command_runner=_runner(recovery._PAPER_UNIT),
        )


def test_manual_recovery_rejects_tampered_revocation_fingerprint(
    tmp_path: Path,
) -> None:
    revocation = _cutover_revocation()
    revocation["revocation_fingerprint_sha256"] = "0" * 64
    path = tmp_path / "revocation.json"
    _write(path, revocation)

    with pytest.raises(
        recovery.FastPaperManualRecoveryError,
        match="fingerprint mismatch",
    ):
        recovery.read_fast_paper_manual_recovery_revocation(path)


def test_manual_recovery_rejects_mismatched_open_position_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_path = tmp_path / "revocation.json"
    failure_path = tmp_path / "failure.json"
    _write(revocation_path, _cutover_revocation())
    _write(failure_path, _cutover_failure())
    bootstrap = _bootstrap(
        decision_sequence=7,
        execution_sequence=7,
        checkpoint_sequence=2,
        open_position_ids=("position-1",),
    )
    bootstrap.execution_bootstrap.runtime_state.market_positions = ()
    _patch_runtime(monkeypatch, tmp_path, bootstrap)

    with pytest.raises(
        recovery.FastPaperManualRecoveryError,
        match="open-position mapping",
    ):
        recovery.assess_fast_paper_manual_recovery(
            authoritative_runtime_env_path=tmp_path / "env",
            production_authorization_path=revocation_path,
            failure_receipt_path=failure_path,
            current_link=_current_link(tmp_path),
            command_runner=_runner(),
        )


def test_manual_recovery_default_runner_is_strictly_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        recovery.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="ActiveState=inactive\nSubState=dead\nMainPID=0\n",
            stderr="",
        ),
    )
    recovery._default_command_runner(
        recovery._show_command(recovery._PAPER_UNIT)
    )

    for forbidden in (
        ("systemctl", "start", recovery._PAPER_UNIT),
        ("systemctl", "stop", recovery._PAPER_UNIT),
        ("systemctl", "restart", recovery._PAPER_UNIT),
        ("systemctl", "daemon-reload"),
        recovery._show_command("other.service"),
    ):
        with pytest.raises(
            recovery.FastPaperManualRecoveryError,
            match="read-only allowlist",
        ):
            recovery._default_command_runner(forbidden)


def test_manual_recovery_source_has_no_mutation_or_live_authority() -> None:
    source = Path(recovery.__file__).read_text(encoding="utf-8")
    for required in (
        "bootstrap_fast_paper_authoritative_runtime",
        "validate_fast_paper_accounting",
        "load_fast_paper_authoritative_release_handoff",
        "RECOVERY_RECONCILIATION_REQUIRED",
        "READY_FOR_FAST_RECOVERY_PLANNING",
    ):
        assert required in source

    for forbidden in (
        '("systemctl", "start"',
        '("systemctl", "stop"',
        '("systemctl", "restart"',
        "daemon-reload",
        "os.replace(",
        "write_fast_paper",
        "commit_fast_paper",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
    ):
        assert forbidden not in source
