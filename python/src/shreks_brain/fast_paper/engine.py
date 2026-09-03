from __future__ import annotations

from collections.abc import Callable
import hashlib
import json

from .models import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperActionAssessment,
    FastPaperAssessmentMismatchError,
    FastPaperEventOutcome,
    FastPaperEventRecord,
    FastPaperEventResult,
    FastPaperLoopConflictError,
    FastPaperLoopOrderError,
    FastPaperLoopState,
    FastPaperMarketCursor,
    FastPaperMaterialUpdate,
)


FastPaperEvaluator = Callable[[FastPaperMaterialUpdate], FastPaperActionAssessment]


def create_fast_paper_loop_state() -> FastPaperLoopState:
    """Create an empty immutable FL7.1 event-resolution PAPER loop state."""

    return FastPaperLoopState(
        version=FAST_PAPER_EVENT_LOOP_VERSION,
        market_cursors=(),
        records=(),
    )


def run_fast_paper_event(
    state: FastPaperLoopState,
    update: FastPaperMaterialUpdate,
    evaluator: FastPaperEvaluator,
) -> FastPaperEventResult:
    """Apply one ordered Fast Lane update and synchronously assess if material.

    This function deliberately has no timer, queue, sleep, wall-clock read, fill,
    risk decision, or ledger mutation. Exact replay is idempotent and never
    invokes the evaluator twice.
    """

    if not isinstance(state, FastPaperLoopState):
        raise ValueError("state must be a FastPaperLoopState")
    if not isinstance(update, FastPaperMaterialUpdate):
        raise ValueError("update must be a FastPaperMaterialUpdate")
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")

    fingerprint = _update_fingerprint(update)
    existing_record = _find_record(state, update.source_event_id)
    if existing_record is not None:
        if existing_record.update_fingerprint != fingerprint:
            raise FastPaperLoopConflictError(
                f"event {update.source_event_id!r} was replayed with conflicting content"
            )
        return FastPaperEventResult(
            outcome=FastPaperEventOutcome.REPLAYED,
            source_event_id=update.source_event_id,
            assessment=existing_record.assessment,
            next_state=state,
        )

    cursor = _find_cursor(state, update.market_key)
    _validate_new_order(cursor, update)

    if not update.is_material:
        next_state = _append_applied_update(
            state,
            update,
            fingerprint,
            assessment=None,
        )
        return FastPaperEventResult(
            outcome=FastPaperEventOutcome.IGNORED_NON_MATERIAL,
            source_event_id=update.source_event_id,
            assessment=None,
            next_state=next_state,
        )

    assessment = evaluator(update)
    _validate_assessment(update, assessment)
    next_state = _append_applied_update(
        state,
        update,
        fingerprint,
        assessment=assessment,
    )
    return FastPaperEventResult(
        outcome=FastPaperEventOutcome.ASSESSED,
        source_event_id=update.source_event_id,
        assessment=assessment,
        next_state=next_state,
    )


def _update_fingerprint(update: FastPaperMaterialUpdate) -> str:
    payload = {
        "version": FAST_PAPER_EVENT_LOOP_VERSION,
        "source_event_id": update.source_event_id,
        "market_key": update.market_key,
        "source_sequence": update.source_sequence,
        "as_of_unix_ms": update.as_of_unix_ms,
        "state_version": update.state_version,
        "is_material": update.is_material,
        "material_reason": update.material_reason,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _find_record(
    state: FastPaperLoopState,
    source_event_id: str,
) -> FastPaperEventRecord | None:
    return next(
        (record for record in state.records if record.source_event_id == source_event_id),
        None,
    )


def _find_cursor(
    state: FastPaperLoopState,
    market_key: str,
) -> FastPaperMarketCursor | None:
    return next(
        (cursor for cursor in state.market_cursors if cursor.market_key == market_key),
        None,
    )


def _validate_new_order(
    cursor: FastPaperMarketCursor | None,
    update: FastPaperMaterialUpdate,
) -> None:
    if cursor is None:
        return
    if update.source_sequence <= cursor.last_source_sequence:
        raise FastPaperLoopOrderError(
            "new event source_sequence must be strictly greater than the market cursor"
        )
    if update.as_of_unix_ms < cursor.last_as_of_unix_ms:
        raise FastPaperLoopOrderError(
            "new event as_of_unix_ms must not precede the market cursor timestamp"
        )


def _validate_assessment(
    update: FastPaperMaterialUpdate,
    assessment: object,
) -> None:
    if not isinstance(assessment, FastPaperActionAssessment):
        raise FastPaperAssessmentMismatchError(
            "evaluator must return FastPaperActionAssessment"
        )
    mismatches: list[str] = []
    if assessment.source_event_id != update.source_event_id:
        mismatches.append("source_event_id")
    if assessment.market_key != update.market_key:
        mismatches.append("market_key")
    if assessment.source_sequence != update.source_sequence:
        mismatches.append("source_sequence")
    if assessment.as_of_unix_ms != update.as_of_unix_ms:
        mismatches.append("as_of_unix_ms")
    if mismatches:
        joined = ", ".join(mismatches)
        raise FastPaperAssessmentMismatchError(
            f"assessment does not match triggering update: {joined}"
        )


def _append_applied_update(
    state: FastPaperLoopState,
    update: FastPaperMaterialUpdate,
    fingerprint: str,
    *,
    assessment: FastPaperActionAssessment | None,
) -> FastPaperLoopState:
    new_cursor = FastPaperMarketCursor(
        market_key=update.market_key,
        last_source_sequence=update.source_sequence,
        last_as_of_unix_ms=update.as_of_unix_ms,
    )
    cursors = _replace_or_append_cursor(state.market_cursors, new_cursor)
    record = FastPaperEventRecord(
        source_event_id=update.source_event_id,
        update_fingerprint=fingerprint,
        market_key=update.market_key,
        source_sequence=update.source_sequence,
        as_of_unix_ms=update.as_of_unix_ms,
        is_material=update.is_material,
        assessment=assessment,
    )
    return FastPaperLoopState(
        version=state.version,
        market_cursors=cursors,
        records=state.records + (record,),
    )


def _replace_or_append_cursor(
    cursors: tuple[FastPaperMarketCursor, ...],
    new_cursor: FastPaperMarketCursor,
) -> tuple[FastPaperMarketCursor, ...]:
    replaced = False
    values: list[FastPaperMarketCursor] = []
    for cursor in cursors:
        if cursor.market_key == new_cursor.market_key:
            values.append(new_cursor)
            replaced = True
        else:
            values.append(cursor)
    if not replaced:
        values.append(new_cursor)
    return tuple(values)
