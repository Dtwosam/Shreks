from __future__ import annotations

import pytest

from shreks_brain.research.counterfactuals import (
    COUNTERFACTUAL_ACTION_LABEL_VERSION,
    CounterfactualAction,
    CounterfactualLabelError,
    ExecutableTradeEvidence,
    ExecutionStatus,
    OpenPositionCounterfactualContext,
    TradeSide,
    label_open_position_counterfactuals,
)


def sell(
    evidence_id: str,
    *,
    observed_at_unix_ms: int,
    base_quantity: float,
    status: ExecutionStatus = ExecutionStatus.EXECUTABLE,
    quote_amount: float | None,
    side: TradeSide = TradeSide.SELL,
) -> ExecutableTradeEvidence:
    return ExecutableTradeEvidence(
        evidence_id=evidence_id,
        source_event_signature=f"sig-{evidence_id}",
        source_event_ordinal=0,
        observed_at_unix_ms=observed_at_unix_ms,
        side=side,
        base_quantity=base_quantity,
        status=status,
        quote_amount=quote_amount,
        evidence_version="fl5-position-test-v1",
    )


def position_context(
    *,
    sell_now: ExecutableTradeEvidence | None,
    hold_exit: ExecutableTradeEvidence | None,
    horizon_complete: bool = True,
    reduce_quantity: float | None = None,
    reduce_now: ExecutableTradeEvidence | None = None,
) -> OpenPositionCounterfactualContext:
    return OpenPositionCounterfactualContext(
        decision_id="position-decision-1",
        mint="mint-1",
        quote_mint="quote-1",
        action_observed_at_unix_ms=1_000,
        position_base_quantity=4.0,
        position_cost_basis_quote=0.20,
        horizon_ms=1_000,
        horizon_complete=horizon_complete,
        sell_now=sell_now,
        hold_exit=hold_exit,
        reduce_quantity=reduce_quantity,
        reduce_now=reduce_now,
    )


def test_sell_now_uses_full_position_executable_proceeds_and_cost_basis() -> None:
    outcomes = label_open_position_counterfactuals(
        position_context(
            sell_now=sell(
                "sell-now",
                observed_at_unix_ms=1_000,
                base_quantity=4.0,
                quote_amount=0.18,
            ),
            hold_exit=sell(
                "hold-exit",
                observed_at_unix_ms=2_000,
                base_quantity=4.0,
                quote_amount=0.24,
            ),
        )
    )

    assert tuple(outcome.action for outcome in outcomes) == (
        CounterfactualAction.HOLD,
        CounterfactualAction.SELL_NOW,
    )
    hold, sell_now = outcomes
    assert sell_now.label_version == COUNTERFACTUAL_ACTION_LABEL_VERSION
    assert sell_now.execution_status is ExecutionStatus.EXECUTABLE
    assert sell_now.position_cost_basis_quote == pytest.approx(0.20)
    assert sell_now.exit_net_quote == pytest.approx(0.18)
    assert sell_now.net_pnl_quote == pytest.approx(-0.02)
    assert sell_now.return_bps == pytest.approx(-1_000.0)
    assert sell_now.exit_evidence_id == "sell-now"

    assert hold.execution_status is ExecutionStatus.EXECUTABLE
    assert hold.position_cost_basis_quote == pytest.approx(0.20)
    assert hold.exit_net_quote == pytest.approx(0.24)
    assert hold.net_pnl_quote == pytest.approx(0.04)
    assert hold.return_bps == pytest.approx(2_000.0)
    assert hold.exit_evidence_id == "hold-exit"


def test_reduce_now_is_caller_sized_and_allocates_cost_basis_pro_rata() -> None:
    outcomes = label_open_position_counterfactuals(
        position_context(
            sell_now=sell(
                "sell-now",
                observed_at_unix_ms=1_000,
                base_quantity=4.0,
                quote_amount=0.18,
            ),
            hold_exit=sell(
                "hold-exit",
                observed_at_unix_ms=2_000,
                base_quantity=4.0,
                quote_amount=0.24,
            ),
            reduce_quantity=1.0,
            reduce_now=sell(
                "reduce-now",
                observed_at_unix_ms=1_000,
                base_quantity=1.0,
                quote_amount=0.06,
            ),
        )
    )

    assert tuple(outcome.action for outcome in outcomes) == (
        CounterfactualAction.HOLD,
        CounterfactualAction.REDUCE_NOW,
        CounterfactualAction.SELL_NOW,
    )
    reduce_now = outcomes[1]
    assert reduce_now.execution_status is ExecutionStatus.EXECUTABLE
    assert reduce_now.base_quantity == pytest.approx(1.0)
    assert reduce_now.position_cost_basis_quote == pytest.approx(0.20)
    assert reduce_now.realized_cost_basis_quote == pytest.approx(0.05)
    assert reduce_now.exit_net_quote == pytest.approx(0.06)
    assert reduce_now.net_pnl_quote == pytest.approx(0.01)
    assert reduce_now.return_bps == pytest.approx(2_000.0)
    assert reduce_now.remaining_base_quantity == pytest.approx(3.0)
    assert reduce_now.remaining_cost_basis_quote == pytest.approx(0.15)
    assert reduce_now.exit_evidence_id == "reduce-now"


def test_no_default_reduce_fraction_or_synthetic_reduce_row_exists() -> None:
    outcomes = label_open_position_counterfactuals(
        position_context(
            sell_now=None,
            hold_exit=None,
            reduce_quantity=None,
            reduce_now=None,
        )
    )

    assert tuple(outcome.action for outcome in outcomes) == (
        CounterfactualAction.HOLD,
        CounterfactualAction.SELL_NOW,
    )
    assert all(
        outcome.action is not CounterfactualAction.REDUCE_NOW for outcome in outcomes
    )
    assert outcomes[0].execution_status is ExecutionStatus.UNKNOWN
    assert outcomes[1].execution_status is ExecutionStatus.UNKNOWN


def test_hold_requires_complete_horizon_and_executable_future_sell() -> None:
    incomplete = label_open_position_counterfactuals(
        position_context(
            sell_now=None,
            hold_exit=sell(
                "hold-exit",
                observed_at_unix_ms=2_000,
                base_quantity=4.0,
                quote_amount=0.24,
            ),
            horizon_complete=False,
        )
    )[0]
    assert incomplete.action is CounterfactualAction.HOLD
    assert incomplete.execution_status is ExecutionStatus.UNKNOWN
    assert incomplete.net_pnl_quote is None
    assert incomplete.return_bps is None

    blocked = label_open_position_counterfactuals(
        position_context(
            sell_now=None,
            hold_exit=sell(
                "blocked-hold-exit",
                observed_at_unix_ms=2_000,
                base_quantity=4.0,
                status=ExecutionStatus.NOT_EXECUTABLE,
                quote_amount=None,
            ),
        )
    )[0]
    assert blocked.execution_status is ExecutionStatus.NOT_EXECUTABLE
    assert blocked.net_pnl_quote is None
    assert blocked.return_bps is None


def test_open_position_quantity_and_time_mismatches_fail_closed() -> None:
    with pytest.raises(CounterfactualLabelError):
        position_context(
            sell_now=sell(
                "wrong-full-size",
                observed_at_unix_ms=1_000,
                base_quantity=3.0,
                quote_amount=0.14,
            ),
            hold_exit=None,
        )

    with pytest.raises(CounterfactualLabelError):
        position_context(
            sell_now=sell(
                "wrong-side",
                observed_at_unix_ms=1_000,
                base_quantity=4.0,
                quote_amount=0.18,
                side=TradeSide.BUY,
            ),
            hold_exit=None,
        )

    with pytest.raises(CounterfactualLabelError):
        position_context(
            sell_now=None,
            hold_exit=sell(
                "not-future",
                observed_at_unix_ms=1_000,
                base_quantity=4.0,
                quote_amount=0.20,
            ),
        )

    with pytest.raises(CounterfactualLabelError):
        position_context(
            sell_now=None,
            hold_exit=None,
            reduce_quantity=5.0,
            reduce_now=None,
        )

    with pytest.raises(CounterfactualLabelError):
        position_context(
            sell_now=None,
            hold_exit=None,
            reduce_quantity=1.0,
            reduce_now=sell(
                "wrong-reduce-size",
                observed_at_unix_ms=1_000,
                base_quantity=2.0,
                quote_amount=0.09,
            ),
        )

    with pytest.raises(CounterfactualLabelError):
        position_context(
            sell_now=None,
            hold_exit=None,
            reduce_quantity=None,
            reduce_now=sell(
                "orphan-reduce",
                observed_at_unix_ms=1_000,
                base_quantity=1.0,
                quote_amount=0.05,
            ),
        )


def test_open_position_labels_are_deterministic() -> None:
    item = position_context(
        sell_now=sell(
            "sell-now",
            observed_at_unix_ms=1_000,
            base_quantity=4.0,
            quote_amount=0.18,
        ),
        hold_exit=sell(
            "hold-exit",
            observed_at_unix_ms=2_000,
            base_quantity=4.0,
            quote_amount=0.24,
        ),
        reduce_quantity=1.0,
        reduce_now=sell(
            "reduce-now",
            observed_at_unix_ms=1_000,
            base_quantity=1.0,
            quote_amount=0.06,
        ),
    )

    first = label_open_position_counterfactuals(item)
    second = label_open_position_counterfactuals(item)
    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256
