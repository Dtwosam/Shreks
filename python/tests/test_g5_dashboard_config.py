from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from shreks_brain.dashboard.config import (
    DashboardRuntimeConfig,
    DashboardRuntimeConfigError,
    load_dashboard_password,
    load_dashboard_runtime_config,
)

from test_observer_campaign_runtime import _runtime_config


def _env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime = _runtime_config(runtime_root, max_cycles=1)
    password_file = tmp_path / "dashboard-password"
    password_file.write_bytes(b"correct-horse-battery-staple\n")
    password_file.chmod(0o640)
    telemetry_path = tmp_path / "telemetry" / "current.json"
    return (
        {
            "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": str(runtime.observer_database_path),
            "SHREKS_PAPER_CAMPAIGN_E11_PATH": str(runtime.evidence_path),
            "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": str(runtime.manifest_path),
            "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS": str(runtime.cycle_interval_seconds),
            "SHREKS_PAPER_CAMPAIGN_MAX_CYCLES": "1",
            "SHREKS_DASHBOARD_BIND_HOST": "127.0.0.1",
            "SHREKS_DASHBOARD_PORT": "8787",
            "SHREKS_DASHBOARD_USERNAME": "operator",
            "SHREKS_DASHBOARD_PASSWORD_FILE": str(password_file),
            "SHREKS_DASHBOARD_TELEMETRY_PATH": str(telemetry_path),
            "SHREKS_DASHBOARD_MAX_TRADES": "100",
        },
        password_file,
    )


def test_dashboard_config_is_exact_and_reuses_paper_runtime_paths(tmp_path: Path) -> None:
    env, password_file = _env(tmp_path)
    config = load_dashboard_runtime_config(env)

    assert {field.name for field in fields(DashboardRuntimeConfig)} == {
        "bind_host",
        "port",
        "username",
        "password_file",
        "telemetry_path",
        "max_trades",
        "paper_runtime_config",
    }
    assert config.bind_host == "127.0.0.1"
    assert config.port == 8787
    assert config.username == "operator"
    assert config.password_file == password_file.resolve()
    assert config.telemetry_path == (tmp_path / "telemetry" / "current.json").resolve()
    assert config.max_trades == 100
    assert config.paper_runtime_config.observer_database_path == Path(
        env["SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH"]
    ).resolve()
    rendered = repr(config).lower()
    assert "correct-horse" not in rendered
    assert "helius" not in rendered
    assert "jupiter" not in rendered
    assert not hasattr(config, "password")


def test_unknown_dashboard_keys_fail_closed_but_unrelated_keys_are_ignored(tmp_path: Path) -> None:
    env, _password_file = _env(tmp_path)
    env["UNRELATED_ENV"] = "ignored"
    load_dashboard_runtime_config(env)

    env["SHREKS_DASHBOARD_UNSUPPORTED"] = "nope"
    with pytest.raises(DashboardRuntimeConfigError, match="unsupported dashboard"):
        load_dashboard_runtime_config(env)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost", "192.168.1.20", "example.com", ""])
def test_dashboard_bind_host_must_be_explicit_loopback(tmp_path: Path, host: str) -> None:
    env, _password_file = _env(tmp_path)
    env["SHREKS_DASHBOARD_BIND_HOST"] = host
    with pytest.raises(DashboardRuntimeConfigError, match="loopback"):
        load_dashboard_runtime_config(env)


@pytest.mark.parametrize("port", ["", "0", "1023", "65536", "8787.0", "abc", "+8787"])
def test_dashboard_port_is_canonical_unprivileged_integer(tmp_path: Path, port: str) -> None:
    env, _password_file = _env(tmp_path)
    env["SHREKS_DASHBOARD_PORT"] = port
    with pytest.raises(DashboardRuntimeConfigError, match="port"):
        load_dashboard_runtime_config(env)


@pytest.mark.parametrize("username", ["", " operator", "operator ", "bad:name", "line\nbreak", "café"])
def test_dashboard_username_is_printable_ascii_without_colon(tmp_path: Path, username: str) -> None:
    env, _password_file = _env(tmp_path)
    env["SHREKS_DASHBOARD_USERNAME"] = username
    with pytest.raises(DashboardRuntimeConfigError, match="username"):
        load_dashboard_runtime_config(env)


@pytest.mark.parametrize("max_trades", ["", "0", "501", "1.0", "abc", "+5"])
def test_dashboard_max_trades_is_bounded_canonical_integer(tmp_path: Path, max_trades: str) -> None:
    env, _password_file = _env(tmp_path)
    env["SHREKS_DASHBOARD_MAX_TRADES"] = max_trades
    with pytest.raises(DashboardRuntimeConfigError, match="max trades"):
        load_dashboard_runtime_config(env)


def test_password_file_must_be_regular_non_symlink_and_protected(tmp_path: Path) -> None:
    env, password_file = _env(tmp_path)

    password_file.chmod(0o644)
    with pytest.raises(DashboardRuntimeConfigError, match="permissions"):
        load_dashboard_runtime_config(env)

    password_file.chmod(0o660)
    with pytest.raises(DashboardRuntimeConfigError, match="permissions"):
        load_dashboard_runtime_config(env)

    password_file.chmod(0o640)
    password_file.write_bytes(b"")
    with pytest.raises(DashboardRuntimeConfigError, match="password file"):
        load_dashboard_runtime_config(env)

    password_file.write_bytes(b"x" * 4097)
    password_file.chmod(0o640)
    with pytest.raises(DashboardRuntimeConfigError, match="password file"):
        load_dashboard_runtime_config(env)

    password_file.unlink()
    password_file.mkdir()
    with pytest.raises(DashboardRuntimeConfigError, match="password file"):
        load_dashboard_runtime_config(env)


def test_password_file_symlink_is_rejected(tmp_path: Path) -> None:
    env, password_file = _env(tmp_path)
    target = tmp_path / "actual-password"
    target.write_bytes(password_file.read_bytes())
    target.chmod(0o640)
    password_file.unlink()
    password_file.symlink_to(target)

    with pytest.raises(DashboardRuntimeConfigError, match="symlink"):
        load_dashboard_runtime_config(env)


def test_password_loader_returns_secret_bytes_without_trailing_newline(tmp_path: Path) -> None:
    env, _password_file = _env(tmp_path)
    config = load_dashboard_runtime_config(env)

    assert load_dashboard_password(config) == b"correct-horse-battery-staple"


def test_missing_required_dashboard_values_fail_closed(tmp_path: Path) -> None:
    env, _password_file = _env(tmp_path)
    for key in (
        "SHREKS_DASHBOARD_BIND_HOST",
        "SHREKS_DASHBOARD_PORT",
        "SHREKS_DASHBOARD_USERNAME",
        "SHREKS_DASHBOARD_PASSWORD_FILE",
        "SHREKS_DASHBOARD_TELEMETRY_PATH",
        "SHREKS_DASHBOARD_MAX_TRADES",
    ):
        mutated = dict(env)
        mutated[key] = ""
        with pytest.raises(DashboardRuntimeConfigError):
            load_dashboard_runtime_config(mutated)
