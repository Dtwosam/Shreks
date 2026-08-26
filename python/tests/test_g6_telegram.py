from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlsplit

import pytest

from shreks_brain.alerts.models import AlertCode, AlertEvent, AlertSeverity
from shreks_brain.alerts.telegram import (
    TelegramAlertError,
    format_alert_message,
    send_telegram_alert,
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _event() -> AlertEvent:
    return AlertEvent(
        event_id="condition:CORE_RUNTIME_STOPPED",
        code=AlertCode.CORE_RUNTIME_STOPPED,
        severity=AlertSeverity.CRITICAL,
        observed_at_unix_ms=1_800_000_000_000,
        title="PAPER runtime is not fully active.",
        lines=("Units: shreks-paper-campaign.service", "LIVE TRADING: DISABLED"),
    )


def test_format_alert_message_is_deterministic_plain_and_bounded() -> None:
    event = _event()
    message = format_alert_message(event)

    assert message == format_alert_message(event)
    assert message.startswith("SHREKS [CRITICAL] CORE_RUNTIME_STOPPED\n")
    assert "PAPER runtime is not fully active." in message
    assert "LIVE TRADING: DISABLED" in message
    assert len(message) <= 4000
    assert "parse_mode" not in message


def test_send_telegram_alert_posts_exact_outbound_send_message_request() -> None:
    captured: dict[str, object] = {}

    def opener(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(b'{"ok":true}')

    token = b"123456:ABC_def-ghi"
    send_telegram_alert(
        chat_id="-1001234567890",
        bot_token=token,
        event=_event(),
        opener=opener,
        timeout_seconds=7.5,
    )

    request = captured["request"]
    parts = urlsplit(request.full_url)
    assert parts.scheme == "https"
    assert parts.netloc == "api.telegram.org"
    assert parts.path == "/bot123456:ABC_def-ghi/sendMessage"
    assert parts.query == ""
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert captured["timeout"] == 7.5
    assert json.loads(request.data.decode("utf-8")) == {
        "chat_id": "-1001234567890",
        "text": format_alert_message(_event()),
    }


def test_send_telegram_alert_requires_exact_true_ok_response() -> None:
    for payload in (
        b'{"ok":false}',
        b'{"ok":"true"}',
        b'{"result":{}}',
        b'[]',
        b'not-json',
    ):
        with pytest.raises(TelegramAlertError, match="telegram alert delivery failed"):
            send_telegram_alert(
                chat_id="-1001234567890",
                bot_token=b"123456:ABC_def-ghi",
                event=_event(),
                opener=lambda request, *, timeout, payload=payload: _Response(payload),
            )


def test_transport_failure_is_generic_and_never_leaks_secret_context() -> None:
    token = b"123456:ABC_SECRET_TOKEN"
    chat_id = "-1009999999999"
    secret_url = "https://api.telegram.org/bot123456:ABC_SECRET_TOKEN/sendMessage"

    def opener(_request, *, timeout):
        raise URLError(f"failed {secret_url} for {chat_id}; body=SECRET_RESPONSE")

    with pytest.raises(TelegramAlertError) as raised:
        send_telegram_alert(
            chat_id=chat_id,
            bot_token=token,
            event=_event(),
            opener=opener,
        )

    text = str(raised.value)
    assert text == "telegram alert delivery failed"
    assert token.decode() not in text
    assert secret_url not in text
    assert chat_id not in text
    assert "SECRET_RESPONSE" not in text


def test_sender_rejects_unbounded_timeout_without_network_call() -> None:
    called = False

    def opener(_request, *, timeout):
        nonlocal called
        called = True
        return _Response(b'{"ok":true}')

    for timeout in (0.0, -1.0, 61.0, float("inf"), float("nan")):
        with pytest.raises(TelegramAlertError):
            send_telegram_alert(
                chat_id="-1001234567890",
                bot_token=b"123456:ABC_def-ghi",
                event=_event(),
                opener=opener,
                timeout_seconds=timeout,
            )
    assert called is False
