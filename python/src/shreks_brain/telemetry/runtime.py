from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import time

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfigError,
    load_observer_paper_campaign_runtime_config,
)

from .models import TelemetrySnapshot
from .snapshot import (
    TelemetrySnapshotError,
    assemble_telemetry_snapshot,
    write_telemetry_snapshot,
)
from .sources import (
    TelemetrySourceConfig,
    TelemetrySourceError,
    collect_telemetry_sources,
)


_TELEMETRY_ENV_PREFIX = "SHREKS_TELEMETRY_"
_PROOF_PATH_KEY = "SHREKS_TELEMETRY_PROOF_PATH"
_PROMOTION_PATH_KEY = "SHREKS_TELEMETRY_PROMOTION_PATH"
_OUTPUT_PATH_KEY = "SHREKS_TELEMETRY_OUTPUT_PATH"
_EVALUATION_POLICY_VERSION_KEY = "SHREKS_TELEMETRY_EVALUATION_POLICY_VERSION"
_CALIBRATION_BUCKET_COUNT_KEY = "SHREKS_TELEMETRY_CALIBRATION_BUCKET_COUNT"
_ALLOWED_TELEMETRY_ENV_KEYS = frozenset(
    {
        _PROOF_PATH_KEY,
        _PROMOTION_PATH_KEY,
        _OUTPUT_PATH_KEY,
        _EVALUATION_POLICY_VERSION_KEY,
        _CALIBRATION_BUCKET_COUNT_KEY,
    }
)


class TelemetryRuntimeConfigError(ValueError):
    """Raised when G4 telemetry runtime configuration or execution is unsafe."""


@dataclass(frozen=True, slots=True)
class TelemetryRuntimeConfig:
    source_config: TelemetrySourceConfig
    output_path: Path
    evaluation_policy_version: str
    calibration_bucket_count: int

    def __post_init__(self) -> None:
        if type(self.source_config) is not TelemetrySourceConfig:
            raise TelemetryRuntimeConfigError(
                "source_config must be an exact TelemetrySourceConfig"
            )
        if not isinstance(self.output_path, Path) or not self.output_path.is_absolute():
            raise TelemetryRuntimeConfigError("telemetry output path must be absolute")
        if (
            not isinstance(self.evaluation_policy_version, str)
            or not self.evaluation_policy_version.strip()
        ):
            raise TelemetryRuntimeConfigError(
                "telemetry evaluation policy version must be non-empty"
            )
        if (
            isinstance(self.calibration_bucket_count, bool)
            or not isinstance(self.calibration_bucket_count, int)
            or not 2 <= self.calibration_bucket_count <= 100
        ):
            raise TelemetryRuntimeConfigError(
                "telemetry calibration bucket count must be between 2 and 100"
            )


@dataclass(frozen=True, slots=True)
class TelemetryRuntimePreflight:
    paper_run_id: str
    accounting_status: str
    live_state: str = "DISABLED"

    def __post_init__(self) -> None:
        if not isinstance(self.paper_run_id, str) or not self.paper_run_id.strip():
            raise TelemetryRuntimeConfigError("paper_run_id must be non-empty")
        if self.accounting_status not in ("VALID", "INCOMPLETE"):
            raise TelemetryRuntimeConfigError(
                "accounting_status must be VALID or INCOMPLETE"
            )
        if self.live_state != "DISABLED":
            raise TelemetryRuntimeConfigError("telemetry runtime must remain live-disabled")


def load_telemetry_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    base_directory: str | os.PathLike[str] | None = None,
) -> TelemetryRuntimeConfig:
    source = os.environ if env is None else env
    if not isinstance(source, Mapping):
        raise TelemetryRuntimeConfigError("telemetry environment must be a mapping")

    unsupported = sorted(
        key
        for key in source
        if isinstance(key, str)
        and key.startswith(_TELEMETRY_ENV_PREFIX)
        and key not in _ALLOWED_TELEMETRY_ENV_KEYS
    )
    if unsupported:
        raise TelemetryRuntimeConfigError(
            "unsupported telemetry environment key(s): " + ", ".join(unsupported)
        )

    base = _resolve_base_directory(base_directory)
    try:
        runtime_config = load_observer_paper_campaign_runtime_config(
            source,
            base_directory=base,
        )
    except ObserverPaperCampaignRuntimeConfigError as error:
        raise TelemetryRuntimeConfigError(
            "paper campaign runtime configuration is invalid"
        ) from error

    proof_path = _required_path(source, _PROOF_PATH_KEY, base)
    promotion_path = _required_path(source, _PROMOTION_PATH_KEY, base)
    output_path = _required_path(source, _OUTPUT_PATH_KEY, base)
    evaluation_policy_version = _required_text(
        source, _EVALUATION_POLICY_VERSION_KEY
    )
    calibration_bucket_count = _required_bucket_count(
        source, _CALIBRATION_BUCKET_COUNT_KEY
    )

    return TelemetryRuntimeConfig(
        source_config=TelemetrySourceConfig(
            runtime_config=runtime_config,
            proof_path=proof_path,
            promotion_path=promotion_path,
        ),
        output_path=output_path,
        evaluation_policy_version=evaluation_policy_version,
        calibration_bucket_count=calibration_bucket_count,
    )


def preflight_telemetry_runtime(
    config: TelemetryRuntimeConfig,
    *,
    as_of_unix_ms: int,
) -> TelemetryRuntimePreflight:
    _require_runtime_config(config)
    _require_timestamp(as_of_unix_ms)
    try:
        sources = collect_telemetry_sources(
            config.source_config,
            as_of_unix_ms=as_of_unix_ms,
        )
    except (TelemetrySourceError, OSError, TypeError, ValueError) as error:
        raise TelemetryRuntimeConfigError(
            "telemetry preflight source validation failed"
        ) from error
    return TelemetryRuntimePreflight(
        paper_run_id=sources.manifest.paper_run_id,
        accounting_status=sources.accounting_status,
    )


def run_telemetry_once(
    config: TelemetryRuntimeConfig,
    *,
    as_of_unix_ms: int,
) -> TelemetrySnapshot:
    _require_runtime_config(config)
    _require_timestamp(as_of_unix_ms)
    try:
        sources = collect_telemetry_sources(
            config.source_config,
            as_of_unix_ms=as_of_unix_ms,
        )
        policy = TradingEvaluationPolicy(
            version=config.evaluation_policy_version,
            starting_equity_usd=sources.state.ledger.starting_cash_usd,
            calibration_bucket_count=config.calibration_bucket_count,
        )
        snapshot = assemble_telemetry_snapshot(
            sources,
            evaluation_policy=policy,
            generated_at_unix_ms=as_of_unix_ms,
        )
        write_telemetry_snapshot(snapshot, config.output_path)
        return snapshot
    except (TelemetrySourceError, TelemetrySnapshotError, OSError, TypeError, ValueError) as error:
        raise TelemetryRuntimeConfigError("telemetry snapshot generation failed") from error


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args not in ((), ("--preflight",)):
        return 2
    try:
        config = load_telemetry_runtime_config()
        now_unix_ms = time.time_ns() // 1_000_000
        if args == ("--preflight",):
            preflight_telemetry_runtime(config, as_of_unix_ms=now_unix_ms)
        else:
            run_telemetry_once(config, as_of_unix_ms=now_unix_ms)
    except TelemetryRuntimeConfigError:
        return 1
    return 0


def _resolve_base_directory(
    base_directory: str | os.PathLike[str] | None,
) -> Path:
    raw = Path.cwd() if base_directory is None else Path(base_directory)
    try:
        return raw.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise TelemetryRuntimeConfigError(
            "telemetry base directory cannot be resolved"
        ) from error


def _required_path(
    env: Mapping[str, str],
    key: str,
    base_directory: Path,
) -> Path:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TelemetryRuntimeConfigError(
            f"required telemetry environment value is missing: {key}"
        )
    try:
        path = Path(value.strip()).expanduser()
        if not path.is_absolute():
            path = base_directory / path
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise TelemetryRuntimeConfigError(
            f"telemetry path is malformed for {key}"
        ) from error


def _required_text(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TelemetryRuntimeConfigError(
            f"required telemetry environment value is missing: {key}"
        )
    return value.strip()


def _required_bucket_count(env: Mapping[str, str], key: str) -> int:
    raw = _required_text(env, key)
    try:
        value = int(raw, 10)
    except ValueError as error:
        raise TelemetryRuntimeConfigError(
            "telemetry calibration bucket count must be an integer"
        ) from error
    if str(value) != raw and raw != f"+{value}":
        raise TelemetryRuntimeConfigError(
            "telemetry calibration bucket count must be an integer"
        )
    if not 2 <= value <= 100:
        raise TelemetryRuntimeConfigError(
            "telemetry calibration bucket count must be between 2 and 100"
        )
    return value


def _require_runtime_config(config: TelemetryRuntimeConfig) -> None:
    if type(config) is not TelemetryRuntimeConfig:
        raise TelemetryRuntimeConfigError(
            "config must be an exact TelemetryRuntimeConfig"
        )


def _require_timestamp(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryRuntimeConfigError(
            "telemetry timestamp must be a non-negative integer"
        )


if __name__ == "__main__":
    raise SystemExit(main())
