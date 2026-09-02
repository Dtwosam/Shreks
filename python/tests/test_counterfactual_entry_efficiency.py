from __future__ import annotations

import pytest

from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
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
    quote_amount: float | None,
    status: ExecutionStatus = ExecutionStatus.EXECUTABLE,
) -> ExecutableTradeEvidence:
    return ExecutableTradeEvidence(
        evidence_id=evidence_id,
        source_event_signature=f"sig-{evidence_id}",
        source_event_ordinal=0,
        observed_at_unix_ms=observed_at_unix_ms,
        side=side,
        base_quantity=2.0,
        status=status,
        quote_amount=quote_amount,
        evidence_version="fl5-efficiency-test-v1",
    )


def delayed(
    alternative_id: str,
    *,
    observed_at_unix_ms: int,
    entry_quote: float | None,
    entry_status: ExecutionStatus = ExecutionStatus.EXECUTABLE,
) -> DelayedEntryAlternative:
    return DelayedEntryAlternative(
        alternative_id=alternative_id,
        entry=trade(
            f"{alternative_id}-buy",
            observed_at_unix_ms=observed_at_unix_ms,
            side=TradeSide.BUY,
            quote_amount=entry_quote,
            status=entry_status,
        ),
        exit=trade(
            f"{alternative_id}-exit",
            observed_at_unix_ms=2_000,
            side=TradeSide.SELL,
            quote_amount=0.132,
        ),
    )


def context(
    *,
    buy_now: ExecutableTradeEvidence | None,
    delayed_entries: tuple[DelayedEntryAlternative, ...],
) -> EntryCounterfactualContext:
    return EntryCounterfactualContext(
        decision_id="decision-efficiency-1",
        mint="mint-1",
        quote_mint="quote-1",
        decision_observed_at_unix_ms=1_000,
        base_quantity=2.0,
        horizon_ms=1_000,
        horizon_complete=True,
        buy_now=buy_now,
        exit_at_horizon=trade(
            "buy-now-exit",
            observed_at_unix_ms=2_000,
            side=TradeSide.SELL,
            quote_amount=0.132,
        ),
        delayed_entries=delayed_entries,
    )


def test_executable_delay_exposes_quote_savings_and_return_delta_vs_buy_now() -> None:
    outcomes = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            delayed_entries=(
                delayed(
                    "delay-250",
                    observed_at_unix_ms=1_250,
                    entry_quote=0.10,
                ),
            ),
        )
    )

    buy_now = outcomes[0]
    delay = outcomes[2]
    assert buy_now.action is CounterfactualAction.BUY_NOW
    assert buy_now.entry_quote_savings_vs_buy_now == pytest.approx(0.0)
    assert buy_now.return_bps_delta_vs_buy_now == pytest.approx(0.0)

    assert delay.action is CounterfactualAction.DELAY_ENTRY
    assert delay.entry_quote_savings_vs_buy_now == pytest.approx(0.01)
    assert delay.return_bps_delta_vs_buy_now == pytest.approx(1_200.0)


def test_efficiency_delta_can_be_negative_without_becoming_a_policy_decision() -> None:
    outcomes = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            delayed_entries=(
                delayed(
                    "delay-worse",
                    observed_at_unix_ms=1_250,
                    entry_quote=0.12,
                ),
            ),
        )
    )

    delay = outcomes[2]
    assert delay.entry_quote_savings_vs_buy_now == pytest.approx(-0.01)
    assert delay.return_bps_delta_vs_buy_now == pytest.approx(-1_000.0)
    assert tuple(outcome.action for outcome in outcomes) == (
        CounterfactualAction.BUY_NOW,
        CounterfactualAction.SKIP,
        CounterfactualAction.DELAY_ENTRY,
    )


def test_efficiency_is_unknown_when_buy_now_or_delay_is_not_executable() -> None:
    no_baseline = label_entry_counterfactuals(
        context(
            buy_now=None,
            delayed_entries=(
                delayed(
                    "delay-only",
                    observed_at_unix_ms=1_250,
                    entry_quote=0.10,
                ),
            ),
        )
    )[2]
    assert no_baseline.execution_status is ExecutionStatus.EXECUTABLE
    assert no_baseline.entry_quote_savings_vs_buy_now is None
    assert no_baseline.return_bps_delta_vs_buy_now is None

    blocked_delay = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            delayed_entries=(
                delayed(
                    "blocked-delay",
                    observed_at_unix_ms=1_250,
                    entry_quote=None,
                    entry_status=ExecutionStatus.NOT_EXECUTABLE,
                ),
            ),
        )
    )[2]
    assert blocked_delay.execution_status is ExecutionStatus.NOT_EXECUTABLE
    assert blocked_delay.entry_quote_savings_vs_buy_now is None
    assert blocked_delay.return_bps_delta_vs_buy_now is None


def test_multiple_explicit_delays_remain_time_ordered_and_independently_compared() -> None:
    outcomes = label_entry_counterfactuals(
        context(
            buy_now=trade(
                "buy-now",
                observed_at_unix_ms=1_000,
                side=TradeSide.BUY,
                quote_amount=0.11,
            ),
            delayed_entries=(
                delayed("delay-100", observed_at_unix_ms=1_100, entry_quote=0.105),
                delayed("delay-300", observed_at_unix_ms=1_300, entry_quote=0.095),
            ),
        )
    )

    delays = tuple(
        outcome
        for outcome in outcomes
        if outcome.action is CounterfactualAction.DELAY_ENTRY
    )
    assert tuple(outcome.alternative_id for outcome in delays) == (
        "delay-100",
        "delay-300",
    )
    assert delays[0].entry_quote_savings_vs_buy_now == pytest.approx(0.005)
    assert delays[1].entry_quote_savings_vs_buy_now == pytest.approx(0.015)
