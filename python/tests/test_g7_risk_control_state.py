from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from shreks_brain.risk_control import (
    G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION,
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    OperatorRiskControlState,
    RiskControlCommandError,
    RiskControlConflictError,
    RiskControlStateError,
    apply_operator_risk_control_command,
    decode_operator_risk_control_state,
    encode_operator_risk_control_state,
    initialize_operator_risk_control_state,
    load_operator_risk_control_state,
    write_operator_risk_control_state,
)


def _state(*, revision: int = 3, halt: bool = False, kill: bool = False) -> OperatorRiskControlState:
    return OperatorRiskControlState(
        schema_version=G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION,
        revision=revision,
        halt_new_entries=halt or kill,
        kill_switch_active=kill,
        updated_at_unix_ms=1_800_000_000_000,
        last_command=OperatorRiskControlCommand.INITIALIZE,
        last_source=OperatorRiskControlSource.HOST_CLI,
        last_reason="initial controlled state",
    )


def test_state_schema_and_safety_invariant_are_exact() -> None:
    assert G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION == "g7-operator-risk-control-v1"
    state = _state(kill=True)
    assert state.kill_switch_active is True
    assert state.halt_new_entries is True

    with pytest.raises(ValueError, match="kill switch requires entry halt"):
        OperatorRiskControlState(
            schema_version=G7_OPERATOR_RISK_CONTROL_SCHEMA_VERSION,
            revision=1,
            halt_new_entries=False,
            kill_switch_active=True,
            updated_at_unix_ms=1,
            last_command=OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH,
            last_source=OperatorRiskControlSource.DASHBOARD,
            last_reason="emergency",
        )


def test_state_codec_is_canonical_exact_and_round_trips() -> None:
    state = _state(halt=True)
    payload = encode_operator_risk_control_state(state)
    document = json.loads(payload)
    assert payload.endswith(b"\n")
    assert set(document) == {
        "schema_version",
        "revision",
        "halt_new_entries",
        "kill_switch_active",
        "updated_at_unix_ms",
        "last_command",
        "last_source",
        "last_reason",
    }
    assert payload == encode_operator_risk_control_state(state)
    assert decode_operator_risk_control_state(payload) == state

    document["unexpected"] = True
    with pytest.raises(RiskControlStateError):
        decode_operator_risk_control_state(json.dumps(document))

    noncanonical = json.dumps(json.loads(payload), indent=2)
    with pytest.raises(RiskControlStateError, match="canonical"):
        decode_operator_risk_control_state(noncanonical)


def test_state_codec_rejects_nonfinite_malformed_or_wrong_types() -> None:
    document = json.loads(encode_operator_risk_control_state(_state()))
    for field, value in (
        ("revision", True),
        ("halt_new_entries", 1),
        ("kill_switch_active", "false"),
        ("updated_at_unix_ms", -1),
        ("last_command", "UNKNOWN"),
        ("last_source", "REMOTE_BOT"),
        ("last_reason", ""),
    ):
        broken = dict(document)
        broken[field] = value
        with pytest.raises(RiskControlStateError):
            decode_operator_risk_control_state(
                json.dumps(broken, sort_keys=True, separators=(",", ":")) + "\n"
            )

    payload = encode_operator_risk_control_state(_state()).decode("utf-8")
    with pytest.raises(RiskControlStateError):
        decode_operator_risk_control_state(payload.replace('"revision":3', '"revision":NaN'))


def test_missing_corrupt_directory_and_symlink_state_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    with pytest.raises(RiskControlStateError, match="unavailable"):
        load_operator_risk_control_state(path)

    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(RiskControlStateError):
        load_operator_risk_control_state(path)

    path.unlink()
    path.mkdir()
    with pytest.raises(RiskControlStateError):
        load_operator_risk_control_state(path)

    path.rmdir()
    target = tmp_path / "target.json"
    target.write_bytes(encode_operator_risk_control_state(_state()))
    path.symlink_to(target)
    with pytest.raises(RiskControlStateError, match="symlink"):
        load_operator_risk_control_state(path)


def test_initialize_creates_private_state_and_refuses_existing_history(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir(mode=0o700)
    state = initialize_operator_risk_control_state(path, observed_at_unix_ms=100)
    assert state.revision == 0
    assert state.halt_new_entries is False
    assert state.kill_switch_active is False
    assert state.last_command is OperatorRiskControlCommand.INITIALIZE
    assert state.last_source is OperatorRiskControlSource.HOST_CLI
    assert load_operator_risk_control_state(path) == state
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.with_name(path.name + ".lock")).st_mode & 0o777 == 0o600

    with pytest.raises(RiskControlStateError, match="already exists"):
        initialize_operator_risk_control_state(path, observed_at_unix_ms=101)


def test_atomic_write_round_trips_and_preserves_existing_on_replace_failure(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    original = _state(revision=1)
    write_operator_risk_control_state(path, original)

    import shreks_brain.risk_control.state as state_module

    real_replace = state_module.os.replace

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(state_module.os, "replace", fail_replace)
    with pytest.raises(RiskControlStateError, match="write failed"):
        write_operator_risk_control_state(path, _state(revision=2, halt=True))
    monkeypatch.setattr(state_module.os, "replace", real_replace)
    assert load_operator_risk_control_state(path) == original


def test_dashboard_halt_is_revision_checked_and_safety_monotonic(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    initialize_operator_risk_control_state(path, observed_at_unix_ms=10)

    halted = apply_operator_risk_control_command(
        path,
        OperatorRiskControlCommand.HALT_NEW_ENTRIES,
        expected_revision=0,
        observed_at_unix_ms=11,
        source=OperatorRiskControlSource.DASHBOARD,
        reason="dashboard emergency halt",
    )
    assert halted.revision == 1
    assert halted.halt_new_entries is True
    assert halted.kill_switch_active is False
    assert halted.last_command is OperatorRiskControlCommand.HALT_NEW_ENTRIES
    assert halted.last_source is OperatorRiskControlSource.DASHBOARD

    with pytest.raises(RiskControlConflictError, match="revision"):
        apply_operator_risk_control_command(
            path,
            OperatorRiskControlCommand.HALT_NEW_ENTRIES,
            expected_revision=0,
            observed_at_unix_ms=12,
            source=OperatorRiskControlSource.DASHBOARD,
            reason="stale replay",
        )
    assert load_operator_risk_control_state(path) == halted


def test_dashboard_kill_switch_latches_halt_and_replay_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    initialize_operator_risk_control_state(path, observed_at_unix_ms=10)

    killed = apply_operator_risk_control_command(
        path,
        OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH,
        expected_revision=0,
        observed_at_unix_ms=20,
        source=OperatorRiskControlSource.DASHBOARD,
        reason="dashboard emergency kill",
    )
    assert killed.revision == 1
    assert killed.halt_new_entries is True
    assert killed.kill_switch_active is True

    with pytest.raises(RiskControlConflictError):
        apply_operator_risk_control_command(
            path,
            OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH,
            expected_revision=0,
            observed_at_unix_ms=21,
            source=OperatorRiskControlSource.DASHBOARD,
            reason="replay",
        )


def test_dashboard_cannot_clear_or_reset_safety_state(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    write_operator_risk_control_state(path, _state(revision=5, kill=True))

    for command in (
        OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
        OperatorRiskControlCommand.RESET_KILL_SWITCH,
    ):
        with pytest.raises(RiskControlCommandError, match="host-only"):
            apply_operator_risk_control_command(
                path,
                command,
                expected_revision=5,
                observed_at_unix_ms=30,
                source=OperatorRiskControlSource.DASHBOARD,
                reason="browser must not restore authority",
            )
    assert load_operator_risk_control_state(path).revision == 5


def test_host_reset_is_two_step_and_cannot_clear_halt_while_kill_is_active(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    write_operator_risk_control_state(path, _state(revision=7, kill=True))

    with pytest.raises(RiskControlCommandError, match="kill switch"):
        apply_operator_risk_control_command(
            path,
            OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
            expected_revision=7,
            observed_at_unix_ms=1_800_000_000_040,
            source=OperatorRiskControlSource.HOST_CLI,
            reason="validated recovery",
        )

    reset = apply_operator_risk_control_command(
        path,
        OperatorRiskControlCommand.RESET_KILL_SWITCH,
        expected_revision=7,
        observed_at_unix_ms=1_800_000_000_041,
        source=OperatorRiskControlSource.HOST_CLI,
        reason="validated emergency recovery",
    )
    assert reset.revision == 8
    assert reset.kill_switch_active is False
    assert reset.halt_new_entries is True

    cleared = apply_operator_risk_control_command(
        path,
        OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
        expected_revision=8,
        observed_at_unix_ms=1_800_000_000_042,
        source=OperatorRiskControlSource.HOST_CLI,
        reason="validated resume after separate review",
    )
    assert cleared.revision == 9
    assert cleared.kill_switch_active is False
    assert cleared.halt_new_entries is False


def test_host_reset_requires_nontrivial_reason(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    write_operator_risk_control_state(path, _state(revision=2, halt=True))

    with pytest.raises(RiskControlCommandError, match="reason"):
        apply_operator_risk_control_command(
            path,
            OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
            expected_revision=2,
            observed_at_unix_ms=50,
            source=OperatorRiskControlSource.HOST_CLI,
            reason="ok",
        )


def test_mutation_rejects_future_time_and_noncanonical_revision_inputs(tmp_path: Path) -> None:
    path = tmp_path / "risk" / "operator-control.json"
    path.parent.mkdir()
    write_operator_risk_control_state(path, _state(revision=3))

    for expected in (True, -1, 3.0):
        with pytest.raises((RiskControlCommandError, RiskControlConflictError)):
            apply_operator_risk_control_command(
                path,
                OperatorRiskControlCommand.HALT_NEW_ENTRIES,
                expected_revision=expected,  # type: ignore[arg-type]
                observed_at_unix_ms=1_800_000_000_001,
                source=OperatorRiskControlSource.DASHBOARD,
                reason="dashboard emergency halt",
            )

    with pytest.raises(RiskControlCommandError, match="timestamp"):
        apply_operator_risk_control_command(
            path,
            OperatorRiskControlCommand.HALT_NEW_ENTRIES,
            expected_revision=3,
            observed_at_unix_ms=1_799_999_999_999,
            source=OperatorRiskControlSource.DASHBOARD,
            reason="dashboard emergency halt",
        )
