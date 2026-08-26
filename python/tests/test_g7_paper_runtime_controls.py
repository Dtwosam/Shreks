from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from shreks_brain.observer_campaign.runtime import run_observer_paper_campaign_runtime
from shreks_brain.observer_campaign.runtime_config import (
    load_observer_paper_campaign_runtime_config,
)
from shreks_brain.risk_control import (
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    apply_operator_risk_control_command,
    initialize_operator_risk_control_state,
)
from shreks_brain.risk_control.paper_runtime import (
    ControlledObserverPaperCampaignCoordinatorRunner,
)

from test_observer_campaign_runner import AS_OF
from test_observer_campaign_runtime import _runtime_config
from test_observer_campaign_runtime_config import VALID_ENV


def _controlled_config(tmp_path: Path, *, max_cycles: int, state_path: Path):
    return replace(
        _runtime_config(tmp_path, max_cycles=max_cycles),
        risk_control_path=state_path.resolve(),
    )


def test_runtime_config_accepts_optional_operator_risk_control_path(tmp_path: Path) -> None:
    env = dict(VALID_ENV)
    env["SHREKS_PAPER_CAMPAIGN_RISK_CONTROL_PATH"] = "control/operator-risk-control.json"

    config = load_observer_paper_campaign_runtime_config(env, base_directory=tmp_path)

    assert config.risk_control_path == (
        tmp_path / "control/operator-risk-control.json"
    ).resolve()


def test_configured_control_state_is_reread_on_every_paper_cycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "control" / "operator-risk-control.json"
    state_path.parent.mkdir()
    initialize_operator_risk_control_state(state_path, observed_at_unix_ms=0)
    config = _controlled_config(tmp_path, max_cycles=2, state_path=state_path)
    real_run_cycle = ControlledObserverPaperCampaignCoordinatorRunner.run_cycle
    observed_controls: list[tuple[bool, bool]] = []

    def recording_run_cycle(self, as_of_unix_ms: int, created_at_unix_ms: int):
        observed_controls.append(
            (
                self.operator_entry_halt_active,
                self.operator_kill_switch_active,
            )
        )
        result = real_run_cycle(self, as_of_unix_ms, created_at_unix_ms)
        if len(observed_controls) == 1:
            apply_operator_risk_control_command(
                state_path,
                OperatorRiskControlCommand.HALT_NEW_ENTRIES,
                expected_revision=0,
                observed_at_unix_ms=as_of_unix_ms,
                source=OperatorRiskControlSource.DASHBOARD,
                reason="authenticated dashboard halt",
            )
        return result

    monkeypatch.setattr(
        ControlledObserverPaperCampaignCoordinatorRunner,
        "run_cycle",
        recording_run_cycle,
    )
    timestamps = iter((AS_OF, AS_OF + 1))

    completed = run_observer_paper_campaign_runtime(
        config,
        clock_unix_ms=lambda: next(timestamps),
        status_sink=lambda _line: None,
    )

    assert completed == 2
    assert observed_controls == [(False, False), (True, False)]


def test_configured_emergency_kill_reaches_runtime_as_halt_and_kill(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "control" / "operator-risk-control.json"
    state_path.parent.mkdir()
    initialize_operator_risk_control_state(state_path, observed_at_unix_ms=0)
    apply_operator_risk_control_command(
        state_path,
        OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH,
        expected_revision=0,
        observed_at_unix_ms=1,
        source=OperatorRiskControlSource.DASHBOARD,
        reason="authenticated dashboard emergency kill",
    )
    config = _controlled_config(tmp_path, max_cycles=1, state_path=state_path)
    real_run_cycle = ControlledObserverPaperCampaignCoordinatorRunner.run_cycle
    observed_controls: list[tuple[bool, bool]] = []

    def recording_run_cycle(self, as_of_unix_ms: int, created_at_unix_ms: int):
        observed_controls.append(
            (
                self.operator_entry_halt_active,
                self.operator_kill_switch_active,
            )
        )
        return real_run_cycle(self, as_of_unix_ms, created_at_unix_ms)

    monkeypatch.setattr(
        ControlledObserverPaperCampaignCoordinatorRunner,
        "run_cycle",
        recording_run_cycle,
    )

    completed = run_observer_paper_campaign_runtime(
        config,
        clock_unix_ms=lambda: AS_OF,
        status_sink=lambda _line: None,
    )

    assert completed == 1
    assert observed_controls == [(True, True)]


@pytest.mark.parametrize("corrupt", (False, True))
def test_unavailable_configured_control_state_fails_closed_entries_without_fake_kill(
    tmp_path: Path,
    monkeypatch,
    corrupt: bool,
) -> None:
    state_path = tmp_path / "control" / "operator-risk-control.json"
    state_path.parent.mkdir()
    if corrupt:
        state_path.write_text("{not-json}\n", encoding="utf-8")
    config = _controlled_config(tmp_path, max_cycles=1, state_path=state_path)
    real_run_cycle = ControlledObserverPaperCampaignCoordinatorRunner.run_cycle
    observed_controls: list[tuple[bool, bool]] = []

    def recording_run_cycle(self, as_of_unix_ms: int, created_at_unix_ms: int):
        observed_controls.append(
            (
                self.operator_entry_halt_active,
                self.operator_kill_switch_active,
            )
        )
        return real_run_cycle(self, as_of_unix_ms, created_at_unix_ms)

    monkeypatch.setattr(
        ControlledObserverPaperCampaignCoordinatorRunner,
        "run_cycle",
        recording_run_cycle,
    )

    completed = run_observer_paper_campaign_runtime(
        config,
        clock_unix_ms=lambda: AS_OF,
        status_sink=lambda _line: None,
    )

    assert completed == 1
    assert observed_controls == [(True, False)]
