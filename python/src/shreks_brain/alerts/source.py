from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sqlite3
import subprocess

from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
    bootstrap_observer_paper_campaign_runtime,
)
from shreks_brain.paper import PaperLedgerEntry
from shreks_brain.telemetry import decode_telemetry_snapshot

from .config import AlertRuntimeConfig
from .models import (
    AlertProviderHealth,
    AlertSourceSnapshot,
    AlertSystemdHealth,
)


CORE_ALERT_UNITS = (
    "shreks.target",
    "shreks-observe.service",
    "shreks-paper-evidence.service",
    "shreks-paper-campaign.service",
    "shreks-telemetry.timer",
)
_TELEMETRY_ERROR = "TELEMETRY_SOURCE_UNAVAILABLE"
_PAPER_ERROR = "PAPER_SOURCE_UNAVAILABLE"
_SYSTEMD_ERROR = "SYSTEMD_HEALTH_UNAVAILABLE"
_KNOWN_INACTIVE_STATES = frozenset(
    {"inactive", "failed", "activating", "deactivating", "reloading"}
)

SystemctlRunner = Callable[[tuple[str, ...]], tuple[int, str]]


def collect_alert_source(
    config: AlertRuntimeConfig,
    *,
    observed_at_unix_ms: int,
    systemctl_runner: SystemctlRunner | None = None,
) -> AlertSourceSnapshot:
    if type(config) is not AlertRuntimeConfig:
        raise ValueError("config must be an exact AlertRuntimeConfig")
    _require_non_negative_int("observed_at_unix_ms", observed_at_unix_ms)

    telemetry, telemetry_error = _collect_telemetry(config.telemetry_path)
    providers, provider_ok = _collect_provider_health(
        config.paper_runtime_config.observer_database_path,
        observed_at_unix_ms,
    )
    ledger_entries, paper_ok = _collect_paper_ledger(config)
    paper_error = None if provider_ok and paper_ok else _PAPER_ERROR
    systemd, systemd_error = _collect_systemd_health(
        _default_systemctl_runner if systemctl_runner is None else systemctl_runner
    )

    return AlertSourceSnapshot(
        observed_at_unix_ms=observed_at_unix_ms,
        telemetry=telemetry,
        telemetry_error_code=telemetry_error,
        providers=providers,
        paper_ledger_entries=ledger_entries,
        paper_error_code=paper_error,
        systemd=systemd,
        systemd_error_code=systemd_error,
    )


def _collect_telemetry(path: Path):
    try:
        if path.is_symlink() or not path.is_file():
            return None, _TELEMETRY_ERROR
        return decode_telemetry_snapshot(path.read_bytes()), None
    except (OSError, TypeError, ValueError):
        return None, _TELEMETRY_ERROR


def _collect_provider_health(
    database_path: Path,
    observed_at_unix_ms: int,
) -> tuple[tuple[AlertProviderHealth, ...], bool]:
    try:
        uri = database_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                "SELECT provider,status,observed_at_unix_ms,consecutive_failures "
                "FROM provider_health ORDER BY provider"
            ).fetchall()
        providers = tuple(
            AlertProviderHealth(
                provider=_exact_text(row[0], "provider"),
                status=_exact_text(row[1], "provider status"),
                observed_at_unix_ms=_bounded_source_timestamp(
                    row[2], observed_at_unix_ms, "provider observed_at_unix_ms"
                ),
                consecutive_failures=_non_negative_row_int(
                    row[3], "provider consecutive_failures"
                ),
            )
            for row in rows
        )
        return providers, True
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError):
        return (), False


def _collect_paper_ledger(
    config: AlertRuntimeConfig,
) -> tuple[tuple[PaperLedgerEntry, ...] | None, bool]:
    try:
        bootstrap = bootstrap_observer_paper_campaign_runtime(config.paper_runtime_config)
        entries = bootstrap.restored_state.ledger.entries
        if not isinstance(entries, tuple) or not all(
            type(entry) is PaperLedgerEntry for entry in entries
        ):
            raise ValueError("PAPER ledger evidence is invalid")
        return entries, True
    except (ObserverPaperCampaignRuntimeError, OSError, TypeError, ValueError):
        return None, False


def _collect_systemd_health(
    runner: SystemctlRunner,
) -> tuple[AlertSystemdHealth | None, str | None]:
    active: list[str] = []
    inactive: list[str] = []
    try:
        for unit in CORE_ALERT_UNITS:
            command = ("/usr/bin/systemctl", "is-active", unit)
            result = runner(command)
            if (
                not isinstance(result, tuple)
                or len(result) != 2
                or isinstance(result[0], bool)
                or not isinstance(result[0], int)
                or not isinstance(result[1], str)
            ):
                return None, _SYSTEMD_ERROR
            return_code, stdout = result
            state = stdout.strip()
            if return_code == 0 and state == "active":
                active.append(unit)
            elif state in _KNOWN_INACTIVE_STATES:
                inactive.append(unit)
            else:
                return None, _SYSTEMD_ERROR
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return None, _SYSTEMD_ERROR
    return AlertSystemdHealth(tuple(active), tuple(inactive)), None


def _default_systemctl_runner(command: tuple[str, ...]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OSError("systemd health query failed") from error
    return completed.returncode, completed.stdout


def _exact_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be exact non-empty text")
    return value


def _bounded_source_timestamp(value: object, maximum: int, label: str) -> int:
    result = _non_negative_row_int(value, label)
    if result > maximum:
        raise ValueError(f"{label} cannot be in the future")
    return result


def _non_negative_row_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _require_non_negative_int(label: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
