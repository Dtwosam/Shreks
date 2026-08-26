from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path
import sqlite3

import pytest

import shreks_brain.backup.restore as restore_module
from shreks_brain.backup import (
    BackupArtifactRole,
    BackupRestoreError,
    create_backup_snapshot,
    restore_backup_bundle,
    verify_backup_bundle,
)
from shreks_brain.observer_campaign.runtime import preflight_observer_paper_campaign_runtime
from shreks_brain.observer_campaign.runtime_config import ObserverPaperCampaignRuntimeConfig
from shreks_brain.paper_validation import load_latest_paper_checkpoint
from shreks_brain.risk_control import (
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    apply_operator_risk_control_command,
    load_operator_risk_control_state,
)

from test_g8_backup_snapshot import _CREATED_AT, _sources


_KILL_REASON = "g8 restore proof emergency latch"


def _sha_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _latched_bundle(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    sources, config, e11, campaign, _risk, alerts = _sources(source_root)
    apply_operator_risk_control_command(
        sources.risk_control_path,
        OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH,
        expected_revision=0,
        observed_at_unix_ms=_CREATED_AT - 1,
        source=OperatorRiskControlSource.HOST_CLI,
        reason=_KILL_REASON,
    )
    latched_risk = sources.risk_control_path.read_bytes()
    bundle = create_backup_snapshot(
        tmp_path / "backups",
        sources,
        created_at_unix_ms=_CREATED_AT,
        max_capture_attempts=1,
    )
    return bundle, sources, config, e11, campaign, latched_risk, alerts


def _restored_config(staging: Path) -> ObserverPaperCampaignRuntimeConfig:
    return ObserverPaperCampaignRuntimeConfig(
        observer_database_path=(staging / "operational.sqlite3").resolve(),
        evidence_path=(staging / "e11.json").resolve(),
        manifest_path=(staging / "paper-campaign.json").resolve(),
        cycle_interval_seconds=1.0,
        max_cycles=1,
        risk_control_path=(staging / "operator-control.json").resolve(),
    )


def test_restore_to_empty_staging_preserves_paper_checkpoint_attribution_and_preflight(
    tmp_path: Path,
) -> None:
    bundle, sources, config, _e11, _campaign, _risk, _alerts = _latched_bundle(tmp_path)
    source_checkpoint = load_latest_paper_checkpoint(
        sources.operational_database_path,
        verify_backup_bundle(bundle).paper_run_id,
    )
    assert source_checkpoint is not None
    staging = tmp_path / "restore-stage"

    result = restore_backup_bundle(bundle, staging)

    manifest = verify_backup_bundle(bundle)
    assert result.paper_run_id == manifest.paper_run_id
    assert (
        result.campaign_manifest_fingerprint_sha256
        == manifest.campaign_manifest_fingerprint_sha256
    )
    assert result.checkpoint_sequence == source_checkpoint.sequence
    assert result.state_as_of_unix_ms == source_checkpoint.state.as_of_unix_ms
    assert result.verified_artifact_sha256 == {
        record.role.value: record.sha256 for record in manifest.artifacts
    }

    restored_checkpoint = load_latest_paper_checkpoint(
        staging / "operational.sqlite3",
        manifest.paper_run_id,
    )
    assert restored_checkpoint == source_checkpoint

    preflight = preflight_observer_paper_campaign_runtime(
        _restored_config(staging),
        status_sink=lambda _line: None,
    )
    assert preflight.restored_state == source_checkpoint.state
    assert config.manifest_path.read_bytes() == (staging / "paper-campaign.json").read_bytes()


def test_restore_preserves_e11_g7_kill_latch_and_pending_alert_bytes_exactly(
    tmp_path: Path,
) -> None:
    bundle, _sources_value, _config, e11, campaign, risk, alerts = _latched_bundle(tmp_path)
    staging = tmp_path / "restore-stage"

    restore_backup_bundle(bundle, staging)

    assert (staging / "e11.json").read_bytes() == e11
    assert (staging / "paper-campaign.json").read_bytes() == campaign
    assert (staging / "operator-control.json").read_bytes() == risk
    assert (staging / "alerts-state.json").read_bytes() == alerts
    restored_risk = load_operator_risk_control_state(staging / "operator-control.json")
    assert restored_risk.revision == 1
    assert restored_risk.halt_new_entries is True
    assert restored_risk.kill_switch_active is True
    assert restored_risk.last_reason == _KILL_REASON


def test_restore_sqlite_is_integral_private_and_contains_no_wal_sidecars(tmp_path: Path) -> None:
    bundle, *_rest = _latched_bundle(tmp_path)
    staging = tmp_path / "restore-stage"

    restore_backup_bundle(bundle, staging)

    database = staging / "operational.sqlite3"
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
    finally:
        connection.close()
    assert os.stat(staging).st_mode & 0o777 == 0o700
    for path in staging.iterdir():
        assert path.is_file()
        assert os.stat(path).st_mode & 0o777 == 0o600
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_restore_refuses_nonempty_target_without_overwriting_anything(tmp_path: Path) -> None:
    bundle, *_rest = _latched_bundle(tmp_path)
    staging = tmp_path / "restore-stage"
    staging.mkdir()
    sentinel = staging / "keep.txt"
    sentinel.write_text("operator-owned", encoding="utf-8")

    with pytest.raises(BackupRestoreError):
        restore_backup_bundle(bundle, staging)

    assert sentinel.read_text(encoding="utf-8") == "operator-owned"
    assert list(staging.iterdir()) == [sentinel]


def test_restore_refuses_symlink_target(tmp_path: Path) -> None:
    bundle, *_rest = _latched_bundle(tmp_path)
    real = tmp_path / "real-stage"
    real.mkdir()
    link = tmp_path / "restore-stage"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(BackupRestoreError):
        restore_backup_bundle(bundle, link)

    assert list(real.iterdir()) == []


def test_restore_rejects_tampered_bundle_before_creating_staged_artifacts(tmp_path: Path) -> None:
    bundle, *_rest = _latched_bundle(tmp_path)
    manifest = verify_backup_bundle(bundle)
    e11_record = next(
        record for record in manifest.artifacts if record.role is BackupArtifactRole.E11_EVIDENCE
    )
    (bundle / e11_record.relative_path).write_bytes(b"tampered")
    staging = tmp_path / "restore-stage"

    with pytest.raises(BackupRestoreError):
        restore_backup_bundle(bundle, staging)

    assert not staging.exists() or list(staging.iterdir()) == []


def test_restore_is_read_only_against_source_bundle(tmp_path: Path) -> None:
    bundle, *_rest = _latched_bundle(tmp_path)
    before = _sha_tree(bundle)

    restore_backup_bundle(bundle, tmp_path / "restore-stage")

    assert _sha_tree(bundle) == before


def test_restore_module_has_no_live_wallet_signing_submission_or_service_control_authority() -> None:
    source = inspect.getsource(restore_module).lower()
    for forbidden in (
        "systemctl",
        "service restart",
        "service stop",
        "service start",
        "shreks_mode=live",
        "--live",
        "wallet",
        "private_key",
        "seed_phrase",
        "sign_transaction",
        "submit_transaction",
        "subprocess",
    ):
        assert forbidden not in source
