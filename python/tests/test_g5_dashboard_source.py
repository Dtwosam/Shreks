from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.dashboard.source as source_module
from shreks_brain.dashboard import (
    DashboardEvidenceAvailability,
    DashboardSourceConfig,
    DashboardSourceError,
    load_dashboard_snapshot,
    load_dashboard_trade,
)
from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperLedgerEntry,
    PaperLedgerReasonCode,
)
from shreks_brain.risk import TradeSide
from shreks_brain.telemetry import encode_telemetry_snapshot

from test_g4_telemetry_financial import _trades
from test_g4_telemetry_models import _snapshot
from test_g4_telemetry_sources import _add_operational_tables
from test_observer_campaign_runtime import _runtime_config


def _entry(
    *,
    sequence: int,
    position_id: str,
    mint: str,
    side: TradeSide,
    booked_at_unix_ms: int,
    filled_notional_usd: float,
    realized_pnl_delta_usd: float,
    ledger_reason_code: PaperLedgerReasonCode,
) -> PaperLedgerEntry:
    return PaperLedgerEntry(
        sequence=sequence,
        intent_idempotency_key=f"intent-{sequence}",
        position_id=position_id,
        mint=mint,
        side=side,
        execution_state=PaperExecutionState.FILLED,
        paper_execution_reason_code=PaperExecutionReasonCode.FILL_COMPLETE,
        ledger_reason_code=ledger_reason_code,
        strategy_name="fresh_launch_continuation",
        strategy_version="candidate-v1",
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        risk_policy_version="risk-v1",
        paper_policy_version="paper-v1",
        booked_at_unix_ms=booked_at_unix_ms,
        filled_quantity=10.0,
        filled_notional_usd=filled_notional_usd,
        cash_flow_usd=-filled_notional_usd if side is TradeSide.BUY else filled_notional_usd,
        explicit_cost_usd=1.0,
        realized_pnl_delta_usd=realized_pnl_delta_usd,
    )


def _fake_bootstrap():
    trades = _trades("candidate-v1")
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
        _entry(
            sequence=3,
            position_id="position-2",
            mint="MintTwo",
            side=TradeSide.BUY,
            booked_at_unix_ms=3_000,
            filled_notional_usd=100.0,
            realized_pnl_delta_usd=0.0,
            ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
        ),
    )

    class Runner:
        def evaluated_trades(self):
            return trades

    return SimpleNamespace(
        runner=Runner(),
        restored_state=SimpleNamespace(
            ledger=SimpleNamespace(entries=entries),
        ),
    )


def _source_config(tmp_path: Path) -> DashboardSourceConfig:
    telemetry_path = tmp_path / "telemetry.json"
    telemetry_path.write_text(encode_telemetry_snapshot(_snapshot()), encoding="utf-8")
    return DashboardSourceConfig(
        telemetry_path=telemetry_path,
        paper_runtime_config=_runtime_config(tmp_path / "runtime", max_cycles=1),
    )


def test_snapshot_copies_g4_telemetry_and_orders_bounded_e11_trades(tmp_path: Path, monkeypatch) -> None:
    config = _source_config(tmp_path)
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: _fake_bootstrap(),
    )

    source = load_dashboard_snapshot(config, max_trades=1)

    assert source.telemetry == _snapshot()
    assert source.telemetry_file_mtime_ns == config.telemetry_path.stat().st_mtime_ns
    assert len(source.trades) == 1
    assert source.trades[0].position_id == "position-2"
    assert source.trades[0].mint == "MintTwo"
    assert source.trades[0].setup_name == "fresh_launch_continuation"
    assert source.trades[0].market_regime == "NORMAL"
    assert source.trades[0].net_pnl_usd == -5.0
    assert source.trades[0].execution_friction_usd == 1.0
    assert source.trades[0].explicit_cost_usd == 1.0


def test_trade_detail_joins_only_exact_ledger_events_and_marks_unpersisted_fields(tmp_path: Path, monkeypatch) -> None:
    config = _source_config(tmp_path)
    bootstrap = _fake_bootstrap()
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: bootstrap,
    )

    detail = load_dashboard_trade(config, "position-1")

    assert detail is not None
    assert detail.summary.position_id == "position-1"
    assert tuple(event.sequence for event in detail.ledger_events) == (1, 2)
    assert tuple(event.side for event in detail.ledger_events) == ("BUY", "SELL")
    assert detail.ledger_events[1].ledger_reason_code == "POSITION_CLOSED"
    assert detail.ledger_events[1].realized_pnl_delta_usd == 10.0
    assert detail.safety_assessment is DashboardEvidenceAvailability.NOT_PERSISTED
    assert detail.feature_vector is DashboardEvidenceAvailability.NOT_PERSISTED
    assert detail.score_assessment is DashboardEvidenceAvailability.NOT_PERSISTED
    assert detail.entry_decision is DashboardEvidenceAvailability.NOT_PERSISTED
    assert detail.risk_assessment is DashboardEvidenceAvailability.NOT_PERSISTED
    assert detail.entry_quote is DashboardEvidenceAvailability.NOT_PERSISTED
    assert detail.strategic_exit_reason is DashboardEvidenceAvailability.NOT_PERSISTED


def test_unknown_trade_returns_none_without_running_a_cycle(tmp_path: Path, monkeypatch) -> None:
    config = _source_config(tmp_path)
    bootstrap = _fake_bootstrap()
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: bootstrap,
    )

    assert load_dashboard_trade(config, "missing-position") is None


def test_corrupt_or_incoherent_required_sources_fail_closed(tmp_path: Path, monkeypatch) -> None:
    config = _source_config(tmp_path)
    config.telemetry_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: _fake_bootstrap(),
    )

    with pytest.raises(DashboardSourceError):
        load_dashboard_snapshot(config, max_trades=10)

    config.telemetry_path.write_text(encode_telemetry_snapshot(_snapshot()), encoding="utf-8")
    bad = _fake_bootstrap()
    bad.runner.evaluated_trades = lambda: _trades("other-candidate")
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: bad,
    )
    with pytest.raises(DashboardSourceError, match="candidate"):
        load_dashboard_snapshot(config, max_trades=10)


def test_real_runtime_source_reads_do_not_mutate_authoritative_inputs(tmp_path: Path) -> None:
    runtime = _runtime_config(tmp_path / "runtime", max_cycles=1)
    _add_operational_tables(runtime.observer_database_path)
    telemetry_path = tmp_path / "telemetry.json"
    telemetry_path.write_text(encode_telemetry_snapshot(_snapshot()), encoding="utf-8")
    config = DashboardSourceConfig(telemetry_path=telemetry_path, paper_runtime_config=runtime)

    database_before = runtime.observer_database_path.read_bytes()
    manifest_before = runtime.manifest_path.read_bytes()
    evidence_existed = runtime.evidence_path.exists()
    evidence_before = runtime.evidence_path.read_bytes() if evidence_existed else None
    telemetry_before = telemetry_path.read_bytes()

    source = load_dashboard_snapshot(config, max_trades=10)

    assert source.telemetry.mode == "PAPER"
    assert runtime.observer_database_path.read_bytes() == database_before
    assert runtime.manifest_path.read_bytes() == manifest_before
    assert runtime.evidence_path.exists() is evidence_existed
    if evidence_existed:
        assert runtime.evidence_path.read_bytes() == evidence_before
    assert telemetry_path.read_bytes() == telemetry_before
