from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.telemetry.sources import (
    TelemetrySourceConfig,
    TelemetrySourceError,
    collect_telemetry_sources,
)

from test_observer_campaign_runtime import _runtime_config
from test_observer_campaign_runner import AS_OF, RUN_ID


def _add_operational_tables(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE provider_health (
                provider TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                observed_at_unix_ms INTEGER NOT NULL,
                latency_ms INTEGER,
                detail TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE ingestion_checkpoints (
                provider TEXT NOT NULL,
                stream TEXT NOT NULL,
                cursor TEXT,
                updated_at_unix_ms INTEGER NOT NULL,
                PRIMARY KEY (provider, stream)
            );
            """
        )
        connection.commit()


def test_collect_sources_reads_operational_campaign_and_e11_without_mutation(tmp_path: Path) -> None:
    runtime = _runtime_config(tmp_path, max_cycles=1)
    _add_operational_tables(runtime.observer_database_path)
    proof_path = tmp_path / "proof.json"
    promotion_path = tmp_path / "promotion.json"
    evidence_path = runtime.evidence_path

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

    before_db = runtime.observer_database_path.stat().st_mtime_ns
    config = TelemetrySourceConfig(
        runtime_config=runtime,
        proof_path=proof_path,
        promotion_path=promotion_path,
    )

    sources = collect_telemetry_sources(config, as_of_unix_ms=AS_OF)

    assert sources.manifest.paper_run_id == RUN_ID
    assert sources.state == sources.manifest.initial_state
    assert sources.accounting_status == "VALID"
    assert sources.operational.provider_count == 1
    assert sources.operational.unhealthy_provider_count == 0
    assert sources.operational.candidate_count == 2
    assert sources.operational.latest_ingestion_checkpoint_at_unix_ms == AS_OF - 20
    assert sources.operational.latest_market_observed_at_unix_ms is not None
    assert sources.operational.holder_distribution_count == 0
    assert sources.operational.paper_quote_count == 0
    assert sources.evaluated_trades == ()
    assert sources.proof_assessments == ()
    assert sources.promotion_assessments == ()
    assert sources.optional_source_errors == (
        "PROOF_ASSESSMENT_UNAVAILABLE",
        "PROMOTION_ASSESSMENT_UNAVAILABLE",
    )
    assert runtime.observer_database_path.stat().st_mtime_ns == before_db
    assert not evidence_path.exists()
    assert not proof_path.exists()
    assert not promotion_path.exists()


def test_operational_sqlite_is_opened_read_only_and_missing_db_is_not_created(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    runtime = _runtime_config(seed, max_cycles=1)
    missing = tmp_path / "missing" / "observer.sqlite"
    config = TelemetrySourceConfig(
        runtime_config=type(runtime)(
            observer_database_path=missing,
            evidence_path=runtime.evidence_path,
            manifest_path=runtime.manifest_path,
            cycle_interval_seconds=runtime.cycle_interval_seconds,
            max_cycles=runtime.max_cycles,
        ),
        proof_path=tmp_path / "proof.json",
        promotion_path=tmp_path / "promotion.json",
    )

    with pytest.raises(TelemetrySourceError, match="operational database"):
        collect_telemetry_sources(config, as_of_unix_ms=AS_OF)

    assert not missing.exists()


def test_corrupt_optional_proof_and_promotion_sources_are_reported_not_fabricated(
    tmp_path: Path,
) -> None:
    runtime = _runtime_config(tmp_path, max_cycles=1)
    _add_operational_tables(runtime.observer_database_path)
    proof_path = tmp_path / "proof.json"
    promotion_path = tmp_path / "promotion.json"
    proof_path.write_text("{broken", encoding="utf-8")
    promotion_path.write_text("{broken", encoding="utf-8")

    sources = collect_telemetry_sources(
        TelemetrySourceConfig(runtime, proof_path, promotion_path),
        as_of_unix_ms=AS_OF,
    )

    assert sources.proof_assessments == ()
    assert sources.promotion_assessments == ()
    assert sources.optional_source_errors == (
        "PROOF_ASSESSMENT_INVALID",
        "PROMOTION_ASSESSMENT_INVALID",
    )


def test_source_config_and_timestamp_validation_fail_closed(tmp_path: Path) -> None:
    runtime = _runtime_config(tmp_path, max_cycles=1)
    with pytest.raises(ValueError):
        TelemetrySourceConfig(runtime_config="wrong", proof_path=tmp_path / "a", promotion_path=tmp_path / "b")  # type: ignore[arg-type]

    config = TelemetrySourceConfig(runtime, tmp_path / "a", tmp_path / "b")
    with pytest.raises(TelemetrySourceError):
        collect_telemetry_sources(config, as_of_unix_ms=-1)
