from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shreks_brain.evaluation import TradingEvaluationReport, TradingPerformanceMetrics
from shreks_brain.registry import RegistryStatus, RegistryStore, build_registry_candidate


def empty_report(candidate_version: str) -> TradingEvaluationReport:
    metrics = TradingPerformanceMetrics(
        trade_count=0,
        win_count=0,
        loss_count=0,
        flat_count=0,
        gross_pnl_usd=0.0,
        net_pnl_usd=0.0,
        net_expectancy_usd=None,
        net_expectancy_pct=None,
        profit_factor=None,
        maximum_drawdown_usd=0.0,
        maximum_drawdown_pct=0.0,
        average_winner_usd=None,
        average_loser_usd=None,
        win_rate=None,
        turnover_usd=0.0,
        turnover_to_starting_equity=0.0,
        execution_friction_usd=0.0,
        explicit_cost_usd=0.0,
        total_cost_usd=0.0,
        cost_burden_pct=None,
    )
    return TradingEvaluationReport(
        schema_version="e5-trading-evaluation-v1",
        policy_version="eval-empty-v1",
        candidate_version=candidate_version,
        metrics=metrics,
        calibration=None,
        setup_performance=(),
        regime_performance=(),
        evaluation_fingerprint_sha256=(candidate_version[-1] * 64),
    )


def candidate(version: str, registered_at: int = 100):
    return build_registry_candidate(
        candidate_version=version,
        strategy_version=f"strategy-{version}",
        feature_schema_version="d6-research-v1",
        feature_columns=("feature_a",),
        evaluation_report=empty_report(version),
        registered_at_unix_ms=registered_at,
        trained_model=None,
        validation_run=None,
    )


def test_missing_store_loads_valid_empty_registry(tmp_path: Path) -> None:
    path = tmp_path / "registry" / "registry.json"
    registry = RegistryStore(path).load()

    assert registry.candidates == ()
    assert registry.status_events == ()
    assert registry.current_champion() is None
    assert len(registry.registry_fingerprint_sha256) == 64
    assert not path.exists()


def test_register_round_trip_is_canonical_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    store = RegistryStore(path)

    first = store.register(candidate("candidate-v2"))
    second = store.register(candidate("candidate-v1"))
    loaded = RegistryStore(path).load()

    assert loaded == second
    assert tuple(value.candidate_version for value in loaded.candidates) == (
        "candidate-v1",
        "candidate-v2",
    )
    assert loaded.current_status("candidate-v1") is RegistryStatus.CHALLENGER
    assert first.registry_fingerprint_sha256 != second.registry_fingerprint_sha256
    assert not path.with_name(path.name + ".tmp").exists()

    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert raw == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def test_identical_registration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    store = RegistryStore(path)
    item = candidate("candidate-v1")

    first = store.register(item)
    before = path.read_bytes()
    second = store.register(item)

    assert second == first
    assert path.read_bytes() == before


def test_conflicting_candidate_identity_fails_closed(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.json")
    item = candidate("candidate-v1")
    store.register(item)

    conflict = replace(
        item,
        strategy_version="different-strategy",
        candidate_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="candidate version"):
        store.register(conflict)


def test_load_rejects_invalid_json_and_tampered_candidate(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="registry file"):
        RegistryStore(path).load()

    store = RegistryStore(path)
    path.unlink()
    store.register(candidate("candidate-v1"))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["candidates"][0]["strategy_version"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="candidate fingerprint"):
        RegistryStore(path).load()


def test_load_rejects_tampered_registry_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    RegistryStore(path).register(candidate("candidate-v1"))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["registry_fingerprint_sha256"] = "f" * 64
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="registry fingerprint"):
        RegistryStore(path).load()
