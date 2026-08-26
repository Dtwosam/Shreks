from __future__ import annotations

from dataclasses import replace
import os
import sqlite3
from pathlib import Path

import pytest

import shreks_brain.telemetry.snapshot as snapshot_module
from shreks_brain.promotion import PromotionDecision
from shreks_brain.telemetry import LayerStatus, encode_telemetry_snapshot
from shreks_brain.telemetry.snapshot import (
    TelemetrySnapshotError,
    assemble_telemetry_snapshot,
    write_telemetry_snapshot,
)
from shreks_brain.telemetry.sources import TelemetrySourceConfig, collect_telemetry_sources

from test_g4_telemetry_financial import (
    SHA_A,
    _evaluation_policy,
    _promotion_assessment,
    _proof_assessment,
)
from test_g4_telemetry_sources import _add_operational_tables
from test_observer_campaign_runner import AS_OF
from test_observer_campaign_runtime import _runtime_config


def _runtime_and_sources(tmp_path: Path):
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
    config = TelemetrySourceConfig(
        runtime_config=runtime,
        proof_path=tmp_path / "proof.json",
        promotion_path=tmp_path / "promotion.json",
    )
    return runtime, collect_telemetry_sources(config, as_of_unix_ms=AS_OF)


def _sources_with_reporting_evidence(sources):
    proof = _proof_assessment(
        sources,
        evaluated_at_unix_ms=AS_OF,
        fingerprint=SHA_A,
        trade_count=0,
        distinct_mints=0,
        expectancy_pct=0.0,
        profit_factor=0.0,
        drawdown_pct=0.0,
        cost_burden_pct=0.0,
    )
    promotion = _promotion_assessment(
        sources,
        evaluated_at_unix_ms=AS_OF,
        fingerprint=SHA_A,
        decision=PromotionDecision.ELIGIBLE,
    )
    return replace(
        sources,
        proof_assessments=(proof,),
        promotion_assessments=(promotion,),
        optional_source_errors=(),
    )


def test_assemble_snapshot_maps_all_four_layers_and_unavailable_precedence(
    tmp_path: Path,
) -> None:
    _runtime, sources = _runtime_and_sources(tmp_path)
    policy = _evaluation_policy(sources.state.ledger.starting_cash_usd)

    snapshot = assemble_telemetry_snapshot(
        sources,
        evaluation_policy=policy,
        generated_at_unix_ms=AS_OF + 5,
    )

    assert snapshot.generated_at_unix_ms == AS_OF + 5
    assert snapshot.mode == "PAPER"
    assert snapshot.system.status is LayerStatus.HEALTHY
    assert snapshot.system.provider_count == 1
    assert snapshot.system.unhealthy_provider_count == 0
    assert (
        snapshot.system.latest_market_observed_at_unix_ms
        == sources.operational.latest_market_observed_at_unix_ms
    )
    assert snapshot.system.market_age_ms == (
        AS_OF - sources.operational.latest_market_observed_at_unix_ms
    )
    assert snapshot.system.latest_ingestion_checkpoint_at_unix_ms == AS_OF - 20
    assert snapshot.system.paper_last_cycle_at_unix_ms == sources.state.last_cycle_at_unix_ms
    assert snapshot.system.accounting_status == sources.accounting_status
    assert snapshot.system.host_metrics_available is False

    assert snapshot.trading.candidate_count == sources.operational.candidate_count
    assert (
        snapshot.trading.holder_distribution_count
        == sources.operational.holder_distribution_count
    )
    assert snapshot.trading.paper_quote_count == sources.operational.paper_quote_count
    assert snapshot.trading.terminal_paper_entry_count == len(sources.state.ledger.entries)
    assert snapshot.trading.open_position_count == len(sources.state.managed_positions)
    assert snapshot.trading.closed_position_count == sum(
        position.state.value == "CLOSED" for position in sources.state.ledger.positions
    )
    assert snapshot.trading.pending_entry is (sources.state.pending_entry is not None)
    assert snapshot.trading.candidate_version == sources.manifest.candidate.candidate_version
    assert snapshot.trading.candidate_mint is None
    assert snapshot.trading.paper_run_id == sources.manifest.paper_run_id
    assert snapshot.trading.historical_score_count is None
    assert snapshot.trading.historical_decision_count is None

    assert snapshot.money.daily_loss_usd is None
    assert snapshot.proof_risk.kill_switch_active is None
    assert snapshot.proof_risk.live_state == "DISABLED"
    assert snapshot.proof_risk.status is LayerStatus.UNAVAILABLE
    assert snapshot.overall_status is LayerStatus.UNAVAILABLE


def test_reporting_evidence_allows_healthy_overall_status(tmp_path: Path) -> None:
    _runtime, sources = _runtime_and_sources(tmp_path)
    sources = _sources_with_reporting_evidence(sources)

    snapshot = assemble_telemetry_snapshot(
        sources,
        evaluation_policy=_evaluation_policy(sources.state.ledger.starting_cash_usd),
        generated_at_unix_ms=AS_OF,
    )

    assert snapshot.system.status is LayerStatus.HEALTHY
    assert snapshot.trading.status is LayerStatus.HEALTHY
    assert snapshot.money.status is LayerStatus.HEALTHY
    assert snapshot.proof_risk.status is LayerStatus.HEALTHY
    assert snapshot.overall_status is LayerStatus.HEALTHY


def test_provider_degradation_is_reported_without_freshness_threshold_invention(
    tmp_path: Path,
) -> None:
    runtime, _sources = _runtime_and_sources(tmp_path)
    with sqlite3.connect(runtime.observer_database_path) as connection:
        connection.execute(
            "UPDATE provider_health SET status='degraded', consecutive_failures=2 "
            "WHERE provider='helius'"
        )
        connection.commit()
    sources = collect_telemetry_sources(
        TelemetrySourceConfig(
            runtime_config=runtime,
            proof_path=tmp_path / "proof.json",
            promotion_path=tmp_path / "promotion.json",
        ),
        as_of_unix_ms=AS_OF,
    )
    sources = _sources_with_reporting_evidence(sources)

    snapshot = assemble_telemetry_snapshot(
        sources,
        evaluation_policy=_evaluation_policy(sources.state.ledger.starting_cash_usd),
        generated_at_unix_ms=AS_OF,
    )

    assert snapshot.system.status is LayerStatus.DEGRADED
    assert snapshot.system.unhealthy_provider_count == 1
    assert snapshot.system.source_errors == ("PROVIDER_HEALTH_DEGRADED",)
    assert snapshot.overall_status is LayerStatus.DEGRADED


def test_atomic_writer_changes_only_output_and_uses_restrictive_permissions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime, sources = _runtime_and_sources(tmp_path)
    snapshot = assemble_telemetry_snapshot(
        sources,
        evaluation_policy=_evaluation_policy(sources.state.ledger.starting_cash_usd),
        generated_at_unix_ms=AS_OF,
    )
    output = tmp_path / "telemetry" / "current.json"

    db_before = runtime.observer_database_path.stat().st_mtime_ns
    manifest_before = runtime.manifest_path.read_bytes()
    evidence_existed_before = runtime.evidence_path.exists()
    evidence_before = (
        runtime.evidence_path.read_bytes() if evidence_existed_before else None
    )

    calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(snapshot_module.os, "replace", recording_replace)

    write_telemetry_snapshot(snapshot, output)

    assert len(calls) == 1
    temporary, destination = calls[0]
    assert destination == output
    assert temporary.parent == output.parent
    assert not temporary.exists()
    assert output.read_bytes() == encode_telemetry_snapshot(snapshot).encode("utf-8")
    assert output.stat().st_mode & 0o777 == 0o600
    assert runtime.observer_database_path.stat().st_mtime_ns == db_before
    assert runtime.manifest_path.read_bytes() == manifest_before
    assert runtime.evidence_path.exists() is evidence_existed_before
    if evidence_existed_before:
        assert runtime.evidence_path.read_bytes() == evidence_before


def test_generated_time_before_source_time_fails_closed(tmp_path: Path) -> None:
    _runtime, sources = _runtime_and_sources(tmp_path)
    with pytest.raises(TelemetrySnapshotError, match="generated timestamp"):
        assemble_telemetry_snapshot(
            sources,
            evaluation_policy=_evaluation_policy(sources.state.ledger.starting_cash_usd),
            generated_at_unix_ms=AS_OF - 1,
        )
