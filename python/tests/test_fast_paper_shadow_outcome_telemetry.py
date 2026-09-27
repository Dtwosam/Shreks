from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.paper import (
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperLedgerReasonCode,
)
from shreks_brain.risk import TradeSide

import shreks_brain.fast_paper_shadow_outcome_telemetry as telemetry


_SHA = "a" * 40
_MANIFEST = "b" * 64
_CHAMPION = "c" * 64
_BINDING = "d" * 64


def _manifest():
    return SimpleNamespace(
        release_source_sha=_SHA,
        manifest_fingerprint_sha256=_MANIFEST,
        champion_version="champion-v1",
        champion_fingerprint_sha256=_CHAMPION,
        action_policy=SimpleNamespace(version=4),
    )


def _binding():
    return SimpleNamespace(
        run_id="shadow-run-1",
        binding_fingerprint_sha256=_BINDING,
    )


def _entry(
    sequence: int,
    booked_at: int,
    *,
    side: TradeSide,
    state: PaperExecutionState,
    paper_reason: PaperExecutionReasonCode,
    ledger_reason: PaperLedgerReasonCode,
    filled_notional: float,
    explicit_cost: float,
    realized_pnl: float,
    cash_flow: float,
):
    return SimpleNamespace(
        sequence=sequence,
        booked_at_unix_ms=booked_at,
        side=side,
        execution_state=state,
        paper_execution_reason_code=paper_reason,
        ledger_reason_code=ledger_reason,
        filled_notional_usd=filled_notional,
        explicit_cost_usd=explicit_cost,
        realized_pnl_delta_usd=realized_pnl,
        cash_flow_usd=cash_flow,
    )


def _checkpoint():
    entries = (
        _entry(
            1,
            900,
            side=TradeSide.BUY,
            state=PaperExecutionState.FILLED,
            paper_reason=PaperExecutionReasonCode.FILL_COMPLETE,
            ledger_reason=PaperLedgerReasonCode.POSITION_OPENED,
            filled_notional=50.0,
            explicit_cost=1.0,
            realized_pnl=0.0,
            cash_flow=-51.0,
        ),
        _entry(
            2,
            1_100,
            side=TradeSide.BUY,
            state=PaperExecutionState.FILLED,
            paper_reason=PaperExecutionReasonCode.FILL_COMPLETE,
            ledger_reason=PaperLedgerReasonCode.POSITION_OPENED,
            filled_notional=100.0,
            explicit_cost=2.0,
            realized_pnl=0.0,
            cash_flow=-102.0,
        ),
        _entry(
            3,
            1_300,
            side=TradeSide.SELL,
            state=PaperExecutionState.FAILED,
            paper_reason=PaperExecutionReasonCode.ROUTE_UNAVAILABLE,
            ledger_reason=PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
            filled_notional=0.0,
            explicit_cost=0.0,
            realized_pnl=0.0,
            cash_flow=0.0,
        ),
        _entry(
            4,
            1_500,
            side=TradeSide.SELL,
            state=PaperExecutionState.FILLED,
            paper_reason=PaperExecutionReasonCode.FILL_COMPLETE,
            ledger_reason=PaperLedgerReasonCode.POSITION_CLOSED,
            filled_notional=120.0,
            explicit_cost=3.0,
            realized_pnl=15.0,
            cash_flow=117.0,
        ),
        _entry(
            5,
            2_100,
            side=TradeSide.SELL,
            state=PaperExecutionState.FILLED,
            paper_reason=PaperExecutionReasonCode.FILL_COMPLETE,
            ledger_reason=PaperLedgerReasonCode.POSITION_CLOSED,
            filled_notional=70.0,
            explicit_cost=1.0,
            realized_pnl=5.0,
            cash_flow=69.0,
        ),
    )
    ledger = SimpleNamespace(
        starting_cash_usd=20_000.0,
        cash_balance_usd=20_033.0,
        realized_pnl_usd=20.0,
        unrealized_pnl_usd=-4.0,
        accumulated_costs_usd=7.0,
        positions=(
            SimpleNamespace(state=SimpleNamespace(value="CLOSED")),
            SimpleNamespace(state=SimpleNamespace(value="OPEN")),
        ),
        entries=entries,
        processed_intent_keys=frozenset(
            f"intent-{index}" for index in range(1, 6)
        ),
    )
    return SimpleNamespace(
        run_id="shadow-run-1",
        sequence=5,
        payload_sha256="e" * 64,
        state_as_of_unix_ms=1_900,
        created_at_unix_ms=1_950,
        state=SimpleNamespace(ledger=ledger),
    )


def test_outcome_rollup_reports_window_and_cumulative_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = _checkpoint()
    calls = []

    def fake_risk(ledger, *, day_started_at_unix_ms):
        calls.append((ledger, day_started_at_unix_ms))
        return SimpleNamespace(
            open_position_count=1,
            aggregate_open_risk_usd=250.0,
            daily_realized_pnl_usd=15.0,
            rolling_drawdown_pct=2.5,
            consecutive_losses=1,
            last_loss_at_unix_ms=1_450,
        )

    monkeypatch.setattr(
        telemetry,
        "derive_paper_risk_accounting_facts",
        fake_risk,
    )

    result = telemetry.summarize_fast_paper_shadow_outcome_telemetry(
        checkpoint,
        manifest=_manifest(),
        binding=_binding(),
        expected_release_sha=_SHA,
        since_unix_ms=1_000,
        until_unix_ms=2_000,
    )

    assert calls == [(checkpoint.state.ledger, 1_000)]
    assert result["terminal_ledger_entry_count"] == 3
    assert result["fill_count"] == 2
    assert result["failed_execution_count"] == 1
    assert result["execution_state_counts"] == {
        "FAILED": 1,
        "PARTIAL": 0,
        "FILLED": 2,
    }
    assert result["side_counts"] == {"BUY": 1, "SELL": 2}
    assert result["paper_execution_reason_counts"] == {
        "FILL_COMPLETE": 2,
        "ROUTE_UNAVAILABLE": 1,
    }
    assert result["ledger_reason_counts"] == {
        "FAILED_EXECUTION_BOOKED": 1,
        "POSITION_CLOSED": 1,
        "POSITION_OPENED": 1,
    }
    assert result["filled_notional_usd"] == pytest.approx(220.0)
    assert result["explicit_cost_usd"] == pytest.approx(5.0)
    assert result["realized_pnl_delta_usd"] == pytest.approx(15.0)
    assert result["cash_flow_usd"] == pytest.approx(15.0)
    assert result["realized_explicit_cost_bps"] == {
        "mean": 225.0,
        "p50": 200.0,
        "p95": 250.0,
    }

    assert result["starting_cash_usd"] == 20_000.0
    assert result["cash_balance_usd"] == 20_033.0
    assert result["realized_pnl_usd"] == 20.0
    assert result["unrealized_pnl_usd"] == -4.0
    assert result["accumulated_costs_usd"] == 7.0
    assert result["open_position_count"] == 1
    assert result["total_position_count"] == 2
    assert result["total_ledger_entry_count"] == 5
    assert result["processed_intent_count"] == 5
    assert result["aggregate_open_risk_usd"] == 250.0
    assert result["daily_realized_pnl_usd"] == 15.0
    assert result["rolling_drawdown_pct"] == 2.5
    assert result["consecutive_losses"] == 1
    assert result["last_loss_at_unix_ms"] == 1_450

    assert result["release_source_sha"] == _SHA
    assert result["manifest_fingerprint_sha256"] == _MANIFEST
    assert result["champion_fingerprint_sha256"] == _CHAMPION
    assert result["binding_fingerprint_sha256"] == _BINDING
    assert result["checkpoint_sequence"] == 5
    assert result["checkpoint_payload_sha256"] == "e" * 64

    fingerprint = result["telemetry_fingerprint_sha256"]
    material = dict(result)
    material.pop("telemetry_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        telemetry.canonical_fast_paper_shadow_outcome_telemetry(
            material
        ).encode("utf-8")
    ).hexdigest()


def test_window_excludes_outside_entries_and_cross_checks_daily_realized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = _checkpoint()
    monkeypatch.setattr(
        telemetry,
        "derive_paper_risk_accounting_facts",
        lambda *_args, **_kwargs: SimpleNamespace(
            open_position_count=1,
            aggregate_open_risk_usd=1.0,
            daily_realized_pnl_usd=14.0,
            rolling_drawdown_pct=0.0,
            consecutive_losses=0,
            last_loss_at_unix_ms=None,
        ),
    )
    with pytest.raises(
        telemetry.FastPaperShadowOutcomeTelemetryError,
        match="daily realized",
    ):
        telemetry.summarize_fast_paper_shadow_outcome_telemetry(
            checkpoint,
            manifest=_manifest(),
            binding=_binding(),
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )


def test_empty_historical_window_is_canonical_and_safe() -> None:
    result = telemetry.summarize_fast_paper_shadow_outcome_telemetry(
        None,
        manifest=_manifest(),
        binding=_binding(),
        expected_release_sha=_SHA,
        since_unix_ms=10_000,
        until_unix_ms=20_000,
    )

    assert result["terminal_ledger_entry_count"] == 0
    assert result["execution_state_counts"] == {
        "FAILED": 0,
        "PARTIAL": 0,
        "FILLED": 0,
    }
    assert result["side_counts"] == {"BUY": 0, "SELL": 0}
    assert result["filled_notional_usd"] == 0.0
    assert result["explicit_cost_usd"] == 0.0
    assert result["realized_explicit_cost_bps"] == {
        "mean": None,
        "p50": None,
        "p95": None,
    }
    assert result["checkpoint_sequence"] is None
    assert result["cash_balance_usd"] is None
    assert result["rolling_drawdown_pct"] is None
    assert result["release_source_sha"] == _SHA
    assert result["manifest_fingerprint_sha256"] == _MANIFEST
    assert result["binding_fingerprint_sha256"] == _BINDING
    payload = telemetry.canonical_fast_paper_shadow_outcome_telemetry(
        result
    )
    assert json.loads(payload)["terminal_ledger_entry_count"] == 0


def test_collect_authenticates_release_binding_and_bounded_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    binding = _binding()
    checkpoint = _checkpoint()
    observed = []

    monkeypatch.setattr(
        telemetry,
        "read_fast_paper_runtime_manifest",
        lambda path: observed.append(("manifest", Path(path))) or manifest,
    )
    monkeypatch.setattr(
        telemetry,
        "verify_fast_paper_runtime_bindings",
        lambda supplied: observed.append(("verify", supplied)),
    )
    monkeypatch.setattr(
        telemetry,
        "build_fast_paper_shadow_ledger_binding",
        lambda supplied, *, run_id, database_path: (
            observed.append(
                ("binding", supplied, run_id, Path(database_path))
            )
            or binding
        ),
    )
    monkeypatch.setattr(
        telemetry,
        "load_fast_paper_shadow_ledger_checkpoint_at_or_before",
        lambda supplied_manifest, supplied_binding, *, as_of_unix_ms: (
            observed.append(
                (
                    "checkpoint",
                    supplied_manifest,
                    supplied_binding,
                    as_of_unix_ms,
                )
            )
            or checkpoint
        ),
    )
    monkeypatch.setattr(
        telemetry,
        "derive_paper_risk_accounting_facts",
        lambda *_args, **_kwargs: SimpleNamespace(
            open_position_count=1,
            aggregate_open_risk_usd=250.0,
            daily_realized_pnl_usd=15.0,
            rolling_drawdown_pct=2.5,
            consecutive_losses=1,
            last_loss_at_unix_ms=1_450,
        ),
    )

    result = telemetry.collect_fast_paper_shadow_outcome_telemetry(
        manifest_path=tmp_path / "manifest.json",
        ledger_database_path=tmp_path / "ledger.sqlite3",
        run_id="shadow-run-1",
        expected_release_sha=_SHA,
        since_unix_ms=1_000,
        until_unix_ms=2_000,
    )
    assert result["checkpoint_sequence"] == 5
    assert observed[-1] == (
        "checkpoint",
        manifest,
        binding,
        1_999,
    )

    wrong = SimpleNamespace(**{
        **manifest.__dict__,
        "release_source_sha": "f" * 40,
    })
    monkeypatch.setattr(
        telemetry,
        "read_fast_paper_runtime_manifest",
        lambda _path: wrong,
    )
    with pytest.raises(
        telemetry.FastPaperShadowOutcomeTelemetryError,
        match="release",
    ):
        telemetry.collect_fast_paper_shadow_outcome_telemetry(
            manifest_path=tmp_path / "manifest.json",
            ledger_database_path=tmp_path / "ledger.sqlite3",
            run_id="shadow-run-1",
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )


@pytest.mark.parametrize(
    ("since", "until"),
    (
        (-1, 10),
        (10, 10),
        (11, 10),
        (0, 86_400_001),
        (True, 10),
    ),
)
def test_window_validation_is_explicit_and_bounded(since, until) -> None:
    with pytest.raises(
        telemetry.FastPaperShadowOutcomeTelemetryError,
        match="window",
    ):
        telemetry.summarize_fast_paper_shadow_outcome_telemetry(
            None,
            manifest=_manifest(),
            binding=_binding(),
            expected_release_sha=_SHA,
            since_unix_ms=since,
            until_unix_ms=until,
        )


def test_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(telemetry.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-outcome-telemetry = '
        '"shreks_brain.fast_paper_shadow_outcome_telemetry:main"'
    ) in pyproject

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "save_fast_paper",
        "write_fast_paper",
        "systemctl",
        "subprocess",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
