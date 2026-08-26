from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from shreks_brain.alerts.config import (
    AlertRuntimeConfig,
    AlertRuntimeConfigError,
    load_alert_runtime_config,
    load_telegram_bot_token,
)

from test_observer_campaign_runtime import _runtime_config


_ALLOWED_ALERT_KEYS = {
    "SHREKS_ALERTS_TELEGRAM_CHAT_ID",
    "SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE",
    "SHREKS_ALERTS_STATE_PATH",
    "SHREKS_ALERTS_MARKET_STALE_MS",
    "SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE",
    "SHREKS_ALERTS_TELEMETRY_PATH",
}


def _env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime = _runtime_config(runtime_root, max_cycles=1)
    token_file = tmp_path / "telegram-bot-token"
    token_file.write_bytes(b"test-alert-bot-token\n")
    token_file.chmod(0o640)
    alerts_dir = tmp_path / "alerts"
    alerts_dir.mkdir()
    return (
        {
            "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": str(runtime.observer_database_path),
            "SHREKS_PAPER_CAMPAIGN_E11_PATH": str(runtime.evidence_path),
            "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": str(runtime.manifest_path),
            "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS": str(runtime.cycle_interval_seconds),
            "SHREKS_PAPER_CAMPAIGN_MAX_CYCLES": "1",
            "SHREKS_ALERTS_TELEGRAM_CHAT_ID": "-1001234567890",
            "SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE": str(token_file),
            "SHREKS_ALERTS_STATE_PATH": str(alerts_dir / "state.json"),
            "SHREKS_ALERTS_MARKET_STALE_MS": "120000",
            "SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE": "3",
            "SHREKS_ALERTS_TELEMETRY_PATH": str(tmp_path / "telemetry" / "current.json"),
        },
        token_file,
    )


def test_alert_config_is_exact_and_reuses_paper_runtime_paths(tmp_path: Path) -> None:
    env, token_file = _env(tmp_path)
    config = load_alert_runtime_config(env)

    assert {field.name for field in fields(AlertRuntimeConfig)} == {
        "telemetry_path",
        "state_path",
        "telegram_chat_id",
        "telegram_bot_token_file",
        "market_stale_ms",
        "provider_failure_min_consecutive",
        "paper_runtime_config",
    }
    assert config.telemetry_path == (tmp_path / "telemetry" / "current.json").resolve()
    assert config.state_path == (tmp_path / "alerts" / "state.json").resolve()
    assert config.telegram_chat_id == "-1001234567890"
    assert config.telegram_bot_token_file == token_file.resolve()
    assert config.market_stale_ms == 120000
    assert config.provider_failure_min_consecutive == 3
    assert config.paper_runtime_config.observer_database_path == Path(
        env["SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH"]
    ).resolve()
    assert config.paper_runtime_config.evidence_path == Path(
        env["SHREKS_PAPER_CAMPAIGN_E11_PATH"]
    ).resolve()
    assert config.paper_runtime_config.manifest_path == Path(
        env["SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH"]
    ).resolve()
    assert not hasattr(config, "telegram_bot_token")
    assert not hasattr(config, "bot_token")
    assert not hasattr(config, "helius_api_key")
    assert not hasattr(config, "jupiter_api_key")
    assert "test-alert-bot-token" not in repr(config)


def test_alert_namespace_is_exact_but_unrelated_environment_is_ignored(tmp_path: Path) -> None:
    env, _token_file = _env(tmp_path)
    assert {key for key in env if key.startswith("SHREKS_ALERTS_")} == _ALLOWED_ALERT_KEYS
    env["UNRELATED_ENVIRONMENT_VALUE"] = "ignored"
    load_alert_runtime_config(env)

    env["SHREKS_ALERTS_UNKNOWN"] = "nope"
    with pytest.raises(AlertRuntimeConfigError, match="unsupported alert"):
        load_alert_runtime_config(env)


@pytest.mark.parametrize(
    "chat_id",
    ["", " ", "chat\nline", "chat\rline", "x" * 257],
)
def test_telegram_chat_id_is_bounded_non_control_text(tmp_path: Path, chat_id: str) -> None:
    env, _token_file = _env(tmp_path)
    env["SHREKS_ALERTS_TELEGRAM_CHAT_ID"] = chat_id
    with pytest.raises(AlertRuntimeConfigError, match="chat"):
        load_alert_runtime_config(env)


@pytest.mark.parametrize("value", ["", "0", "-1", "+3", "3.0", " 3", "3 ", "abc"])
def test_market_stale_ms_is_canonical_positive_integer(tmp_path: Path, value: str) -> None:
    env, _token_file = _env(tmp_path)
    env["SHREKS_ALERTS_MARKET_STALE_MS"] = value
    with pytest.raises(AlertRuntimeConfigError, match="stale"):
        load_alert_runtime_config(env)


@pytest.mark.parametrize("value", ["", "0", "-1", "+2", "2.0", " 2", "2 ", "abc"])
def test_provider_failure_threshold_is_canonical_positive_integer(
    tmp_path: Path,
    value: str,
) -> None:
    env, _token_file = _env(tmp_path)
    env["SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE"] = value
    with pytest.raises(AlertRuntimeConfigError, match="provider"):
        load_alert_runtime_config(env)


def test_paths_resolve_against_explicit_base_directory(tmp_path: Path) -> None:
    env, token_file = _env(tmp_path)
    base = tmp_path / "base"
    base.mkdir()
    relative_token = base / "telegram-token"
    relative_token.write_bytes(token_file.read_bytes())
    relative_token.chmod(0o640)
    relative_alerts = base / "alert-state"
    relative_alerts.mkdir()

    env["SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE"] = "telegram-token"
    env["SHREKS_ALERTS_STATE_PATH"] = "alert-state/state.json"
    env["SHREKS_ALERTS_TELEMETRY_PATH"] = "telemetry/current.json"

    config = load_alert_runtime_config(env, base_directory=base)

    assert config.telegram_bot_token_file == relative_token.resolve()
    assert config.state_path == (relative_alerts / "state.json").resolve()
    assert config.telemetry_path == (base / "telemetry" / "current.json").resolve()


def test_state_path_requires_existing_directory_and_file_name(tmp_path: Path) -> None:
    env, _token_file = _env(tmp_path)

    env["SHREKS_ALERTS_STATE_PATH"] = str(tmp_path / "missing" / "state.json")
    with pytest.raises(AlertRuntimeConfigError, match="state"):
        load_alert_runtime_config(env)

    env["SHREKS_ALERTS_STATE_PATH"] = str(tmp_path / "alerts")
    with pytest.raises(AlertRuntimeConfigError, match="state"):
        load_alert_runtime_config(env)


def test_token_file_must_be_regular_non_symlink_and_protected(tmp_path: Path) -> None:
    env, token_file = _env(tmp_path)

    token_file.chmod(0o644)
    with pytest.raises(AlertRuntimeConfigError, match="permissions"):
        load_alert_runtime_config(env)

    token_file.chmod(0o660)
    with pytest.raises(AlertRuntimeConfigError, match="permissions"):
        load_alert_runtime_config(env)

    token_file.chmod(0o640)
    token_file.write_bytes(b"")
    with pytest.raises(AlertRuntimeConfigError, match="token file"):
        load_alert_runtime_config(env)

    token_file.write_bytes(b"x" * 4097)
    token_file.chmod(0o640)
    with pytest.raises(AlertRuntimeConfigError, match="token file"):
        load_alert_runtime_config(env)

    token_file.unlink()
    token_file.mkdir()
    with pytest.raises(AlertRuntimeConfigError, match="token file"):
        load_alert_runtime_config(env)


def test_token_file_symlink_is_rejected(tmp_path: Path) -> None:
    env, token_file = _env(tmp_path)
    target = tmp_path / "actual-token"
    target.write_bytes(token_file.read_bytes())
    target.chmod(0o640)
    token_file.unlink()
    token_file.symlink_to(target)

    with pytest.raises(AlertRuntimeConfigError, match="symlink"):
        load_alert_runtime_config(env)


def test_token_loader_strips_one_trailing_line_ending_only(tmp_path: Path) -> None:
    env, token_file = _env(tmp_path)
    token_file.write_bytes(b"test-alert-bot-token\r\n")
    token_file.chmod(0o640)
    config = load_alert_runtime_config(env)

    assert load_telegram_bot_token(config) == b"test-alert-bot-token"

    token_file.write_bytes(b"test-alert\nbot-token\n")
    token_file.chmod(0o640)
    with pytest.raises(AlertRuntimeConfigError, match="one non-empty line"):
        load_telegram_bot_token(config)


def test_missing_or_blank_required_alert_values_fail_closed(tmp_path: Path) -> None:
    env, _token_file = _env(tmp_path)
    for key in sorted(_ALLOWED_ALERT_KEYS):
        mutated = dict(env)
        mutated[key] = ""
        with pytest.raises(AlertRuntimeConfigError):
            load_alert_runtime_config(mutated)
