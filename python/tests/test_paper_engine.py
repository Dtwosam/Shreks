from dataclasses import replace
import math

import pytest

from shreks_brain.paper.engine import execute_paper_intent
from shreks_brain.paper.models import (
    PaperExecutionContext,
    PaperExecutionReasonCode,
    PaperExecutionState,
    PaperFillPolicy,
    PaperQuote,
    PaperQuoteState,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


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


def _intent(**overrides):
    values = dict(
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
    values.update(overrides)
    return TradeIntent(**values)


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


def _context(**overrides):
    values = dict(
        evaluated_at_unix_ms=1_000_500,
        processed_intent_keys=frozenset(),
        quote=_quote(),
    )
    values.update(overrides)
    return PaperExecutionContext(**values)


def _reason(result):
    assert len(result.findings) == 1
    return result.findings[0].code


def _assert_zero_failure(result, code):
    assert result.state is PaperExecutionState.FAILED
    assert _reason(result) is code
    assert result.swap_fee_usd == 0.0
    assert result.network_fee_usd == 0.0
    assert result.explicit_cost_usd == 0.0
    assert result.net_cash_flow_usd == 0.0
    assert result.fill is None


def test_canonical_buy_intent_fills_with_explicit_costs():
    result = execute_paper_intent(_intent(), _context(), _policy())

    assert result.state is PaperExecutionState.FILLED
    assert _reason(result) is PaperExecutionReasonCode.FILL_COMPLETE
    fill = result.fill
    assert fill is not None
    assert fill.filled_notional_usd == 500.0
    assert fill.unfilled_notional_usd == 0.0
    assert math.isclose(fill.quantity, 500.0 / 1.01)
    assert math.isclose(fill.signed_slippage_bps, 100.0)
    assert math.isclose(fill.swap_fee_usd, 1.5)
    assert math.isclose(fill.network_fee_usd, 0.01)
    assert math.isclose(fill.explicit_cost_usd, 1.51)
    assert math.isclose(fill.net_cash_flow_usd, -501.51)


@pytest.mark.parametrize(
    ("intent", "context", "code"),
    [
        (
            _intent(execution_mode=RuntimeMode.SHADOW),
            _context(),
            PaperExecutionReasonCode.INTENT_MODE_NOT_PAPER,
        ),
        (
            _intent(),
            _context(processed_intent_keys=frozenset({"intent-key"})),
            PaperExecutionReasonCode.DUPLICATE_INTENT,
        ),
        (
            _intent(),
            _context(evaluated_at_unix_ms=999_999, quote=None),
            PaperExecutionReasonCode.EVALUATION_BEFORE_INTENT,
        ),
        (
            _intent(),
            _context(
                evaluated_at_unix_ms=1_000_100,
                quote=_quote(
                    mint="WrongMint",
                    observed_at_unix_ms=1_000_101,
                ),
            ),
            PaperExecutionReasonCode.QUOTE_AFTER_EVALUATION,
        ),
        (
            _intent(),
            _context(quote=_quote(mint="WrongMint")),
            PaperExecutionReasonCode.QUOTE_MINT_MISMATCH,
        ),
    ],
)
def test_mode_duplicate_and_contradiction_precedence(intent, context, code):
    _assert_zero_failure(execute_paper_intent(intent, context, _policy()), code)


def test_future_quote_precedes_wrong_mint():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_000_100,
            quote=_quote(mint="WrongMint", observed_at_unix_ms=1_000_101),
        ),
        _policy(),
    )
    assert _reason(result) is PaperExecutionReasonCode.QUOTE_AFTER_EVALUATION


def test_latency_pending_before_eligible_time():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_000_100,
            quote=_quote(observed_at_unix_ms=1_000_100),
        ),
        _policy(),
    )
    assert result.state is PaperExecutionState.DEFERRED
    assert _reason(result) is PaperExecutionReasonCode.LATENCY_PENDING
    assert result.fill is None


@pytest.mark.parametrize("evaluated_at", [1_000_250, 1_001_250])
def test_missing_quote_is_pending_at_eligible_and_deadline_boundaries(evaluated_at):
    result = execute_paper_intent(
        _intent(),
        _context(evaluated_at_unix_ms=evaluated_at, quote=None),
        _policy(),
    )
    assert result.state is PaperExecutionState.DEFERRED
    assert _reason(result) is PaperExecutionReasonCode.QUOTE_PENDING


def test_missing_quote_after_deadline_expires():
    result = execute_paper_intent(
        _intent(),
        _context(evaluated_at_unix_ms=1_001_251, quote=None),
        _policy(),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.QUOTE_WINDOW_EXPIRED)


def test_quote_before_latency_is_deferred_while_window_open():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_000_500,
            quote=_quote(observed_at_unix_ms=1_000_200),
        ),
        _policy(),
    )
    assert result.state is PaperExecutionState.DEFERRED
    assert _reason(result) is PaperExecutionReasonCode.QUOTE_BEFORE_LATENCY


def test_quote_before_latency_expires_after_deadline():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_001_251,
            quote=_quote(observed_at_unix_ms=1_000_200),
        ),
        _policy(),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.QUOTE_WINDOW_EXPIRED)


def test_quote_after_deadline_is_too_late():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_001_300,
            quote=_quote(observed_at_unix_ms=1_001_251),
        ),
        _policy(),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.QUOTE_TOO_LATE)


def test_quote_exactly_at_deadline_is_valid():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_001_250,
            quote=_quote(observed_at_unix_ms=1_001_250),
        ),
        _policy(),
    )
    assert result.state is PaperExecutionState.FILLED


def test_zero_latency_and_zero_quote_lag_allow_same_timestamp_quote():
    result = execute_paper_intent(
        _intent(),
        _context(
            evaluated_at_unix_ms=1_000_000,
            quote=_quote(observed_at_unix_ms=1_000_000),
        ),
        _policy(assumed_latency_ms=0, max_quote_lag_ms=0),
    )
    assert result.state is PaperExecutionState.FILLED


def test_unavailable_route_fails_without_cost():
    result = execute_paper_intent(
        _intent(),
        _context(
            quote=_quote(
                state=PaperQuoteState.UNAVAILABLE,
                reference_price_usd=None,
                execution_price_usd=None,
                quoted_notional_usd=None,
                available_notional_usd=None,
            )
        ),
        _policy(),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.ROUTE_UNAVAILABLE)


def test_failed_after_submission_charges_network_fee_without_fill():
    result = execute_paper_intent(
        _intent(),
        _context(
            quote=_quote(
                state=PaperQuoteState.FAILED_AFTER_SUBMISSION,
                reference_price_usd=None,
                execution_price_usd=None,
                quoted_notional_usd=None,
                available_notional_usd=None,
            )
        ),
        _policy(network_fee_usd=0.02),
    )
    assert result.state is PaperExecutionState.FAILED
    assert _reason(result) is PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED
    assert result.fill is None
    assert result.swap_fee_usd == 0.0
    assert result.network_fee_usd == 0.02
    assert result.explicit_cost_usd == 0.02
    assert result.net_cash_flow_usd == -0.02


@pytest.mark.parametrize(
    ("quote", "code"),
    [
        (_quote(reference_price_usd=None), PaperExecutionReasonCode.REFERENCE_PRICE_UNKNOWN),
        (_quote(execution_price_usd=None), PaperExecutionReasonCode.EXECUTION_PRICE_UNKNOWN),
        (_quote(quoted_notional_usd=None), PaperExecutionReasonCode.QUOTED_NOTIONAL_UNKNOWN),
        (_quote(available_notional_usd=None), PaperExecutionReasonCode.AVAILABLE_NOTIONAL_UNKNOWN),
    ],
)
def test_executable_quote_requires_economics_in_fixed_order(quote, code):
    _assert_zero_failure(
        execute_paper_intent(_intent(), _context(quote=quote), _policy()),
        code,
    )


def test_no_executable_notional_fails():
    result = execute_paper_intent(
        _intent(),
        _context(quote=_quote(quoted_notional_usd=0.0)),
        _policy(),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.NO_EXECUTABLE_NOTIONAL)


def test_partial_fill_disabled_rejects_capacity_shortfall():
    result = execute_paper_intent(
        _intent(),
        _context(quote=_quote(quoted_notional_usd=300.0, available_notional_usd=400.0)),
        _policy(allow_partial_fills=False),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.PARTIAL_FILL_DISABLED)


def test_partial_fill_below_minimum_fraction_rejects():
    result = execute_paper_intent(
        _intent(),
        _context(quote=_quote(quoted_notional_usd=100.0, available_notional_usd=100.0)),
        _policy(min_partial_fill_fraction=0.25),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.PARTIAL_FILL_TOO_SMALL)


def test_partial_fill_at_minimum_fraction_passes():
    result = execute_paper_intent(
        _intent(),
        _context(quote=_quote(quoted_notional_usd=125.0, available_notional_usd=125.0)),
        _policy(min_partial_fill_fraction=0.25),
    )
    assert result.state is PaperExecutionState.PARTIAL
    assert result.fill is not None
    assert result.fill.filled_notional_usd == 125.0


@pytest.mark.parametrize(
    ("quoted", "available", "expected"),
    [(300.0, 400.0, 300.0), (800.0, 250.0, 250.0), (900.0, 900.0, 500.0)],
)
def test_fill_never_exceeds_requested_quote_or_available_capacity(quoted, available, expected):
    result = execute_paper_intent(
        _intent(),
        _context(quote=_quote(quoted_notional_usd=quoted, available_notional_usd=available)),
        _policy(),
    )
    assert result.fill is not None
    assert result.fill.filled_notional_usd == expected
    assert result.fill.filled_notional_usd <= quoted
    assert result.fill.filled_notional_usd <= available
    assert result.fill.filled_notional_usd <= 500.0


@pytest.mark.parametrize(
    ("side", "execution_price", "expected_bps"),
    [
        (TradeSide.BUY, 1.01, 100.0),
        (TradeSide.BUY, 0.99, -100.0),
        (TradeSide.SELL, 0.99, 100.0),
        (TradeSide.SELL, 1.01, -100.0),
    ],
)
def test_slippage_is_side_aware_and_favorable_values_are_negative(side, execution_price, expected_bps):
    result = execute_paper_intent(
        _intent(side=side),
        _context(quote=_quote(execution_price_usd=execution_price)),
        _policy(),
    )
    assert result.fill is not None
    assert math.isclose(result.fill.signed_slippage_bps, expected_bps, abs_tol=1e-9)


@pytest.mark.parametrize(
    ("side", "execution_price"),
    [(TradeSide.BUY, 1.03), (TradeSide.SELL, 0.97)],
)
def test_slippage_equality_with_intent_limit_passes(side, execution_price):
    result = execute_paper_intent(
        _intent(side=side, max_slippage_bps=300),
        _context(quote=_quote(execution_price_usd=execution_price)),
        _policy(),
    )
    assert result.state is PaperExecutionState.FILLED


@pytest.mark.parametrize(
    ("side", "execution_price"),
    [(TradeSide.BUY, 1.031), (TradeSide.SELL, 0.969)],
)
def test_slippage_strictly_above_intent_limit_fails(side, execution_price):
    result = execute_paper_intent(
        _intent(side=side, max_slippage_bps=300),
        _context(quote=_quote(execution_price_usd=execution_price)),
        _policy(),
    )
    _assert_zero_failure(result, PaperExecutionReasonCode.SLIPPAGE_EXCEEDS_INTENT)


def test_buy_partial_cost_and_cash_flow_do_not_double_count_slippage():
    result = execute_paper_intent(
        _intent(),
        _context(quote=_quote(quoted_notional_usd=300.0, available_notional_usd=400.0)),
        _policy(),
    )
    fill = result.fill
    assert fill is not None
    assert result.state is PaperExecutionState.PARTIAL
    assert _reason(result) is PaperExecutionReasonCode.FILL_PARTIAL
    assert math.isclose(fill.swap_fee_usd, 0.9)
    assert math.isclose(fill.explicit_cost_usd, 0.91)
    assert math.isclose(fill.net_cash_flow_usd, -300.91)
    assert not math.isclose(fill.signed_slippage_usd, 0.0)
    assert math.isclose(fill.explicit_cost_usd, fill.swap_fee_usd + fill.network_fee_usd)


def test_sell_cash_flow_is_positive_proceeds_net_of_explicit_costs():
    result = execute_paper_intent(
        _intent(side=TradeSide.SELL),
        _context(quote=_quote(execution_price_usd=0.99)),
        _policy(),
    )
    fill = result.fill
    assert fill is not None
    assert result.state is PaperExecutionState.FILLED
    assert math.isclose(fill.swap_fee_usd, 1.5)
    assert math.isclose(fill.explicit_cost_usd, 1.51)
    assert math.isclose(fill.net_cash_flow_usd, 498.49)


def test_sell_exit_liquidity_shortfall_becomes_partial_fill():
    result = execute_paper_intent(
        _intent(side=TradeSide.SELL),
        _context(
            quote=_quote(
                execution_price_usd=0.99,
                quoted_notional_usd=500.0,
                available_notional_usd=125.0,
            )
        ),
        _policy(min_partial_fill_fraction=0.25),
    )
    assert result.state is PaperExecutionState.PARTIAL
    assert result.fill is not None
    assert result.fill.filled_notional_usd == 125.0
    assert result.fill.unfilled_notional_usd == 375.0


def test_equal_inputs_are_deterministic():
    first = execute_paper_intent(_intent(), _context(), _policy())
    second = execute_paper_intent(_intent(), _context(), _policy())
    assert first == second


def test_only_earliest_terminal_reason_is_returned():
    result = execute_paper_intent(
        _intent(),
        _context(
            processed_intent_keys=frozenset({"intent-key"}),
            evaluated_at_unix_ms=999_000,
            quote=_quote(mint="WrongMint", observed_at_unix_ms=2_000_000),
        ),
        _policy(),
    )
    assert result.state is PaperExecutionState.FAILED
    assert len(result.findings) == 1
    assert _reason(result) is PaperExecutionReasonCode.DUPLICATE_INTENT
