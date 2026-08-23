"""Runtime mode definitions for the Shreks brain."""

from enum import StrEnum


class RuntimeMode(StrEnum):
    """Operating mode shared by the Python decision layer."""

    OBSERVE = "observe"
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"
    HALTED = "halted"


def parse_runtime_mode(value: str | None) -> RuntimeMode:
    """Parse a runtime mode without silently accepting invalid values."""

    if value is None:
        return RuntimeMode.OBSERVE

    try:
        return RuntimeMode(value)
    except ValueError as exc:
        raise ValueError(
            "unsupported Shreks runtime mode "
            f"{value!r}; expected observe, paper, shadow, live, or halted"
        ) from exc
