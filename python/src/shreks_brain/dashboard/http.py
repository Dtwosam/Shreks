from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import socket
import time
from typing import Any
from urllib.parse import unquote_to_bytes, urlsplit

from shreks_brain.risk_control import (
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    RiskControlCommandError,
    RiskControlConflictError,
    RiskControlStateError,
    apply_operator_risk_control_command,
    load_operator_risk_control_state,
)

from .config import DashboardRuntimeConfig, load_dashboard_password
from .models import DashboardSourceConfig
from .page import render_dashboard_page
from .source import load_dashboard_snapshot, load_dashboard_trade

_SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    (
        "Content-Security-Policy",
        "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'none'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
    ),
)
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_HTML_CONTENT_TYPE = "text/html; charset=utf-8"
_CONTROL_STATE_PATH = "/api/v1/operator-controls"
_HALT_PATH = "/api/v1/operator-controls/halt-new-entries"
_KILL_PATH = "/api/v1/operator-controls/emergency-kill"
_MAX_CONTROL_BODY_BYTES = 256
_MAX_REQUEST_BODY_BYTES = 4096
_DASHBOARD_HALT_REASON = "authenticated dashboard halt"
_DASHBOARD_KILL_REASON = "authenticated dashboard emergency kill"


@dataclass(frozen=True, slots=True)
class DashboardHTTPResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def __post_init__(self) -> None:
        if isinstance(self.status, bool) or not isinstance(self.status, int) or not 100 <= self.status <= 599:
            raise ValueError("status must be an HTTP status integer")
        if not isinstance(self.headers, tuple) or not all(
            isinstance(item, tuple)
            and len(item) == 2
            and all(isinstance(value, str) and value for value in item)
            for item in self.headers
        ):
            raise ValueError("headers must contain non-empty string pairs")
        if not isinstance(self.body, bytes):
            raise ValueError("body must be bytes")


class DashboardApplication:
    """Authenticated operator dashboard with narrowly scoped G7 safety controls."""

    __slots__ = (
        "_config",
        "_source_config",
        "_expected_credentials",
        "_csrf_token",
        "_clock_unix_ms",
    )

    def __init__(
        self,
        config: DashboardRuntimeConfig,
        password: bytes,
        *,
        csrf_token: str | None = None,
        clock_unix_ms: Callable[[], int] | None = None,
    ) -> None:
        if type(config) is not DashboardRuntimeConfig:
            raise TypeError("config must be an exact DashboardRuntimeConfig")
        if not isinstance(password, bytes) or not password or b"\r" in password or b"\n" in password:
            raise ValueError("dashboard password bytes are invalid")
        token = secrets.token_urlsafe(32) if csrf_token is None else csrf_token
        if (
            type(token) is not str
            or len(token) < 32
            or len(token) > 256
            or token.strip() != token
            or any(ord(character) < 33 or ord(character) > 126 for character in token)
        ):
            raise ValueError("dashboard CSRF token is invalid")
        if clock_unix_ms is not None and not callable(clock_unix_ms):
            raise TypeError("clock_unix_ms must be callable or None")
        self._config = config
        self._source_config = DashboardSourceConfig(
            telemetry_path=config.telemetry_path,
            paper_runtime_config=config.paper_runtime_config,
        )
        self._expected_credentials = config.username.encode("ascii") + b":" + bytes(password)
        self._csrf_token = token
        self._clock_unix_ms = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms

    def dispatch(
        self,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> DashboardHTTPResponse:
        if not self._authorized(headers):
            return _json_response(
                401,
                {"error": "AUTH_REQUIRED"},
                extra_headers=(("WWW-Authenticate", 'Basic realm="Shreks Operator", charset="UTF-8"'),),
            )
        path = _request_path(target)
        if path is None:
            return _json_response(400, {"error": "BAD_REQUEST"})

        if method == "POST":
            if path not in (_HALT_PATH, _KILL_PATH):
                return _json_response(
                    405,
                    {"error": "METHOD_NOT_ALLOWED"},
                    extra_headers=(("Allow", "GET"),),
                )
            return self._control_command_response(path, headers, body)

        if method != "GET":
            return _json_response(
                405,
                {"error": "METHOD_NOT_ALLOWED"},
                extra_headers=(("Allow", "GET"),),
            )
        if path == "/":
            return _html_response(render_dashboard_page())
        if path == "/api/v1/snapshot":
            return self._snapshot_response(include_trades=False)
        if path == "/api/v1/trades":
            return self._snapshot_response(include_trades=True)
        if path == _CONTROL_STATE_PATH:
            return self._control_state_response()
        prefix = "/api/v1/trades/"
        if path.startswith(prefix):
            position_id = _decode_position_id(path[len(prefix):])
            if position_id is None:
                return _json_response(404, {"error": "NOT_FOUND"})
            try:
                detail = load_dashboard_trade(self._source_config, position_id)
            except Exception:
                return _json_response(503, {"error": "SOURCE_UNAVAILABLE"})
            if detail is None:
                return _json_response(404, {"error": "NOT_FOUND"})
            return _json_response(200, _jsonable(detail))
        return _json_response(404, {"error": "NOT_FOUND"})

    def _snapshot_response(self, *, include_trades: bool) -> DashboardHTTPResponse:
        try:
            source = load_dashboard_snapshot(
                self._source_config,
                max_trades=self._config.max_trades,
            )
        except Exception:
            return _json_response(503, {"error": "SOURCE_UNAVAILABLE"})
        if include_trades:
            payload: object = {"trades": source.trades}
        else:
            payload = {
                "telemetry": source.telemetry,
                "telemetry_file_mtime_ns": source.telemetry_file_mtime_ns,
            }
        return _json_response(200, _jsonable(payload))

    def _control_state_response(self) -> DashboardHTTPResponse:
        path = self._config.paper_runtime_config.risk_control_path
        if path is None:
            return _json_response(503, {"error": "CONTROL_UNAVAILABLE"})
        try:
            state = load_operator_risk_control_state(path)
        except (RiskControlStateError, OSError, TypeError, ValueError):
            return _json_response(503, {"error": "CONTROL_UNAVAILABLE"})
        payload = _jsonable(state)
        if not isinstance(payload, dict):
            return _json_response(503, {"error": "CONTROL_UNAVAILABLE"})
        payload["csrf_token"] = self._csrf_token
        return _json_response(200, payload)

    def _control_command_response(
        self,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> DashboardHTTPResponse:
        state_path = self._config.paper_runtime_config.risk_control_path
        if state_path is None:
            return _json_response(503, {"error": "CONTROL_UNAVAILABLE"})
        if not self._valid_csrf(headers):
            return _json_response(403, {"error": "CSRF_REQUIRED"})
        expected_revision = _control_expected_revision(headers, body)
        if expected_revision is None:
            return _json_response(400, {"error": "BAD_REQUEST"})
        try:
            observed_at_unix_ms = self._control_timestamp()
            if path == _HALT_PATH:
                command = OperatorRiskControlCommand.HALT_NEW_ENTRIES
                reason = _DASHBOARD_HALT_REASON
            else:
                command = OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH
                reason = _DASHBOARD_KILL_REASON
            state = apply_operator_risk_control_command(
                state_path,
                command,
                expected_revision=expected_revision,
                observed_at_unix_ms=observed_at_unix_ms,
                source=OperatorRiskControlSource.DASHBOARD,
                reason=reason,
            )
        except RiskControlConflictError:
            return _json_response(409, {"error": "REVISION_CONFLICT"})
        except RiskControlCommandError:
            return _json_response(400, {"error": "CONTROL_REJECTED"})
        except (RiskControlStateError, OSError, TypeError, ValueError):
            return _json_response(503, {"error": "CONTROL_UNAVAILABLE"})
        return _json_response(200, _jsonable(state))

    def _control_timestamp(self) -> int:
        try:
            value = self._clock_unix_ms()
        except Exception as error:
            raise RiskControlStateError("dashboard control clock failed") from error
        if isinstance(value, bool) or type(value) is not int or value < 0:
            raise RiskControlStateError("dashboard control clock is invalid")
        return value

    def _valid_csrf(self, headers: Mapping[str, str]) -> bool:
        supplied = _header_value(headers, "x-shreks-csrf")
        if type(supplied) is not str:
            return False
        return hmac.compare_digest(supplied.encode("utf-8"), self._csrf_token.encode("utf-8"))

    def _authorized(self, headers: Mapping[str, str]) -> bool:
        authorization = _header_value(headers, "authorization")
        if not isinstance(authorization, str) or not authorization.startswith("Basic "):
            return False
        encoded = authorization[6:]
        if not encoded or encoded.strip() != encoded or any(character.isspace() for character in encoded):
            return False
        try:
            supplied = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return False
        return hmac.compare_digest(supplied, self._expected_credentials)


def run_dashboard_server(config: DashboardRuntimeConfig) -> None:
    if type(config) is not DashboardRuntimeConfig:
        raise TypeError("config must be an exact DashboardRuntimeConfig")
    password = load_dashboard_password(config)
    application = DashboardApplication(config, password)
    handler_type = _handler_for(application)
    server_type: type[ThreadingHTTPServer]
    if config.bind_host == "::1":
        server_type = _IPv6ThreadingHTTPServer
    else:
        server_type = ThreadingHTTPServer
    with server_type((config.bind_host, config.port), handler_type) as server:
        server.serve_forever(poll_interval=0.5)


class _IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def _handler_for(application: DashboardApplication) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._dispatch()

        def do_HEAD(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def do_PUT(self) -> None:
            self._dispatch()

        def do_PATCH(self) -> None:
            self._dispatch()

        def do_DELETE(self) -> None:
            self._dispatch()

        def do_OPTIONS(self) -> None:
            self._dispatch()

        def _dispatch(self) -> None:
            request_headers = {name: value for name, value in self.headers.items()}
            body = self._request_body()
            if body is None:
                response = _json_response(400, {"error": "BAD_REQUEST"})
            else:
                response = application.dispatch(
                    self.command,
                    self.path,
                    request_headers,
                    body,
                )
            self.send_response(response.status)
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD" and response.body:
                self.wfile.write(response.body)

        def _request_body(self) -> bytes | None:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return b""
            try:
                length = int(raw_length, 10)
            except (TypeError, ValueError):
                return None
            if length < 0 or length > _MAX_REQUEST_BODY_BYTES:
                return None
            try:
                return self.rfile.read(length)
            except OSError:
                return None

        def log_message(self, _format: str, *args: object) -> None:
            return

    return DashboardRequestHandler


def _request_path(target: object) -> str | None:
    if not isinstance(target, str) or not target or any(ord(character) < 32 for character in target):
        return None
    try:
        parsed = urlsplit(target)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc:
        return None
    return parsed.path


def _decode_position_id(segment: str) -> str | None:
    if not segment or "/" in segment:
        return None
    try:
        value = unquote_to_bytes(segment).decode("utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError):
        return None
    if not value or "/" in value or value.strip() != value:
        return None
    return value


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    try:
        values = [
            value
            for header_name, value in headers.items()
            if isinstance(header_name, str) and header_name.lower() == name
        ]
    except Exception:
        return None
    if len(values) != 1 or type(values[0]) is not str:
        return None
    return values[0]


def _control_expected_revision(
    headers: Mapping[str, str],
    body: object,
) -> int | None:
    if type(body) is not bytes or not body or len(body) > _MAX_CONTROL_BODY_BYTES:
        return None
    content_type = _header_value(headers, "content-type")
    if content_type is None or content_type.split(";", 1)[0].strip().lower() != "application/json":
        return None
    try:
        document = json.loads(body.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if type(document) is not dict or set(document) != {"expected_revision"}:
        return None
    value = document["expected_revision"]
    if isinstance(value, bool) or type(value) is not int or value < 0:
        return None
    return value


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constants are forbidden")


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("dashboard JSON object keys must be strings")
            result[key] = _jsonable(nested)
        return result
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("dashboard value is not JSON serializable")


def _json_response(
    status: int,
    payload: object,
    *,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> DashboardHTTPResponse:
    body = (
        json.dumps(
            _jsonable(payload),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    headers = (
        ("Content-Type", _JSON_CONTENT_TYPE),
        ("Content-Length", str(len(body))),
        *_SECURITY_HEADERS,
        *extra_headers,
    )
    return DashboardHTTPResponse(status=status, headers=tuple(headers), body=body)


def _html_response(body: bytes) -> DashboardHTTPResponse:
    if not isinstance(body, bytes):
        raise TypeError("dashboard page must be bytes")
    headers = (
        ("Content-Type", _HTML_CONTENT_TYPE),
        ("Content-Length", str(len(body))),
        *_SECURITY_HEADERS,
    )
    return DashboardHTTPResponse(status=200, headers=tuple(headers), body=body)
