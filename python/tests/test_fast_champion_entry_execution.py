from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from shreks_brain.fast_champion import (
    FAST_FORECAST_CHAMPION_SCHEMA_NAME,
    FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
    FastForecastChampionArtifact,
    FastForecastChampionMember,
    FastForecastChampionSelection,
    write_fast_forecast_champion,
)
from shreks_brain.fast_champion.models import (
    fast_forecast_champion_fingerprint_sha256,
)
from shreks_brain.fast_deterministic_offline import (
    FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION,
    FastChampionEntryExecutionEvidence,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    build_fast_champion_entry_execution_evidence,
)
from shreks_brain.fast_learning import (
    FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
    FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
    FAST_FORECAST_FEATURE_SCHEMA_VERSION,
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTargetKind,
    fast_forecast_artifact_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
)


T0 = 100_000


def _window(window_ms: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=0,
        sell_count=0,
        unique_buy_actors=0,
        unique_sell_actors=0,
        buy_arrival_rate_per_second=0.0,
        sell_arrival_rate_per_second=0.0,
        count_imbalance=0.0,
        buy_base_quantity=0.0,
        sell_base_quantity=0.0,
        buy_quote_quantity=0.0,
        sell_quote_quantity=0.0,
        net_quote_quantity=0.0,
        quote_flow_imbalance=0.0,
        quote_flow_velocity_per_second=0.0,
        quote_flow_acceleration_per_second2=0.0,
        local_high_price_quote=None,
        local_high_sequence=None,
        local_high_observed_at_unix_ms=None,
        local_low_price_quote=None,
        local_low_sequence=None,
        local_low_observed_at_unix_ms=None,
        post_high_low_price_quote=None,
        post_high_low_sequence=None,
        post_high_low_observed_at_unix_ms=None,
        last_price_quote=10.0,
        drawdown_from_local_high=0.0,
        recovery_from_local_low=0.0,
    )


def _record(*, at: int = T0) -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature="champion-exec-sig",
        decision_ordinal=0,
        decision_sequence=1,
        mint="mint-champion-exec",
        quote_mint="quote-champion-exec",
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=at,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=at - 1,
        decision_occurred_at_unix_ms=at - 2,
        decision_slot=999,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=10.0,
        decision_entry_total_quote=100.0,
        snapshot_as_of_unix_ms=at,
        snapshot_last_sequence=1,
        snapshot_last_price_quote=10.0,
        last_reserve_context=None,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _artifact(
    *,
    target: FastForecastTarget = FastForecastTarget.ENDPOINT_RETURN_BPS,
    horizon_ms: int = 30_000,
    prediction_bps: float = 500.0,
    max_training_at: int = T0 - 2_000,
) -> FastForecastBaselineArtifact:
    provisional = FastForecastBaselineArtifact(
        schema_name=FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
        schema_version=FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
        model_version="endpoint-mean-v1",
        model_family=FastForecastModelFamily.MEAN_REGRESSOR,
        target=target,
        target_kind=FastForecastTargetKind.CONTINUOUS,
        horizon_ms=horizon_ms,
        feature_schema_version=FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        training_policy_version="mean-policy-v1",
        training_bundle_fingerprint_sha256="a" * 64,
        future_path_label_version=1,
        training_row_count=10,
        target_unavailable_row_count=0,
        positive_row_count=None,
        negative_row_count=None,
        min_training_decision_observed_at_unix_ms=max_training_at - 1_000,
        max_training_decision_observed_at_unix_ms=max_training_at,
        training_data_fingerprint_sha256="b" * 64,
        feature_transforms=(),
        coefficients=(),
        intercept=None,
        constant_prediction=prediction_bps,
        artifact_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        artifact_fingerprint_sha256=fast_forecast_artifact_fingerprint_sha256(
            provisional
        ),
    )


def _champion(
    path: Path,
    *,
    target: FastForecastTarget = FastForecastTarget.ENDPOINT_RETURN_BPS,
    horizon_ms: int = 30_000,
    prediction_bps: float = 500.0,
    selected_at: int = T0 - 1_000,
    max_training_at: int = T0 - 2_000,
) -> FastForecastChampionArtifact:
    artifact = _artifact(
        target=target,
        horizon_ms=horizon_ms,
        prediction_bps=prediction_bps,
        max_training_at=max_training_at,
    )
    member = FastForecastChampionMember(
        member_key=f"{target.value}@{horizon_ms}ms",
        forecast_artifact=artifact,
        validation_policy_version="chronological-validation-v1",
        validation_run_fingerprint_sha256="c" * 64,
        test_evaluation_policy_version="test-evaluation-v1",
        test_evaluation_report_fingerprint_sha256="d" * 64,
        test_scored_observation_count=10,
        test_target_unavailable_count=0,
    )
    provisional = FastForecastChampionArtifact(
        schema_name=FAST_FORECAST_CHAMPION_SCHEMA_NAME,
        schema_version=FAST_FORECAST_CHAMPION_SCHEMA_VERSION,
        champion_version="fast-champion-v1",
        selection=FastForecastChampionSelection(
            decision_reference="explicit-selection-proof",
            decided_at_unix_ms=selected_at,
            reason="explicit selected fixture",
        ),
        feature_schema_version=artifact.feature_schema_version,
        training_bundle_fingerprint_sha256=(
            artifact.training_bundle_fingerprint_sha256
        ),
        future_path_label_version=artifact.future_path_label_version,
        members=(member,),
        champion_fingerprint_sha256="0" * 64,
    )
    champion = replace(
        provisional,
        champion_fingerprint_sha256=fast_forecast_champion_fingerprint_sha256(
            provisional
        ),
    )
    write_fast_forecast_champion(champion, path)
    return champion


def _leg() -> FastOfflineExecutionLegCost:
    return FastOfflineExecutionLegCost(
        effective_fee_bps=50,
        expected_impact_bps=20,
        expected_slippage_bps=30,
        expected_latency_bps=10,
        network_fee_quote=0.01,
        priority_fee_quote=0.02,
        expected_failure_cost_quote=0.03,
    )


def _cost_model() -> FastOfflineExecutionCostModel:
    return FastOfflineExecutionCostModel(
        version=1,
        entry=_leg(),
        exit=_leg(),
    )


def test_champion_endpoint_return_builds_shared_fl3_execution_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "champion.json"
    champion = _champion(path)

    evidence = build_fast_champion_entry_execution_evidence(
        champion_path=path,
        record=_record(),
        horizon_ms=30_000,
        cost_model=_cost_model(),
        base_quantity=10.0,
        exit_capacity_base=12.0,
        required_edge_bps=200,
        risk_margin_bps=100,
        execution_policy_source_version="fl3-economic-policy-v1",
        exit_capacity_source_version="jupiter-exit-capacity-v2",
    )

    assert type(evidence) is FastChampionEntryExecutionEvidence
    assert evidence.version == FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION
    assert evidence.champion_version == champion.champion_version
    assert (
        evidence.champion_fingerprint_sha256
        == champion.champion_fingerprint_sha256
    )
    assert evidence.member_key == "endpoint_return_bps@30000ms"
    assert evidence.prediction.predicted_value == pytest.approx(500.0)
    assert evidence.execution.trade.executable_entry_price_quote == 10.0
    assert evidence.execution.trade.forecast_exit_price_quote == pytest.approx(
        10.5
    )
    assert evidence.execution.trade.exit_capacity_base == 12.0
    assert evidence.execution.cost_model == _cost_model()
    assert evidence.execution_policy_source_version == "fl3-economic-policy-v1"
    assert evidence.exit_capacity_source_version == "jupiter-exit-capacity-v2"
    assert champion.champion_fingerprint_sha256 in evidence.forecast_source_version
    assert (
        champion.members[0].forecast_artifact.artifact_fingerprint_sha256
        in evidence.forecast_source_version
    )


def test_champion_selected_after_decision_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future-selection.json"
    _champion(path, selected_at=T0 + 1)

    with pytest.raises(ValueError, match="selection|decision|future|chronolog"):
        build_fast_champion_entry_execution_evidence(
            champion_path=path,
            record=_record(),
            horizon_ms=30_000,
            cost_model=_cost_model(),
            base_quantity=10.0,
            exit_capacity_base=12.0,
            required_edge_bps=200,
            risk_margin_bps=100,
            execution_policy_source_version="fl3-economic-policy-v1",
            exit_capacity_source_version="jupiter-exit-capacity-v2",
        )


def test_champion_trained_through_decision_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future-training.json"
    _champion(path, max_training_at=T0)

    with pytest.raises(ValueError, match="training|decision|leak|chronolog"):
        build_fast_champion_entry_execution_evidence(
            champion_path=path,
            record=_record(),
            horizon_ms=30_000,
            cost_model=_cost_model(),
            base_quantity=10.0,
            exit_capacity_base=12.0,
            required_edge_bps=200,
            risk_margin_bps=100,
            execution_policy_source_version="fl3-economic-policy-v1",
            exit_capacity_source_version="jupiter-exit-capacity-v2",
        )


def test_cost_adjusted_champion_member_cannot_substitute_for_raw_endpoint_return(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cost-adjusted.json"
    _champion(
        path,
        target=FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    )

    with pytest.raises(ValueError, match="endpoint|raw|member|cost"):
        build_fast_champion_entry_execution_evidence(
            champion_path=path,
            record=_record(),
            horizon_ms=30_000,
            cost_model=_cost_model(),
            base_quantity=10.0,
            exit_capacity_base=12.0,
            required_edge_bps=200,
            risk_margin_bps=100,
            execution_policy_source_version="fl3-economic-policy-v1",
            exit_capacity_source_version="jupiter-exit-capacity-v2",
        )


def test_non_positive_gross_forecast_exit_price_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "negative-price.json"
    _champion(path, prediction_bps=-10_000.0)

    with pytest.raises(ValueError, match="forecast|exit|positive"):
        build_fast_champion_entry_execution_evidence(
            champion_path=path,
            record=_record(),
            horizon_ms=30_000,
            cost_model=_cost_model(),
            base_quantity=10.0,
            exit_capacity_base=12.0,
            required_edge_bps=200,
            risk_margin_bps=100,
            execution_policy_source_version="fl3-economic-policy-v1",
            exit_capacity_source_version="jupiter-exit-capacity-v2",
        )


def test_champion_execution_source_has_no_future_labels_io_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_offline"
        / "champion_execution.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "future_path",
        "counterfactual",
        "sqlite3",
        "requests.",
        "httpx",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "evaluate_fast_policy_superiority",
        "promotion",
    ):
        assert forbidden not in source
