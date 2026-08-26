from __future__ import annotations

from dataclasses import dataclass

from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperLedgerEntry,
    PaperLedgerReasonCode,
)

from .config import AlertRuntimeConfig
from .models import (
    AlertCode,
    AlertEvent,
    AlertSeverity,
    AlertSourceSnapshot,
    AlertState,
    G6_ALERT_STATE_SCHEMA_VERSION,
)


@dataclass(frozen=True, slots=True)
class AlertDetectionResult:
    state: AlertState
    queued_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.state) is not AlertState:
            raise ValueError("state must be an exact AlertState")
        if not isinstance(self.queued_event_ids, tuple) or not all(
            isinstance(value, str) and value for value in self.queued_event_ids
        ):
            raise ValueError("queued_event_ids must be a tuple of non-empty strings")
        if len(self.queued_event_ids) != len(set(self.queued_event_ids)):
            raise ValueError("queued_event_ids must be unique")
        pending_ids = {event.event_id for event in self.state.pending_events}
        if not set(self.queued_event_ids).issubset(pending_ids):
            raise ValueError("queued_event_ids must reference pending events")


def detect_alert_events(
    config: AlertRuntimeConfig,
    previous: AlertState | None,
    source: AlertSourceSnapshot,
) -> AlertDetectionResult:
    if type(config) is not AlertRuntimeConfig:
        raise ValueError("config must be an exact AlertRuntimeConfig")
    if previous is not None and type(previous) is not AlertState:
        raise ValueError("previous must be an exact AlertState or None")
    if type(source) is not AlertSourceSnapshot:
        raise ValueError("source must be an exact AlertSourceSnapshot")

    first_run = previous is None or not previous.initialized
    prior_pending = () if previous is None else previous.pending_events
    pending = list(prior_pending)
    pending_ids = {event.event_id for event in pending}
    queued_ids: list[str] = []

    def queue(event: AlertEvent) -> None:
        if event.event_id in pending_ids:
            return
        pending.append(event)
        pending_ids.add(event.event_id)
        queued_ids.append(event.event_id)

    active_conditions = _active_conditions(config, source)
    active_keys = tuple(sorted(condition.key for condition in active_conditions))
    previous_active = set() if previous is None else set(previous.active_condition_keys)

    if first_run:
        queue(_startup_event(source.observed_at_unix_ms))
        for condition in active_conditions:
            if condition.severity is AlertSeverity.CRITICAL:
                queue(condition.event)
    else:
        for condition in active_conditions:
            if condition.key not in previous_active:
                queue(condition.event)

    current_ledger_sequence = _highest_sequence(source.paper_ledger_entries)
    if first_run:
        highest_ledger_sequence = current_ledger_sequence
    else:
        assert previous is not None
        highest_ledger_sequence = max(previous.highest_ledger_sequence, current_ledger_sequence)
        if source.paper_ledger_entries is not None:
            for entry in source.paper_ledger_entries:
                if entry.sequence <= previous.highest_ledger_sequence:
                    continue
                for event in _ledger_events(entry):
                    queue(event)

    current_proof_decision = (
        None if source.telemetry is None else source.telemetry.proof_risk.proof_decision
    )
    if first_run:
        last_proof_decision = current_proof_decision
    else:
        assert previous is not None
        last_proof_decision = previous.last_proof_decision
        if current_proof_decision is not None:
            if current_proof_decision != previous.last_proof_decision:
                proof_event = _proof_transition_event(source, current_proof_decision)
                if proof_event is not None:
                    queue(proof_event)
            last_proof_decision = current_proof_decision

    state = AlertState(
        schema_version=G6_ALERT_STATE_SCHEMA_VERSION,
        initialized=True,
        highest_ledger_sequence=highest_ledger_sequence,
        last_proof_decision=last_proof_decision,
        active_condition_keys=active_keys,
        pending_events=tuple(pending),
        last_observed_at_unix_ms=source.observed_at_unix_ms,
    )
    return AlertDetectionResult(state=state, queued_event_ids=tuple(queued_ids))


@dataclass(frozen=True, slots=True)
class _ActiveCondition:
    key: str
    severity: AlertSeverity
    event: AlertEvent


def _active_conditions(
    config: AlertRuntimeConfig,
    source: AlertSourceSnapshot,
) -> tuple[_ActiveCondition, ...]:
    conditions: list[_ActiveCondition] = []

    if source.systemd is not None and source.systemd.inactive_units:
        conditions.append(
            _condition(
                "CORE_RUNTIME_STOPPED",
                AlertCode.CORE_RUNTIME_STOPPED,
                AlertSeverity.CRITICAL,
                source.observed_at_unix_ms,
                "PAPER runtime is not fully active.",
                ("Units: " + ", ".join(source.systemd.inactive_units),),
            )
        )
    if source.systemd_error_code is not None:
        conditions.append(
            _condition(
                "SYSTEMD_HEALTH_UNAVAILABLE",
                AlertCode.SYSTEMD_HEALTH_UNAVAILABLE,
                AlertSeverity.CRITICAL,
                source.observed_at_unix_ms,
                "Core service health cannot be verified.",
                (),
            )
        )

    if source.telemetry_error_code is not None:
        conditions.append(
            _condition(
                "TELEMETRY_SOURCE_UNAVAILABLE",
                AlertCode.TELEMETRY_SOURCE_UNAVAILABLE,
                AlertSeverity.CRITICAL,
                source.observed_at_unix_ms,
                "Canonical telemetry is unavailable.",
                (),
            )
        )
    elif source.telemetry is not None:
        telemetry = source.telemetry
        market_age_ms = telemetry.system.market_age_ms
        if market_age_ms is None or market_age_ms > config.market_stale_ms:
            lines = (
                "Market age: UNAVAILABLE",
                f"Alert threshold: {config.market_stale_ms} ms",
            ) if market_age_ms is None else (
                f"Market age: {market_age_ms} ms",
                f"Alert threshold: {config.market_stale_ms} ms",
            )
            conditions.append(
                _condition(
                    "MARKET_DATA_STALE",
                    AlertCode.MARKET_DATA_STALE,
                    AlertSeverity.WARNING,
                    source.observed_at_unix_ms,
                    "Market data is stale.",
                    lines,
                )
            )

        for provider in source.providers:
            if (
                provider.status != "healthy"
                and provider.consecutive_failures
                >= config.provider_failure_min_consecutive
            ):
                key = f"PROVIDER_FAILURE_PERSISTENT:{provider.provider}"
                conditions.append(
                    _condition(
                        key,
                        AlertCode.PROVIDER_FAILURE_PERSISTENT,
                        AlertSeverity.WARNING,
                        source.observed_at_unix_ms,
                        "Provider failure is persistent.",
                        (
                            f"Provider: {_display(provider.provider)}",
                            f"Status: {_display(provider.status)}",
                            f"Consecutive failures: {provider.consecutive_failures}",
                        ),
                    )
                )

        if telemetry.system.latest_ingestion_checkpoint_at_unix_ms is None:
            conditions.append(
                _condition(
                    "CHECKPOINT_UNAVAILABLE",
                    AlertCode.CHECKPOINT_UNAVAILABLE,
                    AlertSeverity.WARNING,
                    source.observed_at_unix_ms,
                    "Ingestion checkpoint is unavailable.",
                    (),
                )
            )

    if source.paper_error_code is not None:
        conditions.append(
            _condition(
                "PAPER_SOURCE_UNAVAILABLE",
                AlertCode.PAPER_SOURCE_UNAVAILABLE,
                AlertSeverity.CRITICAL,
                source.observed_at_unix_ms,
                "Required PAPER evidence is unavailable.",
                (),
            )
        )

    if source.telemetry is not None:
        telemetry = source.telemetry
        accounting_status = telemetry.system.accounting_status
        accounting_integrity = telemetry.proof_risk.accounting_integrity
        if accounting_status != "VALID" or accounting_integrity != "VALID":
            conditions.append(
                _condition(
                    "ACCOUNTING_NOT_RECONCILED",
                    AlertCode.ACCOUNTING_NOT_RECONCILED,
                    AlertSeverity.CRITICAL,
                    source.observed_at_unix_ms,
                    "Accounting reconciliation is not valid.",
                    (
                        f"System accounting: {_display(accounting_status)}",
                        f"Proof accounting: {_display(accounting_integrity)}",
                    ),
                )
            )
        if telemetry.proof_risk.global_risk_halt is True:
            conditions.append(
                _condition(
                    "GLOBAL_RISK_HALT_ACTIVE",
                    AlertCode.GLOBAL_RISK_HALT_ACTIVE,
                    AlertSeverity.CRITICAL,
                    source.observed_at_unix_ms,
                    "Global risk halt is active.",
                    (),
                )
            )
        if telemetry.proof_risk.kill_switch_active is True:
            conditions.append(
                _condition(
                    "KILL_SWITCH_ACTIVE",
                    AlertCode.KILL_SWITCH_ACTIVE,
                    AlertSeverity.CRITICAL,
                    source.observed_at_unix_ms,
                    "Kill switch is active.",
                    (),
                )
            )

    return tuple(conditions)


def _condition(
    key: str,
    code: AlertCode,
    severity: AlertSeverity,
    observed_at_unix_ms: int,
    title: str,
    lines: tuple[str, ...],
) -> _ActiveCondition:
    event = AlertEvent(
        event_id=f"condition:{key}",
        code=code,
        severity=severity,
        observed_at_unix_ms=observed_at_unix_ms,
        title=title,
        lines=(*lines, "LIVE TRADING: DISABLED"),
    )
    return _ActiveCondition(key=key, severity=severity, event=event)


def _startup_event(observed_at_unix_ms: int) -> AlertEvent:
    return AlertEvent(
        event_id=f"startup:{observed_at_unix_ms}:ALERTING_STARTED",
        code=AlertCode.ALERTING_STARTED,
        severity=AlertSeverity.INFO,
        observed_at_unix_ms=observed_at_unix_ms,
        title="Outbound alerting initialized.",
        lines=("LIVE TRADING: DISABLED",),
    )


def _ledger_events(entry: PaperLedgerEntry) -> tuple[AlertEvent, ...]:
    events: list[AlertEvent] = []
    if entry.ledger_reason_code in (
        PaperLedgerReasonCode.POSITION_OPENED,
        PaperLedgerReasonCode.POSITION_INCREASED,
    ):
        events.append(
            _ledger_event(
                entry,
                AlertCode.POSITION_OPENED,
                AlertSeverity.INFO,
                "PAPER position opened or increased.",
                (
                    "Mode: PAPER",
                    f"Mint: {_display(entry.mint)}",
                    f"Position: {_display(entry.position_id)}",
                    f"Side: {entry.side.value}",
                    f"Filled notional: ${entry.filled_notional_usd:.2f}",
                    f"Strategy version: {_display(entry.strategy_version)}",
                ),
            )
        )
    if entry.ledger_reason_code is PaperLedgerReasonCode.POSITION_CLOSED:
        events.append(
            _ledger_event(
                entry,
                AlertCode.POSITION_CLOSED,
                AlertSeverity.INFO,
                "PAPER position closed.",
                (
                    "Mode: PAPER",
                    f"Mint: {_display(entry.mint)}",
                    f"Position: {_display(entry.position_id)}",
                    f"Side: {entry.side.value}",
                    f"Filled notional: ${entry.filled_notional_usd:.2f}",
                    f"Realized PnL delta: ${entry.realized_pnl_delta_usd:.2f}",
                ),
            )
        )
    degraded = (
        entry.execution_state in (PaperExecutionState.PARTIAL, PaperExecutionState.FAILED)
        or entry.paper_execution_reason_code
        is PaperExecutionReasonCode.SLIPPAGE_EXCEEDS_INTENT
    )
    if degraded:
        events.append(
            _ledger_event(
                entry,
                AlertCode.EXECUTION_DEGRADED,
                AlertSeverity.WARNING,
                "PAPER execution degraded.",
                (
                    "Mode: PAPER",
                    f"Mint: {_display(entry.mint)}",
                    f"Position: {_display(entry.position_id)}",
                    f"Execution state: {entry.execution_state.value}",
                    f"Execution reason: {entry.paper_execution_reason_code.value}",
                    f"Ledger reason: {entry.ledger_reason_code.value}",
                ),
            )
        )
    return tuple(events)


def _ledger_event(
    entry: PaperLedgerEntry,
    code: AlertCode,
    severity: AlertSeverity,
    title: str,
    lines: tuple[str, ...],
) -> AlertEvent:
    return AlertEvent(
        event_id=f"ledger:{entry.sequence}:{code.value}",
        code=code,
        severity=severity,
        observed_at_unix_ms=entry.booked_at_unix_ms,
        title=title,
        lines=(*lines, "LIVE TRADING: DISABLED"),
    )


def _proof_transition_event(
    source: AlertSourceSnapshot,
    decision: str,
) -> AlertEvent | None:
    assert source.telemetry is not None
    if decision == "SUFFICIENT":
        return AlertEvent(
            event_id=f"proof:{source.telemetry.generated_at_unix_ms}:SUFFICIENT",
            code=AlertCode.PAPER_PROOF_SUFFICIENT,
            severity=AlertSeverity.INFO,
            observed_at_unix_ms=source.telemetry.generated_at_unix_ms,
            title="PAPER proof is sufficient.",
            lines=("LIVE TRADING: DISABLED",),
        )
    if decision == "FAILED":
        return AlertEvent(
            event_id=f"proof:{source.telemetry.generated_at_unix_ms}:FAILED",
            code=AlertCode.CHALLENGER_PROOF_FAILED,
            severity=AlertSeverity.WARNING,
            observed_at_unix_ms=source.telemetry.generated_at_unix_ms,
            title="Challenger PAPER proof failed.",
            lines=("LIVE TRADING: DISABLED",),
        )
    return None


def _highest_sequence(entries: tuple[PaperLedgerEntry, ...] | None) -> int:
    if not entries:
        return 0
    return max(entry.sequence for entry in entries)


def _display(value: object, maximum: int = 160) -> str:
    if value is None:
        return "UNAVAILABLE"
    text = str(value)
    cleaned = "".join(
        character if 32 <= ord(character) != 127 else "?" for character in text
    )
    cleaned = cleaned.strip() or "UNAVAILABLE"
    return cleaned[:maximum]
