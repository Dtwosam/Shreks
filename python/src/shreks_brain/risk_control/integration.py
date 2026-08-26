from __future__ import annotations

from dataclasses import replace

from shreks_brain.exits import ExitExecutionContext
from shreks_brain.risk import RiskContext


def apply_operator_controls_to_risk_context(
    context: RiskContext,
    *,
    halt_new_entries: bool,
    kill_switch_active: bool,
) -> RiskContext:
    """Overlay operator safety controls without changing risk thresholds."""

    if type(context) is not RiskContext:
        raise TypeError("context must be an exact RiskContext")
    _require_bool("halt_new_entries", halt_new_entries)
    _require_bool("kill_switch_active", kill_switch_active)
    return replace(
        context,
        operator_entry_halt_active=(
            context.operator_entry_halt_active
            or halt_new_entries
            or kill_switch_active
        ),
        kill_switch_active=(context.kill_switch_active or kill_switch_active),
    )


def apply_operator_controls_to_exit_context(
    context: ExitExecutionContext,
    *,
    halt_new_entries: bool,
    kill_switch_active: bool,
) -> ExitExecutionContext:
    """Overlay emergency kill onto the existing global-halt exit flag only."""

    if type(context) is not ExitExecutionContext:
        raise TypeError("context must be an exact ExitExecutionContext")
    _require_bool("halt_new_entries", halt_new_entries)
    _require_bool("kill_switch_active", kill_switch_active)
    return replace(
        context,
        global_halt_active=(context.global_halt_active or kill_switch_active),
    )


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")
