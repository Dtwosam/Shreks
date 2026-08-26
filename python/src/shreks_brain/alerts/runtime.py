from __future__ import annotations

from dataclasses import replace
import time
from typing import Callable

from .config import (
    AlertRuntimeConfig,
    AlertRuntimeConfigError,
    load_alert_runtime_config,
    load_telegram_bot_token,
)
from .detector import detect_alert_events
from .models import AlertEvent, AlertSourceSnapshot, AlertState
from .source import collect_alert_source
from .state import AlertStateError, load_alert_state, write_alert_state
from .telegram import TelegramAlertError, send_telegram_alert


class AlertRuntimeError(RuntimeError):
    """Raised when a G6 alert cycle cannot safely complete its durable work."""


def run_alert_cycle(
    config: AlertRuntimeConfig,
    *,
    observed_at_unix_ms: int | None = None,
    source_loader: Callable[..., AlertSourceSnapshot] = collect_alert_source,
    sender: Callable[..., None] = send_telegram_alert,
) -> int:
    if type(config) is not AlertRuntimeConfig:
        raise AlertRuntimeError("alert runtime configuration is invalid")
    observed_at = _observed_at(observed_at_unix_ms)

    try:
        previous = load_alert_state(config.state_path)
        source = source_loader(config, observed_at_unix_ms=observed_at)
        if type(source) is not AlertSourceSnapshot:
            raise AlertRuntimeError("alert source snapshot is invalid")
        detection = detect_alert_events(config, previous, source)
        state = detection.state
        write_alert_state(config.state_path, state)
    except AlertRuntimeError:
        raise
    except (AlertStateError, OSError, TypeError, ValueError) as error:
        raise AlertRuntimeError("alert cycle could not persist its queue") from error
    except Exception as error:
        raise AlertRuntimeError("alert source collection failed") from error

    if not state.pending_events:
        return 0

    try:
        bot_token = load_telegram_bot_token(config)
    except AlertRuntimeConfigError:
        return 1

    while state.pending_events:
        event = state.pending_events[0]
        try:
            sender(
                chat_id=config.telegram_chat_id,
                bot_token=bot_token,
                event=event,
            )
        except Exception:
            return 1

        state = _acknowledge_first(state, event)
        try:
            write_alert_state(config.state_path, state)
        except AlertStateError as error:
            raise AlertRuntimeError("alert acknowledgement could not be persisted") from error

    return 0


def _acknowledge_first(state: AlertState, event: AlertEvent) -> AlertState:
    if not state.pending_events or state.pending_events[0].event_id != event.event_id:
        raise AlertRuntimeError("alert queue acknowledgement order is invalid")
    return replace(state, pending_events=state.pending_events[1:])


def _observed_at(value: int | None) -> int:
    if value is None:
        return time.time_ns() // 1_000_000
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise AlertRuntimeError("alert observation time is invalid")
    return value


def main() -> int:
    try:
        config = load_alert_runtime_config()
        return run_alert_cycle(config)
    except (AlertRuntimeConfigError, AlertRuntimeError, TelegramAlertError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
