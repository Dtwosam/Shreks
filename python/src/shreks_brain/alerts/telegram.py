from __future__ import annotations

import json
import math
from typing import Callable
from urllib.request import Request, urlopen

from .models import AlertEvent


_TELEGRAM_HOST = "api.telegram.org"
_TELEGRAM_TEXT_LIMIT = 4000
_MAX_RESPONSE_BYTES = 65_536


class TelegramAlertError(RuntimeError):
    """Raised when an outbound Telegram notification cannot be delivered safely."""


def format_alert_message(event: AlertEvent) -> str:
    if type(event) is not AlertEvent:
        raise TelegramAlertError("telegram alert delivery failed")

    header = f"SHREKS [{event.severity.value}] {event.code.value}"
    lines = [header, event.title, *event.lines]
    message = "\n".join(lines)
    if len(message) <= _TELEGRAM_TEXT_LIMIT:
        return message

    live_line = "LIVE TRADING: DISABLED"
    content = [header, event.title, *(line for line in event.lines if line != live_line)]
    suffix = "\n" + live_line
    prefix = "\n".join(content)
    available = _TELEGRAM_TEXT_LIMIT - len(suffix)
    if available <= 0:
        raise TelegramAlertError("telegram alert delivery failed")
    return prefix[:available].rstrip() + suffix


def send_telegram_alert(
    *,
    chat_id: str,
    bot_token: bytes,
    event: AlertEvent,
    opener: Callable[..., object] | None = None,
    timeout_seconds: float = 10.0,
) -> None:
    try:
        _validate_chat_id(chat_id)
        token_text = _token_text(bot_token)
        _validate_timeout(timeout_seconds)
        text = format_alert_message(event)
        payload = json.dumps(
            {"chat_id": chat_id, "text": text},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        request = Request(
            f"https://{_TELEGRAM_HOST}/bot{token_text}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        sender = urlopen if opener is None else opener
        with sender(request, timeout=float(timeout_seconds)) as response:
            raw = response.read()
        if type(raw) is not bytes or len(raw) > _MAX_RESPONSE_BYTES:
            raise ValueError("invalid response")
        document = json.loads(raw.decode("utf-8"))
        if type(document) is not dict or type(document.get("ok")) is not bool:
            raise ValueError("invalid response")
        if document["ok"] is not True:
            raise ValueError("delivery rejected")
    except TelegramAlertError:
        raise
    except Exception as error:
        raise TelegramAlertError("telegram alert delivery failed") from error


def _validate_chat_id(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("invalid chat id")


def _token_text(value: object) -> str:
    if type(value) is not bytes or not value or len(value) > 4096:
        raise ValueError("invalid token")
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("invalid token") from error
    if (
        any(ord(character) < 33 or ord(character) > 126 for character in text)
        or any(character in "/?#" for character in text)
    ):
        raise ValueError("invalid token")
    return text


def _validate_timeout(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > 60
    ):
        raise TelegramAlertError("telegram alert delivery failed")
