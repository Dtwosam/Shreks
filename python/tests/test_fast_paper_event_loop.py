from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperAssessmentMismatchError,
    FastPaperEventOutcome,
    FastPaperLoopConflictError,
    FastPaperLoopOrderError,
    FastPaperMaterialUpdate,
    create_fast_paper_loop_state,
    run_fast_paper_event,
)


def update(
    event_id: str = "event-1",
    *,
    market_key: str = "MINT/SOL@pumpswap",
    sequence: int = 1,
    as_of: int = 1_000,
    material: bool = True,
) -> FastPaperMaterialUpdate:
    return FastPaperMaterialUpdate(
        source_event_id=event_id,
        market_key=market_key,
        source_sequence=sequence,
        as_of_unix_ms=as_of,
        state_version="fast-state-v1",
        is_material=material,
        material_reason="flow_changed" if material else None,
    )


def assessment(
    item: FastPaperMaterialUpdate,
    action: FastPaperAction = FastPaperAction.BUY,
) -> FastPaperActionAssessment:
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=item.source_event_id,
        market_key=item.market_key,
        source_sequence=item.source_sequence,
        as_of_unix_ms=item.as_of_unix_ms,
        strategy_family="fixture",
        strategy_version="fixture-v1",
        action=action,
        reasons=("fixture_reason",),
    )


def test_material_update_invokes_evaluator_once_and_journals_assessment() -> None:
    state = create_fast_paper_loop_state()
    item = update()
    calls = 0

    def evaluator(value: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        nonlocal calls
        calls += 1
        return assessment(value)

    result = run_fast_paper_event(state, item, evaluator)

    assert FAST_PAPER_EVENT_LOOP_VERSION == "fl7.1-v1"
    assert calls == 1
    assert result.outcome is FastPaperEventOutcome.ASSESSED
    assert result.source_event_id == item.source_event_id
    assert result.assessment == assessment(item)
    assert result.next_state.records[-1].assessment == result.assessment
    assert result.next_state.market_cursors[0].last_source_sequence == 1


def test_material_updates_one_millisecond_apart_both_assess_without_timer_gate() -> None:
    state = create_fast_paper_loop_state()
    calls = 0

    def evaluator(value: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        nonlocal calls
        calls += 1
        return assessment(value)

    first = run_fast_paper_event(state, update(sequence=1, as_of=1_000), evaluator)
    second = run_fast_paper_event(
        first.next_state,
        update("event-2", sequence=2, as_of=1_001),
        evaluator,
    )

    assert first.outcome is FastPaperEventOutcome.ASSESSED
    assert second.outcome is FastPaperEventOutcome.ASSESSED
    assert calls == 2
    assert len(second.next_state.records) == 2


def test_increasing_sequences_at_same_timestamp_both_assess() -> None:
    state = create_fast_paper_loop_state()
    calls = 0

    def evaluator(value: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        nonlocal calls
        calls += 1
        return assessment(value)

    first = run_fast_paper_event(state, update(sequence=1, as_of=1_000), evaluator)
    second = run_fast_paper_event(
        first.next_state,
        update("event-2", sequence=2, as_of=1_000),
        evaluator,
    )

    assert second.outcome is FastPaperEventOutcome.ASSESSED
    assert calls == 2


def test_non_material_update_advances_cursor_without_evaluation() -> None:
    state = create_fast_paper_loop_state()

    def evaluator(_: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        raise AssertionError("non-material update must not invoke evaluator")

    item = update(material=False)
    result = run_fast_paper_event(state, item, evaluator)

    assert result.outcome is FastPaperEventOutcome.IGNORED_NON_MATERIAL
    assert result.assessment is None
    assert result.next_state.market_cursors[0].last_source_sequence == 1
    assert result.next_state.records[-1].assessment is None


def test_exact_material_replay_does_not_reinvoke_evaluator() -> None:
    state = create_fast_paper_loop_state()
    item = update()
    calls = 0

    def first_evaluator(value: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        nonlocal calls
        calls += 1
        return assessment(value, FastPaperAction.SKIP)

    first = run_fast_paper_event(state, item, first_evaluator)

    def must_not_run(_: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        raise AssertionError("exact replay must not invoke evaluator")

    second = run_fast_paper_event(first.next_state, item, must_not_run)

    assert calls == 1
    assert second.outcome is FastPaperEventOutcome.REPLAYED
    assert second.assessment == first.assessment
    assert second.next_state == first.next_state


def test_exact_non_material_replay_is_idempotent() -> None:
    state = create_fast_paper_loop_state()
    item = update(material=False)

    def must_not_run(_: FastPaperMaterialUpdate) -> FastPaperActionAssessment:
        raise AssertionError("non-material update must not invoke evaluator")

    first = run_fast_paper_event(state, item, must_not_run)
    second = run_fast_paper_event(first.next_state, item, must_not_run)

    assert second.outcome is FastPaperEventOutcome.REPLAYED
    assert second.assessment is None
    assert second.next_state == first.next_state


def test_conflicting_replay_fails_closed() -> None:
    state = create_fast_paper_loop_state()
    item = update()
    first = run_fast_paper_event(state, item, lambda value: assessment(value))
    conflict = replace(item, state_version="different-state-version")

    with pytest.raises(FastPaperLoopConflictError):
        run_fast_paper_event(
            first.next_state,
            conflict,
            lambda _: (_ for _ in ()).throw(AssertionError("must not evaluate conflict")),
        )


def test_stale_or_repeated_new_sequence_fails_closed() -> None:
    state = create_fast_paper_loop_state()
    first = run_fast_paper_event(state, update(sequence=5), lambda value: assessment(value))

    for sequence in (4, 5):
        with pytest.raises(FastPaperLoopOrderError):
            run_fast_paper_event(
                first.next_state,
                update(f"event-{sequence}", sequence=sequence, as_of=1_001),
                lambda value: assessment(value),
            )


def test_timestamp_regression_fails_closed() -> None:
    state = create_fast_paper_loop_state()
    first = run_fast_paper_event(
        state,
        update(sequence=1, as_of=2_000),
        lambda value: assessment(value),
    )

    with pytest.raises(FastPaperLoopOrderError):
        run_fast_paper_event(
            first.next_state,
            update("event-2", sequence=2, as_of=1_999),
            lambda value: assessment(value),
        )


def test_equal_sequence_on_different_markets_is_valid() -> None:
    state = create_fast_paper_loop_state()
    first_item = update(market_key="A/SOL@pumpswap", sequence=1)
    second_item = update(
        "event-2",
        market_key="B/SOL@pumpswap",
        sequence=1,
        as_of=900,
    )

    first = run_fast_paper_event(state, first_item, lambda value: assessment(value))
    second = run_fast_paper_event(
        first.next_state,
        second_item,
        lambda value: assessment(value, FastPaperAction.HOLD),
    )

    assert second.outcome is FastPaperEventOutcome.ASSESSED
    assert len(second.next_state.market_cursors) == 2
    assert {cursor.market_key for cursor in second.next_state.market_cursors} == {
        "A/SOL@pumpswap",
        "B/SOL@pumpswap",
    }


def test_assessment_event_identity_mismatch_fails_closed() -> None:
    item = update()
    wrong = replace(assessment(item), source_event_id="other-event")

    with pytest.raises(FastPaperAssessmentMismatchError):
        run_fast_paper_event(create_fast_paper_loop_state(), item, lambda _: wrong)


def test_assessment_market_sequence_and_timestamp_mismatch_fail_closed() -> None:
    item = update()
    base = assessment(item)

    mismatches = (
        replace(base, market_key="OTHER/SOL@pumpswap"),
        replace(base, source_sequence=2),
        replace(base, as_of_unix_ms=999),
    )
    for wrong in mismatches:
        with pytest.raises(FastPaperAssessmentMismatchError):
            run_fast_paper_event(create_fast_paper_loop_state(), item, lambda _, value=wrong: value)


def test_all_five_actions_cross_boundary_without_interpretation() -> None:
    state = create_fast_paper_loop_state()
    for index, action in enumerate(FastPaperAction, start=1):
        item = update(
            f"event-{index}",
            sequence=index,
            as_of=1_000 + index,
        )
        result = run_fast_paper_event(
            state,
            item,
            lambda value, selected=action: assessment(value, selected),
        )
        assert result.assessment is not None
        assert result.assessment.action is action
        state = result.next_state

    assert tuple(record.assessment.action for record in state.records) == tuple(FastPaperAction)


def test_evaluator_exception_does_not_return_partial_state() -> None:
    state = create_fast_paper_loop_state()
    item = update()

    class EvaluatorFailure(RuntimeError):
        pass

    with pytest.raises(EvaluatorFailure):
        run_fast_paper_event(
            state,
            item,
            lambda _: (_ for _ in ()).throw(EvaluatorFailure("boom")),
        )

    assert state == create_fast_paper_loop_state()


def test_identical_inputs_produce_identical_result_and_state() -> None:
    state = create_fast_paper_loop_state()
    item = update()

    first = run_fast_paper_event(state, item, lambda value: assessment(value, FastPaperAction.BUY))
    second = run_fast_paper_event(state, item, lambda value: assessment(value, FastPaperAction.BUY))

    assert first == second
    assert first.next_state == second.next_state


def test_model_validation_rejects_invalid_material_reason_contract() -> None:
    with pytest.raises(ValueError):
        FastPaperMaterialUpdate(
            source_event_id="event-1",
            market_key="MINT/SOL@pumpswap",
            source_sequence=1,
            as_of_unix_ms=1_000,
            state_version="fast-state-v1",
            is_material=True,
            material_reason=None,
        )

    with pytest.raises(ValueError):
        FastPaperMaterialUpdate(
            source_event_id="event-1",
            market_key="MINT/SOL@pumpswap",
            source_sequence=1,
            as_of_unix_ms=1_000,
            state_version="fast-state-v1",
            is_material=False,
            material_reason="should-be-none",
        )
