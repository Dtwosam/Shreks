from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignRow,
    run_fast_deterministic_chronological_campaign,
)
from shreks_brain.fast_deterministic_lifecycle import (
    decode_fast_deterministic_candidate_manifest,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperPositionState,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
)
from shreks_brain.risk import RiskContext, RiskPolicy


T0 = 20_000_000
MINT = "mint-life"
QUOTE = "quote-life"
VENUE = "pump_fun_bonding_curve"
MARKET = f"{VENUE}:{MINT}:{QUOTE}"
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_candidate_manifest_v1.json"
)


def _manifest():
    return decode_fast_deterministic_candidate_manifest(
        FIXTURE.read_text(encoding="utf-8")
    )


def _window(window_ms: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=8 if window_ms == 500 else 0,
        sell_count=2 if window_ms == 500 else 0,
        unique_buy_actors=6 if window_ms == 500 else 0,
        unique_sell_actors=2 if window_ms == 500 else 0,
        buy_arrival_rate_per_second=16.0 if window_ms == 500 else 0.0,
        sell_arrival_rate_per_second=4.0 if window_ms == 500 else 0.0,
        count_imbalance=0.6 if window_ms == 500 else 0.0,
        buy_base_quantity=1.0 if window_ms == 500 else 0.0,
        sell_base_quantity=0.2 if window_ms == 500 else 0.0,
        buy_quote_quantity=4.5 if window_ms == 500 else 0.0,
        sell_quote_quantity=0.8 if window_ms == 500 else 0.0,
        net_quote_quantity=3.7 if window_ms == 500 else 0.0,
        quote_flow_imbalance=(3.7 / 5.3) if window_ms == 500 else 0.0,
        quote_flow_velocity_per_second=7.4 if window_ms == 500 else 0.0,
        quote_flow_acceleration_per_second2=12.0 if window_ms == 500 else 0.0,
        local_high_price_quote=10.2,
        local_high_sequence=1,
        local_high_observed_at_unix_ms=T0 - 100,
        local_low_price_quote=9.5,
        local_low_sequence=1,
        local_low_observed_at_unix_ms=T0 - 90,
        post_high_low_price_quote=9.9,
        post_high_low_sequence=1,
        post_high_low_observed_at_unix_ms=T0 - 80,
        last_price_quote=10.0,
        drawdown_from_local_high=0.01,
        recovery_from_local_low=0.05,
    )


def _record(signature: str, sequence: int, at: int) -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature=signature,
        decision_ordinal=0,
        decision_sequence=sequence,
        mint=MINT,
        quote_mint=QUOTE,
        venue=VENUE,
        decision_observed_at_unix_ms=at,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=at - 1,
        decision_occurred_at_unix_ms=at - 2,
        decision_slot=100 + sequence,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=10.0,
        decision_entry_total_quote=100.0,
        snapshot_as_of_unix_ms=at,
        snapshot_last_sequence=sequence,
        snapshot_last_price_quote=10.0,
        last_reserve_context=None,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _leg() -> FastOfflineExecutionLegCost:
    return FastOfflineExecutionLegCost(
        effective_fee_bps=50,
        expected_impact_bps=20,
        expected_slippage_bps=20,
        expected_latency_bps=10,
        network_fee_quote=0.01,
        priority_fee_quote=0.0,
        expected_failure_cost_quote=0.0,
    )


def _entry_strategy_evidence() -> FastOfflineImpulseScalpEvidence:
    return FastOfflineImpulseScalpEvidence(
        execution=FastOfflineEntryExecution(
            cost_model=FastOfflineExecutionCostModel(
                version=1,
                entry=_leg(),
                exit=_leg(),
            ),
            trade=FastOfflineExecutionTrade(
                base_quantity=10.0,
                executable_entry_price_quote=10.0,
                forecast_exit_price_quote=12.0,
                exit_capacity_base=10.0,
                required_edge_bps=200,
                risk_margin_bps=100,
            ),
        )
    )


def _open_strategy_evidence() -> FastOfflineLongerRunnerEvidence:
    return FastOfflineLongerRunnerEvidence(
        protective=FastOfflineLongerRunnerProtective(
            hard_stop_triggered=False,
            risk_limit_exit_required=False,
            liquidity_exit_required=False,
        ),
        continuation=None,
    )


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="campaign-driver-fill-v1",
        assumed_latency_ms=0,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=False,
        min_partial_fill_fraction=1.0,
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="campaign-driver-risk-v1",
        required_decision_policy_version="assessment-v1",
        required_feature_schema_version="state-v1",
        target_position_notional_usd=100.0,
        max_notional_per_position_usd=500.0,
        max_capital_fraction_per_position=1.0,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=5_000.0,
        max_daily_realized_loss_usd=5_000.0,
        max_rolling_drawdown_pct=100.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=0,
        min_liquidity_usd=0.0,
        max_expected_price_impact_pct=100.0,
        max_slippage_bps=1_000,
        max_market_data_age_ms=2_000,
    )


def _risk(at: int) -> RiskContext:
    return RiskContext(
        as_of_unix_ms=at,
        trading_capital_usd=20_000.0,
        open_position_count=0,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.0,
        price_impact_notional_usd=10_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _entry_authority() -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint=MINT,
        quote_mint=QUOTE,
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )


def _quote(
    at: int,
    *,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
    reference: float = 10.0,
    execution: float = 10.1,
) -> FastCampaignPaperQuoteEvidence:
    unavailable = state is PaperQuoteState.UNAVAILABLE
    return FastCampaignPaperQuoteEvidence(
        provider="fixture",
        mint=MINT,
        quote_mint=QUOTE,
        observed_at_unix_ms=at,
        state=state,
        reference_price_quote=None if unavailable else reference,
        execution_price_quote=None if unavailable else execution,
        quoted_base_quantity=None if unavailable else 10.0,
        available_base_quantity=None if unavailable else 10.0,
        quote_to_usd_rate=1.0,
    )


def _paper_evidence(
    source_event_id: str,
    at: int,
    *,
    buy: bool,
    state: PaperQuoteState = PaperQuoteState.EXECUTABLE,
    reference: float = 10.0,
    execution: float = 10.1,
) -> FastCampaignPaperDecisionEvidence:
    return FastCampaignPaperDecisionEvidence(
        source_event_id=source_event_id,
        state_version="state-v1",
        evaluated_at_unix_ms=at,
        quote=_quote(
            at,
            state=state,
            reference=reference,
            execution=execution,
        ),
        risk_context=_risk(at) if buy else None,
        entry_authority=_entry_authority() if buy else None,
        market_regime=MarketRegime.NORMAL if buy else None,
    )


def _row(
    signature: str,
    sequence: int,
    at: int,
    *,
    paper: FastCampaignPaperDecisionEvidence,
    flat=None,
    open_=None,
) -> FastDeterministicCampaignRow:
    return FastDeterministicCampaignRow(
        record=_record(signature, sequence, at),
        flat_evidence=_entry_strategy_evidence() if flat is None else flat,
        open_evidence=_open_strategy_evidence() if open_ is None else open_,
        paper_evidence=paper,
    )


def _runner_kwargs(binary: Path, rows: tuple[FastDeterministicCampaignRow, ...]):
    return dict(
        binary_path=binary,
        manifest=_manifest(),
        rows=rows,
        paper_run_id="deterministic-campaign-run",
        assessment_version="assessment-v1",
        starting_ledger=create_paper_ledger(20_000.0, T0),
        fill_policy=_fill_policy(),
        risk_policy=_risk_policy(),
        position_policy=FastPaperPositionActionPolicy(
            version="campaign-driver-position-v1",
            max_slippage_bps=1_000,
        ),
        evaluation_policy=TradingEvaluationPolicy(
            version="campaign-driver-eval-v1",
            starting_equity_usd=20_000.0,
            calibration_bucket_count=10,
        ),
    )


def _write_marker_binary(path: Path, marker: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('launched', encoding='utf-8')\n"
        "raise SystemExit(91)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o111)


def _write_posture_binary(path: Path, posture_log: Path) -> None:
    script = f"""#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
posture = request["posture"]["kind"]
with Path({str(posture_log)!r}).open("a", encoding="utf-8") as handle:
    handle.write(posture + "\\n")

manifest = request["manifest"]
record = request["record"]
policy = manifest["lifecycle_policy"]
policy_wire = {{
    "version": policy["version"],
    "entry_baseline_kind": policy["entry_baseline_kind"],
    "manager_baseline_kind": policy["manager_baseline_kind"],
    "entry_target_exposure_fraction": policy["entry_target_exposure_fraction"],
    "reduce_remaining_fraction": policy["reduce_remaining_fraction"],
}}
if posture == "FLAT":
    action = "BUY"
    current = None
    target = policy["entry_target_exposure_fraction"]
    component = policy["entry_baseline_kind"]
else:
    action = "SELL"
    current = request["posture"]["current_exposure_fraction"]
    target = 0.0
    component = policy["manager_baseline_kind"]

decision = {{
    "source_event_id": f"{{record['decision_signature']}}:{{record['decision_ordinal']}}",
    "market_key": f"{{record['venue']}}:{{record['mint']}}:{{record['quote_mint']}}",
    "source_sequence": record["decision_sequence"],
    "as_of_unix_ms": record["decision_observed_at_unix_ms"],
    "posture": posture,
    "component_kind": component,
    "component_version": 1,
    "action": action,
    "current_exposure_fraction": current,
    "target_exposure_fraction": target,
}}
result = {{
    "schema_name": "shreks.fast_deterministic_row_result",
    "schema_version": 1,
    "candidate_version": manifest["candidate_version"],
    "candidate_fingerprint_sha256": manifest["candidate_fingerprint_sha256"],
    "lifecycle_policy": policy_wire,
    "decision": decision,
    "result_fingerprint_sha256": "",
}}
material = dict(result)
material.pop("result_fingerprint_sha256")
canonical = json.dumps(
    material,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
result["result_fingerprint_sha256"] = hashlib.sha256(
    canonical.encode("utf-8")
).hexdigest()
print(json.dumps(result, separators=(",", ":"), ensure_ascii=False, allow_nan=False), end="")
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_sequence_regression_fails_before_offline_binary_launch(tmp_path: Path) -> None:
    binary = tmp_path / "marker"
    marker = tmp_path / "launched"
    _write_marker_binary(binary, marker)
    rows = (
        _row(
            "sig-2",
            2,
            T0 + 300,
            paper=_paper_evidence("sig-2:0", T0 + 400, buy=True),
        ),
        _row(
            "sig-1",
            1,
            T0 + 100,
            paper=_paper_evidence("sig-1:0", T0 + 200, buy=True),
        ),
    )

    with pytest.raises(ValueError, match="sequence|order"):
        run_fast_deterministic_chronological_campaign(
            **_runner_kwargs(binary, rows)
        )

    assert not marker.exists()


def test_wrong_family_and_paper_identity_fail_before_launch(tmp_path: Path) -> None:
    binary = tmp_path / "marker"
    marker = tmp_path / "launched"
    _write_marker_binary(binary, marker)

    wrong_family = (
        _row(
            "sig-1",
            1,
            T0 + 100,
            paper=_paper_evidence("sig-1:0", T0 + 200, buy=True),
            flat=_open_strategy_evidence(),
        ),
    )
    with pytest.raises(ValueError, match="FLAT|entry|family"):
        run_fast_deterministic_chronological_campaign(
            **_runner_kwargs(binary, wrong_family)
        )
    assert not marker.exists()

    wrong_identity = (
        _row(
            "sig-1",
            1,
            T0 + 100,
            paper=_paper_evidence("other:0", T0 + 200, buy=True),
        ),
    )
    with pytest.raises(ValueError, match="source|identity"):
        run_fast_deterministic_chronological_campaign(
            **_runner_kwargs(binary, wrong_identity)
        )
    assert not marker.exists()


def test_filled_buy_switches_next_row_to_open_and_successful_sell_closes(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "row-evaluator"
    posture_log = tmp_path / "postures"
    _write_posture_binary(binary, posture_log)
    rows = (
        _row(
            "sig-1",
            1,
            T0 + 100,
            paper=_paper_evidence("sig-1:0", T0 + 200, buy=True),
        ),
        _row(
            "sig-2",
            2,
            T0 + 300,
            paper=_paper_evidence(
                "sig-2:0",
                T0 + 400,
                buy=False,
                reference=10.5,
                execution=10.4,
            ),
        ),
    )

    session = run_fast_deterministic_chronological_campaign(
        **_runner_kwargs(binary, rows)
    )

    assert posture_log.read_text(encoding="utf-8").splitlines() == [
        "FLAT",
        "OPEN",
    ]
    assert tuple(value.action for value in session.decisions) == ("BUY", "SELL")
    assert tuple(value.source_event_id for value in session.decisions) == (
        "sig-1:0",
        "sig-2:0",
    )
    assert session.latest_result is not None
    assert session.latest_result.run_evidence.decision_count == 2
    assert session.latest_result.run_evidence.material_update_count == 2
    assert session.latest_result.run_evidence.distinct_market_count == 1
    assert len(session.latest_result.final_ledger.positions) == 1
    assert (
        session.latest_result.final_ledger.positions[0].state
        is PaperPositionState.CLOSED
    )


def test_unavailable_buy_keeps_next_row_flat(tmp_path: Path) -> None:
    binary = tmp_path / "row-evaluator"
    posture_log = tmp_path / "postures"
    _write_posture_binary(binary, posture_log)
    rows = (
        _row(
            "sig-1",
            1,
            T0 + 100,
            paper=_paper_evidence(
                "sig-1:0",
                T0 + 200,
                buy=True,
                state=PaperQuoteState.UNAVAILABLE,
            ),
        ),
        _row(
            "sig-2",
            2,
            T0 + 300,
            paper=_paper_evidence("sig-2:0", T0 + 400, buy=True),
        ),
    )

    session = run_fast_deterministic_chronological_campaign(
        **_runner_kwargs(binary, rows)
    )

    assert posture_log.read_text(encoding="utf-8").splitlines() == [
        "FLAT",
        "FLAT",
    ]
    assert tuple(value.action for value in session.decisions) == ("BUY", "BUY")
    assert session.latest_result is not None
    assert session.latest_result.run_evidence.decision_count == 2
    assert len(session.latest_result.final_ledger.positions) == 1
    assert (
        session.latest_result.final_ledger.positions[0].state
        is PaperPositionState.OPEN
    )


def test_campaign_driver_only_orchestrates_sealed_components() -> None:
    package = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )

    for required in (
        "evaluate_fast_deterministic_row_offline(",
        "fast_deterministic_paper_session_posture(",
        "apply_fast_deterministic_paper_session_step(",
        "create_fast_deterministic_paper_session(",
    ):
        assert required in source

    for forbidden in (
        "import subprocess",
        "subprocess.run",
        "requests.",
        "sqlite3",
        "execute_fast_paper_buy",
        "run_fast_deterministic_lifecycle_paper_candidate",
        "evaluate_fast_policy_superiority",
        "RuntimeMode",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
