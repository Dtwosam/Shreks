from __future__ import annotations

from dataclasses import replace
import inspect
import subprocess
import sys

import pytest

from shreks_brain.backtest import (
    BACKTEST_REPLAY_SCHEMA_VERSION,
    ReplayDecisionInput,
    ReplayOutcomeBundle,
    ReplayPolicySet,
    ReplaySetupKind,
    replay_entry_decisions,
)
from shreks_brain.decision import (
    DecisionAction,
    DecisionPolicy,
    SetupDecisionRule,
    decide_entry,
)
from shreks_brain.features import FeatureVector, WalletFeatureVector
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.research import (
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchOutcomeLabel,
    ResearchOutcomeLabelStatus,
    build_research_dataset,
)
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy, score_candidate
from shreks_brain.setups import (
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_SETUP_NAME,
    FirstPullbackPolicy,
    FreshLaunchPolicy,
    GraduationBreakoutPolicy,
    GraduationContext,
    PullbackContext,
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)


AS_OF = 10_000_000
MINT = "mint-a"


def _market(
    *,
    as_of: int = AS_OF,
    safety: SafetyDecision = SafetyDecision.PASS,
    token_age_seconds: float = 300.0,
) -> FeatureVector:
    source = as_of - 1_000
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=safety,
        token_age_seconds=token_age_seconds,
        price_usd=1.30,
        liquidity_usd=100_000.0,
        liquidity_change_5m_pct=10.0,
        exit_price_impact_pct=1.0,
        volume_m5_usd=25_000.0,
        volume_h1_usd=100_000.0,
        volume_velocity_ratio=3.0,
        tx_count_m5=100,
        tx_count_h1=500,
        buy_fraction_m5=0.70,
        buy_fraction_h1=0.60,
        buy_sell_ratio_m5=2.0,
        buy_sell_ratio_h1=1.5,
        buy_pressure_acceleration=0.10,
        return_1m_pct=5.0,
        return_5m_pct=15.0,
        return_15m_pct=20.0,
        momentum_acceleration_1m_vs_5m=2.0,
        distance_from_local_high_pct=-3.0,
        range_position_pct=85.0,
        safety_soft_finding_count=0,
        safety_liquidity_weak=False,
        safety_holder_concentration_elevated=False,
        safety_creator_concentration_elevated=False,
        safety_exit_price_impact_elevated=False,
        missing_features=(),
    )


def _wallet(*, mint: str = MINT, as_of: int = AS_OF) -> WalletFeatureVector:
    return WalletFeatureVector(
        schema_version="d5-wallet-v1",
        as_of_unix_ms=as_of,
        candidate_mint=mint,
        wallet_feature_policy_version="wallet-feature-v1",
        profile_policy_version=None,
        profile_context_version=None,
        relationship_policy_version="relationship-v1",
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


def _regime(*, as_of: int = AS_OF) -> RegimeAssessment:
    source = as_of - 1_000
    return RegimeAssessment(
        policy_version="regime-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        window_started_at_unix_ms=source - 3_600_000,
        source_age_ms=1_000,
        window_seconds=3600.0,
        candidate_count=10,
        candidate_rate_per_hour=10.0,
        executable_fraction=0.8,
        median_liquidity_usd=100_000.0,
        median_volume_m5_usd=25_000.0,
        base_regime=MarketRegime.NORMAL,
        regime=MarketRegime.NORMAL,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        performance_applied=False,
        findings=(),
    )


def _graduation(*, mint: str = MINT, as_of: int = AS_OF) -> GraduationContext:
    return GraduationContext(
        event_type="pump_graduation",
        provider="provider-a",
        mint=mint,
        quote_mint="So11111111111111111111111111111111111111112",
        from_venue="pump_fun_bonding_curve",
        to_venue="pump_swap",
        pool_address=f"pool-{mint}",
        signature=f"sig-{mint}-{as_of}",
        slot=1,
        detected_at_unix_ms=as_of - 60_000,
        occurred_at_unix_ms=None,
    )


def _pullback(*, as_of: int = AS_OF) -> PullbackContext:
    source = as_of - 1_000
    trough = source - 60_000
    return PullbackContext(
        impulse_started_at_unix_ms=trough - 60_000,
        peak_at_unix_ms=trough - 30_000,
        trough_at_unix_ms=trough,
        impulse_start_price_usd=1.0,
        peak_price_usd=1.5,
        trough_price_usd=1.2,
        peak_liquidity_usd=100_000.0,
        trough_liquidity_usd=90_000.0,
        trough_buy_fraction_m5=0.55,
        sample_count=5,
    )


def _decision_input(
    *,
    mint: str = MINT,
    as_of: int = AS_OF,
    setup_kind: ReplaySetupKind = ReplaySetupKind.FRESH_LAUNCH_CONTINUATION,
    market: FeatureVector | None = None,
    wallet: WalletFeatureVector | None = None,
) -> ReplayDecisionInput:
    if market is None:
        market = _market(as_of=as_of)
    if wallet is None:
        wallet = _wallet(mint=mint, as_of=as_of)
    graduation = (
        _graduation(mint=mint, as_of=as_of)
        if setup_kind is ReplaySetupKind.GRADUATION_BREAKOUT
        else None
    )
    pullback = (
        _pullback(as_of=as_of)
        if setup_kind is ReplaySetupKind.FIRST_PULLBACK
        else None
    )
    return ReplayDecisionInput(
        candidate_mint=mint,
        market_features=market,
        wallet_features=wallet,
        regime=_regime(as_of=as_of),
        setup_kind=setup_kind,
        graduation_context=graduation,
        pullback_context=pullback,
    )


def _label(
    horizon: int,
    *,
    baseline: int,
    return_pct: float | None = None,
) -> ResearchOutcomeLabel:
    due = baseline + horizon * 1_000
    if return_pct is None:
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
        checkpoint_observed_at_unix_ms=due,
        completed_at_unix_ms=due,
        return_pct=return_pct,
        mfe_pct=None,
        mae_pct=None,
        liquidity_change_pct=None,
        volume_m5_change_pct=None,
        buys_m5_change=None,
        sells_m5_change=None,
        rug_or_dead_pool=None,
        exitability=None,
    )


def _outcome_bundle(
    *,
    mint: str = MINT,
    as_of: int = AS_OF,
    first_return_pct: float | None = None,
) -> ReplayOutcomeBundle:
    outcomes = tuple(
        _label(
            horizon,
            baseline=as_of,
            return_pct=first_return_pct if index == 0 else None,
        )
        for index, horizon in enumerate(RESEARCH_OUTCOME_HORIZONS_SECONDS)
    )
    return ReplayOutcomeBundle(
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        outcomes=outcomes,
    )


def _fresh_policy() -> FreshLaunchPolicy:
    return FreshLaunchPolicy(
        version="fresh-replay-v1",
        min_age_seconds=60.0,
        max_age_seconds=3600.0,
        max_source_age_ms=10_000,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=5.0,
        max_return_5m_pct=100.0,
        min_tx_count_m5=10,
        min_volume_velocity_ratio=1.0,
        min_buy_fraction_m5=0.55,
        min_buy_pressure_acceleration=0.0,
        min_return_1m_pct=0.0,
        min_return_5m_pct=0.0,
        min_liquidity_change_5m_pct=0.0,
        min_distance_from_local_high_pct=-20.0,
        min_range_position_pct=50.0,
    )


def _graduation_policy() -> GraduationBreakoutPolicy:
    return GraduationBreakoutPolicy(
        version="graduation-replay-v1",
        min_seconds_since_graduation=30.0,
        max_seconds_since_graduation=600.0,
        max_source_age_ms=10_000,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=5.0,
        min_tx_count_m5=10,
        min_volume_velocity_ratio=1.0,
        min_buy_fraction_m5=0.55,
        min_buy_pressure_acceleration=0.0,
        min_return_1m_pct=0.0,
        max_return_1m_pct=20.0,
        min_liquidity_change_5m_pct=0.0,
        min_distance_from_local_high_pct=-20.0,
        min_range_position_pct=50.0,
    )


def _pullback_policy() -> FirstPullbackPolicy:
    return FirstPullbackPolicy(
        version="pullback-replay-v1",
        min_seconds_since_trough=30.0,
        max_seconds_since_trough=600.0,
        max_source_age_ms=10_000,
        min_structure_samples=3,
        min_initial_impulse_pct=20.0,
        min_pullback_depth_pct=10.0,
        max_pullback_depth_pct=40.0,
        min_recovery_from_trough_pct=5.0,
        min_current_vs_peak_pct=-20.0,
        max_current_vs_peak_pct=5.0,
        min_liquidity_retention_pct=70.0,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=5.0,
        min_tx_count_m5=10,
        min_volume_velocity_ratio=1.0,
        min_buy_fraction_m5=0.55,
        min_buy_fraction_improvement=0.05,
        min_buy_pressure_acceleration=0.0,
        min_return_1m_pct=0.0,
        max_return_1m_pct=20.0,
    )


def _score_policy() -> ScorePolicy:
    return ScorePolicy(
        version="score-replay-v1",
        required_feature_schema_version="b2-v1",
        safety_weight=0.25,
        money_flow_weight=0.25,
        setup_quality_weight=0.25,
        liquidity_executability_weight=0.25,
        safety_liquidity_weak_penalty=10.0,
        safety_holder_concentration_elevated_penalty=10.0,
        safety_creator_concentration_elevated_penalty=10.0,
        safety_exit_price_impact_elevated_penalty=10.0,
        volume_velocity_zero=0.0,
        volume_velocity_full=4.0,
        buy_fraction_m5_zero=0.4,
        buy_fraction_m5_full=0.8,
        buy_pressure_acceleration_zero=-0.2,
        buy_pressure_acceleration_full=0.2,
        liquidity_usd_zero=0.0,
        liquidity_usd_full=200_000.0,
        exit_price_impact_full=0.0,
        exit_price_impact_zero=10.0,
    )


def _decision_policy() -> DecisionPolicy:
    return DecisionPolicy(
        version="decision-replay-v1",
        required_score_policy_version="score-replay-v1",
        setup_rules=tuple(
            SetupDecisionRule(
                setup_name=name,
                enabled=True,
                hot_min_score=50.0,
                normal_min_score=50.0,
                weak_min_score=60.0,
            )
            for name in (
                FRESH_LAUNCH_SETUP_NAME,
                GRADUATION_BREAKOUT_SETUP_NAME,
                FIRST_PULLBACK_SETUP_NAME,
            )
        ),
    )


def _policies(
    *,
    fresh: FreshLaunchPolicy | None = None,
    graduation: GraduationBreakoutPolicy | None = None,
    pullback: FirstPullbackPolicy | None = None,
) -> ReplayPolicySet:
    return ReplayPolicySet(
        version="e1-policy-set-v1",
        fresh_launch_policy=_fresh_policy() if fresh is None else fresh,
        graduation_breakout_policy=(
            _graduation_policy() if graduation is None else graduation
        ),
        first_pullback_policy=_pullback_policy() if pullback is None else pullback,
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
    )


def _direct_expected(value: ReplayDecisionInput, policies: ReplayPolicySet):
    if value.setup_kind is ReplaySetupKind.FRESH_LAUNCH_CONTINUATION:
        assert policies.fresh_launch_policy is not None
        setup = assess_fresh_launch(value.market_features, policies.fresh_launch_policy)
    elif value.setup_kind is ReplaySetupKind.GRADUATION_BREAKOUT:
        assert policies.graduation_breakout_policy is not None
        setup = assess_graduation_breakout(
            value.market_features,
            value.graduation_context,
            policies.graduation_breakout_policy,
        )
    else:
        assert policies.first_pullback_policy is not None
        setup = assess_first_pullback(
            value.market_features,
            value.pullback_context,
            policies.first_pullback_policy,
        )
    score = score_candidate(value.market_features, setup, value.regime, policies.score_policy)
    decision = decide_entry(value.candidate_mint, score, policies.decision_policy)
    return setup, score, decision


def test_replay_validates_argument_containers_and_exact_types() -> None:
    value = _decision_input()
    bundle = _outcome_bundle()
    policies = _policies()
    with pytest.raises(ValueError, match="decision_inputs.*tuple"):
        replay_entry_decisions([value], (bundle,), policies)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        replay_entry_decisions((), (), policies)
    with pytest.raises(ValueError, match="ReplayDecisionInput"):
        replay_entry_decisions((object(),), (bundle,), policies)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="outcome_bundles.*tuple"):
        replay_entry_decisions((value,), [bundle], policies)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ReplayOutcomeBundle"):
        replay_entry_decisions((value,), (object(),), policies)  # type: ignore[arg-type]


def test_replay_rejects_duplicate_or_drifting_identity_sets() -> None:
    value = _decision_input()
    bundle = _outcome_bundle()
    policies = _policies()
    with pytest.raises(ValueError, match="duplicate decision"):
        replay_entry_decisions((value, value), (bundle,), policies)
    with pytest.raises(ValueError, match="duplicate outcome"):
        replay_entry_decisions((value,), (bundle, bundle), policies)
    with pytest.raises(ValueError, match="identit"):
        replay_entry_decisions((value,), (), policies)
    extra = _outcome_bundle(mint="mint-extra")
    with pytest.raises(ValueError, match="identit"):
        replay_entry_decisions((value,), (bundle, extra), policies)


def test_replay_requires_a_policy_for_every_used_setup_kind() -> None:
    value = _decision_input(setup_kind=ReplaySetupKind.GRADUATION_BREAKOUT)
    bundle = _outcome_bundle()
    policies = ReplayPolicySet(
        version="fresh-only-v1",
        fresh_launch_policy=_fresh_policy(),
        graduation_breakout_policy=None,
        first_pullback_policy=None,
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
    )
    with pytest.raises(ValueError, match="configured.*policy|policy.*configured"):
        replay_entry_decisions((value,), (bundle,), policies)


def test_replay_is_input_order_independent_and_sorts_by_time_then_mint() -> None:
    values = (
        _decision_input(mint="mint-z", as_of=AS_OF + 2_000),
        _decision_input(mint="mint-b", as_of=AS_OF),
        _decision_input(mint="mint-a", as_of=AS_OF),
    )
    bundles = tuple(
        _outcome_bundle(
            mint=value.candidate_mint,
            as_of=value.market_features.as_of_unix_ms,
        )
        for value in values
    )
    policies = _policies()
    first = replay_entry_decisions(values, bundles, policies)
    second = replay_entry_decisions(tuple(reversed(values)), tuple(reversed(bundles)), policies)
    assert first == second
    assert [
        (snapshot.market_features.as_of_unix_ms, snapshot.candidate_mint)
        for snapshot in first.snapshots
    ] == [
        (AS_OF, "mint-a"),
        (AS_OF, "mint-b"),
        (AS_OF + 2_000, "mint-z"),
    ]


@pytest.mark.parametrize(
    "setup_kind",
    [
        ReplaySetupKind.FRESH_LAUNCH_CONTINUATION,
        ReplaySetupKind.GRADUATION_BREAKOUT,
        ReplaySetupKind.FIRST_PULLBACK,
    ],
)
def test_replay_dispatch_matches_existing_setup_score_and_decision_path(setup_kind) -> None:
    value = _decision_input(setup_kind=setup_kind)
    bundle = _outcome_bundle()
    policies = _policies()
    expected_setup, expected_score, expected_decision = _direct_expected(value, policies)
    result = replay_entry_decisions((value,), (bundle,), policies)
    snapshot = result.snapshots[0]
    assert snapshot.score == expected_score
    assert snapshot.decision == expected_decision
    assert snapshot.score.setup_name == expected_setup.setup_name
    assert snapshot.score.setup_policy_version == expected_setup.policy_version


def test_replay_preserves_supplied_policy_versions_and_wallet_features() -> None:
    value = _decision_input()
    result = replay_entry_decisions((value,), (_outcome_bundle(),), _policies())
    snapshot = result.snapshots[0]
    assert result.schema_version == BACKTEST_REPLAY_SCHEMA_VERSION
    assert result.policy_set_version == "e1-policy-set-v1"
    assert result.score_policy_version == "score-replay-v1"
    assert result.decision_policy_version == "decision-replay-v1"
    assert snapshot.score.policy_version == "score-replay-v1"
    assert snapshot.decision.policy_version == "decision-replay-v1"
    assert snapshot.wallet_features == value.wallet_features


def test_replay_retains_reject_watch_and_enter_candidates() -> None:
    enter = _decision_input(mint="mint-enter", as_of=AS_OF)
    watch_market = _market(as_of=AS_OF + 1_000, token_age_seconds=30.0)
    watch = _decision_input(
        mint="mint-watch",
        as_of=AS_OF + 1_000,
        market=watch_market,
        wallet=_wallet(mint="mint-watch", as_of=AS_OF + 1_000),
    )
    reject_market = _market(
        as_of=AS_OF + 2_000,
        safety=SafetyDecision.REJECT,
    )
    reject = _decision_input(
        mint="mint-reject",
        as_of=AS_OF + 2_000,
        market=reject_market,
        wallet=_wallet(mint="mint-reject", as_of=AS_OF + 2_000),
    )
    values = (reject, enter, watch)
    bundles = tuple(
        _outcome_bundle(
            mint=value.candidate_mint,
            as_of=value.market_features.as_of_unix_ms,
        )
        for value in values
    )
    result = replay_entry_decisions(values, bundles, _policies())
    assert {snapshot.decision.action for snapshot in result.snapshots} == {
        DecisionAction.REJECT,
        DecisionAction.WATCH,
        DecisionAction.ENTER,
    }
    assert (result.reject_count, result.watch_count, result.enter_count) == (1, 1, 1)


def test_future_outcome_metrics_cannot_change_replayed_score_or_decision() -> None:
    value = _decision_input()
    low = replay_entry_decisions(
        (value,),
        (_outcome_bundle(first_return_pct=-95.0),),
        _policies(),
    )
    high = replay_entry_decisions(
        (value,),
        (_outcome_bundle(first_return_pct=500.0),),
        _policies(),
    )
    assert low.snapshots[0].score == high.snapshots[0].score
    assert low.snapshots[0].decision == high.snapshots[0].decision
    assert low.snapshots[0].outcomes != high.snapshots[0].outcomes


def test_outcomes_join_only_by_exact_identity_and_attach_to_d6_snapshot() -> None:
    value = _decision_input()
    bundle = _outcome_bundle(first_return_pct=12.5)
    result = replay_entry_decisions((value,), (bundle,), _policies())
    snapshot = result.snapshots[0]
    assert snapshot.candidate_mint == bundle.candidate_mint
    assert snapshot.market_features.as_of_unix_ms == bundle.as_of_unix_ms
    assert snapshot.outcomes == bundle.outcomes
    assert "outcomes" not in ReplayDecisionInput.__dataclass_fields__


def test_replay_snapshots_are_directly_accepted_by_d6_dataset_builder() -> None:
    values = (
        _decision_input(mint="mint-b", as_of=AS_OF + 1_000),
        _decision_input(mint="mint-a", as_of=AS_OF),
    )
    bundles = tuple(
        _outcome_bundle(
            mint=value.candidate_mint,
            as_of=value.market_features.as_of_unix_ms,
        )
        for value in values
    )
    result = replay_entry_decisions(values, bundles, _policies())
    rows = build_research_dataset(result.snapshots)
    assert len(rows) == 2
    assert [row["candidate_mint"] for row in rows] == ["mint-a", "mint-b"]


def test_replay_run_counts_bounds_and_repeatability_reconcile() -> None:
    values = (
        _decision_input(mint="mint-a", as_of=AS_OF),
        _decision_input(mint="mint-b", as_of=AS_OF + 5_000),
    )
    bundles = tuple(
        _outcome_bundle(
            mint=value.candidate_mint,
            as_of=value.market_features.as_of_unix_ms,
        )
        for value in values
    )
    policies = _policies()
    first = replay_entry_decisions(values, bundles, policies)
    second = replay_entry_decisions(values, bundles, policies)
    assert first == second
    assert first.min_as_of_unix_ms == AS_OF
    assert first.max_as_of_unix_ms == AS_OF + 5_000
    assert first.reject_count + first.watch_count + first.enter_count == 2


def test_backtest_package_import_and_engine_have_no_io_or_wall_clock_dependency() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import shreks_brain.backtest; "
                "print(any(k == 'pyarrow' or k.startswith('pyarrow.') for k in sys.modules)); "
                "print('sqlite3' in sys.modules)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == ["False", "False"]

    import shreks_brain.backtest.engine as engine

    source = inspect.getsource(engine)
    for forbidden in (
        "sqlite3",
        "pyarrow",
        "pathlib",
        "requests",
        "time.time",
        "datetime.now",
        "open(",
    ):
        assert forbidden not in source
