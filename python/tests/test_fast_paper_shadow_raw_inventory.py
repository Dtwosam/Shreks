from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import (
    FastPaperBuyOutcome,
    FastPaperPositionOutcome,
)
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION,
    FastPaperShadowMarketPosition,
    FastPaperShadowReductionQuote,
    FastPaperShadowExecutionInput,
    build_fast_paper_shadow_runtime_state,
    execute_fast_paper_shadow_decision,
    load_latest_fast_paper_shadow_runtime_state,
    retry_fast_paper_shadow_pending_buy,
    save_fast_paper_shadow_runtime_state,
)
from shreks_brain.fast_paper_runtime.shadow_executor import (
    FastPaperShadowPendingBuyRetryInput,
)

from test_fast_paper_accounting_reconciliation import MARKET_KEY
from test_fast_paper_shadow_decision import _fake_champion, _quote
from test_fast_paper_shadow_execution_input import (
    _decision,
    _risk,
    _usd,
)
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _record,
    _record_at,
    _runtime_fixture,
    _source,
)
from test_fast_paper_shadow_runtime_state import (
    EXECUTION_POLICY_FINGERPRINT,
    _database_fixture,
)


def _matching_buy_source(record, evidence) -> FastPaperShadowExecutionInput:
    source = _source(record, evidence)
    assert source.entry_authority is not None
    assert evidence.entry_quote.quoted_base_quantity is not None
    return replace(
        source,
        entry_authority=replace(
            source.entry_authority,
            intended_base_quantity=(
                evidence.entry_quote.quoted_base_quantity
            ),
        ),
    )


def _exact_open_evidence(
    monkeypatch,
    manifest,
    record,
    *,
    action: str,
    current_exposure: float,
    evaluated_at: int,
    exit_observed_at: int,
    exit_quantity: float,
    exit_input_amount_raw: int,
    reduction_observed_at: int | None = None,
    reduction_quantity: float | None = None,
    reduction_input_amount_raw: int | None = None,
):
    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda _path: _fake_champion(manifest),
    )
    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        lambda *, binary_path, champion_path, batch, timeout_seconds=None: (
            _decision(manifest, batch.decisions[0], action=action)
        ),
    )
    ticks = iter((1_000, 1_250))
    monkeypatch.setattr(shadow.time, "monotonic_ns", lambda: next(ticks))

    exit_quote = replace(
        _quote(
            record,
            observed_at=exit_observed_at,
            execution_price=0.98,
        ),
        quoted_base_quantity=exit_quantity,
        available_base_quantity=exit_quantity,
        input_amount_raw=exit_input_amount_raw,
    )
    reductions = ()
    if reduction_observed_at is not None:
        assert reduction_quantity is not None
        assert reduction_input_amount_raw is not None
        reductions = (
            FastPaperShadowReductionQuote(
                target_exposure_fraction=0.25,
                quote=replace(
                    _quote(
                        record,
                        observed_at=reduction_observed_at,
                        execution_price=0.985,
                    ),
                    quoted_base_quantity=reduction_quantity,
                    available_base_quantity=reduction_quantity,
                    input_amount_raw=reduction_input_amount_raw,
                ),
            ),
        )

    return shadow.evaluate_fast_paper_shadow_decision(
        manifest,
        record,
        FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=current_exposure,
        ),
        evaluated_at_unix_ms=evaluated_at,
        max_exposure_fraction=0.75,
        entry_quote=_quote(
            record,
            observed_at=evaluated_at - 10,
            execution_price=1.01,
        ),
        exit_quote=exit_quote,
        reduction_quotes=reductions,
    )


def test_runtime_state_v3_round_trips_exact_raw_open_inventory(
    tmp_path: Path,
) -> None:
    assert FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION == 3

    manifest, binding, checkpoint = _database_fixture(
        tmp_path,
        open_position=True,
    )
    position = tuple(
        item
        for item in checkpoint.state.ledger.positions
        if item.state.value == "OPEN"
    )[0]
    mapping = FastPaperShadowMarketPosition(
        market_key=MARKET_KEY,
        position_id=position.position_id,
        mint=position.mint,
        current_exposure_fraction=0.5,
        current_base_quantity_raw=10_000_000,
    )
    state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(mapping,),
        execution_policy_fingerprint_sha256=EXECUTION_POLICY_FINGERPRINT,
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        state,
        created_at_unix_ms=checkpoint.created_at_unix_ms,
    )
    restored = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )

    assert restored == state
    assert restored is not None
    assert restored.market_positions[0].current_base_quantity_raw == 10_000_000

    with pytest.raises(ValueError, match="raw|quantity|u64|positive"):
        FastPaperShadowMarketPosition(
            market_key=MARKET_KEY,
            position_id=position.position_id,
            mint=position.mint,
            current_exposure_fraction=0.5,
            current_base_quantity_raw=0,
        )


def test_buy_execution_requires_exact_quote_sized_entry_authority(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, _binding, _policy, _checkpoint, _posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    source = _matching_buy_source(record, evidence)
    assert source.entry_authority is not None
    assert evidence.entry_quote.quoted_base_quantity is not None

    drifted = replace(
        source.entry_authority,
        intended_base_quantity=(
            evidence.entry_quote.quoted_base_quantity * 0.75
        ),
    )
    with pytest.raises(ValueError, match="size|quantity|quote|intended"):
        replace(source, entry_authority=drifted)


def test_fresh_and_retry_buy_seed_exact_raw_inventory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    source = _matching_buy_source(record, evidence)
    filled = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        source,
    )
    assert filled.buy_result is not None
    assert filled.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert len(filled.next_market_positions) == 1
    assert filled.next_market_positions[0].current_base_quantity_raw == (
        evidence.entry_quote.output_amount_raw
    )

    # Exercise the same raw authority through the restart-safe pending-BUY path.
    other_root = tmp_path / "retry"
    other_root.mkdir()
    (
        retry_manifest,
        retry_binding,
        retry_policy,
        retry_checkpoint,
        retry_posture,
    ) = _runtime_fixture(other_root)
    retry_record = _record()
    retry_evidence = _evidence_for(
        monkeypatch,
        retry_manifest,
        retry_record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    retry_source = _matching_buy_source(retry_record, retry_evidence)
    deferred = execute_fast_paper_shadow_decision(
        retry_manifest,
        retry_policy,
        retry_binding,
        retry_checkpoint,
        retry_posture,
        retry_source,
    )
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
    checkpoint1, posture1 = _persist(
        retry_manifest,
        retry_binding,
        deferred,
        sequence=1,
        created_at=20_020,
    )
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=20_200,
        quote=replace(
            retry_evidence.entry_quote,
            observed_at_unix_ms=20_150,
            reference_price_quote=1.02,
            execution_price_quote=1.03,
        ),
        risk_context=_risk(20_200),
        quote_usd_evidence=_usd(
            retry_record,
            observed_at=20_190,
        ),
    )
    retried = retry_fast_paper_shadow_pending_buy(
        retry_manifest,
        retry_policy,
        retry_binding,
        checkpoint1,
        posture1,
        retry,
    )
    assert retried.buy_result is not None
    assert retried.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert retried.next_market_positions[0].current_base_quantity_raw == (
        retry.quote.output_amount_raw
    )


def test_hold_preserves_and_reduce_subtracts_exact_raw_inventory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base = _record()
    buy_evidence = _evidence_for(
        monkeypatch,
        manifest,
        base,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    bought = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        _matching_buy_source(base, buy_evidence),
    )
    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        bought,
        sequence=1,
        created_at=20_020,
    )
    raw_before = posture1.market_positions[0].current_base_quantity_raw
    assert raw_before == 2_000_000

    hold_record = _record_at(
        base,
        signature="raw-inventory-hold",
        sequence=2,
        at=20_300,
    )
    hold_evidence = _evidence_for(
        monkeypatch,
        manifest,
        hold_record,
        action="HOLD",
        position=FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        evaluated_at=20_320,
        entry_observed_at=20_310,
        exit_observed_at=20_315,
    )
    held = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint1,
        posture1,
        _source(hold_record, hold_evidence),
    )
    assert held.position_result is not None
    assert held.position_result.outcome in {
        FastPaperPositionOutcome.HOLD,
        FastPaperPositionOutcome.HOLD_MARKED,
    }
    assert held.next_market_positions[0].current_base_quantity_raw == raw_before

    checkpoint2, posture2 = _persist(
        manifest,
        binding,
        held,
        sequence=2,
        created_at=20_320,
    )
    reduce_record = _record_at(
        base,
        signature="raw-inventory-reduce",
        sequence=3,
        at=20_500,
    )
    reduce_evidence = _exact_open_evidence(
        monkeypatch,
        manifest,
        reduce_record,
        action="REDUCE",
        current_exposure=0.5,
        evaluated_at=20_520,
        exit_observed_at=20_515,
        exit_quantity=2.0,
        exit_input_amount_raw=2_000_000,
        reduction_observed_at=20_512,
        reduction_quantity=1.0,
        reduction_input_amount_raw=1_000_000,
    )
    reduced = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint2,
        posture2,
        _source(reduce_record, reduce_evidence),
    )
    assert reduced.position_result is not None
    assert reduced.position_result.outcome is FastPaperPositionOutcome.REDUCED
    assert len(reduced.next_market_positions) == 1
    mapping = reduced.next_market_positions[0]
    assert mapping.current_base_quantity_raw == 1_000_000
    assert mapping.current_exposure_fraction == pytest.approx(0.25)

    before_position = tuple(
        item
        for item in checkpoint2.state.ledger.positions
        if item.state.value == "OPEN"
    )[0]
    after_position = tuple(
        item
        for item in reduced.next_paper_state.ledger.positions
        if item.state.value == "OPEN"
    )[0]
    assert (
        mapping.current_base_quantity_raw / raw_before
        == pytest.approx(after_position.quantity / before_position.quantity)
    )


def test_sell_requires_full_raw_authority_and_removes_mapping(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base = _record()
    buy_evidence = _evidence_for(
        monkeypatch,
        manifest,
        base,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    bought = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        _matching_buy_source(base, buy_evidence),
    )
    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        bought,
        sequence=1,
        created_at=20_020,
    )

    sell_record = _record_at(
        base,
        signature="raw-inventory-sell",
        sequence=2,
        at=20_300,
    )
    mismatched = _exact_open_evidence(
        monkeypatch,
        manifest,
        sell_record,
        action="SELL",
        current_exposure=0.5,
        evaluated_at=20_320,
        exit_observed_at=20_315,
        exit_quantity=1.0,
        exit_input_amount_raw=1_000_000,
    )
    with pytest.raises(ValueError, match="SELL|raw|inventory|quantity"):
        execute_fast_paper_shadow_decision(
            manifest,
            policy,
            binding,
            checkpoint1,
            posture1,
            _source(sell_record, mismatched),
        )

    exact = _exact_open_evidence(
        monkeypatch,
        manifest,
        sell_record,
        action="SELL",
        current_exposure=0.5,
        evaluated_at=20_320,
        exit_observed_at=20_315,
        exit_quantity=2.0,
        exit_input_amount_raw=2_000_000,
    )
    sold = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint1,
        posture1,
        _source(sell_record, exact),
    )
    assert sold.position_result is not None
    assert sold.position_result.outcome is FastPaperPositionOutcome.SOLD
    assert sold.next_market_positions == ()


def test_raw_inventory_sources_never_reverse_convert_float_quantity() -> None:
    import shreks_brain.fast_paper_runtime.shadow_executor as executor
    import shreks_brain.fast_paper_runtime.shadow_runtime_state as runtime_state

    payload = (
        Path(executor.__file__).read_text(encoding="utf-8")
        + "\n"
        + Path(runtime_state.__file__).read_text(encoding="utf-8")
    )
    for forbidden in (
        "quantity_to_raw",
        "float_to_raw",
        "decimal_quantity_to_raw",
        "round(position.quantity",
        "int(position.quantity",
        "round(mapping.current_exposure_fraction",
    ):
        assert forbidden not in payload
