from __future__ import annotations

from shreks_brain.observer_market import (
    ObservedMarketWindow,
    ObserverMarketStore,
    ObserverQuoteAssetUsdEvidence,
)

from .models import ObserverPaperQuoteAsset


OBSERVER_PAPER_QUOTE_USD_VALUATION_MODE_EXACT_MARKET_RATIO = (
    "exact_market_ratio"
)
OBSERVER_PAPER_QUOTE_USD_VALUATION_MODE_MANIFEST_FIXED = "manifest_fixed"


class ObserverPaperQuoteUsdValuationError(ValueError):
    """Raised when quote-USD valuation authority cannot be applied safely."""


def validate_observer_paper_quote_usd_valuation_mode(
    mode: str | None,
) -> str | None:
    if mode is None:
        return None
    if mode != OBSERVER_PAPER_QUOTE_USD_VALUATION_MODE_EXACT_MARKET_RATIO:
        raise ObserverPaperQuoteUsdValuationError(
            "unsupported observer PAPER quote USD valuation mode"
        )
    return mode


def resolve_observer_paper_quote_usd_evidence(
    store: ObserverMarketStore,
    window: ObservedMarketWindow,
    quote_asset: ObserverPaperQuoteAsset,
    *,
    mode: str,
    max_age_ms: int,
) -> ObserverQuoteAssetUsdEvidence:
    if type(store) is not ObserverMarketStore:
        raise ObserverPaperQuoteUsdValuationError(
            "store must be an exact ObserverMarketStore"
        )
    if type(window) is not ObservedMarketWindow:
        raise ObserverPaperQuoteUsdValuationError(
            "window must be an exact ObservedMarketWindow"
        )
    if type(quote_asset) is not ObserverPaperQuoteAsset:
        raise ObserverPaperQuoteUsdValuationError(
            "quote_asset must be an exact ObserverPaperQuoteAsset"
        )
    validate_observer_paper_quote_usd_valuation_mode(mode)
    if isinstance(max_age_ms, bool) or not isinstance(max_age_ms, int) or max_age_ms < 0:
        raise ObserverPaperQuoteUsdValuationError(
            "max_age_ms must be a non-negative integer"
        )

    current = window.current
    try:
        evidence = store.quote_asset_usd_evidence(
            window.candidate.candidate_id,
            window.as_of_unix_ms,
            source=current.source,
            venue=current.venue,
            base_mint=window.candidate.mint,
            quote_mint=quote_asset.mint,
            max_age_ms=max_age_ms,
            expected_market_row_id=current.row_id,
        )
    except ValueError as error:
        raise ObserverPaperQuoteUsdValuationError(
            f"quote USD valuation evidence failed: {error}"
        ) from error

    if evidence.market_row_id != current.row_id:
        raise ObserverPaperQuoteUsdValuationError(
            "quote USD valuation evidence changed market row identity"
        )
    if evidence.candidate_id != window.candidate.candidate_id:
        raise ObserverPaperQuoteUsdValuationError(
            "quote USD valuation evidence changed candidate identity"
        )
    if evidence.base_mint != window.candidate.mint:
        raise ObserverPaperQuoteUsdValuationError(
            "quote USD valuation evidence changed base mint"
        )
    if evidence.quote_mint != quote_asset.mint:
        raise ObserverPaperQuoteUsdValuationError(
            "quote USD valuation evidence changed quote mint"
        )
    return evidence
