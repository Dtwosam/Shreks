from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

import shreks_brain.alerts.source as source_module
from shreks_brain.alerts.config import load_alert_runtime_config
from shreks_brain.alerts.source import (
    CORE_ALERT_UNITS,
    AlertSourceSnapshot,
    collect_alert_source,
)
from shreks_brain.observer_campaign.runtime import ObserverPaperCampaignRuntimeError
from shreks_brain.telemetry import encode_telemetry_snapshot

from test_g4_telemetry_models import _snapshot
from test_g4_telemetry_sources import _add_operational_tables
from test_g5_dashboard_source import _fake_bootstrap
from test_g6_alert_config import _env


OBSERVED_AT = 2_000_000


def _configured(tmp_path: Path):
    env, _token_file = _env(tmp_path)
    telemetry_path = Path(env["SHREKS_ALERTS_TELEMETRY_PATH"])
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_path.write_text(encode_telemetry_snapshot(_snapshot()), encoding="utf-8")
    database_path = Path(env["SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH"])
    _add_operational_tables(database_path)
    return load_alert_runtime_config(env), database_path, telemetry_path


def _seed_provider_health(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            "INSERT INTO provider_health(provider,status,observed_at_unix_ms,latency_ms,detail,consecutive_failures) "
            "VALUES (?,?,?,?,?,?)",
            (
                ("jupiter", "degraded", OBSERVED_AT - 20, 200, "route timeout", 4),
                ("helius", "healthy", OBSERVED_AT - 10, 15, None, 0),
            ),
        )
        connection.commit()


def _all_active_runner(calls: list[tuple[str, ...]]):
    def run(command: tuple[str, ...]) -> tuple[int, str]:
        calls.append(command)
        return 0, "active\n"

    return run


def test_collect_alert_source_reads_all_sources_without_mutation(tmp_path: Path, monkeypatch) -> None:
    config, database_path, telemetry_path = _configured(tmp_path)
    _seed_provider_health(database_path)
    bootstrap = _fake_bootstrap()
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: bootstrap,
    )
    systemctl_calls: list[tuple[str, ...]] = []
    before_db = database_path.read_bytes()
    before_db_mtime = database_path.stat().st_mtime_ns
    before_telemetry = telemetry_path.read_bytes()
    before_telemetry_mtime = telemetry_path.stat().st_mtime_ns

    source = collect_alert_source(
        config,
        observed_at_unix_ms=OBSERVED_AT,
        systemctl_runner=_all_active_runner(systemctl_calls),
    )

    assert type(source) is AlertSourceSnapshot
    assert source.observed_at_unix_ms == OBSERVED_AT
    assert source.telemetry == _snapshot()
    assert source.telemetry_error_code is None
    assert tuple(provider.provider for provider in source.providers) == ("helius", "jupiter")
    assert source.providers[0].status == "healthy"
    assert source.providers[0].consecutive_failures == 0
    assert source.providers[1].status == "degraded"
    assert source.providers[1].consecutive_failures == 4
    assert source.paper_error_code is None
    assert source.paper_ledger_entries == bootstrap.restored_state.ledger.entries
    assert source.systemd is not None
    assert source.systemd.active_units == CORE_ALERT_UNITS
    assert source.systemd.inactive_units == ()
    assert source.systemd_error_code is None
    assert systemctl_calls == [
        ("/usr/bin/systemctl", "is-active", unit) for unit in CORE_ALERT_UNITS
    ]

    assert database_path.read_bytes() == before_db
    assert database_path.stat().st_mtime_ns == before_db_mtime
    assert telemetry_path.read_bytes() == before_telemetry
    assert telemetry_path.stat().st_mtime_ns == before_telemetry_mtime


def test_source_failures_are_stable_codes_without_internal_exception_text(tmp_path: Path, monkeypatch) -> None:
    config, database_path, telemetry_path = _configured(tmp_path)
    _seed_provider_health(database_path)
    telemetry_path.write_text("{broken\n", encoding="utf-8")

    def fail_bootstrap(_config):
        raise ObserverPaperCampaignRuntimeError("sensitive paper source detail")

    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        fail_bootstrap,
    )

    source = collect_alert_source(
        config,
        observed_at_unix_ms=OBSERVED_AT,
        systemctl_runner=lambda _command: (0, "active\n"),
    )

    assert source.telemetry is None
    assert source.telemetry_error_code == "TELEMETRY_SOURCE_UNAVAILABLE"
    assert source.paper_ledger_entries is None
    assert source.paper_error_code == "PAPER_SOURCE_UNAVAILABLE"
    rendered = repr(source)
    assert "sensitive paper source detail" not in rendered
    assert "broken" not in rendered


def test_provider_health_query_is_read_only_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
    env, _token_file = _env(tmp_path)
    telemetry_path = Path(env["SHREKS_ALERTS_TELEMETRY_PATH"])
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_path.write_text(encode_telemetry_snapshot(_snapshot()), encoding="utf-8")
    config = load_alert_runtime_config(env)
    database_path = config.paper_runtime_config.observer_database_path
    before = database_path.read_bytes()
    before_mtime = database_path.stat().st_mtime_ns
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: _fake_bootstrap(),
    )

    source = collect_alert_source(
        config,
        observed_at_unix_ms=OBSERVED_AT,
        systemctl_runner=lambda _command: (0, "active\n"),
    )

    assert source.providers == ()
    assert source.paper_error_code == "PAPER_SOURCE_UNAVAILABLE"
    assert database_path.read_bytes() == before
    assert database_path.stat().st_mtime_ns == before_mtime


def test_systemd_health_is_read_only_and_classifies_inactive_units(tmp_path: Path, monkeypatch) -> None:
    config, database_path, _telemetry_path = _configured(tmp_path)
    _seed_provider_health(database_path)
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: _fake_bootstrap(),
    )
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> tuple[int, str]:
        calls.append(command)
        if command[-1] == "shreks-paper-campaign.service":
            return 3, "inactive\n"
        return 0, "active\n"

    source = collect_alert_source(
        config,
        observed_at_unix_ms=OBSERVED_AT,
        systemctl_runner=runner,
    )

    assert source.systemd is not None
    assert source.systemd.inactive_units == ("shreks-paper-campaign.service",)
    assert "shreks-paper-campaign.service" not in source.systemd.active_units
    assert source.systemd_error_code is None
    assert calls == [("/usr/bin/systemctl", "is-active", unit) for unit in CORE_ALERT_UNITS]
    flattened = " ".join(" ".join(command) for command in calls)
    for forbidden in (" start ", " stop ", " restart ", " enable ", " disable ", " reset-failed ", " daemon-reload "):
        assert forbidden not in f" {flattened} "


def test_unknown_systemd_response_becomes_unavailable_without_remediation(tmp_path: Path, monkeypatch) -> None:
    config, database_path, _telemetry_path = _configured(tmp_path)
    _seed_provider_health(database_path)
    monkeypatch.setattr(
        source_module,
        "bootstrap_observer_paper_campaign_runtime",
        lambda _config: _fake_bootstrap(),
    )
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> tuple[int, str]:
        calls.append(command)
        return 1, "unexpected-state\n"

    source = collect_alert_source(
        config,
        observed_at_unix_ms=OBSERVED_AT,
        systemctl_runner=runner,
    )

    assert source.systemd is None
    assert source.systemd_error_code == "SYSTEMD_HEALTH_UNAVAILABLE"
    assert calls == [("/usr/bin/systemctl", "is-active", CORE_ALERT_UNITS[0])]


@pytest.mark.parametrize("observed_at", [-1, True, 1.5])
def test_observation_timestamp_must_be_non_negative_integer(tmp_path: Path, observed_at) -> None:
    config, _database_path, _telemetry_path = _configured(tmp_path)
    with pytest.raises(ValueError):
        collect_alert_source(
            config,
            observed_at_unix_ms=observed_at,
            systemctl_runner=lambda _command: (0, "active\n"),
        )
