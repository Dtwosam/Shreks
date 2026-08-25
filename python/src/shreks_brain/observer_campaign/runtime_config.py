from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import os
from pathlib import Path


_PAPER_CAMPAIGN_ENV_PREFIX = "SHREKS_PAPER_CAMPAIGN_"
_OBSERVER_DB_PATH_KEY = "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH"
_E11_PATH_KEY = "SHREKS_PAPER_CAMPAIGN_E11_PATH"
_MANIFEST_PATH_KEY = "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH"
_INTERVAL_SECONDS_KEY = "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS"
_MAX_CYCLES_KEY = "SHREKS_PAPER_CAMPAIGN_MAX_CYCLES"
_ALLOWED_ENV_KEYS = frozenset(
    {
        _OBSERVER_DB_PATH_KEY,
        _E11_PATH_KEY,
        _MANIFEST_PATH_KEY,
        _INTERVAL_SECONDS_KEY,
        _MAX_CYCLES_KEY,
    }
)


class ObserverPaperCampaignRuntimeConfigError(ValueError):
    """Raised when G1C operational runtime configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ObserverPaperCampaignRuntimeConfig:
    observer_database_path: Path
    evidence_path: Path
    manifest_path: Path
    cycle_interval_seconds: float
    max_cycles: int | None

    def __post_init__(self) -> None:
        for name in (
            "observer_database_path",
            "evidence_path",
            "manifest_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ObserverPaperCampaignRuntimeConfigError(
                    f"{name} must be an absolute Path"
                )

        if (
            isinstance(self.cycle_interval_seconds, bool)
            or not isinstance(self.cycle_interval_seconds, (int, float))
            or not math.isfinite(self.cycle_interval_seconds)
            or self.cycle_interval_seconds <= 0
        ):
            raise ObserverPaperCampaignRuntimeConfigError(
                "cycle interval must be a positive finite number"
            )

        if self.max_cycles is not None and (
            isinstance(self.max_cycles, bool)
            or not isinstance(self.max_cycles, int)
            or self.max_cycles <= 0
        ):
            raise ObserverPaperCampaignRuntimeConfigError(
                "cycle limit must be a positive integer when supplied"
            )


def load_observer_paper_campaign_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    base_directory: str | os.PathLike[str] | None = None,
) -> ObserverPaperCampaignRuntimeConfig:
    source = os.environ if env is None else env
    if not isinstance(source, Mapping):
        raise ObserverPaperCampaignRuntimeConfigError(
            "runtime environment must be a mapping"
        )

    unsupported = sorted(
        key
        for key in source
        if isinstance(key, str)
        and key.startswith(_PAPER_CAMPAIGN_ENV_PREFIX)
        and key not in _ALLOWED_ENV_KEYS
    )
    if unsupported:
        raise ObserverPaperCampaignRuntimeConfigError(
            "unsupported paper campaign runtime environment key(s): "
            + ", ".join(unsupported)
        )

    base = _resolve_base_directory(base_directory)
    observer_database_path = _required_path(source, _OBSERVER_DB_PATH_KEY, base)
    evidence_path = _required_path(source, _E11_PATH_KEY, base)
    manifest_path = _required_path(source, _MANIFEST_PATH_KEY, base)
    cycle_interval_seconds = _positive_interval(source, _INTERVAL_SECONDS_KEY)
    max_cycles = _optional_cycle_limit(source, _MAX_CYCLES_KEY)

    return ObserverPaperCampaignRuntimeConfig(
        observer_database_path=observer_database_path,
        evidence_path=evidence_path,
        manifest_path=manifest_path,
        cycle_interval_seconds=cycle_interval_seconds,
        max_cycles=max_cycles,
    )


def _resolve_base_directory(
    base_directory: str | os.PathLike[str] | None,
) -> Path:
    raw = Path.cwd() if base_directory is None else Path(base_directory)
    try:
        return raw.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ObserverPaperCampaignRuntimeConfigError(
            f"runtime base directory cannot be resolved: {error}"
        ) from error


def _required_path(
    env: Mapping[str, str],
    key: str,
    base_directory: Path,
) -> Path:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ObserverPaperCampaignRuntimeConfigError(
            f"required runtime environment value is missing: {key}"
        )

    try:
        path = Path(value.strip()).expanduser()
        if not path.is_absolute():
            path = base_directory / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ObserverPaperCampaignRuntimeConfigError(
            f"runtime path is malformed for {key}: {error}"
        ) from error


def _positive_interval(env: Mapping[str, str], key: str) -> float:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ObserverPaperCampaignRuntimeConfigError(
            f"required cycle interval is missing: {key}"
        )
    try:
        interval = float(value.strip())
    except ValueError as error:
        raise ObserverPaperCampaignRuntimeConfigError(
            "cycle interval must be a positive finite number"
        ) from error
    if not math.isfinite(interval) or interval <= 0:
        raise ObserverPaperCampaignRuntimeConfigError(
            "cycle interval must be a positive finite number"
        )
    return interval


def _optional_cycle_limit(env: Mapping[str, str], key: str) -> int | None:
    value = env.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ObserverPaperCampaignRuntimeConfigError(
            "cycle limit must be a positive integer when supplied"
        )
    stripped = value.strip()
    if not stripped:
        return None
    try:
        limit = int(stripped, 10)
    except ValueError as error:
        raise ObserverPaperCampaignRuntimeConfigError(
            "cycle limit must be a positive integer when supplied"
        ) from error
    if str(limit) != stripped and stripped != f"+{limit}":
        raise ObserverPaperCampaignRuntimeConfigError(
            "cycle limit must be a positive integer when supplied"
        )
    if limit <= 0:
        raise ObserverPaperCampaignRuntimeConfigError(
            "cycle limit must be a positive integer when supplied"
        )
    return limit
