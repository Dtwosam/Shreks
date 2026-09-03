from __future__ import annotations

from dataclasses import dataclass

from shreks_brain.fast_paper import (
    FastPaperBuyApproval,
    FastPaperLoopState,
    FastPaperPositionActionPolicy,
    FastPaperPositionActionState,
)
from shreks_brain.paper import PaperFillPolicy, PaperLedger, PaperPositionState

from .models import AccountingValidationReport, AccountingValidationStatus


FAST_PAPER_RUNTIME_STATE_VERSION = "fl7.5-v1"
FAST_PAPER_CHECKPOINT_SCHEMA_VERSION = "fl7.5-fast-paper-state-v1"


class FastPaperCheckpointError(ValueError):
    """Raised when Fast PAPER runtime state cannot be safely checkpointed/restored."""


@dataclass(frozen=True, slots=True)
class FastPaperRuntimeState:
    version: str
    as_of_unix_ms: int
    event_loop_state: FastPaperLoopState
    ledger: PaperLedger
    fill_policy: PaperFillPolicy
    position_action_policy: FastPaperPositionActionPolicy
    pending_buy: FastPaperBuyApproval | None
    position_action_states: tuple[FastPaperPositionActionState, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_RUNTIME_STATE_VERSION:
            raise ValueError("unsupported Fast PAPER runtime-state version")
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.event_loop_state, FastPaperLoopState):
            raise ValueError("event_loop_state must be FastPaperLoopState")
        if not isinstance(self.ledger, PaperLedger):
            raise ValueError("ledger must be PaperLedger")
        if not isinstance(self.fill_policy, PaperFillPolicy):
            raise ValueError("fill_policy must be PaperFillPolicy")
        if not isinstance(self.position_action_policy, FastPaperPositionActionPolicy):
            raise ValueError("position_action_policy must be FastPaperPositionActionPolicy")
        if self.pending_buy is not None and not isinstance(
            self.pending_buy, FastPaperBuyApproval
        ):
            raise ValueError("pending_buy must be FastPaperBuyApproval or None")
        if not isinstance(self.position_action_states, tuple) or not all(
            isinstance(item, FastPaperPositionActionState)
            for item in self.position_action_states
        ):
            raise ValueError(
                "position_action_states must be a tuple of FastPaperPositionActionState values"
            )

        if self.ledger.as_of_unix_ms > self.as_of_unix_ms:
            raise ValueError("runtime as_of_unix_ms cannot precede authoritative ledger time")
        for cursor in self.event_loop_state.market_cursors:
            if cursor.last_as_of_unix_ms > self.as_of_unix_ms:
                raise ValueError("runtime as_of_unix_ms cannot precede event-loop cursor time")
        for record in self.event_loop_state.records:
            if record.as_of_unix_ms > self.as_of_unix_ms:
                raise ValueError("runtime as_of_unix_ms cannot precede event record time")

        action_ids = tuple(item.position_id for item in self.position_action_states)
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("position_action_states must use unique position IDs")

        open_positions = tuple(
            position
            for position in self.ledger.positions
            if position.state is PaperPositionState.OPEN
        )
        open_ids = tuple(position.position_id for position in open_positions)
        if set(action_ids) != set(open_ids):
            raise ValueError(
                "position_action_states must exactly cover authoritative OPEN positions"
            )
        open_by_id = {position.position_id: position for position in open_positions}
        records_by_id = {
            record.source_event_id: record for record in self.event_loop_state.records
        }

        if self.pending_buy is not None:
            approval = self.pending_buy
            if approval.assessment.as_of_unix_ms > self.as_of_unix_ms:
                raise ValueError("runtime as_of_unix_ms cannot precede pending BUY decision")
            if any(position.mint == approval.mint for position in open_positions):
                raise ValueError("pending BUY cannot target an already OPEN mint")
            _require_recorded_assessment(
                records_by_id,
                approval.assessment.source_event_id,
                approval.assessment,
                "pending BUY",
            )

        for action_state in self.position_action_states:
            if action_state.last_assessment_at_unix_ms > self.as_of_unix_ms:
                raise ValueError(
                    "runtime as_of_unix_ms cannot precede position-action state clock"
                )
            position = open_by_id[action_state.position_id]
            pending = action_state.pending_exit
            if pending is None:
                continue
            if pending.mint != position.mint:
                raise ValueError(
                    "pending exit mint must match authoritative OPEN position mint"
                )
            if pending.assessment.as_of_unix_ms > self.as_of_unix_ms:
                raise ValueError("runtime as_of_unix_ms cannot precede pending exit decision")
            _require_recorded_assessment(
                records_by_id,
                pending.assessment.source_event_id,
                pending.assessment,
                "pending exit",
            )


@dataclass(frozen=True, slots=True)
class FastPaperCheckpointRecord:
    run_id: str
    sequence: int
    checkpoint_schema_version: str
    state_as_of_unix_ms: int
    created_at_unix_ms: int
    payload_sha256: str
    state: FastPaperRuntimeState

    def __post_init__(self) -> None:
        _require_non_empty_string("run_id", self.run_id)
        _require_non_negative_int("sequence", self.sequence)
        if self.checkpoint_schema_version != FAST_PAPER_CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("unsupported Fast PAPER checkpoint schema version")
        _require_non_negative_int("state_as_of_unix_ms", self.state_as_of_unix_ms)
        _require_non_negative_int("created_at_unix_ms", self.created_at_unix_ms)
        if self.created_at_unix_ms < self.state_as_of_unix_ms:
            raise ValueError("created_at_unix_ms must not precede state_as_of_unix_ms")
        _require_sha256("payload_sha256", self.payload_sha256)
        if not isinstance(self.state, FastPaperRuntimeState):
            raise ValueError("state must be FastPaperRuntimeState")
        if self.state.as_of_unix_ms != self.state_as_of_unix_ms:
            raise ValueError("state_as_of_unix_ms must equal Fast PAPER runtime time")


@dataclass(frozen=True, slots=True)
class FastPaperRestartValidationReport:
    equivalent: bool
    expected_state_sha256: str
    restored_state_sha256: str
    expected_accounting: AccountingValidationReport
    restored_accounting: AccountingValidationReport
    differences: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.equivalent, bool):
            raise ValueError("equivalent must be a boolean")
        _require_sha256("expected_state_sha256", self.expected_state_sha256)
        _require_sha256("restored_state_sha256", self.restored_state_sha256)
        if not isinstance(self.expected_accounting, AccountingValidationReport):
            raise ValueError("expected_accounting must be AccountingValidationReport")
        if not isinstance(self.restored_accounting, AccountingValidationReport):
            raise ValueError("restored_accounting must be AccountingValidationReport")
        if not isinstance(self.differences, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.differences
        ):
            raise ValueError("differences must be a tuple of non-empty strings")
        if self.equivalent != (not self.differences):
            raise ValueError("equivalent must match whether differences are empty")
        if self.equivalent and (
            self.expected_accounting.status is AccountingValidationStatus.INVALID
            or self.restored_accounting.status is AccountingValidationStatus.INVALID
        ):
            raise ValueError("equivalent restart report cannot contain invalid accounting")


def _require_recorded_assessment(
    records_by_id: dict[str, object],
    source_event_id: str,
    assessment: object,
    label: str,
) -> None:
    record = records_by_id.get(source_event_id)
    if record is None:
        raise ValueError(f"{label} authority is not backed by a recorded Fast PAPER event")
    recorded_assessment = getattr(record, "assessment", None)
    if recorded_assessment != assessment:
        raise ValueError(f"{label} assessment conflicts with recorded Fast PAPER authority")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
