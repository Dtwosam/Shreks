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


_ALERT_ENV_PREFIX = "SHREKS_ALERTS_"
_CHAT_ID_KEY = "SHREKS_ALERTS_TELEGRAM_CHAT_ID"
_TOKEN_FILE_KEY = "SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE"
_STATE_PATH_KEY = "SHREKS_ALERTS_STATE_PATH"
_MARKET_STALE_MS_KEY = "SHREKS_ALERTS_MARKET_STALE_MS"
_PROVIDER_FAILURE_MIN_KEY = "SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE"
_TELEMETRY_PATH_KEY = "SHREKS_ALERTS_TELEMETRY_PATH"
_ALLOWED_ALERT_KEYS = frozenset(
    {
        _CHAT_ID_KEY,
        _TOKEN_FILE_KEY,
        _STATE_PATH_KEY,
        _MARKET_STALE_MS_KEY,
        _PROVIDER_FAILURE_MIN_KEY,
        _TELEMETRY_PATH_KEY,
    }
)
_MAX_TOKEN_FILE_BYTES = 4096
_MAX_CHAT_ID_CHARS = 256


class AlertRuntimeConfigError(ValueError):
    """Raised when G6 alert runtime configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class AlertRuntimeConfig:
    telemetry_path: Path
    state_path: Path
    telegram_chat_id: str
    telegram_bot_token_file: Path
    market_stale_ms: int
    provider_failure_min_consecutive: int
    paper_runtime_config: ObserverPaperCampaignRuntimeConfig

    def __post_init__(self) -> None:
        for name in ("telemetry_path", "state_path", "telegram_bot_token_file"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise AlertRuntimeConfigError(f"{name} must be an absolute Path")
        _validate_chat_id(self.telegram_chat_id)
        _require_positive_int("market stale ms", self.market_stale_ms)
        _require_positive_int(
            "provider failure minimum consecutive",
            self.provider_failure_min_consecutive,
        )
        if type(self.paper_runtime_config) is not ObserverPaperCampaignRuntimeConfig:
            raise AlertRuntimeConfigError("paper_runtime_config must be exact")


def load_alert_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    base_directory: str | os.PathLike[str] | None = None,
) -> AlertRuntimeConfig:
    source = os.environ if env is None else env
    if not isinstance(source, Mapping):
        raise AlertRuntimeConfigError("alert environment must be a mapping")

    unsupported = sorted(
        key
        for key in source
        if isinstance(key, str)
        and key.startswith(_ALERT_ENV_PREFIX)
        and key not in _ALLOWED_ALERT_KEYS
    )
    if unsupported:
        raise AlertRuntimeConfigError(
            "unsupported alert runtime environment key(s): " + ", ".join(unsupported)
        )

    base = _base_directory(base_directory)
    telegram_chat_id = _required_text(source, _CHAT_ID_KEY, "Telegram chat ID")
    _validate_chat_id(telegram_chat_id)
    telegram_bot_token_file = _token_path(source, base)
    state_path = _state_path(source, base)
    telemetry_path = _required_path(source, _TELEMETRY_PATH_KEY, base, "telemetry")
    market_stale_ms = _canonical_positive_integer(
        source, _MARKET_STALE_MS_KEY, "market stale ms"
    )
    provider_failure_min_consecutive = _canonical_positive_integer(
        source,
        _PROVIDER_FAILURE_MIN_KEY,
        "provider failure minimum consecutive",
    )
    try:
        paper_runtime_config = load_observer_paper_campaign_runtime_config(
            source,
            base_directory=base,
        )
    except ObserverPaperCampaignRuntimeConfigError as error:
        raise AlertRuntimeConfigError("paper runtime configuration is invalid") from error

    return AlertRuntimeConfig(
        telemetry_path=telemetry_path,
        state_path=state_path,
        telegram_chat_id=telegram_chat_id,
        telegram_bot_token_file=telegram_bot_token_file,
        market_stale_ms=market_stale_ms,
        provider_failure_min_consecutive=provider_failure_min_consecutive,
        paper_runtime_config=paper_runtime_config,
    )


def load_telegram_bot_token(config: AlertRuntimeConfig) -> bytes:
    if type(config) is not AlertRuntimeConfig:
        raise AlertRuntimeConfigError("config must be an exact AlertRuntimeConfig")
    _validate_token_file(config.telegram_bot_token_file)
    try:
        payload = config.telegram_bot_token_file.read_bytes()
    except OSError as error:
        raise AlertRuntimeConfigError("Telegram bot token file cannot be read") from error

    if payload.endswith(b"\r\n"):
        payload = payload[:-2]
    elif payload.endswith(b"\n"):
        payload = payload[:-1]
    if (
        not payload
        or b"\n" in payload
        or b"\r" in payload
        or len(payload) > _MAX_TOKEN_FILE_BYTES
        or any(byte < 33 or byte > 126 for byte in payload)
    ):
        raise AlertRuntimeConfigError(
            "Telegram bot token file must contain one non-empty line of printable ASCII"
        )
    return payload


def _base_directory(value: str | os.PathLike[str] | None) -> Path:
    raw = Path.cwd() if value is None else Path(value)
    try:
        return raw.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise AlertRuntimeConfigError("alert base directory cannot be resolved") from error


def _required_text(env: Mapping[str, str], key: str, label: str) -> str:
    value = env.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AlertRuntimeConfigError(f"required {label} is missing or malformed")
    return value


def _validate_chat_id(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > _MAX_CHAT_ID_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise AlertRuntimeConfigError(
            "Telegram chat ID must be bounded non-control text"
        )


def _canonical_positive_integer(
    env: Mapping[str, str],
    key: str,
    label: str,
) -> int:
    raw = env.get(key)
    if (
        not isinstance(raw, str)
        or not raw
        or not raw.isascii()
        or not raw.isdecimal()
    ):
        raise AlertRuntimeConfigError(f"{label} must be a canonical positive integer")
    value = int(raw, 10)
    if value <= 0 or str(value) != raw:
        raise AlertRuntimeConfigError(f"{label} must be a canonical positive integer")
    return value


def _required_path(
    env: Mapping[str, str],
    key: str,
    base: Path,
    label: str,
) -> Path:
    raw = env.get(key)
    if not isinstance(raw, str) or not raw or raw.strip() != raw:
        raise AlertRuntimeConfigError(f"required alert {label} path is missing")
    try:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise AlertRuntimeConfigError(f"alert {label} path is malformed") from error


def _state_path(env: Mapping[str, str], base: Path) -> Path:
    path = _required_path(env, _STATE_PATH_KEY, base, "state")
    if not path.name:
        raise AlertRuntimeConfigError("alert state path must name a file")
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise AlertRuntimeConfigError("alert state parent directory is unavailable")
    if path.is_symlink():
        raise AlertRuntimeConfigError("alert state path must not be a symlink")
    if path.exists() and not path.is_file():
        raise AlertRuntimeConfigError("alert state path must name a file")
    return path


def _token_path(env: Mapping[str, str], base: Path) -> Path:
    raw = env.get(_TOKEN_FILE_KEY)
    if not isinstance(raw, str) or not raw or raw.strip() != raw:
        raise AlertRuntimeConfigError("required Telegram bot token file path is missing")
    try:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = base / path
        path = path.absolute()
    except (OSError, RuntimeError, ValueError) as error:
        raise AlertRuntimeConfigError("Telegram bot token file path is malformed") from error
    if path.is_symlink():
        raise AlertRuntimeConfigError("Telegram bot token file must not be a symlink")
    _validate_token_file(path)
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise AlertRuntimeConfigError("Telegram bot token file cannot be resolved") from error


def _validate_token_file(path: Path) -> None:
    if path.is_symlink():
        raise AlertRuntimeConfigError("Telegram bot token file must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as error:
        raise AlertRuntimeConfigError("Telegram bot token file is unavailable") from error
    if not path.is_file():
        raise AlertRuntimeConfigError("Telegram bot token file must be a regular file")
    if metadata.st_size <= 0 or metadata.st_size > _MAX_TOKEN_FILE_BYTES:
        raise AlertRuntimeConfigError("Telegram bot token file size is invalid")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & (stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        raise AlertRuntimeConfigError("Telegram bot token file permissions are unsafe")


def _require_positive_int(label: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AlertRuntimeConfigError(f"{label} must be a positive integer")
