from __future__ import annotations

from dataclasses import replace
import math

import pytest

from shreks_brain.observer_campaign.models import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.observer_campaign.quotes import (
    ObserverPaperQuoteError,
    build_entry_paper_quote,
    build_exit_paper_quote,
)
from shreks_brain.observer_market.models import (
    OBSERVER_MARKET_SCHEMA_VERSION,
    ObservedMarketWindow,
    ObserverCandidateIdentity,
    ObserverMarketSnapshot,
)
from shreks_brain.paper import PaperQuoteState


TOKEN = "Mint111"
QUOTE_ASSET = "QuoteAsset111"


def _window(*, price_usd: float | None = 2.0) -> ObservedMarketWindow:
    candidate = ObserverCandidateIdentity(
        candidate_id=7,
        mint=TOKEN,
        pair_address="Pair111",
        discovery_source="pump",
        discovered_at_unix_ms=100,
        venue="pump_fun",
    )
    current = ObserverMarketSnapshot(
        row_id=11,
        candidate_id=7,
        observed_at_unix_ms=1_000_000,
        source="dexscreener",
        source_observed_at_unix_ms=999_900,
        venue="pump_fun",
        pair_address="Pair111",
        price_usd=price_usd,
        liquidity_usd=50_000.0,
        volume_m5_usd=5_000.0,
        volume_h1_usd=50_000.0,
        buys_m5=10,
        sells_m5=5,
        buys_h1=100,
        sells_h1=50,
        pair_created_at_unix_ms=100,
    )
    return ObservedMarketWindow(
        schema_version=OBSERVER_MARKET_SCHEMA_VERSION,
        policy_version="market-v1",
        candidate=candidate,
        as_of_unix_ms=1_000_000,
        selected_source="dexscreener",
        selected_pair_address="Pair111",
        current=current,
        one_minute_ago=None,
        five_minutes_ago=None,
        fifteen_minutes_ago=None,
        pair_created_at_unix_ms=100,
        local_high_price_usd=2.0 if price_usd is not None else None,
        local_low_price_usd=2.0 if price_usd is not None else None,
    )


def _asset(**changes) -> ObserverPaperQuoteAsset:
    values = {
        "mint": QUOTE_ASSET,
        "decimals": 6,
        "usd_per_token": 1.25,
    }
    values.update(changes)
    return ObserverPaperQuoteAsset(**values)


def _entry_evidence(**changes) -> ObserverPaperQuoteEvidence:
    identity = ObserverPaperQuoteIdentity(
        candidate_id=7,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider="jupiter",
        probe_policy_version="probe-v2",
        input_mint=QUOTE_ASSET,
        output_mint=TOKEN,
        taker="Taker111",
        input_amount=2_000_000,
        slippage_bps=75,
    )
    values = {
        "identity": identity,
        "output_amount": 1_000_000_000,
        "minimum_output_amount": 990_000_000,
        "route_available": True,
        "price_impact_pct": "0.2",
        "route_labels": ("Raydium",),
        "quoted_at_unix_ms": 999_950,
    }
    values.update(changes)
    return ObserverPaperQuoteEvidence(**values)


def _exit_evidence(**changes) -> ObserverPaperQuoteEvidence:
    identity = ObserverPaperQuoteIdentity(
        candidate_id=7,
        purpose=ObserverPaperQuotePurpose.EXIT,
        provider="jupiter",
        probe_policy_version="probe-v2",
        input_mint=TOKEN,
        output_mint=QUOTE_ASSET,
        taker="Taker111",
        input_amount=500_000_000,
        slippage_bps=75,
    )
    values = {
        "identity": identity,
        "output_amount": 1_200_000,
        "minimum_output_amount": 1_190_000,
        "route_available": True,
        "price_impact_pct": "0.2",
        "route_labels": ("Raydium",),
        "quoted_at_unix_ms": 999_960,
    }
    values.update(changes)
    return ObserverPaperQuoteEvidence(**values)


def test_entry_quote_reconstruction_uses_quote_asset_usd_and_token_decimals_exactly():
    quote = build_entry_paper_quote(
        _window(),
        _entry_evidence(),
        token_decimals=9,
        quote_asset=_asset(),
    )

    assert quote.provider == "jupiter"
    assert quote.mint == TOKEN
    assert quote.observed_at_unix_ms == 999_950
    assert quote.state is PaperQuoteState.EXECUTABLE
    assert quote.reference_price_usd == 2.0
    assert quote.execution_price_usd == 2.5
    assert quote.quoted_notional_usd == 2.5
    assert quote.available_notional_usd == 2.5


def test_exit_quote_reconstruction_uses_reference_notional_and_real_quote_proceeds():
    quote = build_exit_paper_quote(
        _window(),
        _exit_evidence(),
        token_decimals=9,
        quote_asset=_asset(),
    )

    assert quote.provider == "jupiter"
    assert quote.mint == TOKEN
    assert quote.observed_at_unix_ms == 999_960
    assert quote.state is PaperQuoteState.EXECUTABLE
    assert quote.reference_price_usd == 2.0
    assert quote.execution_price_usd == 3.0
    assert quote.quoted_notional_usd == 1.0
    assert quote.available_notional_usd == 1.0


def test_no_route_maps_to_sealed_unavailable_shape_without_fabricated_economics():
    unavailable_entry = _entry_evidence(
        output_amount=0,
        minimum_output_amount=0,
        route_available=False,
        price_impact_pct=None,
        route_labels=(),
    )
    quote = build_entry_paper_quote(
        _window(),
        unavailable_entry,
        token_decimals=9,
        quote_asset=_asset(),
    )
    assert quote.state is PaperQuoteState.UNAVAILABLE
    assert quote.reference_price_usd is None
    assert quote.execution_price_usd is None
    assert quote.quoted_notional_usd is None
    assert quote.available_notional_usd is None


def test_entry_and_exit_reject_wrong_purpose_mints_candidate_and_quote_asset_attribution():
    entry = _entry_evidence()
    exit_ = _exit_evidence()

    wrong_entry_purpose = replace(
        entry,
        identity=replace(
            entry.identity,
            purpose=ObserverPaperQuotePurpose.EXIT,
            input_mint=TOKEN,
            output_mint=QUOTE_ASSET,
        ),
    )
    with pytest.raises(ObserverPaperQuoteError):
        build_entry_paper_quote(_window(), wrong_entry_purpose, 9, _asset())

    wrong_exit_purpose = replace(
        exit_,
        identity=replace(
            exit_.identity,
            purpose=ObserverPaperQuotePurpose.ENTRY,
            input_mint=QUOTE_ASSET,
            output_mint=TOKEN,
        ),
    )
    with pytest.raises(ObserverPaperQuoteError):
        build_exit_paper_quote(_window(), wrong_exit_purpose, 9, _asset())

    wrong_candidate = replace(
        entry,
        identity=replace(entry.identity, candidate_id=8),
    )
    with pytest.raises(ObserverPaperQuoteError, match="candidate"):
        build_entry_paper_quote(_window(), wrong_candidate, 9, _asset())

    with pytest.raises(ObserverPaperQuoteError, match="quote asset"):
        build_entry_paper_quote(
            _window(),
            entry,
            9,
            _asset(mint="DifferentQuoteAsset"),
        )


def test_reconstruction_rejects_invalid_decimals_missing_reference_and_future_quote():
    for token_decimals in (-1, 256, True):
        with pytest.raises(ObserverPaperQuoteError, match="token_decimals"):
            build_entry_paper_quote(
                _window(), _entry_evidence(), token_decimals, _asset()
            )

    with pytest.raises(ObserverPaperQuoteError, match="reference"):
        build_entry_paper_quote(
            _window(price_usd=None), _entry_evidence(), 9, _asset()
        )

    future = replace(_entry_evidence(), quoted_at_unix_ms=1_000_001)
    with pytest.raises(ObserverPaperQuoteError, match="future"):
        build_entry_paper_quote(_window(), future, 9, _asset())


def test_reconstruction_fails_closed_on_zero_denominator_even_if_evidence_object_was_corrupted():
    evidence = _entry_evidence()
    object.__setattr__(evidence, "output_amount", 0)
    with pytest.raises(ObserverPaperQuoteError, match="quantity"):
        build_entry_paper_quote(_window(), evidence, 9, _asset())


def test_quote_asset_name_has_no_special_semantics():
    asset = _asset(mint="DefinitelyNotAStablecoin", usd_per_token=3.5)
    evidence = replace(
        _entry_evidence(),
        identity=replace(_entry_evidence().identity, input_mint=asset.mint),
    )
    quote = build_entry_paper_quote(_window(), evidence, 9, asset)
    assert math.isclose(quote.execution_price_usd, 7.0)
    assert math.isclose(quote.quoted_notional_usd, 7.0)
