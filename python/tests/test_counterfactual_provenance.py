from __future__ import annotations

from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
    EntryCounterfactualContext,
    ExecutableTradeEvidence,
    ExecutionStatus,
    OpenPositionCounterfactualContext,
    TradeSide,
    label_entry_counterfactuals,
    label_open_position_counterfactuals,
)


def evidence(
    evidence_id: str,
    *,
    observed_at_unix_ms: int,
    side: TradeSide,
    base_quantity: float,
    quote_amount: float,
    ordinal: int,
    version: str,
) -> ExecutableTradeEvidence:
    return ExecutableTradeEvidence(
        evidence_id=evidence_id,
        source_event_signature=f"sig-{evidence_id}",
        source_event_ordinal=ordinal,
        observed_at_unix_ms=observed_at_unix_ms,
        side=side,
        base_quantity=base_quantity,
        status=ExecutionStatus.EXECUTABLE,
        quote_amount=quote_amount,
        evidence_version=version,
    )


def test_entry_outcome_retains_exact_entry_and_exit_execution_provenance() -> None:
    buy = evidence(
        "buy-now",
        observed_at_unix_ms=1_000,
        side=TradeSide.BUY,
        base_quantity=2.0,
        quote_amount=0.11,
        ordinal=3,
        version="entry-proof-v7",
    )
    exit_trade = evidence(
        "exit",
        observed_at_unix_ms=2_000,
        side=TradeSide.SELL,
        base_quantity=2.0,
        quote_amount=0.132,
        ordinal=9,
        version="exit-proof-v4",
    )
    outcome = label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id="decision-provenance",
            mint="mint-1",
            quote_mint="quote-1",
            decision_observed_at_unix_ms=1_000,
            base_quantity=2.0,
            horizon_ms=1_000,
            horizon_complete=True,
            buy_now=buy,
            exit_at_horizon=exit_trade,
        )
    )[0]

    assert outcome.action is CounterfactualAction.BUY_NOW
    assert outcome.entry_source_event_signature == "sig-buy-now"
    assert outcome.entry_source_event_ordinal == 3
    assert outcome.entry_evidence_observed_at_unix_ms == 1_000
    assert outcome.entry_evidence_version == "entry-proof-v7"
    assert outcome.exit_source_event_signature == "sig-exit"
    assert outcome.exit_source_event_ordinal == 9
    assert outcome.exit_evidence_observed_at_unix_ms == 2_000
    assert outcome.exit_evidence_version == "exit-proof-v4"


def test_skip_retains_no_fake_execution_provenance() -> None:
    outcomes = label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id="decision-skip-provenance",
            mint="mint-1",
            quote_mint="quote-1",
            decision_observed_at_unix_ms=1_000,
            base_quantity=2.0,
            horizon_ms=1_000,
            horizon_complete=False,
            buy_now=None,
            exit_at_horizon=None,
        )
    )
    skip = outcomes[1]
    assert skip.action is CounterfactualAction.SKIP
    assert skip.entry_source_event_signature is None
    assert skip.entry_source_event_ordinal is None
    assert skip.entry_evidence_observed_at_unix_ms is None
    assert skip.entry_evidence_version is None
    assert skip.exit_source_event_signature is None
    assert skip.exit_source_event_ordinal is None
    assert skip.exit_evidence_observed_at_unix_ms is None
    assert skip.exit_evidence_version is None


def test_open_position_outcomes_retain_sell_source_provenance_without_fabrication() -> None:
    sell_now = evidence(
        "sell-now",
        observed_at_unix_ms=5_000,
        side=TradeSide.SELL,
        base_quantity=4.0,
        quote_amount=0.18,
        ordinal=11,
        version="sell-proof-v2",
    )
    hold_exit = evidence(
        "hold-exit",
        observed_at_unix_ms=6_000,
        side=TradeSide.SELL,
        base_quantity=4.0,
        quote_amount=0.24,
        ordinal=12,
        version="hold-proof-v3",
    )
    outcomes = label_open_position_counterfactuals(
        OpenPositionCounterfactualContext(
            decision_id="position-provenance",
            mint="mint-1",
            quote_mint="quote-1",
            action_observed_at_unix_ms=5_000,
            position_base_quantity=4.0,
            position_cost_basis_quote=0.20,
            horizon_ms=1_000,
            horizon_complete=True,
            sell_now=sell_now,
            hold_exit=hold_exit,
        )
    )

    hold, sell = outcomes
    assert hold.action is CounterfactualAction.HOLD
    assert hold.entry_source_event_signature is None
    assert hold.exit_source_event_signature == "sig-hold-exit"
    assert hold.exit_source_event_ordinal == 12
    assert hold.exit_evidence_observed_at_unix_ms == 6_000
    assert hold.exit_evidence_version == "hold-proof-v3"

    assert sell.action is CounterfactualAction.SELL_NOW
    assert sell.entry_source_event_signature is None
    assert sell.exit_source_event_signature == "sig-sell-now"
    assert sell.exit_source_event_ordinal == 11
    assert sell.exit_evidence_observed_at_unix_ms == 5_000
    assert sell.exit_evidence_version == "sell-proof-v2"
