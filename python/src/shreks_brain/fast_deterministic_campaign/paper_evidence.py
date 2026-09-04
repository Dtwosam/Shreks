from __future__ import annotations

from dataclasses import dataclass

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicLifecycleDecision,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignPaperEvidence:
    source_event_id: str
    state_version: str
    evaluated_at_unix_ms: int
    quote: FastCampaignPaperQuoteEvidence | None
    risk_context: RiskContext | None
    entry_authority: FastCampaignPaperEntryAuthority | None
    market_regime: MarketRegime | None

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("state_version", self.state_version)
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if self.quote is not None and type(self.quote) is not FastCampaignPaperQuoteEvidence:
            raise ValueError(
                "quote must be exact FastCampaignPaperQuoteEvidence or None"
            )
        if self.risk_context is not None and type(self.risk_context) is not RiskContext:
            raise ValueError(
                "risk_context must be exact RiskContext or None"
            )
        if (
            self.entry_authority is not None
            and type(self.entry_authority) is not FastCampaignPaperEntryAuthority
        ):
            raise ValueError(
                "entry_authority must be exact FastCampaignPaperEntryAuthority or None"
            )
        if (
            self.market_regime is not None
            and type(self.market_regime) is not MarketRegime
        ):
            raise ValueError(
                "market_regime must be exact MarketRegime or None"
            )


def materialize_fast_deterministic_campaign_paper_evidence(
    decision: FastDeterministicLifecycleDecision,
    evidence: FastDeterministicCampaignPaperEvidence,
) -> FastCampaignPaperDecisionEvidence:
    if type(decision) is not FastDeterministicLifecycleDecision:
        raise ValueError(
            "decision must be exact FastDeterministicLifecycleDecision"
        )
    if type(evidence) is not FastDeterministicCampaignPaperEvidence:
        raise ValueError(
            "evidence must be exact FastDeterministicCampaignPaperEvidence"
        )
    if evidence.source_event_id != decision.source_event_id:
        raise ValueError(
            "campaign PAPER evidence source identity does not match deterministic decision"
        )
    if evidence.evaluated_at_unix_ms < decision.as_of_unix_ms:
        raise ValueError(
            "campaign PAPER evidence evaluated clock cannot precede deterministic decision"
        )

    if decision.action == "SKIP":
        return _point(evidence)

    quote = evidence.quote
    if quote is None:
        raise ValueError(
            f"{decision.action} requires explicit campaign quote evidence"
        )

    if decision.action == "BUY":
        if evidence.risk_context is None:
            raise ValueError("BUY requires explicit RiskContext evidence")
        if evidence.entry_authority is None:
            raise ValueError("BUY requires explicit entry authority")
        if evidence.market_regime is None:
            raise ValueError("BUY requires point-in-time MarketRegime")
        return _point(
            evidence,
            quote=quote,
            risk_context=evidence.risk_context,
            entry_authority=evidence.entry_authority,
            market_regime=evidence.market_regime,
        )

    if decision.action in {"HOLD", "REDUCE", "SELL"}:
        return _point(
            evidence,
            quote=quote,
        )

    raise ValueError(
        f"unsupported deterministic campaign action '{decision.action}'"
    )


def _point(
    evidence: FastDeterministicCampaignPaperEvidence,
    *,
    quote: FastCampaignPaperQuoteEvidence | None = None,
    risk_context: RiskContext | None = None,
    entry_authority: FastCampaignPaperEntryAuthority | None = None,
    market_regime: MarketRegime | None = None,
) -> FastCampaignPaperDecisionEvidence:
    return FastCampaignPaperDecisionEvidence(
        source_event_id=evidence.source_event_id,
        state_version=evidence.state_version,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        quote=quote,
        risk_context=risk_context,
        entry_authority=entry_authority,
        market_regime=market_regime,
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
