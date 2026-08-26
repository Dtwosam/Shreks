from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.backup import (
    BackupArtifactRole,
    BackupSnapshotError,
    BackupSnapshotSources,
    create_backup_snapshot,
    verify_backup_bundle,
)
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
    bootstrap_observer_paper_campaign_runtime,
    preflight_observer_paper_campaign_runtime,
)
from shreks_brain.risk_control import initialize_operator_risk_control_state

from test_observer_campaign_runner import AS_OF
from test_observer_campaign_runtime import _runtime_config


_CREATED_AT = AS_OF + 10_000


def _sources(tmp_path: Path) -> tuple[BackupSnapshotSources, object, bytes, bytes, bytes, bytes]:
    config = _runtime_config(tmp_path, max_cycles=1)
    bootstrap = bootstrap_observer_paper_campaign_runtime(config)
    bootstrap.runner.run_cycle(AS_OF, AS_OF)

    risk_path = (tmp_path / "risk" / "operator-control.json").resolve()
    risk_path.parent.mkdir()
    initialize_operator_risk_control_state(risk_path, observed_at_unix_ms=AS_OF)
    config = replace(config, risk_control_path=risk_path)

    alert_path = (tmp_path / "alerts" / "state.json").resolve()
    alert_path.parent.mkdir()
    alert_payload = b'{"pending_events":["critical-provider-failure"]}\n'
    alert_path.write_bytes(alert_payload)

    sources = BackupSnapshotSources(
        operational_database_path=config.observer_database_path,
        e11_path=config.evidence_path,
        campaign_manifest_path=config.manifest_path,
        risk_control_path=risk_path,
        alert_state_path=alert_path,
    )
    return (
        sources,
        config,
        config.evidence_path.read_bytes(),
        config.manifest_path.read_bytes(),
        risk_path.read_bytes(),
        alert_payload,
    )


def _artifact_bytes(bundle: Path, role: BackupArtifactRole) -> bytes:
    manifest = verify_backup_bundle(bundle)
    record = next(record for record in manifest.artifacts if record.role is role)
    return (bundle / record.relative_path).read_bytes()


def test_online_snapshot_captures_wal_committed_truth_without_copying_wal_or_shm(
    tmp_path: Path,
) -> None:
    sources, _config, _e11, _manifest, _risk, _alerts = _sources(tmp_path)
    connection = sqlite3.connect(sources.operational_database_path)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        connection.execute("CREATE TABLE g8_wal_proof (value TEXT NOT NULL)")
        connection.execute("INSERT INTO g8_wal_proof(value) VALUES ('committed-in-wal')")
        connection.commit()
        assert Path(str(sources.operational_database_path) + "-wal").exists()

        bundle = create_backup_snapshot(
            tmp_path / "backups",
            sources,
            created_at_unix_ms=_CREATED_AT,
            max_capture_attempts=1,
        )
    finally:
        connection.close()

    verified = verify_backup_bundle(bundle)
    db_record = next(
        record
        for record in verified.artifacts
        if record.role is BackupArtifactRole.OPERATIONAL_SQLITE
    )
    backed_up_db = bundle / db_record.relative_path
    restored = sqlite3.connect(backed_up_db)
    try:
        assert restored.execute("SELECT value FROM g8_wal_proof").fetchone() == (
            "committed-in-wal",
        )
    finally:
        restored.close()

    names = {path.name for path in bundle.rglob("*") if path.is_file()}
    assert not any(name.endswith("-wal") or name.endswith("-shm") for name in names)


def test_snapshot_copies_exact_required_state_and_excludes_secrets_and_telemetry(
    tmp_path: Path,
) -> None:
    sources, _config, e11, campaign, risk, alerts = _sources(tmp_path)
    secret = tmp_path / "dashboard-password"
    token = tmp_path / "telegram-bot-token"
    telemetry = tmp_path / "telemetry" / "current.json"
    secret.write_text("do-not-copy", encoding="utf-8")
    token.write_text("do-not-copy-token", encoding="utf-8")
    telemetry.parent.mkdir()
    telemetry.write_text('{"derived":true}', encoding="utf-8")

    bundle = create_backup_snapshot(
        tmp_path / "backups",
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=1,
    )

    assert _artifact_bytes(bundle, BackupArtifactRole.E11_EVIDENCE) == e11
    assert _artifact_bytes(bundle, BackupArtifactRole.CAMPAIGN_MANIFEST) == campaign
    assert _artifact_bytes(bundle, BackupArtifactRole.OPERATOR_RISK_CONTROL) == risk
    assert _artifact_bytes(bundle, BackupArtifactRole.ALERT_STATE) == alerts
    all_payload = b"\n".join(
        path.read_bytes() for path in bundle.rglob("*") if path.is_file()
    )
    assert b"do-not-copy" not in all_payload
    assert b"do-not-copy-token" not in all_payload
    assert b'"derived":true' not in all_payload


def test_snapshot_is_read_only_against_authoritative_sources(tmp_path: Path) -> None:
    sources, _config, e11, campaign, risk, alerts = _sources(tmp_path)
    before_rows = sqlite3.connect(sources.operational_database_path).execute(
        "SELECT COUNT(*) FROM paper_loop_checkpoints"
    ).fetchone()

    create_backup_snapshot(
        tmp_path / "backups",
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=1,
    )

    after_connection = sqlite3.connect(sources.operational_database_path)
    try:
        after_rows = after_connection.execute(
            "SELECT COUNT(*) FROM paper_loop_checkpoints"
        ).fetchone()
    finally:
        after_connection.close()
    assert after_rows == before_rows
    assert sources.e11_path.read_bytes() == e11
    assert sources.campaign_manifest_path.read_bytes() == campaign
    assert sources.risk_control_path.read_bytes() == risk
    assert sources.alert_state_path is not None
    assert sources.alert_state_path.read_bytes() == alerts


def test_completed_bundle_uses_private_permissions(tmp_path: Path) -> None:
    sources, _config, *_payloads = _sources(tmp_path)

    bundle = create_backup_snapshot(
        tmp_path / "backups",
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=1,
    )

    assert os.stat(bundle).st_mode & 0o777 == 0o700
    assert os.stat(bundle / "artifacts").st_mode & 0o777 == 0o700
    for path in bundle.rglob("*"):
        if path.is_file():
            assert os.stat(path).st_mode & 0o777 == 0o600


def test_snapshot_retries_bounded_cross_file_preflight_before_publish(
    tmp_path: Path,
) -> None:
    sources, _config, *_payloads = _sources(tmp_path)
    calls = 0

    def flaky_preflight(config):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ObserverPaperCampaignRuntimeError("simulated raced snapshot")
        return preflight_observer_paper_campaign_runtime(
            config,
            status_sink=lambda _line: None,
        )

    bundle = create_backup_snapshot(
        tmp_path / "backups",
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=2,
        preflight_validator=flaky_preflight,
    )

    assert calls == 2
    assert verify_backup_bundle(bundle).completed is True
    completed = [path for path in (tmp_path / "backups").iterdir() if path.is_dir()]
    assert completed == [bundle]


def test_snapshot_never_publishes_or_retries_forever_when_preflight_never_reconciles(
    tmp_path: Path,
) -> None:
    sources, _config, *_payloads = _sources(tmp_path)
    calls = 0

    def always_fail(_config):
        nonlocal calls
        calls += 1
        raise ObserverPaperCampaignRuntimeError("still incoherent")

    with pytest.raises(BackupSnapshotError):
        create_backup_snapshot(
            tmp_path / "backups",
            sources,
            created_at_unix_ms=_CREATED_AT,
            max_capture_attempts=3,
            preflight_validator=always_fail,
        )

    assert calls == 3
    root = tmp_path / "backups"
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_snapshot_rejects_missing_or_symlinked_required_sources(tmp_path: Path) -> None:
    sources, _config, *_payloads = _sources(tmp_path)
    sources.e11_path.unlink()

    with pytest.raises(BackupSnapshotError):
        create_backup_snapshot(
            tmp_path / "backups-missing",
            sources,
            created_at_unix_ms=_CREATED_AT,
            max_capture_attempts=1,
        )

    replacement = tmp_path / "real-e11.json"
    replacement.write_bytes(b"outside")
    try:
        os.symlink(replacement, sources.e11_path)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(BackupSnapshotError):
        create_backup_snapshot(
            tmp_path / "backups-symlink",
            sources,
            created_at_unix_ms=_CREATED_AT,
            max_capture_attempts=1,
        )
