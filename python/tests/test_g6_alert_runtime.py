from __future__ import annotations

from pathlib import Path

from shreks_brain.alerts.config import AlertRuntimeConfig
from shreks_brain.alerts.models import (
    AlertCode,
    AlertEvent,
    AlertSeverity,
    AlertSourceSnapshot,
    AlertState,
    AlertSystemdHealth,
    G6_ALERT_STATE_SCHEMA_VERSION,
)
from shreks_brain.alerts.runtime import run_alert_cycle
from shreks_brain.alerts.state import load_alert_state, write_alert_state
from shreks_brain.observer_campaign.runtime_config import ObserverPaperCampaignRuntimeConfig


def _config(tmp_path: Path) -> AlertRuntimeConfig:
    token = tmp_path / "telegram-token"
    token.write_bytes(b"123456:ABC_def-ghi\n")
    token.chmod(0o640)
    paper = ObserverPaperCampaignRuntimeConfig(
        observer_database_path=(tmp_path / "observer.db").resolve(),
        evidence_path=(tmp_path / "e11.json").resolve(),
        manifest_path=(tmp_path / "manifest.json").resolve(),
        cycle_interval_seconds=30.0,
        max_cycles=None,
    )
    return AlertRuntimeConfig(
        telemetry_path=(tmp_path / "telemetry.json").resolve(),
        state_path=(tmp_path / "state.json").resolve(),
        telegram_chat_id="-1001234567890",
        telegram_bot_token_file=token.resolve(),
        market_stale_ms=60_000,
        provider_failure_min_consecutive=3,
        paper_runtime_config=paper,
    )


def _event(sequence: int) -> AlertEvent:
    code = (
        AlertCode.POSITION_OPENED
        if sequence == 1
        else AlertCode.EXECUTION_DEGRADED
        if sequence == 2
        else AlertCode.POSITION_CLOSED
    )
    severity = AlertSeverity.WARNING if sequence == 2 else AlertSeverity.INFO
    return AlertEvent(
        event_id=f"pending:{sequence}:{code.value}",
        code=code,
        severity=severity,
        observed_at_unix_ms=1_800_000_000_000 + sequence,
        title=f"event {sequence}",
        lines=("LIVE TRADING: DISABLED",),
    )


def _state() -> AlertState:
    return AlertState(
        schema_version=G6_ALERT_STATE_SCHEMA_VERSION,
        initialized=True,
        highest_ledger_sequence=0,
        last_proof_decision=None,
        active_condition_keys=(),
        pending_events=(_event(1), _event(2), _event(3)),
        last_observed_at_unix_ms=1_800_000_000_000,
    )


def _source(observed_at_unix_ms: int) -> AlertSourceSnapshot:
    return AlertSourceSnapshot(
        observed_at_unix_ms=observed_at_unix_ms,
        telemetry=None,
        telemetry_error_code=None,
        providers=(),
        paper_ledger_entries=(),
        paper_error_code=None,
        systemd=AlertSystemdHealth(active_units=(), inactive_units=()),
        systemd_error_code=None,
    )


def test_runtime_persists_queue_before_send_and_acknowledges_one_at_a_time(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_alert_state(config.state_path, _state())
    calls: list[str] = []

    def source_loader(_config, *, observed_at_unix_ms):
        return _source(observed_at_unix_ms)

    def sender(*, chat_id, bot_token, event):
        persisted = load_alert_state(config.state_path)
        assert persisted is not None
        ids = tuple(item.event_id for item in persisted.pending_events)
        calls.append(event.event_id)
        assert chat_id == config.telegram_chat_id
        assert bot_token == b"123456:ABC_def-ghi"
        if event.event_id == _event(1).event_id:
            assert ids == tuple(item.event_id for item in _state().pending_events)
            return
        if event.event_id == _event(2).event_id:
            assert _event(1).event_id not in ids
            assert ids == (_event(2).event_id, _event(3).event_id)
            raise RuntimeError("simulated transport failure")
        raise AssertionError("event 3 must not be attempted after event 2 fails")

    result = run_alert_cycle(
        config,
        observed_at_unix_ms=1_800_000_000_100,
        source_loader=source_loader,
        sender=sender,
    )
    assert result == 1
    assert calls == [_event(1).event_id, _event(2).event_id]

    persisted = load_alert_state(config.state_path)
    assert persisted is not None
    assert tuple(item.event_id for item in persisted.pending_events) == (
        _event(2).event_id,
        _event(3).event_id,
    )


def test_next_successful_cycle_does_not_resend_acknowledged_event(tmp_path: Path) -> None:
    config = _config(tmp_path)
    remaining = AlertState(
        schema_version=G6_ALERT_STATE_SCHEMA_VERSION,
        initialized=True,
        highest_ledger_sequence=0,
        last_proof_decision=None,
        active_condition_keys=(),
        pending_events=(_event(2), _event(3)),
        last_observed_at_unix_ms=1_800_000_000_100,
    )
    write_alert_state(config.state_path, remaining)
    sent: list[str] = []

    def sender(*, chat_id, bot_token, event):
        sent.append(event.event_id)

    result = run_alert_cycle(
        config,
        observed_at_unix_ms=1_800_000_000_200,
        source_loader=lambda _config, *, observed_at_unix_ms: _source(observed_at_unix_ms),
        sender=sender,
    )
    assert result == 0
    assert sent == [_event(2).event_id, _event(3).event_id]
    assert _event(1).event_id not in sent

    persisted = load_alert_state(config.state_path)
    assert persisted is not None
    assert persisted.pending_events == ()


def test_first_install_state_is_written_before_startup_notification(tmp_path: Path) -> None:
    config = _config(tmp_path)
    observed = 1_800_000_000_300
    inspected = False

    def sender(*, chat_id, bot_token, event):
        nonlocal inspected
        persisted = load_alert_state(config.state_path)
        assert persisted is not None
        assert persisted.initialized is True
        assert persisted.pending_events[0].event_id == event.event_id
        assert event.code is AlertCode.ALERTING_STARTED
        inspected = True

    assert run_alert_cycle(
        config,
        observed_at_unix_ms=observed,
        source_loader=lambda _config, *, observed_at_unix_ms: _source(observed_at_unix_ms),
        sender=sender,
    ) == 0
    assert inspected is True
    persisted = load_alert_state(config.state_path)
    assert persisted is not None
    assert persisted.pending_events == ()
