from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from collections.abc import Callable
from typing import TextIO

from .models import OperatorRiskControlCommand, OperatorRiskControlSource
from .state import (
    RiskControlCommandError,
    RiskControlConflictError,
    RiskControlStateError,
    apply_operator_risk_control_command,
    encode_operator_risk_control_state,
    initialize_operator_risk_control_state,
)

_RESET_CONFIRMATION = "RESET KILL SWITCH"
_CLEAR_CONFIRMATION = "CLEAR ENTRY HALT"


class HostRiskControlCLIError(ValueError):
    """Raised when host-only G7 recovery CLI input is unsafe or incomplete."""


def main(
    argv: list[str] | None = None,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms

    try:
        command, state_path, expected_revision, confirmation, reason = _parse_args(args)
        observed_at_unix_ms = _timestamp(clock)
        if command == "initialize":
            state = initialize_operator_risk_control_state(
                state_path,
                observed_at_unix_ms=observed_at_unix_ms,
            )
        elif command == "reset-kill-switch":
            _require_confirmation(confirmation, _RESET_CONFIRMATION)
            _require_reason(reason)
            state = apply_operator_risk_control_command(
                state_path,
                OperatorRiskControlCommand.RESET_KILL_SWITCH,
                expected_revision=_require_revision(expected_revision),
                observed_at_unix_ms=observed_at_unix_ms,
                source=OperatorRiskControlSource.HOST_CLI,
                reason=reason,
            )
        elif command == "clear-entry-halt":
            _require_confirmation(confirmation, _CLEAR_CONFIRMATION)
            _require_reason(reason)
            state = apply_operator_risk_control_command(
                state_path,
                OperatorRiskControlCommand.CLEAR_ENTRY_HALT,
                expected_revision=_require_revision(expected_revision),
                observed_at_unix_ms=observed_at_unix_ms,
                source=OperatorRiskControlSource.HOST_CLI,
                reason=reason,
            )
        else:
            raise HostRiskControlCLIError("unsupported host risk-control command")
    except (
        HostRiskControlCLIError,
        RiskControlCommandError,
        RiskControlConflictError,
        RiskControlStateError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(_safe_error(error), file=err)
        return 2

    out.write(encode_operator_risk_control_state(state).decode("utf-8"))
    return 0


def _parse_args(
    args: list[str],
) -> tuple[str, Path, str | None, str | None, str | None]:
    if not args:
        raise HostRiskControlCLIError("command is required")
    command = args[0]
    if command not in {"initialize", "reset-kill-switch", "clear-entry-halt"}:
        raise HostRiskControlCLIError("unsupported host risk-control command")

    values: dict[str, str] = {}
    index = 1
    while index < len(args):
        flag = args[index]
        if flag not in {
            "--state-path",
            "--expected-revision",
            "--confirmation",
            "--reason",
        }:
            raise HostRiskControlCLIError("unsupported host risk-control argument")
        if flag in values or index + 1 >= len(args):
            raise HostRiskControlCLIError(f"value is required exactly once for {flag}")
        values[flag] = args[index + 1]
        index += 2

    state_path = _state_path(values.get("--state-path"))
    if command == "initialize":
        extras = set(values) - {"--state-path"}
        if extras:
            raise HostRiskControlCLIError("initialize accepts only --state-path")
        return command, state_path, None, None, None

    required = {"--state-path", "--expected-revision", "--confirmation", "--reason"}
    missing = required - set(values)
    if missing:
        label = sorted(missing)[0].removeprefix("--").replace("-", " ")
        raise HostRiskControlCLIError(f"{label} is required")
    extras = set(values) - required
    if extras:
        raise HostRiskControlCLIError("unsupported host risk-control argument")
    return (
        command,
        state_path,
        values["--expected-revision"],
        values["--confirmation"],
        values["--reason"],
    )


def _state_path(value: object) -> Path:
    if type(value) is not str or not value or value.strip() != value:
        raise HostRiskControlCLIError("state path is required")
    try:
        path = Path(value).expanduser()
    except (TypeError, ValueError, OSError) as error:
        raise HostRiskControlCLIError("state path is invalid") from error
    if not path.is_absolute() or not path.name:
        raise HostRiskControlCLIError("state path must be absolute and name a file")
    return path


def _require_revision(value: object) -> int:
    if type(value) is not str or not value or not value.isascii() or not value.isdecimal():
        raise HostRiskControlCLIError("expected revision must be a non-negative integer")
    revision = int(value, 10)
    if str(revision) != value:
        raise HostRiskControlCLIError("expected revision must be canonical")
    return revision


def _require_confirmation(value: object, expected: str) -> None:
    if value != expected:
        raise HostRiskControlCLIError(f"confirmation must be exactly {expected!r}")


def _require_reason(value: object) -> None:
    if type(value) is not str or not value:
        raise HostRiskControlCLIError("reason is required")


def _timestamp(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception as error:
        raise HostRiskControlCLIError("host risk-control clock failed") from error
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise HostRiskControlCLIError(
            "host risk-control clock must return a non-negative integer millisecond timestamp"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _safe_error(error: BaseException) -> str:
    if isinstance(error, RiskControlConflictError):
        return "host risk-control command rejected: expected revision conflict"
    if isinstance(error, HostRiskControlCLIError):
        return str(error)
    if isinstance(error, RiskControlCommandError):
        return f"host risk-control command rejected: {error}"
    if isinstance(error, RiskControlStateError):
        return "host risk-control state unavailable or invalid"
    return "host risk-control command failed"


if __name__ == "__main__":
    raise SystemExit(main())
