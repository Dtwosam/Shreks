from __future__ import annotations

import pytest

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperDecisionEvidence,
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


T0 = 30_000_000
MARKET = "pump_fun_bonding_curve:mint-life:quote-life"


def _quote() -> FastCampaignPaperQuoteEvidence:
    return FastCampaignPaperQuoteEvidence(
        provider="fixture",
        mint="mint-life",
        quote_mint="quote-life",
        observed_at_unix_ms=T0 + 100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=10.1,
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
        price_impact_notional_usd=10_000.0,
        market_data_age_ms=0,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _entry() -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint="mint-life",
        quote_mint="quote-life",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )


def _raw(
    *,
    source_event_id: str = "sig-1:0",
    quote=True,
    risk=True,
    entry=True,
    regime=True,
) -> FastDeterministicCampaignPaperEvidence:
    return FastDeterministicCampaignPaperEvidence(
        source_event_id=source_event_id,
        state_version="state-v1",
        evaluated_at_unix_ms=T0 + 100,
        quote=_quote() if quote else None,
        risk_context=_risk() if risk else None,
        entry_authority=_entry() if entry else None,
        market_regime=MarketRegime.NORMAL if regime else None,
    )


def _decision(
    action: str,
    *,
    posture: str = "FLAT",
) -> FastDeterministicLifecycleDecision:
    current = None if posture == "FLAT" else 0.8
    if action == "BUY":
        target = 0.8
    elif action == "HOLD":
        target = 0.8
    elif action == "REDUCE":
        target = 0.4
    else:
        target = 0.0
    return FastDeterministicLifecycleDecision(
        source_event_id="sig-1:0",
        market_key=MARKET,
        source_sequence=1,
        as_of_unix_ms=T0,
        posture=posture,
        component_kind=(
            "IMPULSE_SCALP" if posture == "FLAT" else "LONGER_RUNNER"
        ),
        component_version=1,
        action=action,
        current_exposure_fraction=current,
        target_exposure_fraction=target,
    )


def test_rich_raw_evidence_materializes_skip_without_execution_fields() -> None:
    raw = _raw()
    point = materialize_fast_deterministic_campaign_paper_evidence(
        _decision("SKIP"),
        raw,
    )

    assert type(point) is FastCampaignPaperDecisionEvidence
    assert point.source_event_id == raw.source_event_id
    assert point.state_version == raw.state_version
    assert point.evaluated_at_unix_ms == raw.evaluated_at_unix_ms
    assert point.quote is None
    assert point.risk_context is None
    assert point.entry_authority is None
    assert point.market_regime is None


def test_buy_preserves_all_exact_required_evidence() -> None:
    raw = _raw()
    point = materialize_fast_deterministic_campaign_paper_evidence(
        _decision("BUY"),
        raw,
    )

    assert point.quote is raw.quote
    assert point.risk_context is raw.risk_context
    assert point.entry_authority is raw.entry_authority
    assert point.market_regime is raw.market_regime


@pytest.mark.parametrize(
    ("field", "kwargs"),
    (
        ("quote", {"quote": False}),
        ("RiskContext", {"risk": False}),
        ("entry", {"entry": False}),
        ("MarketRegime", {"regime": False}),
    ),
)
def test_buy_missing_required_raw_evidence_fails_closed(
    field: str,
    kwargs: dict[str, bool],
) -> None:
    with pytest.raises(ValueError, match=field):
        materialize_fast_deterministic_campaign_paper_evidence(
            _decision("BUY"),
            _raw(**kwargs),
        )


@pytest.mark.parametrize("action", ("HOLD", "REDUCE", "SELL"))
def test_position_actions_preserve_quote_and_drop_buy_only_fields(
    action: str,
) -> None:
    raw = _raw()
    point = materialize_fast_deterministic_campaign_paper_evidence(
        _decision(action, posture="OPEN"),
        raw,
    )

    assert point.quote is raw.quote
    assert point.risk_context is None
    assert point.entry_authority is None
    assert point.market_regime is None


def test_position_action_without_quote_fails_closed() -> None:
    with pytest.raises(ValueError, match="quote"):
        materialize_fast_deterministic_campaign_paper_evidence(
            _decision("SELL", posture="OPEN"),
            _raw(quote=False),
        )


def test_source_identity_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="source|identity"):
        materialize_fast_deterministic_campaign_paper_evidence(
            _decision("BUY"),
            _raw(source_event_id="other:0"),
        )
