from __future__ import annotations

import pytest

from shreks_brain.fast_campaign_paper import (
    FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
    FastCampaignPaperCandidateIdentity,
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.paper import PaperQuoteState
from shreks_brain.regime import MarketRegime


def test_public_version_and_candidate_identity_validation() -> None:
    assert FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION == "fl9-campaign-paper-v1"
    identity = FastCampaignPaperCandidateIdentity(
        version=FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
        paper_run_id="paper-run-1",
        candidate_version="learned-v1",
        candidate_fingerprint_sha256="a" * 64,
        strategy_family="fl9-continuous-action",
        strategy_version="fl9-v1",
        assessment_version="assessment-v1",
    )
    assert identity.candidate_version == "learned-v1"

    with pytest.raises(ValueError):
        FastCampaignPaperCandidateIdentity(
            version=FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
            paper_run_id="paper-run-1",
            candidate_version="learned-v1",
            candidate_fingerprint_sha256="ABC",
            strategy_family="fl9-continuous-action",
            strategy_version="fl9-v1",
            assessment_version="assessment-v1",
        )


def test_entry_authority_and_quote_evidence_are_strict() -> None:
    authority = FastCampaignPaperEntryAuthority(
        mint="mint-a",
        quote_mint="quote-a",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.1,
    )
    assert authority.intended_base_quantity == pytest.approx(10.0)

    quote = FastCampaignPaperQuoteEvidence(
        provider="fixture",
        mint="mint-a",
        quote_mint="quote-a",
        observed_at_unix_ms=1_100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=10.1,
        quoted_base_quantity=10.0,
        available_base_quantity=10.0,
        quote_to_usd_rate=1.0,
    )
    assert quote.state is PaperQuoteState.EXECUTABLE

    with pytest.raises(ValueError):
        FastCampaignPaperQuoteEvidence(
            provider="fixture",
            mint="mint-a",
            quote_mint="quote-a",
            observed_at_unix_ms=1_100,
            state=PaperQuoteState.EXECUTABLE,
            reference_price_quote=None,
            execution_price_quote=None,
            quoted_base_quantity=None,
            available_base_quantity=None,
            quote_to_usd_rate=1.0,
        )


def test_decision_evidence_carries_only_explicit_point_in_time_inputs() -> None:
    evidence = FastCampaignPaperDecisionEvidence(
        source_event_id="event-1",
        state_version="state-v1",
        evaluated_at_unix_ms=1_100,
        quote=None,
        risk_context=None,
        entry_authority=None,
        market_regime=None,
    )
    assert evidence.source_event_id == "event-1"

    buy_context = FastCampaignPaperDecisionEvidence(
        source_event_id="event-buy",
        state_version="state-v1",
        evaluated_at_unix_ms=1_100,
        quote=FastCampaignPaperQuoteEvidence(
            provider="fixture",
            mint="mint-a",
            quote_mint="quote-a",
            observed_at_unix_ms=1_100,
            state=PaperQuoteState.UNAVAILABLE,
            reference_price_quote=None,
            execution_price_quote=None,
            quoted_base_quantity=None,
            available_base_quantity=None,
            quote_to_usd_rate=1.0,
        ),
        risk_context=None,
        entry_authority=None,
        market_regime=MarketRegime.NORMAL,
    )
    assert buy_context.market_regime is MarketRegime.NORMAL
