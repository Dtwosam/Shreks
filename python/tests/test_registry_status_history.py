from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from shreks_brain.evaluation import TradingEvaluationReport, TradingPerformanceMetrics
from shreks_brain.registry import RegistryStatus, RegistryStore, build_registry_candidate


def report(candidate_version: str, fingerprint_char: str) -> TradingEvaluationReport:
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
        policy_version="eval-v1",
        candidate_version=candidate_version,
        metrics=metrics,
        calibration=None,
        setup_performance=(),
        regime_performance=(),
        evaluation_fingerprint_sha256=fingerprint_char * 64,
    )


def candidate(version: str, registered_at: int, fingerprint_char: str):
    return build_registry_candidate(
        candidate_version=version,
        strategy_version=f"strategy-{version}",
        feature_schema_version="d6-research-v1",
        feature_columns=("feature_a",),
        evaluation_report=report(version, fingerprint_char),
        registered_at_unix_ms=registered_at,
        trained_model=None,
        validation_run=None,
    )


def seeded_store(path: Path) -> RegistryStore:
    store = RegistryStore(path)
    store.register(candidate("candidate-v1", 100, "a"))
    store.register(candidate("candidate-v2", 110, "b"))
    return store


def test_explicit_promotion_is_audited_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    store = seeded_store(path)

    updated = store.record_status(
        candidate_version="candidate-v1",
        to_status=RegistryStatus.CHAMPION,
        decision_reference="e8-decision-001",
        decided_at_unix_ms=200,
        reason="Explicit external decision after required evidence.",
    )

    assert updated.current_status("candidate-v1") is RegistryStatus.CHAMPION
    assert updated.current_champion().candidate_version == "candidate-v1"  # type: ignore[union-attr]
    assert len(updated.status_events) == 1
    event = updated.status_events[0]
    assert event.from_status is RegistryStatus.CHALLENGER
    assert event.to_status is RegistryStatus.CHAMPION
    assert event.decision_reference == "e8-decision-001"
    assert len(event.event_fingerprint_sha256) == 64
    assert RegistryStore(path).load() == updated


def test_unknown_candidate_pre_registration_and_noop_transitions_fail_closed(tmp_path: Path) -> None:
    store = seeded_store(tmp_path / "registry.json")

    with pytest.raises(ValueError, match="candidate"):
        store.record_status(
            candidate_version="missing",
            to_status=RegistryStatus.CHAMPION,
            decision_reference="decision-x",
            decided_at_unix_ms=200,
            reason="Missing candidate cannot be promoted.",
        )

    with pytest.raises(ValueError, match="registration"):
        store.record_status(
            candidate_version="candidate-v1",
            to_status=RegistryStatus.CHAMPION,
            decision_reference="decision-y",
            decided_at_unix_ms=99,
            reason="Timestamp is invalid.",
        )

    with pytest.raises(ValueError, match="different"):
        store.record_status(
            candidate_version="candidate-v1",
            to_status=RegistryStatus.CHALLENGER,
            decision_reference="decision-z",
            decided_at_unix_ms=200,
            reason="No-op is invalid.",
        )


def test_registry_never_auto_demotes_to_make_room_for_second_champion(tmp_path: Path) -> None:
    store = seeded_store(tmp_path / "registry.json")
    store.record_status(
        candidate_version="candidate-v1",
        to_status=RegistryStatus.CHAMPION,
        decision_reference="promote-v1",
        decided_at_unix_ms=200,
        reason="First explicit promotion.",
    )

    with pytest.raises(ValueError, match="one current champion"):
        store.record_status(
            candidate_version="candidate-v2",
            to_status=RegistryStatus.CHAMPION,
            decision_reference="promote-v2-too-soon",
            decided_at_unix_ms=210,
            reason="Cannot silently replace incumbent.",
        )

    store.record_status(
        candidate_version="candidate-v1",
        to_status=RegistryStatus.RETIRED,
        decision_reference="retire-v1",
        decided_at_unix_ms=220,
        reason="Explicitly retire incumbent first.",
    )
    final = store.record_status(
        candidate_version="candidate-v2",
        to_status=RegistryStatus.CHAMPION,
        decision_reference="promote-v2",
        decided_at_unix_ms=230,
        reason="Explicitly promote replacement.",
    )
    assert final.current_champion().candidate_version == "candidate-v2"  # type: ignore[union-attr]


def test_retired_candidate_can_be_explicitly_reactivated_for_future_e8_rollback_rules(tmp_path: Path) -> None:
    store = seeded_store(tmp_path / "registry.json")
    store.record_status(
        candidate_version="candidate-v1",
        to_status=RegistryStatus.RETIRED,
        decision_reference="retire-v1",
        decided_at_unix_ms=200,
        reason="Retire explicitly.",
    )
    final = store.record_status(
        candidate_version="candidate-v1",
        to_status=RegistryStatus.CHALLENGER,
        decision_reference="reactivate-v1",
        decided_at_unix_ms=210,
        reason="Explicit reactivation for re-evaluation.",
    )
    assert final.current_status("candidate-v1") is RegistryStatus.CHALLENGER


def test_duplicate_event_is_idempotent_but_conflicting_event_identity_fails(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    store = seeded_store(path)
    first = store.record_status(
        candidate_version="candidate-v1",
        to_status=RegistryStatus.CHAMPION,
        decision_reference="decision-1",
        decided_at_unix_ms=200,
        reason="First explicit decision.",
    )
    event = first.status_events[0]
    before = path.read_bytes()

    duplicate = store.record_status_event(event)
    assert duplicate == first
    assert path.read_bytes() == before

    with pytest.raises(ValueError, match="event identity"):
        store.record_status(
            candidate_version="candidate-v1",
            to_status=RegistryStatus.RETIRED,
            decision_reference="decision-1",
            decided_at_unix_ms=200,
            reason="Conflicting reuse of the same decision identity.",
        )


def test_status_mutation_source_has_no_metric_driven_promotion_logic() -> None:
    source = inspect.getsource(RegistryStore.record_status) + inspect.getsource(
        RegistryStore.record_status_event
    )
    for forbidden in (
        "net_expectancy",
        "profit_factor",
        "maximum_drawdown",
        "win_rate",
        "brier_score",
        "expected_calibration_error",
        "enable_live",
        "TradeIntent",
    ):
        assert forbidden not in source
