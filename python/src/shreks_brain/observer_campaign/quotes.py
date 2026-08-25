from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math

from shreks_brain.observer_market.models import ObservedMarketWindow
from shreks_brain.paper import PaperQuote, PaperQuoteState

from .models import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteEvidence,
    ObserverPaperQuotePurpose,
)


class ObserverPaperQuoteError(ValueError):
    """Raised when persisted quote evidence cannot be converted without guessing."""


def build_entry_paper_quote(
    window: ObservedMarketWindow,
    evidence: ObserverPaperQuoteEvidence,
    token_decimals: int,
    quote_asset: ObserverPaperQuoteAsset,
) -> PaperQuote:
    _validate_common(window, evidence, token_decimals, quote_asset)
    identity = evidence.identity
    if identity.purpose is not ObserverPaperQuotePurpose.ENTRY:
        raise ObserverPaperQuoteError("entry quote evidence must have ENTRY purpose")
    if identity.input_mint != quote_asset.mint:
        raise ObserverPaperQuoteError("entry quote input mint does not match quote asset")
    if identity.output_mint != window.candidate.mint:
        raise ObserverPaperQuoteError("entry quote output mint does not match candidate mint")

    if not evidence.route_available:
        return _unavailable_quote(window, evidence)

    reference_price = _reference_price(window)
    quote_input_usd = _raw_to_value(
        identity.input_amount,
        quote_asset.decimals,
        quote_asset.usd_per_token,
        "entry quote input",
    )
    token_quantity = _raw_quantity(
        evidence.output_amount,
        token_decimals,
        "entry quoted token quantity",
    )
    if token_quantity <= 0:
        raise ObserverPaperQuoteError("entry quoted token quantity must be positive")
    execution_price = quote_input_usd / token_quantity
    _require_positive_finite("entry execution price", execution_price)

    return PaperQuote(
        provider=identity.provider,
        mint=window.candidate.mint,
        observed_at_unix_ms=evidence.quoted_at_unix_ms,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=reference_price,
        execution_price_usd=execution_price,
        quoted_notional_usd=quote_input_usd,
        available_notional_usd=quote_input_usd,
    )


def build_exit_paper_quote(
    window: ObservedMarketWindow,
    evidence: ObserverPaperQuoteEvidence,
    token_decimals: int,
    quote_asset: ObserverPaperQuoteAsset,
) -> PaperQuote:
    _validate_common(window, evidence, token_decimals, quote_asset)
    identity = evidence.identity
    if identity.purpose is not ObserverPaperQuotePurpose.EXIT:
        raise ObserverPaperQuoteError("exit quote evidence must have EXIT purpose")
    if identity.input_mint != window.candidate.mint:
        raise ObserverPaperQuoteError("exit quote input mint does not match candidate mint")
    if identity.output_mint != quote_asset.mint:
        raise ObserverPaperQuoteError("exit quote output mint does not match quote asset")

    if not evidence.route_available:
        return _unavailable_quote(window, evidence)

    reference_price = _reference_price(window)
    token_quantity = _raw_quantity(
        identity.input_amount,
        token_decimals,
        "exit input token quantity",
    )
    if token_quantity <= 0:
        raise ObserverPaperQuoteError("exit input token quantity must be positive")
    quote_output_usd = _raw_to_value(
        evidence.output_amount,
        quote_asset.decimals,
        quote_asset.usd_per_token,
        "exit quote output",
    )
    execution_price = quote_output_usd / token_quantity
    quoted_notional = token_quantity * reference_price
    _require_positive_finite("exit execution price", execution_price)
    _require_positive_finite("exit quoted notional", quoted_notional)

    return PaperQuote(
        provider=identity.provider,
        mint=window.candidate.mint,
        observed_at_unix_ms=evidence.quoted_at_unix_ms,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=reference_price,
        execution_price_usd=execution_price,
        quoted_notional_usd=quoted_notional,
        available_notional_usd=quoted_notional,
    )


def _validate_common(
    window: ObservedMarketWindow,
    evidence: ObserverPaperQuoteEvidence,
    token_decimals: int,
    quote_asset: ObserverPaperQuoteAsset,
) -> None:
    if type(window) is not ObservedMarketWindow:
        raise ObserverPaperQuoteError("window must be an ObservedMarketWindow")
    if type(evidence) is not ObserverPaperQuoteEvidence:
        raise ObserverPaperQuoteError("evidence must be an ObserverPaperQuoteEvidence")
    if type(quote_asset) is not ObserverPaperQuoteAsset:
        raise ObserverPaperQuoteError("quote_asset must be an ObserverPaperQuoteAsset")
    if isinstance(token_decimals, bool) or not isinstance(token_decimals, int) or not 0 <= token_decimals <= 255:
        raise ObserverPaperQuoteError("token_decimals must be an integer within [0, 255]")
    if evidence.identity.candidate_id != window.candidate.candidate_id:
        raise ObserverPaperQuoteError("quote candidate attribution does not match market window")
    if evidence.quoted_at_unix_ms > window.as_of_unix_ms:
        raise ObserverPaperQuoteError("quote evidence cannot be from the future")


def _reference_price(window: ObservedMarketWindow) -> float:
    value = window.current.price_usd
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObserverPaperQuoteError("reference token price is unavailable")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ObserverPaperQuoteError("reference token price must be positive and finite")
    return parsed


def _unavailable_quote(
    window: ObservedMarketWindow,
    evidence: ObserverPaperQuoteEvidence,
) -> PaperQuote:
    return PaperQuote(
        provider=evidence.identity.provider,
        mint=window.candidate.mint,
        observed_at_unix_ms=evidence.quoted_at_unix_ms,
        state=PaperQuoteState.UNAVAILABLE,
        reference_price_usd=None,
        execution_price_usd=None,
        quoted_notional_usd=None,
        available_notional_usd=None,
    )


def _raw_quantity(raw_amount: int, decimals: int, name: str) -> float:
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, int) or raw_amount < 0:
        raise ObserverPaperQuoteError(f"{name} raw amount is invalid")
    try:
        value = Decimal(raw_amount) / (Decimal(10) ** decimals)
        converted = float(value)
    except (InvalidOperation, OverflowError, ValueError) as error:
        raise ObserverPaperQuoteError(f"{name} cannot be converted safely") from error
    if not math.isfinite(converted) or converted < 0:
        raise ObserverPaperQuoteError(f"{name} must be finite and non-negative")
    return converted


def _raw_to_value(
    raw_amount: int,
    decimals: int,
    usd_per_token: float,
    name: str,
) -> float:
    quantity = _raw_quantity(raw_amount, decimals, name)
    value = quantity * usd_per_token
    _require_positive_finite(name, value)
    return value


def _require_positive_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ObserverPaperQuoteError(f"{name} must be positive and finite")
