from dataclasses import replace
import json

import pytest

from shreks_brain.decision import DecisionAction, TradeDecision
from shreks_brain.features import (
    FEATURE_SCHEMA_VERSION,
    WALLET_FEATURE_SCHEMA_VERSION,
    FeatureVector,
    WalletFeatureVector,
    WalletHistoricalStrengthState,
    WalletStrengthAssessment,
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
    build_research_dataset,
    build_research_row,
)
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScoreAssessment
from shreks_brain.setups import SetupState


AS_OF = 10_000_000
MINT = "mint-a"


EXPECTED_FEATURE_COLUMNS = (
    "dataset_schema_version",
    "candidate_mint",
    "as_of_unix_ms",
    "market_feature_schema_version",
    "wallet_feature_schema_version",
    "market_source_observed_at_unix_ms",
    "market_source_age_ms",
    "safety_policy_version",
    "wallet_feature_policy_version",
    "wallet_profile_policy_version",
    "wallet_profile_context_version",
    "wallet_relationship_policy_version",
    "regime_policy_version",
    "score_policy_version",
    "decision_policy_version",
    "setup_name",
    "setup_policy_version",
    "market_token_age_seconds",
    "market_price_usd",
    "market_liquidity_usd",
    "market_liquidity_change_5m_pct",
    "market_exit_price_impact_pct",
    "market_volume_m5_usd",
    "market_volume_h1_usd",
    "market_volume_velocity_ratio",
    "market_tx_count_m5",
    "market_tx_count_h1",
    "market_buy_fraction_m5",
    "market_buy_fraction_h1",
    "market_buy_sell_ratio_m5",
    "market_buy_sell_ratio_h1",
    "market_buy_pressure_acceleration",
    "market_return_1m_pct",
    "market_return_5m_pct",
    "market_return_15m_pct",
    "market_momentum_acceleration_1m_vs_5m",
    "market_distance_from_local_high_pct",
    "market_range_position_pct",
    "market_safety_soft_finding_count",
    "market_safety_liquidity_weak",
    "market_safety_holder_concentration_elevated",
    "market_safety_creator_concentration_elevated",
    "market_safety_exit_price_impact_elevated",
    "market_missing_features",
    "wallet_count",
    "wallet_recent_entry_wallet_count",
    "wallet_recent_exit_wallet_count",
    "wallet_strong_wallet_count",
    "wallet_unknown_strength_wallet_count",
    "wallet_strong_entry_wallet_count",
    "wallet_strong_exit_wallet_count",
    "wallet_confidence_weighted_strong_entry_count",
    "wallet_confidence_weighted_strong_exit_count",
    "wallet_entry_quality_profile_sample_count",
    "wallet_confidence_weighted_entry_median_return_pct",
    "wallet_confidence_weighted_entry_win_rate",
    "wallet_independently_strong_entry_wallet_count",
    "wallet_strong_entry_all_pairs_independent_under_evidence",
    "wallet_strong_entry_linked_pair_count",
    "wallet_strong_entry_conflicting_pair_count",
    "wallet_strong_entry_unknown_pair_count",
    "wallet_strong_entry_coordination_cluster_count",
    "wallet_strong_entry_max_independent_group_count_upper_bound",
    "wallet_creator_deployer_action_observation_count",
    "wallet_missing_features",
    "wallet_strength_assessments_json",
    "regime",
    "regime_base",
    "regime_source_observed_at_unix_ms",
    "regime_window_started_at_unix_ms",
    "regime_source_age_ms",
    "regime_window_seconds",
    "regime_candidate_count",
    "regime_candidate_rate_per_hour",
    "regime_executable_fraction",
    "regime_median_liquidity_usd",
    "regime_median_volume_m5_usd",
    "regime_performance_sample_count",
    "regime_performance_net_expectancy_after_costs_pct",
    "regime_performance_applied",
    "regime_reason_codes",
    "safety_decision",
    "setup_state",
    "market_regime",
    "score_safety_quality",
    "score_money_flow",
    "score_setup_quality",
    "score_liquidity_executability",
    "total_score",
    "decision_action",
    "required_score_threshold",
    "score_reason_codes",
    "decision_reason_codes",
)


LABEL_SUFFIXES = (
    "status",
    "baseline_observed_at_unix_ms",
    "due_at_unix_ms",
    "checkpoint_observed_at_unix_ms",
    "completed_at_unix_ms",
    "return_pct",
    "mfe_pct",
    "mae_pct",
    "liquidity_change_pct",
    "volume_m5_change_pct",
    "buys_m5_change",
    "sells_m5_change",
    "rug_or_dead_pool",
    "exitability",
)


EXPECTED_LABEL_COLUMNS = tuple(
    f"label_{horizon}s_{suffix}"
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS
    for suffix in LABEL_SUFFIXES
)


def _label(*, horizon: int, baseline: int, completed: bool = False):
    due = baseline + horizon * 1_000
    if not completed:
        return ResearchOutcomeLabel(
            horizon_seconds=horizon,
            baseline_observed_at_unix_ms=baseline,
            due_at_unix_ms=due,
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
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=due,
        status=ResearchOutcomeLabelStatus.COMPLETED,
        checkpoint_observed_at_unix_ms=due + 100,
        completed_at_unix_ms=due + 200,
        return_pct=12.5,
        mfe_pct=20.0,
        mae_pct=-4.0,
        liquidity_change_pct=5.0,
        volume_m5_change_pct=-10.0,
        buys_m5_change=3,
        sells_m5_change=-2,
        rug_or_dead_pool=None,
        exitability=None,
    )


def _market_features(*, as_of: int = AS_OF):
    return FeatureVector(
        schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=as_of - 1_000,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=120.0,
        price_usd=1.25,
        liquidity_usd=50_000.0,
        liquidity_change_5m_pct=5.0,
        exit_price_impact_pct=1.0,
        volume_m5_usd=25_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=3.0,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.65,
        buy_fraction_h1=0.55,
        buy_sell_ratio_m5=1.8,
        buy_sell_ratio_h1=1.2,
        buy_pressure_acceleration=0.10,
        return_1m_pct=4.0,
        return_5m_pct=12.0,
        return_15m_pct=25.0,
        momentum_acceleration_1m_vs_5m=1.6,
        distance_from_local_high_pct=-3.0,
        range_position_pct=85.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _wallet_features(*, mint: str = MINT, as_of: int = AS_OF):
    strength = WalletStrengthAssessment(
        wallet="wallet-a",
        state=WalletHistoricalStrengthState.STRONG,
        effective_closed_sample_size=8.0,
        evidence_sample_confidence=0.8,
        median_return_pct=20.0,
        win_rate=0.65,
        rug_exposure_rate=0.0,
        median_drawdown_pct=15.0,
        failed_checks=(),
        missing_checks=(),
    )
    return WalletFeatureVector(
        schema_version=WALLET_FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        candidate_mint=mint,
        wallet_feature_policy_version="wallet-feature-v1",
        profile_policy_version="wallet-profile-v1",
        profile_context_version="wallet-context-v1",
        relationship_policy_version="wallet-relationship-v1",
        wallet_count=1,
        recent_entry_wallet_count=1,
        recent_exit_wallet_count=0,
        strong_wallet_count=1,
        unknown_strength_wallet_count=0,
        strong_entry_wallet_count=1,
        strong_exit_wallet_count=0,
        confidence_weighted_strong_entry_count=0.8,
        confidence_weighted_strong_exit_count=0.0,
        entry_quality_profile_sample_count=1,
        confidence_weighted_entry_median_return_pct=20.0,
        confidence_weighted_entry_win_rate=0.65,
        independently_strong_entry_wallet_count=1,
        strong_entry_all_pairs_independent_under_evidence=True,
        strong_entry_linked_pair_count=0,
        strong_entry_conflicting_pair_count=0,
        strong_entry_unknown_pair_count=0,
        strong_entry_coordination_cluster_count=0,
        strong_entry_max_independent_group_count_upper_bound=1,
        creator_deployer_action_observation_count=1,
        strength_assessments=(strength,),
        missing_features=(),
    )


def _regime(*, as_of: int = AS_OF, regime: MarketRegime = MarketRegime.NORMAL):
    return RegimeAssessment(
        policy_version="regime-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=as_of - 1_000,
        window_started_at_unix_ms=as_of - 61_000,
        source_age_ms=1_000,
        window_seconds=60.0,
        candidate_count=10,
        candidate_rate_per_hour=600.0,
        executable_fraction=0.6,
        median_liquidity_usd=40_000.0,
        median_volume_m5_usd=20_000.0,
        base_regime=regime,
        regime=regime,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        performance_applied=False,
        findings=(),
    )


def _score(*, as_of: int = AS_OF, regime: MarketRegime = MarketRegime.NORMAL):
    return ScoreAssessment(
        policy_version="score-v1",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=as_of - 1_000,
        safety_decision=SafetyDecision.PASS,
        setup_name="fresh_launch_continuation",
        setup_policy_version="setup-v1",
        setup_state=SetupState.READY,
        regime_policy_version="regime-v1",
        market_regime=regime,
        safety_quality_score=90.0,
        money_flow_score=80.0,
        setup_quality_score=85.0,
        liquidity_executability_score=88.0,
        total_score=86.0,
        findings=(),
    )


def _decision(
    *,
    mint: str = MINT,
    as_of: int = AS_OF,
    action: DecisionAction = DecisionAction.ENTER,
    regime: MarketRegime = MarketRegime.NORMAL,
):
    return TradeDecision(
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
        market_regime=regime,
        total_score=86.0,
        required_score_threshold=80.0,
        findings=(),
    )


def _snapshot(
    *,
    mint: str = MINT,
    as_of: int = AS_OF,
    action: DecisionAction = DecisionAction.ENTER,
    first_label_completed: bool = False,
):
    outcomes = tuple(
        _label(
            horizon=horizon,
            baseline=as_of,
            completed=first_label_completed and index == 0,
        )
        for index, horizon in enumerate(RESEARCH_OUTCOME_HORIZONS_SECONDS)
    )
    return ResearchSnapshotInputs(
        candidate_mint=mint,
        market_features=_market_features(as_of=as_of),
        wallet_features=_wallet_features(mint=mint, as_of=as_of),
        regime=_regime(as_of=as_of),
        score=_score(as_of=as_of),
        decision=_decision(mint=mint, as_of=as_of, action=action),
        outcomes=outcomes,
    )


def test_research_snapshot_accepts_all_pre_entry_actions():
    for action in (DecisionAction.REJECT, DecisionAction.WATCH, DecisionAction.ENTER):
        assert _snapshot(action=action).decision.action is action


@pytest.mark.parametrize(
    "action",
    [DecisionAction.HOLD, DecisionAction.REDUCE, DecisionAction.EXIT],
)
def test_research_snapshot_rejects_position_lifecycle_actions(action):
    with pytest.raises(ValueError, match="decision action"):
        _snapshot(action=action)


def test_research_snapshot_rejects_candidate_mismatch():
    value = _snapshot()
    with pytest.raises(ValueError, match="candidate"):
        replace(value, candidate_mint="mint-other")


@pytest.mark.parametrize("component", ["market", "wallet", "regime", "score", "decision"])
def test_research_snapshot_requires_exact_shared_as_of(component):
    value = _snapshot()
    if component == "market":
        field_name = "market_features"
        changed = replace(value.market_features, as_of_unix_ms=AS_OF + 1)
    elif component == "wallet":
        field_name = "wallet_features"
        changed = _wallet_features(as_of=AS_OF + 1)
    elif component == "regime":
        field_name = "regime"
        changed = _regime(as_of=AS_OF + 1)
    elif component == "score":
        field_name = "score"
        changed = _score(as_of=AS_OF + 1)
    else:
        field_name = "decision"
        changed = _decision(as_of=AS_OF + 1)
    with pytest.raises(ValueError, match="as_of"):
        replace(value, **{field_name: changed})


def test_research_snapshot_rejects_market_schema_mismatch():
    value = _snapshot()
    with pytest.raises(ValueError, match="market feature schema"):
        replace(
            value,
            market_features=replace(value.market_features, schema_version="wrong"),
        )


def test_research_snapshot_rejects_score_source_timestamp_mismatch():
    value = _snapshot()
    with pytest.raises(ValueError, match="source"):
        replace(
            value,
            score=replace(
                value.score,
                source_observed_at_unix_ms=value.score.source_observed_at_unix_ms - 1,
            ),
        )


@pytest.mark.parametrize("target", ["score", "decision"])
def test_research_snapshot_rejects_feature_schema_mismatch(target):
    value = _snapshot()
    if target == "score":
        changed = replace(value.score, feature_schema_version="other")
        field_name = "score"
    else:
        changed = replace(value.decision, feature_schema_version="other")
        field_name = "decision"
    with pytest.raises(ValueError, match="feature schema"):
        replace(value, **{field_name: changed})


def test_research_snapshot_rejects_safety_decision_mismatch():
    value = _snapshot()
    with pytest.raises(ValueError, match="safety"):
        replace(
            value,
            decision=replace(value.decision, safety_decision=SafetyDecision.REJECT),
        )


@pytest.mark.parametrize(
    ("field_name", "replacement_value", "match"),
    [
        ("score_policy_version", "other-score", "score policy"),
        ("setup_name", "other-setup", "setup"),
        ("setup_policy_version", "other-setup-policy", "setup"),
        ("setup_state", SetupState.WATCH, "setup"),
        ("market_regime", MarketRegime.HOT, "regime"),
        ("total_score", 85.0, "total score"),
    ],
)
def test_research_snapshot_rejects_score_decision_semantic_mismatch(
    field_name, replacement_value, match
):
    value = _snapshot()
    with pytest.raises(ValueError, match=match):
        replace(
            value,
            decision=replace(value.decision, **{field_name: replacement_value}),
        )


def test_research_snapshot_rejects_regime_policy_mismatch():
    value = _snapshot()
    with pytest.raises(ValueError, match="regime policy"):
        replace(
            value,
            score=replace(value.score, regime_policy_version="other-regime"),
        )


def test_research_snapshot_requires_exact_seven_sorted_outcomes():
    value = _snapshot()
    with pytest.raises(ValueError, match="outcomes"):
        replace(value, outcomes=list(value.outcomes))
    with pytest.raises(ValueError, match="seven"):
        replace(value, outcomes=value.outcomes[:-1])
    duplicate = value.outcomes[:-1] + (value.outcomes[-2],)
    with pytest.raises(ValueError, match="horizon"):
        replace(value, outcomes=duplicate)
    with pytest.raises(ValueError, match="order"):
        replace(value, outcomes=tuple(reversed(value.outcomes)))


def test_research_snapshot_rejects_discovery_anchored_label_baseline():
    value = _snapshot()
    wrong_baseline = AS_OF - 60_000
    wrong_label = _label(
        horizon=RESEARCH_OUTCOME_HORIZONS_SECONDS[0],
        baseline=wrong_baseline,
    )
    with pytest.raises(ValueError, match="baseline"):
        replace(value, outcomes=(wrong_label,) + value.outcomes[1:])


def test_feature_and_label_columns_are_exact_disjoint_contracts():
    assert RESEARCH_FEATURE_COLUMNS == EXPECTED_FEATURE_COLUMNS
    assert RESEARCH_LABEL_COLUMNS == EXPECTED_LABEL_COLUMNS
    assert not set(RESEARCH_FEATURE_COLUMNS) & set(RESEARCH_LABEL_COLUMNS)
    assert all(not name.startswith("label_") for name in RESEARCH_FEATURE_COLUMNS)
    assert all(name.startswith("label_") for name in RESEARCH_LABEL_COLUMNS)


def test_build_research_row_flattens_features_wallet_audit_and_labels():
    row = build_research_row(_snapshot(first_label_completed=True))
    assert tuple(row) == RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
    assert row["dataset_schema_version"] == RESEARCH_DATASET_SCHEMA_VERSION
    assert row["candidate_mint"] == MINT
    assert row["market_price_usd"] == 1.25
    assert row["wallet_strong_entry_wallet_count"] == 1
    assert row["regime"] == "NORMAL"
    assert row["total_score"] == 86.0
    assert row["decision_action"] == "ENTER"
    assert row["label_60s_status"] == "COMPLETED"
    assert row["label_60s_return_pct"] == 12.5
    assert row["label_300s_status"] == "PENDING"
    assert row["label_300s_return_pct"] is None

    wallet_audit = json.loads(row["wallet_strength_assessments_json"])
    assert wallet_audit == [
        {
            "effective_closed_sample_size": 8.0,
            "evidence_sample_confidence": 0.8,
            "failed_checks": [],
            "median_drawdown_pct": 15.0,
            "median_return_pct": 20.0,
            "missing_checks": [],
            "rug_exposure_rate": 0.0,
            "state": "STRONG",
            "wallet": "wallet-a",
            "win_rate": 0.65,
        }
    ]


def test_build_research_dataset_rejects_invalid_container_and_duplicates():
    with pytest.raises(ValueError, match="tuple"):
        build_research_dataset([])
    with pytest.raises(ValueError, match="empty"):
        build_research_dataset(())
    with pytest.raises(ValueError, match="ResearchSnapshotInputs"):
        build_research_dataset((object(),))

    value = _snapshot()
    with pytest.raises(ValueError, match="duplicate"):
        build_research_dataset((value, value))


def test_build_research_dataset_sorts_rows_and_keeps_all_pre_entry_actions():
    snapshots = (
        _snapshot(mint="mint-c", action=DecisionAction.ENTER),
        _snapshot(mint="mint-a", action=DecisionAction.REJECT),
        _snapshot(mint="mint-b", action=DecisionAction.WATCH),
    )
    rows = build_research_dataset(tuple(reversed(snapshots)))
    assert [(row["candidate_mint"], row["decision_action"]) for row in rows] == [
        ("mint-a", "REJECT"),
        ("mint-b", "WATCH"),
        ("mint-c", "ENTER"),
    ]
    assert rows == build_research_dataset(snapshots)
