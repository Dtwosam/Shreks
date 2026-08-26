from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from shreks_brain.alerts import (
    AlertCode,
    AlertProviderHealth,
    AlertSourceSnapshot,
    AlertState,
    AlertSystemdHealth,
    CORE_ALERT_UNITS,
    G6_ALERT_STATE_SCHEMA_VERSION,
)
from shreks_brain.alerts.config import load_alert_runtime_config
from shreks_brain.alerts.detector import AlertDetectionResult, detect_alert_events
from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperLedgerReasonCode,
)
from shreks_brain.risk import TradeSide

from test_g4_telemetry_models import _snapshot
from test_g5_dashboard_source import _entry
from test_g6_alert_config import _env


OBSERVED_AT = 1_800_000_000_500


def _config(tmp_path: Path):
    env, _token_file = _env(tmp_path)
    return load_alert_runtime_config(env)


def _state(
    *,
    highest_ledger_sequence: int = 0,
    last_proof_decision: str | None = None,
    active_condition_keys: tuple[str, ...] = (),
    pending_events=(),
) -> AlertState:
    return AlertState(
        schema_version=G6_ALERT_STATE_SCHEMA_VERSION,
        initialized=True,
        highest_ledger_sequence=highest_ledger_sequence,
        last_proof_decision=last_proof_decision,
        active_condition_keys=active_condition_keys,
        pending_events=tuple(pending_events),
        last_observed_at_unix_ms=OBSERVED_AT - 1,
    )


def _source(
    *,
    telemetry=None,
    telemetry_error_code: str | None = None,
    providers: tuple[AlertProviderHealth, ...] = (),
    entries=(),
    paper_error_code: str | None = None,
    inactive_units: tuple[str, ...] = (),
    systemd_error_code: str | None = None,
) -> AlertSourceSnapshot:
    if telemetry_error_code is None and telemetry is None:
        telemetry = _snapshot()
    if systemd_error_code is None:
        active_units = tuple(unit for unit in CORE_ALERT_UNITS if unit not in inactive_units)
        systemd = AlertSystemdHealth(active_units=active_units, inactive_units=inactive_units)
    else:
        systemd = None
    return AlertSourceSnapshot(
        observed_at_unix_ms=OBSERVED_AT,
        telemetry=telemetry,
        telemetry_error_code=telemetry_error_code,
        providers=providers,
        paper_ledger_entries=tuple(entries),
        paper_error_code=paper_error_code,
        systemd=systemd,
        systemd_error_code=systemd_error_code,
    )


def _codes(result: AlertDetectionResult) -> tuple[AlertCode, ...]:
    queued = set(result.queued_event_ids)
    return tuple(event.code for event in result.state.pending_events if event.event_id in queued)


def test_first_run_suppresses_history_and_noncritical_conditions_but_keeps_current_critical(tmp_path: Path) -> None:
    config = _config(tmp_path)
    telemetry = _snapshot()
    telemetry = replace(
        telemetry,
        system=replace(
            telemetry.system,
            market_age_ms=config.market_stale_ms + 1,
            latest_ingestion_checkpoint_at_unix_ms=None,
            accounting_status="BROKEN",
        ),
        proof_risk=replace(
            telemetry.proof_risk,
            proof_decision="SUFFICIENT",
            global_risk_halt=True,
            kill_switch_active=True,
        ),
    )
    providers = (
        AlertProviderHealth(
            provider="jupiter",
            status="degraded",
            observed_at_unix_ms=OBSERVED_AT - 1,
            consecutive_failures=config.provider_failure_min_consecutive,
        ),
    )
    entries = (
        _entry(
            sequence=1,
            position_id="position-1",
            mint="MintOne",
            side=TradeSide.BUY,
            booked_at_unix_ms=1_000,
            filled_notional_usd=100.0,
            realized_pnl_delta_usd=0.0,
            ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
        ),
        _entry(
            sequence=2,
            position_id="position-1",
            mint="MintOne",
            side=TradeSide.SELL,
            booked_at_unix_ms=2_000,
            filled_notional_usd=110.0,
            realized_pnl_delta_usd=10.0,
            ledger_reason_code=PaperLedgerReasonCode.POSITION_CLOSED,
        ),
    )
    source = _source(
        telemetry=telemetry,
        providers=providers,
        entries=entries,
        inactive_units=("shreks-paper-campaign.service",),
    )

    result = detect_alert_events(config, None, source)

    assert result.state.initialized is True
    assert result.state.highest_ledger_sequence == 2
    assert result.state.last_proof_decision == "SUFFICIENT"
    assert _codes(result) == (
        AlertCode.ALERTING_STARTED,
        AlertCode.CORE_RUNTIME_STOPPED,
        AlertCode.ACCOUNTING_NOT_RECONCILED,
        AlertCode.GLOBAL_RISK_HALT_ACTIVE,
        AlertCode.KILL_SWITCH_ACTIVE,
    )
    assert AlertCode.POSITION_OPENED not in _codes(result)
    assert AlertCode.POSITION_CLOSED not in _codes(result)
    assert AlertCode.PAPER_PROOF_SUFFICIENT not in _codes(result)
    assert AlertCode.MARKET_DATA_STALE not in _codes(result)
    assert AlertCode.PROVIDER_FAILURE_PERSISTENT not in _codes(result)
    assert AlertCode.CHECKPOINT_UNAVAILABLE not in _codes(result)
    assert "MARKET_DATA_STALE" in result.state.active_condition_keys
    assert "PROVIDER_FAILURE_PERSISTENT:jupiter" in result.state.active_condition_keys
    assert "CHECKPOINT_UNAVAILABLE" in result.state.active_condition_keys
    assert "CORE_RUNTIME_STOPPED" in result.state.active_condition_keys
    assert all(
        "LIVE TRADING: DISABLED" in event.lines
        for event in result.state.pending_events
    )


def test_conditions_alert_once_clear_and_can_reactivate_after_acknowledgement(tmp_path: Path) -> None:
    config = _config(tmp_path)
    telemetry = _snapshot()
    telemetry = replace(
        telemetry,
        system=replace(
            telemetry.system,
            market_age_ms=config.market_stale_ms + 1,
            latest_ingestion_checkpoint_at_unix_ms=None,
            accounting_status="INVALID",
        ),
        proof_risk=replace(
            telemetry.proof_risk,
            global_risk_halt=True,
            kill_switch_active=True,
        ),
    )
    providers = (
        AlertProviderHealth(
            provider="jupiter",
            status="failed",
            observed_at_unix_ms=OBSERVED_AT - 1,
            consecutive_failures=config.provider_failure_min_consecutive + 1,
        ),
    )
    active_source = _source(
        telemetry=telemetry,
        providers=providers,
        paper_error_code="PAPER_SOURCE_UNAVAILABLE",
        inactive_units=("shreks-observe.service",),
    )

    first = detect_alert_events(config, _state(), active_source)
    assert set(_codes(first)) == {
        AlertCode.CORE_RUNTIME_STOPPED,
        AlertCode.MARKET_DATA_STALE,
        AlertCode.PROVIDER_FAILURE_PERSISTENT,
        AlertCode.CHECKPOINT_UNAVAILABLE,
        AlertCode.PAPER_SOURCE_UNAVAILABLE,
        AlertCode.ACCOUNTING_NOT_RECONCILED,
        AlertCode.GLOBAL_RISK_HALT_ACTIVE,
        AlertCode.KILL_SWITCH_ACTIVE,
    }

    unchanged = detect_alert_events(config, first.state, active_source)
    assert unchanged.queued_event_ids == ()
    assert unchanged.state.pending_events == first.state.pending_events

    clean = detect_alert_events(config, unchanged.state, _source())
    assert clean.state.active_condition_keys == ()
    acknowledged = replace(clean.state, pending_events=())

    reactivated = detect_alert_events(config, acknowledged, active_source)
    assert set(_codes(reactivated)) == set(_codes(first))


def test_unavailable_telemetry_and_systemd_are_explicit_critical_conditions(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = _source(
        telemetry=None,
        telemetry_error_code="TELEMETRY_SOURCE_UNAVAILABLE",
        systemd_error_code="SYSTEMD_HEALTH_UNAVAILABLE",
    )

    result = detect_alert_events(config, _state(), source)

    assert set(_codes(result)) == {
        AlertCode.TELEMETRY_SOURCE_UNAVAILABLE,
        AlertCode.SYSTEMD_HEALTH_UNAVAILABLE,
    }


def test_new_ledger_entries_emit_exact_position_and_execution_events_once(tmp_path: Path) -> None:
    config = _config(tmp_path)
    opened = _entry(
        sequence=1,
        position_id="position-1",
        mint="MintOne",
        side=TradeSide.BUY,
        booked_at_unix_ms=1_000,
        filled_notional_usd=100.0,
        realized_pnl_delta_usd=0.0,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
    )
    closed = _entry(
        sequence=2,
        position_id="position-1",
        mint="MintOne",
        side=TradeSide.SELL,
        booked_at_unix_ms=2_000,
        filled_notional_usd=110.0,
        realized_pnl_delta_usd=10.0,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_CLOSED,
    )
    partial = replace(
        _entry(
            sequence=3,
            position_id="position-2",
            mint="MintTwo",
            side=TradeSide.BUY,
            booked_at_unix_ms=3_000,
            filled_notional_usd=50.0,
            realized_pnl_delta_usd=0.0,
            ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
        ),
        execution_state=PaperExecutionState.PARTIAL,
        paper_execution_reason_code=PaperExecutionReasonCode.FILL_PARTIAL,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_INCREASED,
    )
    failed_slippage = replace(
        _entry(
            sequence=4,
            position_id="position-3",
            mint="MintThree",
            side=TradeSide.BUY,
            booked_at_unix_ms=4_000,
            filled_notional_usd=25.0,
            realized_pnl_delta_usd=0.0,
            ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
        ),
        execution_state=PaperExecutionState.FAILED,
        paper_execution_reason_code=PaperExecutionReasonCode.SLIPPAGE_EXCEEDS_INTENT,
        ledger_reason_code=PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
        filled_quantity=0.0,
        filled_notional_usd=0.0,
        cash_flow_usd=0.0,
        explicit_cost_usd=0.0,
    )

    result = detect_alert_events(
        config,
        _state(),
        _source(entries=(opened, closed, partial, failed_slippage)),
    )

    assert result.state.highest_ledger_sequence == 4
    assert _codes(result) == (
        AlertCode.POSITION_OPENED,
        AlertCode.POSITION_CLOSED,
        AlertCode.POSITION_OPENED,
        AlertCode.EXECUTION_DEGRADED,
        AlertCode.EXECUTION_DEGRADED,
    )
    close_event = next(event for event in result.state.pending_events if event.code is AlertCode.POSITION_CLOSED)
    assert "Realized PnL delta: $10.00" in close_event.lines
    assert "Mint: MintOne" in close_event.lines
    assert all("LIVE TRADING: DISABLED" in event.lines for event in result.state.pending_events)

    unchanged = detect_alert_events(config, result.state, _source(entries=(opened, closed, partial, failed_slippage)))
    assert unchanged.queued_event_ids == ()
    assert unchanged.state.highest_ledger_sequence == 4


def test_proof_decision_transitions_alert_without_reconstructing_proof(tmp_path: Path) -> None:
    config = _config(tmp_path)
    base = _snapshot()
    sufficient = replace(
        base,
        proof_risk=replace(base.proof_risk, proof_decision="SUFFICIENT"),
    )
    previous = _state(last_proof_decision="INSUFFICIENT_EVIDENCE")

    result = detect_alert_events(config, previous, _source(telemetry=sufficient))
    assert _codes(result) == (AlertCode.PAPER_PROOF_SUFFICIENT,)
    assert result.state.last_proof_decision == "SUFFICIENT"

    unchanged = detect_alert_events(config, result.state, _source(telemetry=sufficient))
    assert unchanged.queued_event_ids == ()

    missing = replace(base, proof_risk=replace(base.proof_risk, proof_decision=None))
    missing_result = detect_alert_events(config, unchanged.state, _source(telemetry=missing))
    assert missing_result.queued_event_ids == ()
    assert missing_result.state.last_proof_decision == "SUFFICIENT"

    failed = replace(base, proof_risk=replace(base.proof_risk, proof_decision="FAILED"))
    failed_result = detect_alert_events(config, missing_result.state, _source(telemetry=failed))
    assert _codes(failed_result) == (AlertCode.CHALLENGER_PROOF_FAILED,)
    assert failed_result.state.last_proof_decision == "FAILED"
