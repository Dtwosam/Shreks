from __future__ import annotations

import math

import pytest

from shreks_brain.research.counterfactuals import (
    COUNTERFACTUAL_ACTION_LABEL_VERSION,
    CounterfactualAction,
    CounterfactualLabelError,
    DelayedEntryAlternative,
    EntryCounterfactualContext,
    ExecutableTradeEvidence,
    ExecutionStatus,
    TradeSide,
    label_entry_counterfactuals,
)


def trade(
    evidence_id: str,
    *,
    observed_at_unix_ms: int,
    side: TradeSide,
    base_quantity: float = 2.0,
    status: ExecutionStatus = ExecutionStatus.EXECUTABLE,
    quote_amount: float | None = 0.11,
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
        evidence_version="fl5-test-v1",
    )


def context(
    *,
    buy_now: ExecutableTradeEvidence | None,
    exit_at_horizon: ExecutableTradeEvidence | None,
    horizon_complete: bool = True,
    delayed_entries: tuple[DelayedEntryAlternative, ...] = (),
) -> EntryCounterfactualContext:
    return EntryCounterfactualContext(
        decision_id="decision-1",
        mint="mint-1",
        quote_mint="quote-1",
        decision_observed_at_unix_ms=1_000,
        base_quantity=2.0,
        horizon_ms=1_000,
        horizon_complete=horizon_complete,
        buy_now=buy_now,
        exit_at_horizon=exit_at_horizon,
        delayed_entries=delayed_entries,
    )


def test_buy_now_and_skip_use_exact_executable_quote_economics() -> None:
    outcomes = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            exit_at_horizon=trade(
                "exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                quote_amount=0.132,
            ),
        )
    )

    assert tuple(outcome.action for outcome in outcomes) == (
        CounterfactualAction.BUY_NOW,
        CounterfactualAction.SKIP,
    )
    buy, skip = outcomes
    assert buy.label_version == COUNTERFACTUAL_ACTION_LABEL_VERSION
    assert buy.execution_status is ExecutionStatus.EXECUTABLE
    assert buy.entry_total_quote == pytest.approx(0.11)
    assert buy.exit_net_quote == pytest.approx(0.132)
    assert buy.net_pnl_quote == pytest.approx(0.022)
    assert buy.return_bps == pytest.approx(2_000.0)
    assert buy.entry_evidence_id == "buy-now"
    assert buy.exit_evidence_id == "exit"

    assert skip.execution_status is ExecutionStatus.EXECUTABLE
    assert skip.entry_total_quote is None
    assert skip.exit_net_quote is None
    assert skip.net_pnl_quote == 0.0
    assert skip.return_bps == 0.0


def test_missing_or_incomplete_execution_evidence_stays_unknown_not_zero_filled() -> None:
    no_entry = label_entry_counterfactuals(
        context(
            buy_now=None,
            exit_at_horizon=trade(
                "exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                quote_amount=0.132,
            ),
        )
    )[0]
    assert no_entry.action is CounterfactualAction.BUY_NOW
    assert no_entry.execution_status is ExecutionStatus.UNKNOWN
    assert no_entry.entry_total_quote is None
    assert no_entry.net_pnl_quote is None
    assert no_entry.return_bps is None

    no_exit = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            exit_at_horizon=None,
        )
    )[0]
    assert no_exit.execution_status is ExecutionStatus.UNKNOWN
    assert no_exit.net_pnl_quote is None
    assert no_exit.return_bps is None

    incomplete = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            exit_at_horizon=trade(
                "exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                quote_amount=0.132,
            ),
            horizon_complete=False,
        )
    )[0]
    assert incomplete.execution_status is ExecutionStatus.UNKNOWN
    assert incomplete.net_pnl_quote is None
    assert incomplete.return_bps is None


def test_explicit_non_executability_is_distinct_from_unknown() -> None:
    outcome = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "blocked-buy",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                status=ExecutionStatus.NOT_EXECUTABLE,
                quote_amount=None,
            ),
            exit_at_horizon=trade(
                "exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                quote_amount=0.132,
            ),
        )
    )[0]

    assert outcome.execution_status is ExecutionStatus.NOT_EXECUTABLE
    assert outcome.net_pnl_quote is None
    assert outcome.return_bps is None


def test_delay_requires_explicit_later_executable_buy_evidence() -> None:
    without_delay = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            exit_at_horizon=trade(
                "exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                quote_amount=0.132,
            ),
        )
    )
    assert all(
        outcome.action is not CounterfactualAction.DELAY_ENTRY
        for outcome in without_delay
    )

    delayed = DelayedEntryAlternative(
        alternative_id="delay-250ms",
        entry=trade(
            "delayed-buy",
            observed_at_unix_ms=1_250,
            side=TradeSide.BUY,
            quote_amount=0.10,
        ),
        exit=trade(
            "delayed-exit",
            observed_at_unix_ms=2_000,
            side=TradeSide.SELL,
            quote_amount=0.132,
        ),
    )
    outcomes = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            exit_at_horizon=trade(
                "exit",
                observed_at_unix_ms=2_000,
                side=TradeSide.SELL,
                quote_amount=0.132,
            ),
            delayed_entries=(delayed,),
        )
    )
    assert tuple(outcome.action for outcome in outcomes) == (
        CounterfactualAction.BUY_NOW,
        CounterfactualAction.SKIP,
        CounterfactualAction.DELAY_ENTRY,
    )
    delay = outcomes[2]
    assert delay.alternative_id == "delay-250ms"
    assert delay.delay_ms == 250
    assert delay.entry_total_quote == pytest.approx(0.10)
    assert delay.exit_net_quote == pytest.approx(0.132)
    assert delay.net_pnl_quote == pytest.approx(0.032)
    assert delay.return_bps == pytest.approx(3_200.0)


def test_invalid_evidence_and_context_fail_closed() -> None:
    with pytest.raises(CounterfactualLabelError):
        trade(
            "bad-nan",
            observed_at_unix_ms=1_000,
            side=TradeSide.BUY,
            quote_amount=math.nan,
        )

    with pytest.raises(CounterfactualLabelError):
        trade(
            "unknown-with-fill",
            observed_at_unix_ms=1_000,
            side=TradeSide.BUY,
            status=ExecutionStatus.UNKNOWN,
            quote_amount=0.11,
        )

    with pytest.raises(CounterfactualLabelError):
        context(
            buy_now=trade(
                "wrong-size",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                base_quantity=1.0,
                quote_amount=0.055,
            ),
            exit_at_horizon=None,
        )

    with pytest.raises(CounterfactualLabelError):
        context(
            buy_now=trade(
                "wrong-side",
                observed_at_unix_ms=1_000,
                side=TradeSide.SELL,
                quote_amount=0.11,
            ),
            exit_at_horizon=None,
        )

    not_later = DelayedEntryAlternative(
        alternative_id="not-later",
        entry=trade(
            "late-buy",
            observed_at_unix_ms=1_000,
            side=TradeSide.BUY,
            quote_amount=0.10,
        ),
        exit=trade(
            "late-exit",
            observed_at_unix_ms=2_000,
            side=TradeSide.SELL,
            quote_amount=0.132,
        ),
    )
    with pytest.raises(CounterfactualLabelError):
        context(
            buy_now=None,
            exit_at_horizon=None,
            delayed_entries=(not_later,),
        )


def test_same_entry_evidence_produces_identical_rows_and_fingerprint() -> None:
    delayed = DelayedEntryAlternative(
        alternative_id="delay-250ms",
        entry=trade(
            "delayed-buy",
            observed_at_unix_ms=1_250,
            side=TradeSide.BUY,
            quote_amount=0.10,
        ),
        exit=trade(
            "delayed-exit",
            observed_at_unix_ms=2_000,
            side=TradeSide.SELL,
            quote_amount=0.132,
        ),
    )
    item = context(
        buy_now=trade(
            "buy-now",
            observed_at_unix_ms=1_000,
            side=TradeSide.BUY,
            quote_amount=0.11,
        ),
        exit_at_horizon=trade(
            "exit",
            observed_at_unix_ms=2_000,
            side=TradeSide.SELL,
            quote_amount=0.132,
        ),
        delayed_entries=(delayed,),
    )

    first = label_entry_counterfactuals(item)
    second = label_entry_counterfactuals(item)
    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert len(first.fingerprint_sha256) == 64
    assert set(first.fingerprint_sha256) <= set("0123456789abcdef")
