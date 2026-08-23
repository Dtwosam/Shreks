from shreks_brain import paper
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionResult,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerFinding,
    PaperLedgerReasonCode,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionMark,
    PaperPositionState,
    PaperQuote,
    PaperQuoteState,
    apply_paper_execution,
    create_paper_ledger,
    execute_paper_intent,
    mark_paper_position,
)
from shreks_brain.risk import TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode


_C1_EXPORTS = {
    "PaperExecutionContext",
    "PaperExecutionFinding",
    "PaperExecutionReasonCode",
    "PaperExecutionResult",
    "PaperExecutionState",
    "PaperFill",
    "PaperFillPolicy",
    "PaperQuote",
    "PaperQuoteState",
    "execute_paper_intent",
}
_C3_EXPORTS = {
    "PaperLedger",
    "PaperLedgerEntry",
    "PaperLedgerFinding",
    "PaperLedgerReasonCode",
    "PaperLedgerUpdate",
    "PaperLedgerUpdateState",
    "PaperPosition",
    "PaperPositionMark",
    "PaperPositionState",
    "apply_paper_execution",
    "create_paper_ledger",
    "mark_paper_position",
}


def _canonical_execution():
    intent = TradeIntent(
        mint="Mint111",
        side=TradeSide.BUY,
        requested_notional_usd=100.0,
        max_slippage_bps=100,
        strategy_name="fresh_launch_continuation",
        strategy_version="fresh-test",
        score_policy_version="score-test",
        decision_policy_version="decision-test",
        risk_policy_version="risk-test",
        reason="public api test",
        idempotency_key="api-intent",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=1_000_100,
    )
    policy = PaperFillPolicy(
        version="paper-api-test",
        assumed_latency_ms=0,
        max_quote_lag_ms=1_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.01,
    )
    quote = PaperQuote(
        provider="paper-api-quote",
        mint=intent.mint,
        observed_at_unix_ms=1_000_200,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        quoted_notional_usd=100.0,
        available_notional_usd=100.0,
    )
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(
            evaluated_at_unix_ms=1_000_200,
            processed_intent_keys=frozenset(),
            quote=quote,
        ),
        policy,
    )
    return intent, execution


def test_paper_package_retains_c1_and_adds_exact_c3_surface():
    exports = set(paper.__all__)
    assert exports == _C1_EXPORTS | _C3_EXPORTS
    assert len(paper.__all__) == len(exports) == 22

    assert callable(execute_paper_intent)
    assert callable(apply_paper_execution)
    assert callable(create_paper_ledger)
    assert callable(mark_paper_position)


def test_public_api_can_book_and_mark_real_c1_execution():
    intent, execution = _canonical_execution()
    assert isinstance(execution, PaperExecutionResult)

    ledger = create_paper_ledger(1_000.0, 1_000_000)
    assert isinstance(ledger, PaperLedger)

    booked = apply_paper_execution(ledger, intent, execution)
    assert isinstance(booked, PaperLedgerUpdate)
    assert booked.state is PaperLedgerUpdateState.APPLIED
    assert isinstance(booked.ledger.entries[0], PaperLedgerEntry)
    assert isinstance(booked.ledger.positions[0], PaperPosition)
    assert booked.ledger.positions[0].state is PaperPositionState.OPEN

    position = booked.ledger.positions[0]
    marked = mark_paper_position(
        booked.ledger,
        PaperPositionMark(
            position_id=position.position_id,
            mint=position.mint,
            observed_at_unix_ms=1_000_300,
            mark_price_usd=1.05,
        ),
    )
    assert isinstance(marked, PaperLedgerUpdate)
    assert marked.findings[0].code is PaperLedgerReasonCode.POSITION_MARKED
    assert isinstance(marked.findings[0], PaperLedgerFinding)
    assert marked.ledger.positions[0].unrealized_pnl_usd is not None


def test_public_c3_models_have_no_exit_signing_transaction_or_live_authority():
    public_models = (
        PaperLedger,
        PaperLedgerEntry,
        PaperLedgerFinding,
        PaperLedgerUpdate,
        PaperPosition,
        PaperPositionMark,
    )
    forbidden_fragments = (
        "signer",
        "signature",
        "transaction",
        "wallet",
        "private_key",
        "secret",
        "stop_loss",
        "take_profit",
        "trailing_stop",
        "exit_rule",
        "live_execution",
    )

    for model in public_models:
        fields = tuple(model.__dataclass_fields__)
        lowered = " ".join(fields).lower()
        assert not any(fragment in lowered for fragment in forbidden_fragments)

    exported = " ".join(paper.__all__).lower()
    assert "signer" not in exported
    assert "transaction" not in exported
    assert "wallet" not in exported
    assert "live_execution" not in exported
