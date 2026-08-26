from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import stat

from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
    ObserverPaperCampaignRuntimeConfigError,
    load_observer_paper_campaign_runtime_config,
)

_DASHBOARD_ENV_PREFIX = "SHREKS_DASHBOARD_"
_BIND_HOST_KEY = "SHREKS_DASHBOARD_BIND_HOST"
_PORT_KEY = "SHREKS_DASHBOARD_PORT"
_USERNAME_KEY = "SHREKS_DASHBOARD_USERNAME"
_PASSWORD_FILE_KEY = "SHREKS_DASHBOARD_PASSWORD_FILE"
_TELEMETRY_PATH_KEY = "SHREKS_DASHBOARD_TELEMETRY_PATH"
_MAX_TRADES_KEY = "SHREKS_DASHBOARD_MAX_TRADES"
_ALLOWED_DASHBOARD_KEYS = frozenset({
    _BIND_HOST_KEY,
    _PORT_KEY,
    _USERNAME_KEY,
    _PASSWORD_FILE_KEY,
    _TELEMETRY_PATH_KEY,
    _MAX_TRADES_KEY,
})
_MAX_PASSWORD_FILE_BYTES = 4096
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


class DashboardRuntimeConfigError(ValueError):
    """Raised when the G5 dashboard runtime configuration is unsafe."""


@dataclass(frozen=True, slots=True)
class DashboardRuntimeConfig:
    bind_host: str
    port: int
    username: str
    password_file: Path
    telemetry_path: Path
    max_trades: int
    paper_runtime_config: ObserverPaperCampaignRuntimeConfig

    def __post_init__(self) -> None:
        if self.bind_host not in _LOOPBACK_HOSTS:
            raise DashboardRuntimeConfigError("dashboard bind host must be explicit loopback")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1024 <= self.port <= 65535:
            raise DashboardRuntimeConfigError("dashboard port must be an integer in 1024..65535")
        _validate_username(self.username)
        for name in ("password_file", "telemetry_path"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise DashboardRuntimeConfigError(f"{name} must be an absolute Path")
        if isinstance(self.max_trades, bool) or not isinstance(self.max_trades, int) or not 1 <= self.max_trades <= 500:
            raise DashboardRuntimeConfigError("dashboard max trades must be an integer in 1..500")
        if type(self.paper_runtime_config) is not ObserverPaperCampaignRuntimeConfig:
            raise DashboardRuntimeConfigError("paper_runtime_config must be exact")


def load_dashboard_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    base_directory: str | os.PathLike[str] | None = None,
) -> DashboardRuntimeConfig:
    source = os.environ if env is None else env
    if not isinstance(source, Mapping):
        raise DashboardRuntimeConfigError("dashboard environment must be a mapping")
    unsupported = sorted(
        key for key in source
        if isinstance(key, str)
        and key.startswith(_DASHBOARD_ENV_PREFIX)
        and key not in _ALLOWED_DASHBOARD_KEYS
    )
    if unsupported:
        raise DashboardRuntimeConfigError(
            "unsupported dashboard runtime environment key(s): " + ", ".join(unsupported)
        )
    base = _base_directory(base_directory)
    bind_host = _required_text(source, _BIND_HOST_KEY)
    if bind_host not in _LOOPBACK_HOSTS:
        raise DashboardRuntimeConfigError("dashboard bind host must be explicit loopback")
    port = _bounded_integer(source, _PORT_KEY, 1024, 65535, "dashboard port")
    username = _required_text(source, _USERNAME_KEY)
    _validate_username(username)
    password_file = _password_path(source, base)
    telemetry_path = _required_path(source, _TELEMETRY_PATH_KEY, base)
    max_trades = _bounded_integer(source, _MAX_TRADES_KEY, 1, 500, "dashboard max trades")
    try:
        paper_runtime_config = load_observer_paper_campaign_runtime_config(source, base_directory=base)
    except ObserverPaperCampaignRuntimeConfigError as error:
        raise DashboardRuntimeConfigError("paper runtime configuration is invalid") from error
    return DashboardRuntimeConfig(
        bind_host=bind_host,
        port=port,
        username=username,
        password_file=password_file,
        telemetry_path=telemetry_path,
        max_trades=max_trades,
        paper_runtime_config=paper_runtime_config,
    )


def load_dashboard_password(config: DashboardRuntimeConfig) -> bytes:
    if type(config) is not DashboardRuntimeConfig:
        raise DashboardRuntimeConfigError("config must be an exact DashboardRuntimeConfig")
    _validate_password_file(config.password_file)
    try:
        payload = config.password_file.read_bytes()
    except OSError as error:
        raise DashboardRuntimeConfigError("dashboard password file cannot be read") from error
    if payload.endswith(b"\n"):
        payload = payload[:-1]
        if payload.endswith(b"\r"):
            payload = payload[:-1]
    if not payload or b"\n" in payload or b"\r" in payload:
        raise DashboardRuntimeConfigError("dashboard password file must contain one non-empty line")
    if len(payload) > _MAX_PASSWORD_FILE_BYTES:
        raise DashboardRuntimeConfigError("dashboard password file is too large")
    return payload


def _base_directory(value: str | os.PathLike[str] | None) -> Path:
    raw = Path.cwd() if value is None else Path(value)
    try:
        return raw.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise DashboardRuntimeConfigError("dashboard base directory cannot be resolved") from error


def _required_text(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not isinstance(value, str):
        raise DashboardRuntimeConfigError(f"required dashboard value is missing: {key}")
    return value


def _validate_username(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or ":" in value
        or any(ord(character) < 33 or ord(character) > 126 for character in value)
    ):
        raise DashboardRuntimeConfigError("dashboard username must be printable ASCII without colon")


def _bounded_integer(env: Mapping[str, str], key: str, minimum: int, maximum: int, label: str) -> int:
    raw = env.get(key)
    if not isinstance(raw, str) or not raw or not raw.isascii() or not raw.isdecimal():
        raise DashboardRuntimeConfigError(f"{label} must be a canonical integer")
    value = int(raw, 10)
    if not minimum <= value <= maximum:
        raise DashboardRuntimeConfigError(f"{label} is outside the allowed range")
    return value


def _required_path(env: Mapping[str, str], key: str, base: Path) -> Path:
    raw = env.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise DashboardRuntimeConfigError(f"required dashboard path is missing: {key}")
    try:
        path = Path(raw.strip()).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise DashboardRuntimeConfigError(f"dashboard path is malformed: {key}") from error


def _password_path(env: Mapping[str, str], base: Path) -> Path:
    raw = env.get(_PASSWORD_FILE_KEY)
    if not isinstance(raw, str) or not raw.strip():
        raise DashboardRuntimeConfigError(f"required dashboard path is missing: {_PASSWORD_FILE_KEY}")
    try:
        path = Path(raw.strip()).expanduser()
        if not path.is_absolute():
            path = base / path
        path = path.absolute()
    except (OSError, RuntimeError, ValueError) as error:
        raise DashboardRuntimeConfigError("dashboard password file path is malformed") from error
    if path.is_symlink():
        raise DashboardRuntimeConfigError("dashboard password file must not be a symlink")
    _validate_password_file(path)
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise DashboardRuntimeConfigError("dashboard password file cannot be resolved") from error


def _validate_password_file(path: Path) -> None:
    if path.is_symlink():
        raise DashboardRuntimeConfigError("dashboard password file must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as error:
        raise DashboardRuntimeConfigError("dashboard password file is unavailable") from error
    if not path.is_file():
        raise DashboardRuntimeConfigError("dashboard password file must be a regular file")
    if metadata.st_size <= 0 or metadata.st_size > _MAX_PASSWORD_FILE_BYTES:
        raise DashboardRuntimeConfigError("dashboard password file size is invalid")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & (stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        raise DashboardRuntimeConfigError("dashboard password file permissions are unsafe")
