from dataclasses import fields

from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionFinding,
    PaperExecutionReasonCode,
    PaperExecutionResult,
    PaperExecutionState,
    PaperFill,
    PaperFillPolicy,
    PaperQuote,
    PaperQuoteState,
    execute_paper_intent,
)
from shreks_brain.decision import TradeDecision
from shreks_brain.features import FeatureVector
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScoreAssessment
from shreks_brain.setups import SetupState


def _intent():
    return TradeIntent(
        mint="Mint111",
        side=TradeSide.BUY,
        requested_notional_usd=500.0,
        max_slippage_bps=300,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-test",
        score_policy_version="score-v1-test",
        decision_policy_version="decision-v1-test",
        risk_policy_version="risk-v1-test",
        reason="ENTRY_APPROVED",
        idempotency_key="intent-key",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=1_000_000,
    )


def _policy():
    return PaperFillPolicy(
        version="paper-v1-test",
        assumed_latency_ms=250,
        max_quote_lag_ms=1_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.25,
    )


def _context():
    return PaperExecutionContext(
        evaluated_at_unix_ms=1_000_500,
        processed_intent_keys=frozenset(),
        quote=PaperQuote(
            provider="paper-quote-test",
            mint="Mint111",
            observed_at_unix_ms=1_000_500,
            state=PaperQuoteState.EXECUTABLE,
            reference_price_usd=1.0,
            execution_price_usd=1.01,
            quoted_notional_usd=1_000.0,
            available_notional_usd=750.0,
        ),
    )


def test_paper_package_exports_stable_api_and_executes_canonical_intent():
    assert callable(execute_paper_intent)
    result = execute_paper_intent(_intent(), _context(), _policy())
    assert isinstance(result, PaperExecutionResult)
    assert result.state is PaperExecutionState.FILLED
    assert isinstance(result.fill, PaperFill)
    assert isinstance(result.findings[0], PaperExecutionFinding)
    assert result.findings[0].code is PaperExecutionReasonCode.FILL_COMPLETE


def test_previous_brain_layer_imports_remain_available():
    for symbol in (
        RuntimeMode,
        SafetyDecision,
        FeatureVector,
        SetupState,
        MarketRegime,
        ScoreAssessment,
        TradeDecision,
        TradeIntent,
    ):
        assert symbol is not None


def test_public_paper_models_do_not_expose_position_live_or_secret_authority():
    forbidden = {
        "private_key",
        "secret",
        "wallet_secret",
        "transaction",
        "signature",
        "realized_pnl",
        "unrealized_pnl",
        "average_entry",
        "position",
        "balance",
        "live_executor",
    }
    assert forbidden.isdisjoint(field.name for field in fields(PaperFill))
    assert forbidden.isdisjoint(field.name for field in fields(PaperExecutionResult))
