from __future__ import annotations

import pytest

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignPaperEvidence,
    materialize_fast_deterministic_campaign_paper_evidence,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicLifecycleDecision,
)
from shreks_brain.paper import PaperQuoteState
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext


T0 = 70_000_000
MARKET = "pump_fun_bonding_curve:mint-directional:quote-directional"


def _quote(*, execution: float) -> FastCampaignPaperQuoteEvidence:
    return FastCampaignPaperQuoteEvidence(
        provider="jupiter",
        mint="mint-directional",
        quote_mint="quote-directional",
        observed_at_unix_ms=T0 + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=execution,
        quoted_base_quantity=10.0,
        available_base_quantity=10.0,
        quote_to_usd_rate=1.0,
    )


def _risk() -> RiskContext:
    return RiskContext(
        as_of_unix_ms=T0 + 100,
        trading_capital_usd=20_000.0,
        open_position_count=0,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.0,
        price_impact_notional_usd=1_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _entry_authority() -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint="mint-directional",
        quote_mint="quote-directional",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=100,
        expected_entry_fixed_cost_quote=0.01,
    )


def _decision(action: str, posture: str) -> FastDeterministicLifecycleDecision:
    return FastDeterministicLifecycleDecision(
        source_event_id="sig-directional:0",
        market_key=MARKET,
        source_sequence=1,
        as_of_unix_ms=T0,
        posture=posture,
        component_kind=(
            "IMPULSE_SCALP" if posture == "FLAT" else "LONGER_RUNNER"
        ),
        component_version=1,
        action=action,
        current_exposure_fraction=None if posture == "FLAT" else 1.0,
        target_exposure_fraction=(
            1.0 if action in {"BUY", "HOLD"} else 0.0
        ),
    )


def _directional() -> FastDeterministicCampaignPaperEvidence:
    return FastDeterministicCampaignPaperEvidence(
        source_event_id="sig-directional:0",
        state_version="state-v2",
        evaluated_at_unix_ms=T0 + 100,
        quote=None,
        entry_quote=_quote(execution=10.1),
        exit_quote=_quote(execution=9.9),
        risk_context=_risk(),
        entry_authority=_entry_authority(),
        market_regime=MarketRegime.NORMAL,
    )


def test_buy_uses_entry_quote_and_open_action_uses_exit_quote() -> None:
    raw = _directional()

    buy = materialize_fast_deterministic_campaign_paper_evidence(
        _decision("BUY", "FLAT"),
        raw,
    )
    sell = materialize_fast_deterministic_campaign_paper_evidence(
        _decision("SELL", "OPEN"),
        raw,
    )

    assert buy.quote is raw.entry_quote
    assert buy.quote is not raw.exit_quote
    assert sell.quote is raw.exit_quote
    assert sell.quote is not raw.entry_quote


def test_skip_consumes_neither_directional_quote() -> None:
    raw = _directional()

    skip = materialize_fast_deterministic_campaign_paper_evidence(
        _decision("SKIP", "FLAT"),
        raw,
    )

    assert skip.quote is None


def test_legacy_and_directional_quote_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="legacy|directional|quote"):
        FastDeterministicCampaignPaperEvidence(
            source_event_id="sig-directional:0",
            state_version="state-v2",
            evaluated_at_unix_ms=T0 + 100,
            quote=_quote(execution=10.0),
            entry_quote=_quote(execution=10.1),
            exit_quote=_quote(execution=9.9),
            risk_context=_risk(),
            entry_authority=_entry_authority(),
            market_regime=MarketRegime.NORMAL,
        )
