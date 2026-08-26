from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from typing import Any
from urllib.parse import unquote_to_bytes, urlsplit

from .config import DashboardRuntimeConfig, load_dashboard_password
from .models import DashboardSourceConfig
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
    """Authenticated, read-only request dispatcher for the G5 operator dashboard."""

    __slots__ = ("_config", "_source_config", "_expected_credentials")

    def __init__(self, config: DashboardRuntimeConfig, password: bytes) -> None:
        if type(config) is not DashboardRuntimeConfig:
            raise TypeError("config must be an exact DashboardRuntimeConfig")
        if not isinstance(password, bytes) or not password or b"\r" in password or b"\n" in password:
            raise ValueError("dashboard password bytes are invalid")
        self._config = config
        self._source_config = DashboardSourceConfig(
            telemetry_path=config.telemetry_path,
            paper_runtime_config=config.paper_runtime_config,
        )
        self._expected_credentials = config.username.encode("ascii") + b":" + bytes(password)

    def dispatch(
        self,
        method: str,
        target: str,
        headers: Mapping[str, str],
    ) -> DashboardHTTPResponse:
        if not self._authorized(headers):
            return _json_response(
                401,
                {"error": "AUTH_REQUIRED"},
                extra_headers=(("WWW-Authenticate", 'Basic realm="Shreks Operator", charset="UTF-8"'),),
            )
        if method != "GET":
            return _json_response(
                405,
                {"error": "METHOD_NOT_ALLOWED"},
                extra_headers=(("Allow", "GET"),),
            )
        path = _request_path(target)
        if path is None:
            return _json_response(400, {"error": "BAD_REQUEST"})
        if path == "/api/v1/snapshot":
            return self._snapshot_response(include_trades=False)
        if path == "/api/v1/trades":
            return self._snapshot_response(include_trades=True)
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

    def _authorized(self, headers: Mapping[str, str]) -> bool:
        try:
            authorization = next(
                (
                    value
                    for name, value in headers.items()
                    if isinstance(name, str) and name.lower() == "authorization"
                ),
                None,
            )
        except Exception:
            return False
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
            response = application.dispatch(self.command, self.path, request_headers)
            self.send_response(response.status)
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD" and response.body:
                self.wfile.write(response.body)

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
