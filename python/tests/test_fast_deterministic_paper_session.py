from __future__ import annotations

from pathlib import Path

import pytest

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
    apply_fast_deterministic_paper_session_step,
    create_fast_deterministic_paper_session,
    fast_deterministic_paper_session_posture,
    run_fast_deterministic_lifecycle_paper_candidate,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicLifecycleDecision,
    FastDeterministicLifecyclePolicy,
    build_fast_deterministic_lifecycle_results,
    decode_fast_deterministic_candidate_manifest,
    decode_fast_deterministic_lifecycle_results,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperPositionState,
    PaperQuoteState,
    create_paper_ledger,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext, RiskPolicy


T0 = 12_000_000
MARKET = "pump_fun_bonding_curve:mint-life:quote-life"
MINT = "mint-life"
QUOTE = "quote-life"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = FIXTURES / "fast_deterministic_candidate_manifest_v1.json"
LIFECYCLE = FIXTURES / "fast_deterministic_lifecycle_results_v1.json"


def _manifest():
    return decode_fast_deterministic_candidate_manifest(
        MANIFEST.read_text(encoding="utf-8")
    )


def _policy() -> FastDeterministicLifecyclePolicy:
    return FastDeterministicLifecyclePolicy(
        version=1,
        entry_baseline_kind="IMPULSE_SCALP",
        manager_baseline_kind="LONGER_RUNNER",
        entry_target_exposure_fraction=0.8,
        reduce_remaining_fraction=0.5,
    )


def _decision(
    event: str,
    sequence: int,
    at: int,
    *,
    posture: str,
    action: str,
    current: float | None,
    target: float,
) -> FastDeterministicLifecycleDecision:
    return FastDeterministicLifecycleDecision(
        source_event_id=event,
        market_key=MARKET,
        source_sequence=sequence,
        as_of_unix_ms=at,
        posture=posture,
        component_kind=(
            "IMPULSE_SCALP" if posture == "FLAT" else "LONGER_RUNNER"
        ),
        component_version=1,
        action=action,
        current_exposure_fraction=current,
        target_exposure_fraction=target,
    )


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-session-v1",
        assumed_latency_ms=0,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=False,
        min_partial_fill_fraction=1.0,
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-session-v1",
        required_decision_policy_version="assessment-v1",
        required_feature_schema_version="state-v1",
        target_position_notional_usd=500.0,
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


def _entry() -> FastCampaignPaperEntryAuthority:
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


def _evidence(
    event: str,
    at: int,
    *,
    quote: FastCampaignPaperQuoteEvidence | None = None,
    buy: bool = False,
) -> FastCampaignPaperDecisionEvidence:
    return FastCampaignPaperDecisionEvidence(
        source_event_id=event,
        state_version="state-v1",
        evaluated_at_unix_ms=at,
        quote=quote,
        risk_context=_risk(at) if buy else None,
        entry_authority=_entry() if buy else None,
        market_regime=MarketRegime.NORMAL if buy else None,
    )


def _session():
    return create_fast_deterministic_paper_session(
        manifest=_manifest(),
        paper_run_id="paper-run-session",
        assessment_version="assessment-v1",
        starting_ledger=create_paper_ledger(20_000.0, T0),
        fill_policy=_fill_policy(),
        risk_policy=_risk_policy(),
        position_policy=FastPaperPositionActionPolicy(
            version="position-session-v1",
            max_slippage_bps=1_000,
        ),
        evaluation_policy=TradingEvaluationPolicy(
            version="eval-session-v1",
            starting_equity_usd=20_000.0,
            calibration_bucket_count=10,
        ),
    )


def test_python_lifecycle_builder_matches_shared_golden_fingerprint() -> None:
    decoded = decode_fast_deterministic_lifecycle_results(
        LIFECYCLE.read_text(encoding="utf-8")
    )
    built = build_fast_deterministic_lifecycle_results(
        decoded.policy,
        decoded.decisions,
    )

    assert built == decoded
    assert (
        built.batch_fingerprint_sha256
        == "bd7e267a2a7cf836f6db87ad75306676efaf500446e62097d58004559812a576"
    )


def test_session_posture_follows_actual_paper_outcomes() -> None:
    session = _session()
    initial = fast_deterministic_paper_session_posture(session, MARKET)
    assert initial.posture == "FLAT"
    assert initial.current_exposure_fraction is None
    assert initial.position_id is None
    assert initial.opened_at_unix_ms is None

    unavailable_buy = _decision(
        "event-1",
        1,
        T0 + 100,
        posture="FLAT",
        action="BUY",
        current=None,
        target=0.8,
    )
    session = apply_fast_deterministic_paper_session_step(
        session,
        unavailable_buy,
        _evidence(
            "event-1",
            T0 + 200,
            quote=_quote(T0 + 200, state=PaperQuoteState.UNAVAILABLE),
            buy=True,
        ),
    )
    assert fast_deterministic_paper_session_posture(session, MARKET).posture == "FLAT"

    buy = _decision(
        "event-2",
        2,
        T0 + 300,
        posture="FLAT",
        action="BUY",
        current=None,
        target=0.8,
    )
    session = apply_fast_deterministic_paper_session_step(
        session,
        buy,
        _evidence(
            "event-2",
            T0 + 400,
            quote=_quote(T0 + 400),
            buy=True,
        ),
    )
    opened = fast_deterministic_paper_session_posture(session, MARKET)
    assert opened.posture == "OPEN"
    assert opened.current_exposure_fraction == pytest.approx(0.8)
    assert opened.position_id is not None
    assert opened.opened_at_unix_ms == T0 + 400
    assert session.latest_result is not None
    position = next(
        value
        for value in session.latest_result.final_ledger.positions
        if value.position_id == opened.position_id
    )
    assert position.state is PaperPositionState.OPEN

    reduce = _decision(
        "event-3",
        3,
        T0 + 500,
        posture="OPEN",
        action="REDUCE",
        current=0.8,
        target=0.4,
    )
    session = apply_fast_deterministic_paper_session_step(
        session,
        reduce,
        _evidence(
            "event-3",
            T0 + 600,
            quote=_quote(T0 + 600, reference=10.5, execution=10.4),
        ),
    )
    reduced = fast_deterministic_paper_session_posture(session, MARKET)
    assert reduced.posture == "OPEN"
    assert reduced.current_exposure_fraction == pytest.approx(0.4)
    assert reduced.position_id == opened.position_id

    unavailable_sell = _decision(
        "event-4",
        4,
        T0 + 700,
        posture="OPEN",
        action="SELL",
        current=0.4,
        target=0.0,
    )
    session = apply_fast_deterministic_paper_session_step(
        session,
        unavailable_sell,
        _evidence(
            "event-4",
            T0 + 800,
            quote=_quote(T0 + 800, state=PaperQuoteState.UNAVAILABLE),
        ),
    )
    still_open = fast_deterministic_paper_session_posture(session, MARKET)
    assert still_open.posture == "OPEN"
    assert still_open.current_exposure_fraction == pytest.approx(0.4)

    sell = _decision(
        "event-5",
        5,
        T0 + 900,
        posture="OPEN",
        action="SELL",
        current=0.4,
        target=0.0,
    )
    session = apply_fast_deterministic_paper_session_step(
        session,
        sell,
        _evidence(
            "event-5",
            T0 + 1_000,
            quote=_quote(T0 + 1_000, reference=11.0, execution=10.9),
        ),
    )
    closed = fast_deterministic_paper_session_posture(session, MARKET)
    assert closed.posture == "FLAT"
    assert closed.current_exposure_fraction is None
    assert session.latest_result is not None
    assert session.latest_result.final_ledger.positions[0].state is PaperPositionState.CLOSED


def test_wrong_candidate_specific_posture_fails_before_prefix_replay() -> None:
    session = _session()
    wrong = _decision(
        "event-1",
        1,
        T0 + 100,
        posture="OPEN",
        action="HOLD",
        current=0.8,
        target=0.8,
    )

    with pytest.raises(ValueError, match="posture|FLAT|OPEN"):
        apply_fast_deterministic_paper_session_step(
            session,
            wrong,
            _evidence(
                "event-1",
                T0 + 200,
                quote=_quote(T0 + 200),
            ),
        )


def test_session_prefix_result_equals_direct_sealed_runner() -> None:
    session = _session()
    decisions = (
        _decision(
            "event-1",
            1,
            T0 + 100,
            posture="FLAT",
            action="BUY",
            current=None,
            target=0.8,
        ),
        _decision(
            "event-2",
            2,
            T0 + 300,
            posture="OPEN",
            action="SELL",
            current=0.8,
            target=0.0,
        ),
    )
    evidence = (
        _evidence(
            "event-1",
            T0 + 200,
            quote=_quote(T0 + 200),
            buy=True,
        ),
        _evidence(
            "event-2",
            T0 + 400,
            quote=_quote(T0 + 400, reference=10.5, execution=10.4),
        ),
    )

    for decision, point in zip(decisions, evidence):
        session = apply_fast_deterministic_paper_session_step(
            session,
            decision,
            point,
        )

    direct = run_fast_deterministic_lifecycle_paper_candidate(
        manifest=session.manifest,
        paper_run_id=session.paper_run_id,
        assessment_version=session.assessment_version,
        decisions=build_fast_deterministic_lifecycle_results(
            session.manifest.lifecycle_policy,
            decisions,
        ),
        evidence=evidence,
        starting_ledger=session.starting_ledger,
        fill_policy=session.fill_policy,
        risk_policy=session.risk_policy,
        position_policy=session.position_policy,
        evaluation_policy=session.evaluation_policy,
    )

    assert session.latest_result == direct


def test_deterministic_paper_session_has_no_provider_rust_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_campaign_paper"
        / "session.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "requests.",
        "sqlite3",
        "subprocess",
        "cargo",
        "FastTrainingFeatureRecord",
        "WalletCohortEvidence",
        "LongerRunnerContinuationEvidence",
        "RuntimeMode",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source

    assert source.count("run_fast_deterministic_lifecycle_paper_candidate(") == 1
