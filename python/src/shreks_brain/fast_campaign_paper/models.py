from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.evaluation import TradingEvaluationEvidence
from shreks_brain.fast_paper import (
    FastPaperBuyResult,
    FastPaperLoopState,
    FastPaperPositionActionResult,
)
from shreks_brain.fast_policy_proof import FastPolicyRunEvidence
from shreks_brain.paper import PaperLedger, PaperQuoteState
from shreks_brain.paper_evaluation import PaperEvaluationCapture
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext


FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION = "fl9-campaign-paper-v1"


@dataclass(frozen=True, slots=True)
class FastCampaignPaperCandidateIdentity:
    version: str
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_family: str
    strategy_version: str
    assessment_version: str

    def __post_init__(self) -> None:
        if self.version != FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION:
            raise ValueError("unsupported Fast campaign PAPER executor version")
        for name in (
            "paper_run_id",
            "candidate_version",
            "strategy_family",
            "strategy_version",
            "assessment_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_sha256(
            "candidate_fingerprint_sha256", self.candidate_fingerprint_sha256
        )


@dataclass(frozen=True, slots=True)
class FastCampaignPaperEntryAuthority:
    mint: str
    quote_mint: str
    intended_base_quantity: float
    decision_executable_entry_price_quote: float
    maximum_acceptable_entry_price_quote: float
    expected_entry_variable_cost_bps: int
    expected_entry_fixed_cost_quote: float

    def __post_init__(self) -> None:
        _require_non_empty_string("mint", self.mint)
        _require_non_empty_string("quote_mint", self.quote_mint)
        _require_positive_finite(
            "intended_base_quantity", self.intended_base_quantity
        )
        _require_positive_finite(
            "decision_executable_entry_price_quote",
            self.decision_executable_entry_price_quote,
        )
        _require_positive_finite(
            "maximum_acceptable_entry_price_quote",
            self.maximum_acceptable_entry_price_quote,
        )
        if (
            self.decision_executable_entry_price_quote
            > self.maximum_acceptable_entry_price_quote
        ):
            raise ValueError(
                "decision executable entry price cannot exceed maximum acceptable entry price"
            )
        if (
            isinstance(self.expected_entry_variable_cost_bps, bool)
            or not isinstance(self.expected_entry_variable_cost_bps, int)
            or not 0 <= self.expected_entry_variable_cost_bps <= 40_000
        ):
            raise ValueError(
                "expected_entry_variable_cost_bps must be within [0, 40000]"
            )
        _require_non_negative_finite(
            "expected_entry_fixed_cost_quote",
            self.expected_entry_fixed_cost_quote,
        )


@dataclass(frozen=True, slots=True)
class FastCampaignPaperQuoteEvidence:
    provider: str
    mint: str
    quote_mint: str
    observed_at_unix_ms: int
    state: PaperQuoteState
    reference_price_quote: float | None
    execution_price_quote: float | None
    quoted_base_quantity: float | None
    available_base_quantity: float | None
    quote_to_usd_rate: float

    def __post_init__(self) -> None:
        for name in ("provider", "mint", "quote_mint"):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if type(self.state) is not PaperQuoteState:
            raise ValueError("state must be an exact PaperQuoteState")
        for name in (
            "reference_price_quote",
            "execution_price_quote",
            "quoted_base_quantity",
            "available_base_quantity",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_positive_finite(name, value)
        _require_positive_finite("quote_to_usd_rate", self.quote_to_usd_rate)

        if self.state in (
            PaperQuoteState.EXECUTABLE,
            PaperQuoteState.FAILED_AFTER_SUBMISSION,
        ):
            if any(
                getattr(self, name) is None
                for name in (
                    "reference_price_quote",
                    "execution_price_quote",
                    "quoted_base_quantity",
                    "available_base_quantity",
                )
            ):
                raise ValueError(
                    "executable/submitted campaign quote requires complete price and capacity evidence"
                )


@dataclass(frozen=True, slots=True)
class FastCampaignPaperDecisionEvidence:
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
            "evaluated_at_unix_ms", self.evaluated_at_unix_ms
        )
        if self.quote is not None and type(self.quote) is not FastCampaignPaperQuoteEvidence:
            raise ValueError(
                "quote must be exact FastCampaignPaperQuoteEvidence or None"
            )
        if self.risk_context is not None and type(self.risk_context) is not RiskContext:
            raise ValueError("risk_context must be exact RiskContext or None")
        if (
            self.entry_authority is not None
            and type(self.entry_authority) is not FastCampaignPaperEntryAuthority
        ):
            raise ValueError(
                "entry_authority must be exact FastCampaignPaperEntryAuthority or None"
            )
        if self.market_regime is not None and type(self.market_regime) is not MarketRegime:
            raise ValueError("market_regime must be exact MarketRegime or None")


@dataclass(frozen=True, slots=True)
class FastCampaignPaperRunResult:
    version: str
    identity: FastCampaignPaperCandidateIdentity
    event_loop_state: FastPaperLoopState
    final_ledger: PaperLedger
    buy_results: tuple[FastPaperBuyResult, ...]
    position_results: tuple[FastPaperPositionActionResult, ...]
    evaluation_capture: PaperEvaluationCapture
    trading_evaluation: TradingEvaluationEvidence
    run_evidence: FastPolicyRunEvidence

    def __post_init__(self) -> None:
        if self.version != FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION:
            raise ValueError("unsupported Fast campaign PAPER result version")
        if type(self.identity) is not FastCampaignPaperCandidateIdentity:
            raise ValueError(
                "identity must be exact FastCampaignPaperCandidateIdentity"
            )
        if type(self.event_loop_state) is not FastPaperLoopState:
            raise ValueError("event_loop_state must be exact FastPaperLoopState")
        if type(self.final_ledger) is not PaperLedger:
            raise ValueError("final_ledger must be exact PaperLedger")
        _require_exact_tuple("buy_results", self.buy_results, FastPaperBuyResult)
        _require_exact_tuple(
            "position_results",
            self.position_results,
            FastPaperPositionActionResult,
        )
        if type(self.evaluation_capture) is not PaperEvaluationCapture:
            raise ValueError(
                "evaluation_capture must be exact PaperEvaluationCapture"
            )
        if type(self.trading_evaluation) is not TradingEvaluationEvidence:
            raise ValueError(
                "trading_evaluation must be exact TradingEvaluationEvidence"
            )
        if type(self.run_evidence) is not FastPolicyRunEvidence:
            raise ValueError("run_evidence must be exact FastPolicyRunEvidence")
        if self.trading_evaluation.candidate_version != self.identity.candidate_version:
            raise ValueError("trading evaluation candidate identity mismatch")
        if self.run_evidence.candidate_version != self.identity.candidate_version:
            raise ValueError("run evidence candidate identity mismatch")
        if (
            self.run_evidence.candidate_fingerprint_sha256
            != self.identity.candidate_fingerprint_sha256
        ):
            raise ValueError("run evidence candidate fingerprint mismatch")


def _require_exact_tuple(name: str, value: object, expected_type: type) -> None:
    if not isinstance(value, tuple) or not all(
        type(item) is expected_type for item in value
    ):
        raise ValueError(
            f"{name} must be a tuple of exact {expected_type.__name__} values"
        )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be finite and strictly positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
