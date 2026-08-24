import builtins
from dataclasses import replace
import subprocess
import sys

import pytest

from shreks_brain.decision import DecisionAction, TradeDecision
from shreks_brain.features import (
    FEATURE_SCHEMA_VERSION,
    WALLET_FEATURE_SCHEMA_VERSION,
    FeatureVector,
    WalletFeatureVector,
)
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchOutcomeLabel,
    ResearchOutcomeLabelStatus,
    ResearchSnapshotInputs,
    write_research_parquet,
)
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScoreAssessment
from shreks_brain.setups import SetupState


AS_OF = 20_000_000


def _pending_label(horizon: int, baseline: int):
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=baseline + horizon * 1_000,
        status=ResearchOutcomeLabelStatus.PENDING,
        checkpoint_observed_at_unix_ms=None,
        completed_at_unix_ms=None,
        return_pct=None,
        mfe_pct=None,
        mae_pct=None,
        liquidity_change_pct=None,
        volume_m5_change_pct=None,
        buys_m5_change=None,
        sells_m5_change=None,
        rug_or_dead_pool=None,
        exitability=None,
    )


def _completed_label(horizon: int, baseline: int, *, return_pct: float = 5.0):
    due = baseline + horizon * 1_000
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=due,
        status=ResearchOutcomeLabelStatus.COMPLETED,
        checkpoint_observed_at_unix_ms=due + 100,
        completed_at_unix_ms=due + 200,
        return_pct=return_pct,
        mfe_pct=8.0,
        mae_pct=-2.0,
        liquidity_change_pct=None,
        volume_m5_change_pct=None,
        buys_m5_change=None,
        sells_m5_change=None,
        rug_or_dead_pool=None,
        exitability=None,
    )


def _snapshot(
    mint: str,
    action: DecisionAction,
    *,
    as_of: int = AS_OF,
    completed_first_label: bool = False,
    first_return_pct: float = 5.0,
):
    source = as_of - 1_000
    market = FeatureVector(
        schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=120.0,
        price_usd=1.0,
        liquidity_usd=25_000.0,
        liquidity_change_5m_pct=None,
        exit_price_impact_pct=1.0,
        volume_m5_usd=10_000.0,
        volume_h1_usd=None,
        volume_velocity_ratio=None,
        tx_count_m5=50,
        tx_count_h1=None,
        buy_fraction_m5=0.6,
        buy_fraction_h1=None,
        buy_sell_ratio_m5=1.5,
        buy_sell_ratio_h1=None,
        buy_pressure_acceleration=None,
        return_1m_pct=2.0,
        return_5m_pct=None,
        return_15m_pct=None,
        momentum_acceleration_1m_vs_5m=None,
        distance_from_local_high_pct=-5.0,
        range_position_pct=70.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=("volume_h1_usd",),
    )
    wallet = WalletFeatureVector(
        schema_version=WALLET_FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        candidate_mint=mint,
        wallet_feature_policy_version="wallet-feature-v1",
        profile_policy_version=None,
        profile_context_version=None,
        relationship_policy_version="wallet-relationship-v1",
        wallet_count=0,
        recent_entry_wallet_count=0,
        recent_exit_wallet_count=0,
        strong_wallet_count=0,
        unknown_strength_wallet_count=0,
        strong_entry_wallet_count=0,
        strong_exit_wallet_count=0,
        confidence_weighted_strong_entry_count=0.0,
        confidence_weighted_strong_exit_count=0.0,
        entry_quality_profile_sample_count=0,
        confidence_weighted_entry_median_return_pct=None,
        confidence_weighted_entry_win_rate=None,
        independently_strong_entry_wallet_count=0,
        strong_entry_all_pairs_independent_under_evidence=None,
        strong_entry_linked_pair_count=0,
        strong_entry_conflicting_pair_count=0,
        strong_entry_unknown_pair_count=0,
        strong_entry_coordination_cluster_count=0,
        strong_entry_max_independent_group_count_upper_bound=0,
        creator_deployer_action_observation_count=0,
        strength_assessments=(),
        missing_features=(
            "confidence_weighted_entry_median_return_pct",
            "confidence_weighted_entry_win_rate",
            "strong_entry_all_pairs_independent_under_evidence",
        ),
    )
    regime = RegimeAssessment(
        policy_version="regime-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        window_started_at_unix_ms=source - 60_000,
        source_age_ms=1_000,
        window_seconds=60.0,
        candidate_count=5,
        candidate_rate_per_hour=300.0,
        executable_fraction=0.4,
        median_liquidity_usd=20_000.0,
        median_volume_m5_usd=8_000.0,
        base_regime=MarketRegime.NORMAL,
        regime=MarketRegime.NORMAL,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        performance_applied=False,
        findings=(),
    )
    score = ScoreAssessment(
        policy_version="score-v1",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        safety_decision=SafetyDecision.PASS,
        setup_name="fresh_launch_continuation",
        setup_policy_version="setup-v1",
        setup_state=SetupState.READY,
        regime_policy_version="regime-v1",
        market_regime=MarketRegime.NORMAL,
        safety_quality_score=90.0,
        money_flow_score=None,
        setup_quality_score=85.0,
        liquidity_executability_score=None,
        total_score=82.0,
        findings=(),
    )
    decision = TradeDecision(
        policy_version="decision-v1",
        mint=mint,
        as_of_unix_ms=as_of,
        action=action,
        score_policy_version="score-v1",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        safety_decision=SafetyDecision.PASS,
        setup_name="fresh_launch_continuation",
        setup_policy_version="setup-v1",
        setup_state=SetupState.READY,
        market_regime=MarketRegime.NORMAL,
        total_score=82.0,
        required_score_threshold=80.0,
        findings=(),
    )
    outcomes = []
    for index, horizon in enumerate(RESEARCH_OUTCOME_HORIZONS_SECONDS):
        if completed_first_label and index == 0:
            outcomes.append(
                _completed_label(
                    horizon,
                    as_of,
                    return_pct=first_return_pct,
                )
            )
        else:
            outcomes.append(_pending_label(horizon, as_of))
    return ResearchSnapshotInputs(
        candidate_mint=mint,
        market_features=market,
        wallet_features=wallet,
        regime=regime,
        score=score,
        decision=decision,
        outcomes=tuple(outcomes),
    )


def test_importing_research_does_not_eagerly_import_pyarrow():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import shreks_brain.research; "
                "print(any(k == 'pyarrow' or k.startswith('pyarrow.') "
                "for k in sys.modules))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"


def test_writer_validates_logical_dataset_before_creating_parent(tmp_path):
    destination = tmp_path / "missing" / "dataset.parquet"
    with pytest.raises(ValueError, match="empty"):
        write_research_parquet((), destination)
    assert not destination.parent.exists()


def test_writer_requires_parquet_suffix(tmp_path):
    with pytest.raises(ValueError, match=r"\.parquet"):
        write_research_parquet(
            (_snapshot("mint-a", DecisionAction.REJECT),),
            tmp_path / "dataset.bin",
        )


def test_writer_reports_research_extra_when_pyarrow_is_unavailable(
    monkeypatch, tmp_path
):
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "pyarrow" or name.startswith("pyarrow."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(RuntimeError, match=r"shreks-brain\[research\]"):
        write_research_parquet(
            (_snapshot("mint-a", DecisionAction.REJECT),),
            tmp_path / "dataset.parquet",
        )


def test_parquet_round_trip_preserves_schema_metadata_nulls_and_actions(tmp_path):
    path = tmp_path / "nested" / "research.parquet"
    snapshots = (
        _snapshot("mint-c", DecisionAction.ENTER, completed_first_label=True),
        _snapshot("mint-a", DecisionAction.REJECT),
        _snapshot("mint-b", DecisionAction.WATCH),
    )
    manifest = write_research_parquet(snapshots, path)

    import pyarrow.parquet as pq

    table = pq.read_table(path)
    assert path.exists()
    assert table.num_rows == 3
    assert tuple(table.column_names) == RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS

    metadata = table.schema.metadata
    assert metadata is not None
    assert metadata[b"shreks_dataset_schema_version"] == RESEARCH_DATASET_SCHEMA_VERSION.encode()
    assert metadata[b"shreks_market_feature_schema_version"] == b"b2-v1"
    assert metadata[b"shreks_wallet_feature_schema_version"] == b"d5-wallet-v1"
    assert metadata[b"shreks_label_horizons_seconds"] == (
        b"60,300,900,1800,3600,14400,86400"
    )
    assert metadata[b"shreks_row_count"] == b"3"
    assert metadata[b"shreks_logical_sha256"] == manifest.dataset_fingerprint_sha256.encode()

    rows = table.to_pylist()
    assert [row["decision_action"] for row in rows] == ["REJECT", "WATCH", "ENTER"]
    assert rows[0]["market_volume_h1_usd"] is None
    assert rows[0]["wallet_missing_features"] == [
        "confidence_weighted_entry_median_return_pct",
        "confidence_weighted_entry_win_rate",
        "strong_entry_all_pairs_independent_under_evidence",
    ]
    assert rows[2]["label_60s_status"] == "COMPLETED"
    assert rows[2]["label_60s_return_pct"] == 5.0
    assert rows[2]["label_300s_return_pct"] is None


def test_logical_fingerprint_is_path_and_input_order_independent(tmp_path):
    snapshots = (
        _snapshot("mint-b", DecisionAction.WATCH),
        _snapshot("mint-a", DecisionAction.REJECT, completed_first_label=True),
    )
    first = write_research_parquet(snapshots, tmp_path / "a.parquet")
    second = write_research_parquet(
        tuple(reversed(snapshots)),
        tmp_path / "other" / "b.parquet",
    )
    assert first == second


def test_logical_fingerprint_changes_when_feature_or_label_changes(tmp_path):
    base = _snapshot("mint-a", DecisionAction.REJECT, completed_first_label=True)
    feature_changed = replace(
        base,
        market_features=replace(base.market_features, price_usd=1.0001),
    )
    labels = list(base.outcomes)
    labels[0] = _completed_label(
        labels[0].horizon_seconds,
        AS_OF,
        return_pct=5.0001,
    )
    label_changed = replace(base, outcomes=tuple(labels))

    base_manifest = write_research_parquet((base,), tmp_path / "base.parquet")
    feature_manifest = write_research_parquet(
        (feature_changed,),
        tmp_path / "feature.parquet",
    )
    label_manifest = write_research_parquet(
        (label_changed,),
        tmp_path / "label.parquet",
    )
    assert base_manifest.dataset_fingerprint_sha256 != feature_manifest.dataset_fingerprint_sha256
    assert base_manifest.dataset_fingerprint_sha256 != label_manifest.dataset_fingerprint_sha256
