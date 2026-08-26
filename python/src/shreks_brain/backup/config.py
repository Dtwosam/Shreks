from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path


_BACKUP_ENV_PREFIX = "SHREKS_BACKUP_"
_BACKUP_ROOT_KEY = "SHREKS_BACKUP_ROOT"
_RETENTION_COUNT_KEY = "SHREKS_BACKUP_RETENTION_COUNT"
_MAX_CAPTURE_ATTEMPTS_KEY = "SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS"
_ALLOWED_BACKUP_KEYS = frozenset(
    {
        _BACKUP_ROOT_KEY,
        _RETENTION_COUNT_KEY,
        _MAX_CAPTURE_ATTEMPTS_KEY,
    }
)
_OBSERVER_DATABASE_KEY = "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH"
_E11_KEY = "SHREKS_PAPER_CAMPAIGN_E11_PATH"
_CAMPAIGN_MANIFEST_KEY = "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH"
_RISK_CONTROL_KEY = "SHREKS_RISK_CONTROL_STATE_PATH"
_ALERT_STATE_KEY = "SHREKS_ALERTS_STATE_PATH"
_MAX_RETENTION_COUNT = 10_000
_MAX_CAPTURE_ATTEMPTS = 100


class BackupRuntimeConfigError(ValueError):
    """Raised when G8 backup runtime configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class BackupRuntimeConfig:
    backup_root: Path
    retention_count: int
    max_capture_attempts: int
    operational_database_path: Path
    e11_path: Path
    campaign_manifest_path: Path
    risk_control_path: Path
    alert_state_path: Path | None = None

    def __post_init__(self) -> None:
        for name in (
            "backup_root",
            "operational_database_path",
            "e11_path",
            "campaign_manifest_path",
            "risk_control_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise BackupRuntimeConfigError(f"{name} must be an absolute Path")
        if self.alert_state_path is not None and (
            not isinstance(self.alert_state_path, Path)
            or not self.alert_state_path.is_absolute()
        ):
            raise BackupRuntimeConfigError(
                "alert_state_path must be an absolute Path when supplied"
            )
        _bounded_positive_int(
            "retention_count", self.retention_count, maximum=_MAX_RETENTION_COUNT
        )
        _bounded_positive_int(
            "max_capture_attempts",
            self.max_capture_attempts,
            maximum=_MAX_CAPTURE_ATTEMPTS,
        )


def load_backup_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    base_directory: str | os.PathLike[str] | None = None,
) -> BackupRuntimeConfig:
    source = os.environ if env is None else env
    if not isinstance(source, Mapping):
        raise BackupRuntimeConfigError("backup environment must be a mapping")

    unsupported = sorted(
        key
        for key in source
        if isinstance(key, str)
        and key.startswith(_BACKUP_ENV_PREFIX)
        and key not in _ALLOWED_BACKUP_KEYS
    )
    if unsupported:
        raise BackupRuntimeConfigError(
            "unsupported backup runtime environment key(s): " + ", ".join(unsupported)
        )

    base = _base_directory(base_directory)
    return BackupRuntimeConfig(
        backup_root=_required_path(source, _BACKUP_ROOT_KEY, base),
        retention_count=_required_bounded_integer(
            source,
            _RETENTION_COUNT_KEY,
            maximum=_MAX_RETENTION_COUNT,
        ),
        max_capture_attempts=_required_bounded_integer(
            source,
            _MAX_CAPTURE_ATTEMPTS_KEY,
            maximum=_MAX_CAPTURE_ATTEMPTS,
        ),
        operational_database_path=_required_path(source, _OBSERVER_DATABASE_KEY, base),
        e11_path=_required_path(source, _E11_KEY, base),
        campaign_manifest_path=_required_path(source, _CAMPAIGN_MANIFEST_KEY, base),
        risk_control_path=_required_path(source, _RISK_CONTROL_KEY, base),
        alert_state_path=_optional_path(source, _ALERT_STATE_KEY, base),
    )


def _base_directory(value: str | os.PathLike[str] | None) -> Path:
    raw = Path.cwd() if value is None else Path(value)
    try:
        return raw.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise BackupRuntimeConfigError("backup base directory cannot be resolved") from error


def _required_path(env: Mapping[str, str], key: str, base: Path) -> Path:
    raw = env.get(key)
    if not isinstance(raw, str) or not raw.strip() or raw.strip() != raw:
        raise BackupRuntimeConfigError(f"required backup path is missing or malformed: {key}")
    return _resolve_path(raw, key, base)


def _optional_path(env: Mapping[str, str], key: str, base: Path) -> Path | None:
    raw = env.get(key)
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or not raw.strip() or raw.strip() != raw:
        raise BackupRuntimeConfigError(f"optional backup path is malformed: {key}")
    return _resolve_path(raw, key, base)


def _resolve_path(raw: str, key: str, base: Path) -> Path:
    try:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise BackupRuntimeConfigError(f"backup path cannot be resolved: {key}") from error


def _required_bounded_integer(
    env: Mapping[str, str],
    key: str,
    *,
    maximum: int,
) -> int:
    raw = env.get(key)
    if not isinstance(raw, str) or not raw or not raw.isascii() or not raw.isdecimal():
        raise BackupRuntimeConfigError(f"required backup integer is malformed: {key}")
    if len(raw) > 1 and raw.startswith("0"):
        raise BackupRuntimeConfigError(f"required backup integer is non-canonical: {key}")
    value = int(raw)
    _bounded_positive_int(key, value, maximum=maximum)
    return value


def _bounded_positive_int(name: str, value: object, *, maximum: int) -> None:
    if isinstance(value, bool) or type(value) is not int or value < 1 or value > maximum:
        raise BackupRuntimeConfigError(f"{name} must be an integer from 1 through {maximum}")
