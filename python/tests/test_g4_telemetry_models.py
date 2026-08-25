from __future__ import annotations

import json
import math

import pytest

from shreks_brain.telemetry import (
    G4_TELEMETRY_SCHEMA_VERSION,
    LayerStatus,
    MoneyTelemetry,
    ProofRiskTelemetry,
    SystemTelemetry,
    TelemetrySnapshot,
    TradingPerformanceTelemetry,
    TradingTelemetry,
    encode_telemetry_snapshot,
)


def _performance() -> TradingPerformanceTelemetry:
    return TradingPerformanceTelemetry(
        trade_count=2,
        win_count=1,
        loss_count=1,
        flat_count=0,
        gross_pnl_usd=12.0,
        net_pnl_usd=8.0,
        net_expectancy_usd=4.0,
        net_expectancy_pct=4.0,
        profit_factor=2.0,
        maximum_drawdown_usd=3.0,
        maximum_drawdown_pct=3.0,
        win_rate=0.5,
        turnover_usd=200.0,
        execution_friction_usd=2.0,
        explicit_cost_usd=2.0,
        total_cost_usd=4.0,
        cost_burden_pct=2.0,
    )


def _snapshot() -> TelemetrySnapshot:
    return TelemetrySnapshot(
        schema_version=G4_TELEMETRY_SCHEMA_VERSION,
        generated_at_unix_ms=1_800_000_000_000,
        mode="PAPER",
        overall_status=LayerStatus.DEGRADED,
        system=SystemTelemetry(
            status=LayerStatus.HEALTHY,
            observed_at_unix_ms=1_800_000_000_000,
            source_errors=(),
            provider_count=2,
            unhealthy_provider_count=0,
            latest_market_observed_at_unix_ms=1_799_999_999_000,
            market_age_ms=1_000,
            latest_ingestion_checkpoint_at_unix_ms=1_799_999_999_500,
            paper_last_cycle_at_unix_ms=1_799_999_999_700,
            accounting_status="VALID",
            host_metrics_available=False,
        ),
        trading=TradingTelemetry(
            status=LayerStatus.HEALTHY,
            observed_at_unix_ms=1_800_000_000_000,
            source_errors=(),
            candidate_count=12,
            holder_distribution_count=10,
            paper_quote_count=20,
            terminal_paper_entry_count=4,
            open_position_count=1,
            closed_position_count=1,
            pending_entry=False,
            candidate_version="candidate-v1",
            candidate_mint="mint-a",
            paper_run_id="paper-run-1",
            historical_score_count=None,
            historical_decision_count=None,
        ),
        money=MoneyTelemetry(
            status=LayerStatus.HEALTHY,
            observed_at_unix_ms=1_800_000_000_000,
            source_errors=(),
            starting_cash_usd=100.0,
            cash_balance_usd=108.0,
            realized_pnl_usd=8.0,
            unrealized_pnl_usd=1.5,
            accumulated_costs_usd=2.0,
            open_cost_basis_usd=20.0,
            open_position_count=1,
            daily_loss_usd=None,
            performance=_performance(),
        ),
        proof_risk=ProofRiskTelemetry(
            status=LayerStatus.DEGRADED,
            observed_at_unix_ms=1_800_000_000_000,
            source_errors=("PROOF_ASSESSMENT_UNAVAILABLE",),
            proof_decision=None,
            proof_gate_count=0,
            proof_pass_count=0,
            proof_fail_count=0,
            proof_insufficient_count=0,
            promotion_decision=None,
            promotion_gate_count=0,
            global_risk_halt=False,
            accounting_integrity="VALID",
            live_state="DISABLED",
            kill_switch_active=None,
            proof_trade_count=None,
            proof_distinct_mint_count=None,
            proof_net_expectancy_pct=None,
            proof_profit_factor=None,
            proof_maximum_drawdown_pct=None,
            proof_cost_burden_pct=None,
        ),
    )


def test_snapshot_schema_is_exactly_four_layers_and_canonical_json() -> None:
    snapshot = _snapshot()
    payload = encode_telemetry_snapshot(snapshot)

    assert G4_TELEMETRY_SCHEMA_VERSION == "g4-telemetry-snapshot-v1"
    assert payload.endswith("\n")
    assert payload == encode_telemetry_snapshot(snapshot)
    document = json.loads(payload)
    assert set(document) == {
        "schema_version",
        "generated_at_unix_ms",
        "mode",
        "overall_status",
        "system",
        "trading",
        "money",
        "proof_risk",
    }
    assert document["overall_status"] == "DEGRADED"
    assert document["proof_risk"]["source_errors"] == [
        "PROOF_ASSESSMENT_UNAVAILABLE"
    ]
    assert document["money"]["performance"]["net_expectancy_pct"] == 4.0
    assert payload == json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def test_layer_status_and_snapshot_invariants_fail_closed() -> None:
    with pytest.raises(ValueError):
        SystemTelemetry(
            status="HEALTHY",  # type: ignore[arg-type]
            observed_at_unix_ms=1,
            source_errors=(),
            provider_count=0,
            unhealthy_provider_count=0,
            latest_market_observed_at_unix_ms=None,
            market_age_ms=None,
            latest_ingestion_checkpoint_at_unix_ms=None,
            paper_last_cycle_at_unix_ms=None,
            accounting_status=None,
            host_metrics_available=False,
        )

    base = _snapshot()
    with pytest.raises(ValueError):
        TelemetrySnapshot(
            schema_version="wrong",
            generated_at_unix_ms=base.generated_at_unix_ms,
            mode=base.mode,
            overall_status=base.overall_status,
            system=base.system,
            trading=base.trading,
            money=base.money,
            proof_risk=base.proof_risk,
        )


def test_performance_rejects_nonfinite_or_internally_inconsistent_values() -> None:
    values = _performance()
    kwargs = {name: getattr(values, name) for name in values.__dataclass_fields__}
    kwargs["net_pnl_usd"] = math.nan
    with pytest.raises(ValueError):
        TradingPerformanceTelemetry(**kwargs)

    kwargs = {name: getattr(values, name) for name in values.__dataclass_fields__}
    kwargs["trade_count"] = 3
    with pytest.raises(ValueError):
        TradingPerformanceTelemetry(**kwargs)


def test_telemetry_public_surface_has_no_control_or_secret_authority() -> None:
    import shreks_brain.telemetry as telemetry

    public = set(telemetry.__all__)
    forbidden_fragments = (
        "trade_intent",
        "execute",
        "submit",
        "sign",
        "promote",
        "registry",
        "wallet",
        "secret",
        "api_key",
        "kill_switch_set",
        "live_enable",
    )
    lowered = " ".join(sorted(public)).lower()
    for fragment in forbidden_fragments:
        assert fragment not in lowered
