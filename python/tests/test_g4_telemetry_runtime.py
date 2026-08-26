from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.telemetry import LayerStatus, encode_telemetry_snapshot
from shreks_brain.telemetry.runtime import (
    TelemetryRuntimeConfigError,
    load_telemetry_runtime_config,
    preflight_telemetry_runtime,
    run_telemetry_once,
)

from test_g4_telemetry_sources import _add_operational_tables
from test_observer_campaign_runner import AS_OF
from test_observer_campaign_runtime import _runtime_config


def _env(tmp_path: Path) -> tuple[dict[str, str], object]:
    runtime = _runtime_config(tmp_path, max_cycles=1)
    _add_operational_tables(runtime.observer_database_path)
    with sqlite3.connect(runtime.observer_database_path) as connection:
        connection.execute(
            "INSERT INTO provider_health(provider,status,observed_at_unix_ms,latency_ms,detail,consecutive_failures) "
            "VALUES ('helius','healthy',?,12,NULL,0)",
            (AS_OF - 10,),
        )
        connection.execute(
            "INSERT INTO ingestion_checkpoints(provider,stream,cursor,updated_at_unix_ms) "
            "VALUES ('helius','launches','cursor-a',?)",
            (AS_OF - 20,),
        )
        connection.commit()

    env = {
        "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH": str(runtime.observer_database_path),
        "SHREKS_PAPER_CAMPAIGN_E11_PATH": str(runtime.evidence_path),
        "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH": str(runtime.manifest_path),
        "SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS": str(runtime.cycle_interval_seconds),
        "SHREKS_PAPER_CAMPAIGN_MAX_CYCLES": "1",
        "SHREKS_TELEMETRY_PROOF_PATH": str(tmp_path / "proof.json"),
        "SHREKS_TELEMETRY_PROMOTION_PATH": str(tmp_path / "promotion.json"),
        "SHREKS_TELEMETRY_OUTPUT_PATH": str(tmp_path / "telemetry" / "current.json"),
        "SHREKS_TELEMETRY_EVALUATION_POLICY_VERSION": "g4-paper-evaluation-v1",
        "SHREKS_TELEMETRY_CALIBRATION_BUCKET_COUNT": "2",
    }
    return env, runtime


def test_runtime_config_is_explicit_and_rejects_unknown_telemetry_keys(tmp_path: Path) -> None:
    env, _runtime = _env(tmp_path)
    config = load_telemetry_runtime_config(env)

    assert config.output_path == tmp_path / "telemetry" / "current.json"
    assert config.source_config.proof_path == tmp_path / "proof.json"
    assert config.source_config.promotion_path == tmp_path / "promotion.json"
    assert config.evaluation_policy_version == "g4-paper-evaluation-v1"
    assert config.calibration_bucket_count == 2

    invalid = dict(env)
    invalid["SHREKS_TELEMETRY_UNSUPPORTED"] = "nope"
    with pytest.raises(TelemetryRuntimeConfigError, match="unsupported telemetry"):
        load_telemetry_runtime_config(invalid)


def test_preflight_reads_required_sources_without_creating_snapshot(tmp_path: Path) -> None:
    env, runtime = _env(tmp_path)
    config = load_telemetry_runtime_config(env)
    db_before = runtime.observer_database_path.stat().st_mtime_ns

    result = preflight_telemetry_runtime(config, as_of_unix_ms=AS_OF)

    assert result.paper_run_id
    assert result.accounting_status == "VALID"
    assert result.live_state == "DISABLED"
    assert not config.output_path.exists()
    assert runtime.observer_database_path.stat().st_mtime_ns == db_before


def test_one_shot_runtime_writes_only_derived_snapshot(tmp_path: Path) -> None:
    env, runtime = _env(tmp_path)
    config = load_telemetry_runtime_config(env)
    db_before = runtime.observer_database_path.stat().st_mtime_ns
    manifest_before = runtime.manifest_path.read_bytes()
    evidence_existed_before = runtime.evidence_path.exists()
    evidence_before = runtime.evidence_path.read_bytes() if evidence_existed_before else None

    snapshot = run_telemetry_once(config, as_of_unix_ms=AS_OF)

    assert snapshot.mode == "PAPER"
    assert snapshot.proof_risk.live_state == "DISABLED"
    assert snapshot.proof_risk.status is LayerStatus.UNAVAILABLE
    assert config.output_path.read_text(encoding="utf-8") == encode_telemetry_snapshot(snapshot)
    assert config.output_path.stat().st_mode & 0o777 == 0o600
    assert runtime.observer_database_path.stat().st_mtime_ns == db_before
    assert runtime.manifest_path.read_bytes() == manifest_before
    assert runtime.evidence_path.exists() is evidence_existed_before
    if evidence_existed_before:
        assert runtime.evidence_path.read_bytes() == evidence_before


def test_runtime_timestamp_validation_fails_closed(tmp_path: Path) -> None:
    env, _runtime = _env(tmp_path)
    config = load_telemetry_runtime_config(env)

    with pytest.raises(TelemetryRuntimeConfigError):
        preflight_telemetry_runtime(config, as_of_unix_ms=-1)
    with pytest.raises(TelemetryRuntimeConfigError):
        run_telemetry_once(config, as_of_unix_ms=-1)
