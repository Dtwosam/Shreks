from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.exits import ExitState
from shreks_brain.fast_paper import FastPaperProtectiveExitPolicy
from shreks_brain.paper import PaperPositionState

from .fast_models import FastPaperRuntimeState


FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION = "fl7.6-v1"
FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION = (
    "fl7.6-fast-paper-protected-state-v1"
)

_REL_TOL = 1e-12
_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class FastPaperProtectedRuntimeState:
    version: str
    base_runtime_state: FastPaperRuntimeState
    protective_policy: FastPaperProtectiveExitPolicy
    protective_states: tuple[ExitState, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION:
            raise ValueError("unsupported Fast PAPER protected runtime-state version")
        if not isinstance(self.base_runtime_state, FastPaperRuntimeState):
            raise ValueError("base_runtime_state must be FastPaperRuntimeState")
        if not isinstance(self.protective_policy, FastPaperProtectiveExitPolicy):
            raise ValueError(
                "protective_policy must be FastPaperProtectiveExitPolicy"
            )
        if not isinstance(self.protective_states, tuple) or not all(
            isinstance(item, ExitState) for item in self.protective_states
        ):
            raise ValueError("protective_states must be a tuple of ExitState values")

        state_ids = tuple(item.position_id for item in self.protective_states)
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("protective_states must use unique position IDs")

        open_positions = tuple(
            position
            for position in self.base_runtime_state.ledger.positions
            if position.state is PaperPositionState.OPEN
        )
        open_ids = tuple(position.position_id for position in open_positions)
        if set(state_ids) != set(open_ids):
            raise ValueError(
                "protective_states must exactly cover authoritative OPEN positions"
            )

        positions_by_id = {position.position_id: position for position in open_positions}
        policy_version = self.protective_policy.exit_policy.version
        runtime_time = self.base_runtime_state.as_of_unix_ms
        for state in self.protective_states:
            position = positions_by_id[state.position_id]
            if state.mint != position.mint:
                raise ValueError(
                    "protective state mint must match authoritative OPEN position"
                )
            if state.policy_version != policy_version:
                raise ValueError(
                    "protective state policy version must match protective C4 policy"
                )
            if state.initialized_at_unix_ms != position.opened_at_unix_ms:
                raise ValueError(
                    "protective state initialized time must equal position opened time"
                )
            if state.last_evaluated_at_unix_ms > runtime_time:
                raise ValueError(
                    "protective state last-evaluated time cannot exceed runtime time"
                )
            if state.high_water_at_unix_ms > runtime_time:
                raise ValueError(
                    "protective state high-water time cannot exceed runtime time"
                )
            if (
                state.high_water_price_usd < position.weighted_entry_price_usd
                and not math.isclose(
                    state.high_water_price_usd,
                    position.weighted_entry_price_usd,
                    rel_tol=_REL_TOL,
                    abs_tol=_ABS_TOL,
                )
            ):
                raise ValueError(
                    "protective state high-water price cannot be below position entry price"
                )


@dataclass(frozen=True, slots=True)
class FastPaperProtectedCheckpointRecord:
    run_id: str
    sequence: int
    checkpoint_schema_version: str
    state_as_of_unix_ms: int
    created_at_unix_ms: int
    payload_sha256: str
    state: FastPaperProtectedRuntimeState

    def __post_init__(self) -> None:
        _require_non_empty_string("run_id", self.run_id)
        _require_non_negative_int("sequence", self.sequence)
        if (
            self.checkpoint_schema_version
            != FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION
        ):
            raise ValueError("unsupported Fast PAPER protected checkpoint schema version")
        _require_non_negative_int("state_as_of_unix_ms", self.state_as_of_unix_ms)
        _require_non_negative_int("created_at_unix_ms", self.created_at_unix_ms)
        if self.created_at_unix_ms < self.state_as_of_unix_ms:
            raise ValueError("created_at_unix_ms must not precede state_as_of_unix_ms")
        _require_sha256("payload_sha256", self.payload_sha256)
        if not isinstance(self.state, FastPaperProtectedRuntimeState):
            raise ValueError("state must be FastPaperProtectedRuntimeState")
        if (
            self.state.base_runtime_state.as_of_unix_ms
            != self.state_as_of_unix_ms
        ):
            raise ValueError(
                "state_as_of_unix_ms must equal protected base-runtime time"
            )


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
