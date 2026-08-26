from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.backup import create_backup_snapshot, verify_backup_bundle
from shreks_brain.backup.config import (
    BackupRuntimeConfigError,
    load_backup_runtime_config,
)
from shreks_brain.backup.runtime import (
    prune_backup_retention,
    run_backup_command,
    run_restore_command,
    run_verify_command,
)

from test_g8_backup_snapshot import _CREATED_AT, _sources


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "SHREKS_BACKUP_ROOT": str(tmp_path / "backups"),
        "SHREKS_BACKUP_RETENTION_COUNT": "7",
        "SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS": "3",
        "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": str(tmp_path / "observer.sqlite"),
        "SHREKS_PAPER_CAMPAIGN_E11_PATH": str(tmp_path / "e11.json"),
        "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": str(tmp_path / "paper-campaign.json"),
        "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS": "1",
        "SHREKS_RISK_CONTROL_STATE_PATH": str(tmp_path / "operator-control.json"),
        "SHREKS_ALERTS_STATE_PATH": str(tmp_path / "alerts-state.json"),
    }


def test_backup_config_reuses_authoritative_paths_and_validates_bounded_operational_keys(
    tmp_path: Path,
) -> None:
    config = load_backup_runtime_config(_env(tmp_path))

    assert config.backup_root == (tmp_path / "backups").resolve()
    assert config.retention_count == 7
    assert config.max_capture_attempts == 3
    assert config.operational_database_path == (tmp_path / "observer.sqlite").resolve()
    assert config.e11_path == (tmp_path / "e11.json").resolve()
    assert config.campaign_manifest_path == (tmp_path / "paper-campaign.json").resolve()
    assert config.risk_control_path == (tmp_path / "operator-control.json").resolve()
    assert config.alert_state_path == (tmp_path / "alerts-state.json").resolve()


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("SHREKS_BACKUP_RETENTION_COUNT", "0"),
        ("SHREKS_BACKUP_RETENTION_COUNT", "10001"),
        ("SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS", "0"),
        ("SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS", "101"),
        ("SHREKS_BACKUP_ROOT", ""),
    ),
)
def test_backup_config_rejects_missing_or_out_of_bounds_values(
    tmp_path: Path,
    key: str,
    value: str,
) -> None:
    env = _env(tmp_path)
    env[key] = value
    with pytest.raises(BackupRuntimeConfigError):
        load_backup_runtime_config(env)


@pytest.mark.parametrize(
    "key",
    (
        "SHREKS_BACKUP_STRATEGY_VERSION",
        "SHREKS_BACKUP_RISK_LIMIT",
        "SHREKS_BACKUP_LIVE_MODE",
        "SHREKS_BACKUP_PRIVATE_KEY",
    ),
)
def test_backup_namespace_rejects_strategy_risk_live_and_secret_keys(
    tmp_path: Path,
    key: str,
) -> None:
    env = _env(tmp_path)
    env[key] = "forbidden"
    with pytest.raises(BackupRuntimeConfigError):
        load_backup_runtime_config(env)


def test_backup_command_publishes_verified_bundle_then_applies_retention(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    sources, *_rest = _sources(source_root)
    env = _env(source_root)
    env.update(
        {
            "SHREKS_BACKUP_ROOT": str(tmp_path / "backups"),
            "SHREKS_BACKUP_RETENTION_COUNT": "1",
            "SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS": "1",
            "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": str(sources.operational_database_path),
            "SHREKS_PAPER_CAMPAIGN_E11_PATH": str(sources.e11_path),
            "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": str(sources.campaign_manifest_path),
            "SHREKS_RISK_CONTROL_STATE_PATH": str(sources.risk_control_path),
            "SHREKS_ALERTS_STATE_PATH": str(sources.alert_state_path),
        }
    )
    config = load_backup_runtime_config(env)
    first = create_backup_snapshot(
        config.backup_root,
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=1,
    )
    statuses: list[str] = []

    second = run_backup_command(
        config,
        created_at_unix_ms=_CREATED_AT + 1,
        status_sink=statuses.append,
    )

    assert verify_backup_bundle(second).created_at_unix_ms == _CREATED_AT + 1
    assert not first.exists()
    assert second.exists()
    assert len(statuses) == 1
    status = json.loads(statuses[0])
    assert status["operation"] == "backup"
    assert status["state"] == "COMPLETED"
    assert status["paper_run_id"] == verify_backup_bundle(second).paper_run_id
    lowered = statuses[0].lower()
    for forbidden in ("token", "password", "private_key", "seed_phrase"):
        assert forbidden not in lowered


def test_retention_removes_only_oldest_verified_completed_bundles(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    sources, *_rest = _sources(source_root)
    backup_root = tmp_path / "backups"
    oldest = create_backup_snapshot(
        backup_root, sources, created_at_unix_ms=_CREATED_AT, max_capture_attempts=1
    )
    newest = create_backup_snapshot(
        backup_root, sources, created_at_unix_ms=_CREATED_AT + 1, max_capture_attempts=1
    )
    unrelated = backup_root / "operator-notes"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("do not delete", encoding="utf-8")
    malformed = backup_root / "123-malformed"
    malformed.mkdir()
    (malformed / "manifest.json").write_text("{}", encoding="utf-8")

    removed = prune_backup_retention(backup_root, retention_count=1)

    assert removed == (oldest,)
    assert not oldest.exists()
    assert newest.exists()
    assert (unrelated / "keep.txt").read_text(encoding="utf-8") == "do not delete"
    assert malformed.exists()


def test_verify_command_is_read_only_and_restore_requires_explicit_empty_staging(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    sources, *_rest = _sources(source_root)
    bundle = create_backup_snapshot(
        tmp_path / "backups",
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=1,
    )
    before = {path: path.read_bytes() for path in bundle.rglob("*") if path.is_file()}
    verify_status: list[str] = []

    manifest = run_verify_command(bundle, status_sink=verify_status.append)

    assert manifest == verify_backup_bundle(bundle)
    assert {path: path.read_bytes() for path in bundle.rglob("*") if path.is_file()} == before
    assert json.loads(verify_status[0])["state"] == "VERIFIED"

    staging = tmp_path / "restore-stage"
    result = run_restore_command(bundle, staging, status_sink=lambda _line: None)
    assert result.paper_run_id == manifest.paper_run_id

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "sentinel").write_text("keep", encoding="utf-8")
    with pytest.raises(Exception):
        run_restore_command(bundle, occupied, status_sink=lambda _line: None)
    assert (occupied / "sentinel").read_text(encoding="utf-8") == "keep"
