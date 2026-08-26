from __future__ import annotations

import ast
from importlib import import_module
import io
from pathlib import Path

import pytest

import shreks_brain.dashboard as dashboard_package
from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfigError,
    load_observer_paper_campaign_runtime_config,
)
from shreks_brain.risk_control import (
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    apply_operator_risk_control_command,
    initialize_operator_risk_control_state,
    load_operator_risk_control_state,
)

from test_observer_campaign_runtime_config import VALID_ENV


_STATE_NAME = "operator-control.json"


def _cli_module():
    return import_module("shreks_brain.risk_control.cli")


def _invoke_cli(*args: str, clock: int) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = _cli_module().main(
        list(args),
        clock_unix_ms=lambda: clock,
        stdout=stdout,
        stderr=stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_runtime_config_uses_standalone_g7_risk_control_path_key(tmp_path: Path) -> None:
    env = dict(VALID_ENV)
    env["SHREKS_RISK_CONTROL_STATE_PATH"] = f"risk/{_STATE_NAME}"

    config = load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)

    assert config.risk_control_path == (tmp_path / "risk" / _STATE_NAME).resolve()

    legacy_branch_only_key = dict(VALID_ENV)
    legacy_branch_only_key["SHREKS_PAPER_CAMPAIGN_RISK_CONTROL_PATH"] = f"risk/{_STATE_NAME}"
    with pytest.raises(ObserverPaperCampaignRuntimeConfigError, match="unsupported"):
        load_observer_paper_campaign_runtime_config(
            legacy_branch_only_key,
            base_directory=tmp_path,
        )


def test_host_cli_initializes_state_through_authority(tmp_path: Path) -> None:
    path = (tmp_path / "risk" / _STATE_NAME).resolve()
    path.parent.mkdir()

    code, stdout, stderr = _invoke_cli(
        "initialize",
        "--state-path",
        str(path),
        clock=100,
    )

    assert code == 0
    assert stderr == ""
    assert '"revision":0' in stdout
    state = load_operator_risk_control_state(path)
    assert state.revision == 0
    assert state.halt_new_entries is False
    assert state.kill_switch_active is False
    assert state.last_command is OperatorRiskControlCommand.INITIALIZE
    assert state.last_source is OperatorRiskControlSource.HOST_CLI


def test_host_cli_reset_and_clear_require_revision_confirmation_and_reason(tmp_path: Path) -> None:
    path = (tmp_path / "risk" / _STATE_NAME).resolve()
    path.parent.mkdir()
    initialize_operator_risk_control_state(path, observed_at_unix_ms=100)
    apply_operator_risk_control_command(
        path,
        OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH,
        expected_revision=0,
        observed_at_unix_ms=101,
        source=OperatorRiskControlSource.DASHBOARD,
        reason="authenticated dashboard emergency kill",
    )

    bad_code, _bad_stdout, bad_stderr = _invoke_cli(
        "reset-kill-switch",
        "--state-path",
        str(path),
        "--expected-revision",
        "1",
        "--confirmation",
        "RESET",
        "--reason",
        "host operator verified incident clear",
        clock=102,
    )
    assert bad_code == 2
    assert "confirmation" in bad_stderr.lower()
    assert load_operator_risk_control_state(path).revision == 1

    reset_code, _reset_stdout, reset_stderr = _invoke_cli(
        "reset-kill-switch",
        "--state-path",
        str(path),
        "--expected-revision",
        "1",
        "--confirmation",
        "RESET KILL SWITCH",
        "--reason",
        "host operator verified incident clear",
        clock=102,
    )
    assert reset_code == 0
    assert reset_stderr == ""
    reset_state = load_operator_risk_control_state(path)
    assert reset_state.revision == 2
    assert reset_state.halt_new_entries is True
    assert reset_state.kill_switch_active is False
    assert reset_state.last_command is OperatorRiskControlCommand.RESET_KILL_SWITCH
    assert reset_state.last_source is OperatorRiskControlSource.HOST_CLI

    missing_reason_code, _stdout, missing_reason_stderr = _invoke_cli(
        "clear-entry-halt",
        "--state-path",
        str(path),
        "--expected-revision",
        "2",
        "--confirmation",
        "CLEAR ENTRY HALT",
        clock=103,
    )
    assert missing_reason_code == 2
    assert "reason" in missing_reason_stderr.lower()
    assert load_operator_risk_control_state(path).revision == 2

    clear_code, _clear_stdout, clear_stderr = _invoke_cli(
        "clear-entry-halt",
        "--state-path",
        str(path),
        "--expected-revision",
        "2",
        "--confirmation",
        "CLEAR ENTRY HALT",
        "--reason",
        "host operator verified normal operation",
        clock=103,
    )
    assert clear_code == 0
    assert clear_stderr == ""
    cleared = load_operator_risk_control_state(path)
    assert cleared.revision == 3
    assert cleared.halt_new_entries is False
    assert cleared.kill_switch_active is False
    assert cleared.last_command is OperatorRiskControlCommand.CLEAR_ENTRY_HALT
    assert cleared.last_source is OperatorRiskControlSource.HOST_CLI


def test_dashboard_package_cannot_import_host_reset_cli_or_host_source() -> None:
    root = Path(dashboard_package.__file__).resolve().parent
    for path in sorted(root.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            assert not any(
                module == "shreks_brain.risk_control.cli"
                or module.startswith("shreks_brain.risk_control.cli.")
                for module in modules
            ), path.name
        assert "HOST_CLI" not in source, path.name
        assert "RESET_KILL_SWITCH" not in source, path.name
        assert "CLEAR_ENTRY_HALT" not in source, path.name


def test_host_cli_exposes_no_trade_live_wallet_or_service_commands() -> None:
    source_path = Path(_cli_module().__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()

    for forbidden in (
        "buy",
        "sell",
        "live-enable",
        "promote",
        "wallet",
        "sign",
        "submit",
        "systemctl",
        "service restart",
        "service stop",
        "service start",
    ):
        assert forbidden not in lowered
