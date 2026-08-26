from __future__ import annotations

from dataclasses import asdict, fields
import json
from typing import Any

from .models import (
    LayerStatus,
    MoneyTelemetry,
    ProofRiskTelemetry,
    SystemTelemetry,
    TelemetrySnapshot,
    TradingPerformanceTelemetry,
    TradingTelemetry,
)


def encode_telemetry_snapshot(snapshot: TelemetrySnapshot) -> str:
    if type(snapshot) is not TelemetrySnapshot:
        raise ValueError("snapshot must be an exact TelemetrySnapshot")
    return json.dumps(
        asdict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def decode_telemetry_snapshot(payload: str | bytes) -> TelemetrySnapshot:
    if type(payload) is bytes:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("telemetry payload must be UTF-8") from error
    elif type(payload) is str:
        text = payload
    else:
        raise ValueError("telemetry payload must be exact str or bytes")

    try:
        raw = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("telemetry payload must be valid finite JSON") from error

    obj = _exact_object(raw, TelemetrySnapshot)
    snapshot = TelemetrySnapshot(
        schema_version=obj["schema_version"],
        generated_at_unix_ms=obj["generated_at_unix_ms"],
        mode=obj["mode"],
        overall_status=_decode_status(obj["overall_status"]),
        system=_decode_system(obj["system"]),
        trading=_decode_trading(obj["trading"]),
        money=_decode_money(obj["money"]),
        proof_risk=_decode_proof_risk(obj["proof_risk"]),
    )
    if encode_telemetry_snapshot(snapshot) != text:
        raise ValueError("telemetry payload must use canonical encoding")
    return snapshot


def _decode_system(value: object) -> SystemTelemetry:
    obj = _exact_object(value, SystemTelemetry)
    return SystemTelemetry(
        status=_decode_status(obj["status"]),
        observed_at_unix_ms=obj["observed_at_unix_ms"],
        source_errors=_string_tuple("system.source_errors", obj["source_errors"]),
        provider_count=obj["provider_count"],
        unhealthy_provider_count=obj["unhealthy_provider_count"],
        latest_market_observed_at_unix_ms=obj["latest_market_observed_at_unix_ms"],
        market_age_ms=obj["market_age_ms"],
        latest_ingestion_checkpoint_at_unix_ms=obj["latest_ingestion_checkpoint_at_unix_ms"],
        paper_last_cycle_at_unix_ms=obj["paper_last_cycle_at_unix_ms"],
        accounting_status=obj["accounting_status"],
        host_metrics_available=obj["host_metrics_available"],
    )


def _decode_trading(value: object) -> TradingTelemetry:
    obj = _exact_object(value, TradingTelemetry)
    return TradingTelemetry(
        status=_decode_status(obj["status"]),
        observed_at_unix_ms=obj["observed_at_unix_ms"],
        source_errors=_string_tuple("trading.source_errors", obj["source_errors"]),
        candidate_count=obj["candidate_count"],
        holder_distribution_count=obj["holder_distribution_count"],
        paper_quote_count=obj["paper_quote_count"],
        terminal_paper_entry_count=obj["terminal_paper_entry_count"],
        open_position_count=obj["open_position_count"],
        closed_position_count=obj["closed_position_count"],
        pending_entry=obj["pending_entry"],
        candidate_version=obj["candidate_version"],
        candidate_mint=obj["candidate_mint"],
        paper_run_id=obj["paper_run_id"],
        historical_score_count=obj["historical_score_count"],
        historical_decision_count=obj["historical_decision_count"],
    )


def _decode_money(value: object) -> MoneyTelemetry:
    obj = _exact_object(value, MoneyTelemetry)
    performance = obj["performance"]
    return MoneyTelemetry(
        status=_decode_status(obj["status"]),
        observed_at_unix_ms=obj["observed_at_unix_ms"],
        source_errors=_string_tuple("money.source_errors", obj["source_errors"]),
        starting_cash_usd=obj["starting_cash_usd"],
        cash_balance_usd=obj["cash_balance_usd"],
        realized_pnl_usd=obj["realized_pnl_usd"],
        unrealized_pnl_usd=obj["unrealized_pnl_usd"],
        accumulated_costs_usd=obj["accumulated_costs_usd"],
        open_cost_basis_usd=obj["open_cost_basis_usd"],
        open_position_count=obj["open_position_count"],
        daily_loss_usd=obj["daily_loss_usd"],
        performance=None if performance is None else _decode_performance(performance),
    )


def _decode_performance(value: object) -> TradingPerformanceTelemetry:
    return TradingPerformanceTelemetry(**_exact_object(value, TradingPerformanceTelemetry))


def _decode_proof_risk(value: object) -> ProofRiskTelemetry:
    obj = _exact_object(value, ProofRiskTelemetry)
    return ProofRiskTelemetry(
        status=_decode_status(obj["status"]),
        observed_at_unix_ms=obj["observed_at_unix_ms"],
        source_errors=_string_tuple("proof_risk.source_errors", obj["source_errors"]),
        proof_decision=obj["proof_decision"],
        proof_gate_count=obj["proof_gate_count"],
        proof_pass_count=obj["proof_pass_count"],
        proof_fail_count=obj["proof_fail_count"],
        proof_insufficient_count=obj["proof_insufficient_count"],
        promotion_decision=obj["promotion_decision"],
        promotion_gate_count=obj["promotion_gate_count"],
        global_risk_halt=obj["global_risk_halt"],
        accounting_integrity=obj["accounting_integrity"],
        live_state=obj["live_state"],
        kill_switch_active=obj["kill_switch_active"],
        proof_trade_count=obj["proof_trade_count"],
        proof_distinct_mint_count=obj["proof_distinct_mint_count"],
        proof_net_expectancy_pct=obj["proof_net_expectancy_pct"],
        proof_profit_factor=obj["proof_profit_factor"],
        proof_maximum_drawdown_pct=obj["proof_maximum_drawdown_pct"],
        proof_cost_burden_pct=obj["proof_cost_burden_pct"],
    )


def _exact_object(value: object, expected_type: type) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{expected_type.__name__} JSON value must be an exact object")
    expected = {item.name for item in fields(expected_type)}
    if set(value) != expected:
        raise ValueError(f"{expected_type.__name__} JSON keys must be exact")
    return value


def _decode_status(value: object) -> LayerStatus:
    if type(value) is not str:
        raise ValueError("telemetry status must be an exact string")
    try:
        return LayerStatus(value)
    except ValueError as error:
        raise ValueError("unsupported telemetry status") from error


def _string_tuple(name: str, value: object) -> tuple[str, ...]:
    if type(value) is not list or not all(type(item) is str for item in value):
        raise ValueError(f"{name} must be an exact JSON string array")
    return tuple(value)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
