from dataclasses import FrozenInstanceError, fields
import math

import pytest

from shreks_brain.risk import TradeSide
from shreks_brain.paper.models import (
    PaperExecutionContext,
    PaperExecutionFinding,
    PaperExecutionReasonCode,
    PaperExecutionResult,
    PaperExecutionState,
    PaperFill,
    PaperFillPolicy,
    PaperQuote,
    PaperQuoteState,
)


def _policy(**overrides):
    values = dict(
        version="paper-v1-test",
        assumed_latency_ms=250,
        max_quote_lag_ms=1_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.25,
    )
    values.update(overrides)
    return PaperFillPolicy(**values)


def _quote(**overrides):
    values = dict(
        provider="paper-quote-test",
        mint="Mint111",
        observed_at_unix_ms=1_000_500,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=1.0,
        execution_price_usd=1.01,
        quoted_notional_usd=1_000.0,
        available_notional_usd=750.0,
    )
    values.update(overrides)
    return PaperQuote(**values)


def _finding(code=PaperExecutionReasonCode.FILL_COMPLETE):
    return PaperExecutionFinding(code=code, message="paper execution finding")


def _buy_fill(**overrides):
    quantity = 500.0 / 1.01
    values = dict(
        intent_idempotency_key="intent-key",
        mint="Mint111",
        side=TradeSide.BUY,
        state=PaperExecutionState.FILLED,
        requested_notional_usd=500.0,
        filled_notional_usd=500.0,
        unfilled_notional_usd=0.0,
        quantity=quantity,
        reference_price_usd=1.0,
        execution_price_usd=1.01,
        signed_slippage_bps=100.0,
        signed_slippage_usd=quantity * 0.01,
        swap_fee_usd=1.5,
        network_fee_usd=0.01,
        explicit_cost_usd=1.51,
        net_cash_flow_usd=-501.51,
        quote_provider="paper-quote-test",
        executed_at_unix_ms=1_000_500,
    )
    values.update(overrides)
    return PaperFill(**values)


def _sell_partial(**overrides):
    quantity = 250.0 / 0.99
    values = dict(
        intent_idempotency_key="sell-key",
        mint="Mint111",
        side=TradeSide.SELL,
        state=PaperExecutionState.PARTIAL,
        requested_notional_usd=500.0,
        filled_notional_usd=250.0,
        unfilled_notional_usd=250.0,
        quantity=quantity,
        reference_price_usd=1.0,
        execution_price_usd=0.99,
        signed_slippage_bps=100.0,
        signed_slippage_usd=quantity * 0.01,
        swap_fee_usd=0.75,
        network_fee_usd=0.01,
        explicit_cost_usd=0.76,
        net_cash_flow_usd=249.24,
        quote_provider="paper-quote-test",
        executed_at_unix_ms=1_000_500,
    )
    values.update(overrides)
    return PaperFill(**values)


def _result(**overrides):
    fill = _buy_fill()
    values = dict(
        policy_version="paper-v1-test",
        intent_idempotency_key="intent-key",
        mint="Mint111",
        side=TradeSide.BUY,
        state=PaperExecutionState.FILLED,
        requested_notional_usd=500.0,
        evaluated_at_unix_ms=1_000_500,
        quote_observed_at_unix_ms=1_000_500,
        swap_fee_usd=fill.swap_fee_usd,
        network_fee_usd=fill.network_fee_usd,
        explicit_cost_usd=fill.explicit_cost_usd,
        net_cash_flow_usd=fill.net_cash_flow_usd,
        findings=(_finding(),),
        fill=fill,
    )
    values.update(overrides)
    return PaperExecutionResult(**values)


def test_public_enum_orders_are_stable():
    assert tuple(item.value for item in PaperQuoteState) == (
        "EXECUTABLE",
        "UNAVAILABLE",
        "FAILED_AFTER_SUBMISSION",
    )
    assert tuple(item.value for item in PaperExecutionState) == (
        "DEFERRED",
        "FAILED",
        "PARTIAL",
        "FILLED",
    )
    assert tuple(item.value for item in PaperExecutionReasonCode) == (
        "INTENT_MODE_NOT_PAPER",
        "DUPLICATE_INTENT",
        "EVALUATION_BEFORE_INTENT",
        "QUOTE_AFTER_EVALUATION",
        "QUOTE_MINT_MISMATCH",
        "LATENCY_PENDING",
        "QUOTE_PENDING",
        "QUOTE_BEFORE_LATENCY",
        "QUOTE_WINDOW_EXPIRED",
        "QUOTE_TOO_LATE",
        "ROUTE_UNAVAILABLE",
        "SIMULATED_SUBMISSION_FAILED",
        "REFERENCE_PRICE_UNKNOWN",
        "EXECUTION_PRICE_UNKNOWN",
        "QUOTED_NOTIONAL_UNKNOWN",
        "AVAILABLE_NOTIONAL_UNKNOWN",
        "NO_EXECUTABLE_NOTIONAL",
        "PARTIAL_FILL_DISABLED",
        "PARTIAL_FILL_TOO_SMALL",
        "SLIPPAGE_EXCEEDS_INTENT",
        "FILL_PARTIAL",
        "FILL_COMPLETE",
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"version": ""}, "version"),
        ({"assumed_latency_ms": -1}, "assumed_latency_ms"),
        ({"assumed_latency_ms": True}, "assumed_latency_ms"),
        ({"max_quote_lag_ms": -1}, "max_quote_lag_ms"),
        ({"swap_fee_bps": -1}, "swap_fee_bps"),
        ({"swap_fee_bps": 10_001}, "swap_fee_bps"),
        ({"network_fee_usd": -0.01}, "network_fee_usd"),
        ({"network_fee_usd": math.inf}, "network_fee_usd"),
        ({"allow_partial_fills": 1}, "allow_partial_fills"),
        ({"min_partial_fill_fraction": 0.0}, "min_partial_fill_fraction"),
        ({"min_partial_fill_fraction": 1.01}, "min_partial_fill_fraction"),
    ],
)
def test_policy_rejects_invalid_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        _policy(**overrides)


def test_policy_boundary_values_are_allowed():
    assert _policy(assumed_latency_ms=0, max_quote_lag_ms=0).assumed_latency_ms == 0
    assert _policy(swap_fee_bps=0).swap_fee_bps == 0
    assert _policy(swap_fee_bps=10_000).swap_fee_bps == 10_000
    assert _policy(network_fee_usd=0.0).network_fee_usd == 0.0
    assert _policy(min_partial_fill_fraction=1.0).min_partial_fill_fraction == 1.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"provider": ""}, "provider"),
        ({"mint": ""}, "mint"),
        ({"observed_at_unix_ms": -1}, "observed_at_unix_ms"),
        ({"state": "EXECUTABLE"}, "state"),
        ({"reference_price_usd": 0.0}, "reference_price_usd"),
        ({"execution_price_usd": -1.0}, "execution_price_usd"),
        ({"quoted_notional_usd": -1.0}, "quoted_notional_usd"),
        ({"available_notional_usd": math.inf}, "available_notional_usd"),
    ],
)
def test_quote_rejects_invalid_present_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        _quote(**overrides)


def test_quote_allows_missing_economics_for_non_executable_evidence():
    quote = _quote(
        state=PaperQuoteState.UNAVAILABLE,
        reference_price_usd=None,
        execution_price_usd=None,
        quoted_notional_usd=None,
        available_notional_usd=None,
    )
    assert quote.reference_price_usd is None


def test_execution_context_validates_processed_keys_and_quote():
    context = PaperExecutionContext(
        evaluated_at_unix_ms=1_000_500,
        processed_intent_keys=frozenset({"intent-key"}),
        quote=_quote(),
    )
    assert context.quote == _quote()
    with pytest.raises(ValueError, match="evaluated_at_unix_ms"):
        PaperExecutionContext(-1, frozenset(), None)
    with pytest.raises(ValueError, match="processed_intent_keys"):
        PaperExecutionContext(0, set(), None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="processed_intent_keys"):
        PaperExecutionContext(0, frozenset({""}), None)
    with pytest.raises(ValueError, match="quote"):
        PaperExecutionContext(0, frozenset(), "bad")  # type: ignore[arg-type]


def test_models_are_frozen():
    with pytest.raises(FrozenInstanceError):
        _policy().version = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        _quote().provider = "changed"  # type: ignore[misc]


def test_finding_requires_enum_and_message():
    assert _finding().code is PaperExecutionReasonCode.FILL_COMPLETE
    with pytest.raises(ValueError, match="code"):
        PaperExecutionFinding("FILL_COMPLETE", "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="message"):
        PaperExecutionFinding(PaperExecutionReasonCode.FILL_COMPLETE, "")


def test_buy_fill_enforces_arithmetic_and_cash_flow():
    fill = _buy_fill()
    assert math.isclose(fill.quantity, fill.filled_notional_usd / fill.execution_price_usd)
    assert math.isclose(fill.explicit_cost_usd, fill.swap_fee_usd + fill.network_fee_usd)
    assert math.isclose(fill.net_cash_flow_usd, -(fill.filled_notional_usd + fill.explicit_cost_usd))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"state": PaperExecutionState.DEFERRED}, "state"),
        ({"filled_notional_usd": 0.0}, "filled_notional_usd"),
        ({"unfilled_notional_usd": 1.0}, "FILLED"),
        ({"quantity": 1.0}, "quantity"),
        ({"explicit_cost_usd": 9.0}, "explicit_cost_usd"),
        ({"net_cash_flow_usd": -500.0}, "net_cash_flow_usd"),
    ],
)
def test_fill_rejects_inconsistent_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        _buy_fill(**overrides)


def test_sell_partial_fill_enforces_arithmetic_and_cash_flow():
    fill = _sell_partial()
    assert fill.state is PaperExecutionState.PARTIAL
    assert fill.unfilled_notional_usd == 250.0
    assert math.isclose(fill.net_cash_flow_usd, fill.filled_notional_usd - fill.explicit_cost_usd)


def test_signed_slippage_fields_may_be_favorable():
    fill = _buy_fill(signed_slippage_bps=-50.0, signed_slippage_usd=-2.0)
    assert fill.signed_slippage_bps < 0.0


def test_deferred_result_has_zero_economics_and_no_fill():
    result = _result(
        state=PaperExecutionState.DEFERRED,
        quote_observed_at_unix_ms=None,
        swap_fee_usd=0.0,
        network_fee_usd=0.0,
        explicit_cost_usd=0.0,
        net_cash_flow_usd=0.0,
        findings=(_finding(PaperExecutionReasonCode.QUOTE_PENDING),),
        fill=None,
    )
    assert result.fill is None


def test_failed_after_submission_result_can_charge_network_fee_without_fill():
    result = _result(
        state=PaperExecutionState.FAILED,
        swap_fee_usd=0.0,
        network_fee_usd=0.01,
        explicit_cost_usd=0.01,
        net_cash_flow_usd=-0.01,
        findings=(_finding(PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED),),
        fill=None,
    )
    assert result.network_fee_usd == 0.01


def test_partial_result_must_match_fill_economics():
    fill = _sell_partial()
    result = _result(
        intent_idempotency_key=fill.intent_idempotency_key,
        side=TradeSide.SELL,
        state=PaperExecutionState.PARTIAL,
        swap_fee_usd=fill.swap_fee_usd,
        network_fee_usd=fill.network_fee_usd,
        explicit_cost_usd=fill.explicit_cost_usd,
        net_cash_flow_usd=fill.net_cash_flow_usd,
        findings=(_finding(PaperExecutionReasonCode.FILL_PARTIAL),),
        fill=fill,
    )
    assert result.fill == fill


def test_result_rejects_state_economic_mismatches():
    with pytest.raises(ValueError):
        _result(state=PaperExecutionState.DEFERRED)
    with pytest.raises(ValueError):
        _result(explicit_cost_usd=9.0)
    with pytest.raises(ValueError):
        _result(findings=())


def test_public_models_do_not_own_position_or_live_execution_state():
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
    }
    for model in (
        PaperFillPolicy,
        PaperQuote,
        PaperExecutionContext,
        PaperExecutionFinding,
        PaperFill,
        PaperExecutionResult,
    ):
        assert forbidden.isdisjoint(field.name for field in fields(model))
