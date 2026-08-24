from __future__ import annotations

import inspect
import subprocess
import sys

from shreks_brain import baselines
from shreks_brain.backtest import (
    ReplayDecisionInput,
    ReplayOutcomeBundle,
    ReplayPolicySet,
    ReplaySetupKind,
    replay_entry_decisions,
)
from shreks_brain.baselines import (
    BaselineKind,
    BaselineSuitePolicy,
    ThresholdDeltaBaselineSpec,
    build_baseline_suite,
)
from shreks_brain.decision import DecisionAction, DecisionPolicy, SetupDecisionRule
from shreks_brain.features import FeatureVector, WalletFeatureVector
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.research import (
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchOutcomeLabel,
    ResearchOutcomeLabelStatus,
    build_research_dataset,
)
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import (
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_SETUP_NAME,
    FirstPullbackPolicy,
    FreshLaunchPolicy,
    GraduationBreakoutPolicy,
    GraduationContext,
    PullbackContext,
)


AS_OF = 30_000_000


def _market(*, as_of: int) -> FeatureVector:
    source = as_of - 1_000
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=300.0,
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


def _wallet(*, mint: str, as_of: int) -> WalletFeatureVector:
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


def _regime(*, as_of: int, regime: MarketRegime) -> RegimeAssessment:
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
        base_regime=regime,
        regime=regime,
        performance_sample_count=None,
        performance_net_expectancy_after_costs_pct=None,
        performance_applied=False,
        findings=(),
    )


def _graduation(*, mint: str, as_of: int) -> GraduationContext:
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


def _pullback(*, as_of: int) -> PullbackContext:
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
    mint: str,
    as_of: int,
    setup_kind: ReplaySetupKind,
    regime: MarketRegime,
) -> ReplayDecisionInput:
    return ReplayDecisionInput(
        candidate_mint=mint,
        market_features=_market(as_of=as_of),
        wallet_features=_wallet(mint=mint, as_of=as_of),
        regime=_regime(as_of=as_of, regime=regime),
        setup_kind=setup_kind,
        graduation_context=(
            _graduation(mint=mint, as_of=as_of)
            if setup_kind is ReplaySetupKind.GRADUATION_BREAKOUT
            else None
        ),
        pullback_context=(
            _pullback(as_of=as_of)
            if setup_kind is ReplaySetupKind.FIRST_PULLBACK
            else None
        ),
    )


def _label(
    horizon: int,
    *,
    as_of: int,
    return_pct: float | None,
) -> ResearchOutcomeLabel:
    due = as_of + horizon * 1_000
    if return_pct is None:
        return ResearchOutcomeLabel(
            horizon_seconds=horizon,
            baseline_observed_at_unix_ms=as_of,
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
        baseline_observed_at_unix_ms=as_of,
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
    mint: str,
    as_of: int,
    first_return_pct: float | None = None,
) -> ReplayOutcomeBundle:
    return ReplayOutcomeBundle(
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        outcomes=tuple(
            _label(
                horizon,
                as_of=as_of,
                return_pct=first_return_pct if index == 0 else None,
            )
            for index, horizon in enumerate(RESEARCH_OUTCOME_HORIZONS_SECONDS)
        ),
    )


def _fresh_policy() -> FreshLaunchPolicy:
    return FreshLaunchPolicy(
        version="fresh-e2-v1",
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
        version="graduation-e2-v1",
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
        version="pullback-e2-v1",
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
        version="score-e2-v1",
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
        version="decision-e2-base-v1",
        required_score_policy_version="score-e2-v1",
        setup_rules=(
            SetupDecisionRule(
                setup_name=FRESH_LAUNCH_SETUP_NAME,
                enabled=True,
                hot_min_score=5.0,
                normal_min_score=95.0,
                weak_min_score=95.0,
            ),
            SetupDecisionRule(
                setup_name=GRADUATION_BREAKOUT_SETUP_NAME,
                enabled=False,
                hot_min_score=5.0,
                normal_min_score=95.0,
                weak_min_score=95.0,
            ),
            SetupDecisionRule(
                setup_name=FIRST_PULLBACK_SETUP_NAME,
                enabled=True,
                hot_min_score=5.0,
                normal_min_score=95.0,
                weak_min_score=None,
            ),
        ),
    )


def _replay_policies() -> ReplayPolicySet:
    return ReplayPolicySet(
        version="replay-e2-base-v1",
        fresh_launch_policy=_fresh_policy(),
        graduation_breakout_policy=_graduation_policy(),
        first_pullback_policy=_pullback_policy(),
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
    )


def _suite_policy(
    variants: tuple[ThresholdDeltaBaselineSpec, ...] | None = None,
) -> BaselineSuitePolicy:
    if variants is None:
        variants = (
            ThresholdDeltaBaselineSpec("stricter", 15.0),
            ThresholdDeltaBaselineSpec("looser", -20.0),
        )
    return BaselineSuitePolicy(
        version="e2-suite-policy-v1",
        base_replay_policies=_replay_policies(),
        threshold_variants=variants,
    )


def _inputs() -> tuple[ReplayDecisionInput, ...]:
    return (
        _decision_input(
            mint="mint-fresh-normal",
            as_of=AS_OF,
            setup_kind=ReplaySetupKind.FRESH_LAUNCH_CONTINUATION,
            regime=MarketRegime.NORMAL,
        ),
        _decision_input(
            mint="mint-fresh-hot",
            as_of=AS_OF + 1_000,
            setup_kind=ReplaySetupKind.FRESH_LAUNCH_CONTINUATION,
            regime=MarketRegime.HOT,
        ),
        _decision_input(
            mint="mint-graduation-disabled",
            as_of=AS_OF + 2_000,
            setup_kind=ReplaySetupKind.GRADUATION_BREAKOUT,
            regime=MarketRegime.NORMAL,
        ),
        _decision_input(
            mint="mint-pullback-weak-none",
            as_of=AS_OF + 3_000,
            setup_kind=ReplaySetupKind.FIRST_PULLBACK,
            regime=MarketRegime.WEAK,
        ),
    )


def _bundles(
    values: tuple[ReplayDecisionInput, ...],
    *,
    first_return_pct: float | None = None,
) -> tuple[ReplayOutcomeBundle, ...]:
    return tuple(
        _outcome_bundle(
            mint=value.candidate_mint,
            as_of=value.market_features.as_of_unix_ms,
            first_return_pct=first_return_pct,
        )
        for value in values
    )


def _decision_map(result) -> dict[str, object]:
    return {snapshot.candidate_mint: snapshot.decision for snapshot in result.replay.snapshots}


def test_v0_is_exact_e1_replay() -> None:
    values = _inputs()
    bundles = _bundles(values)
    policy = _suite_policy()
    suite = build_baseline_suite(values, bundles, policy)
    expected = replay_entry_decisions(values, bundles, policy.base_replay_policies)
    assert suite.results[0].name == "v0"
    assert suite.results[0].kind is BaselineKind.V0
    assert suite.results[0].replay == expected


def test_zero_threshold_preserves_disabled_and_none_semantics_without_mutating_base() -> None:
    values = _inputs()
    bundles = _bundles(values)
    policy = _suite_policy()
    base_before = policy.base_replay_policies
    suite = build_baseline_suite(values, bundles, policy)
    zero = suite.results[1]
    decisions = _decision_map(zero)

    assert zero.name == "zero_score_threshold"
    assert zero.replay_policy_set_version == "e2-suite-policy-v1:zero_score_threshold"
    assert decisions["mint-fresh-normal"].required_score_threshold == 0.0
    assert decisions["mint-fresh-hot"].required_score_threshold == 0.0
    assert decisions["mint-graduation-disabled"].action is DecisionAction.WATCH
    assert decisions["mint-graduation-disabled"].required_score_threshold is None
    assert decisions["mint-pullback-weak-none"].action is DecisionAction.WATCH
    assert decisions["mint-pullback-weak-none"].required_score_threshold is None
    assert policy.base_replay_policies == base_before


def test_threshold_delta_variants_are_sorted_clamped_and_preserve_none() -> None:
    values = _inputs()
    suite = build_baseline_suite(values, _bundles(values), _suite_policy())
    assert tuple(result.name for result in suite.results) == (
        "v0",
        "zero_score_threshold",
        "looser",
        "stricter",
    )

    looser = _decision_map(suite.results[2])
    stricter = _decision_map(suite.results[3])
    assert looser["mint-fresh-hot"].required_score_threshold == 0.0
    assert looser["mint-fresh-normal"].required_score_threshold == 75.0
    assert stricter["mint-fresh-hot"].required_score_threshold == 20.0
    assert stricter["mint-fresh-normal"].required_score_threshold == 100.0
    assert looser["mint-pullback-weak-none"].required_score_threshold is None
    assert stricter["mint-pullback-weak-none"].required_score_threshold is None


def test_every_baseline_preserves_population_provenance_and_d6_compatibility() -> None:
    values = _inputs()
    suite = build_baseline_suite(values, _bundles(values), _suite_policy())
    identities = tuple(
        (snapshot.market_features.as_of_unix_ms, snapshot.candidate_mint)
        for snapshot in suite.results[0].replay.snapshots
    )
    replay_versions = []
    decision_versions = []
    for result in suite.results:
        assert tuple(
            (snapshot.market_features.as_of_unix_ms, snapshot.candidate_mint)
            for snapshot in result.replay.snapshots
        ) == identities
        assert all(
            snapshot.decision.score_policy_version == "score-e2-v1"
            for snapshot in result.replay.snapshots
        )
        assert len(build_research_dataset(result.replay.snapshots)) == len(values)
        replay_versions.append(result.replay.policy_set_version)
        decision_versions.append(result.replay.snapshots[0].decision.policy_version)

    assert len(set(replay_versions)) == len(replay_versions)
    assert len(set(decision_versions)) == len(decision_versions)
    assert replay_versions[0] == "replay-e2-base-v1"
    assert replay_versions[1] == "e2-suite-policy-v1:zero_score_threshold"
    assert replay_versions[2:] == [
        "e2-suite-policy-v1:threshold:looser",
        "e2-suite-policy-v1:threshold:stricter",
    ]


def test_future_outcomes_cannot_change_any_baseline_score_or_decision() -> None:
    value = _inputs()[0]
    low = build_baseline_suite(
        (value,),
        _bundles((value,), first_return_pct=-95.0),
        _suite_policy(),
    )
    high = build_baseline_suite(
        (value,),
        _bundles((value,), first_return_pct=95.0),
        _suite_policy(),
    )
    for low_result, high_result in zip(low.results, high.results, strict=True):
        low_snapshot = low_result.replay.snapshots[0]
        high_snapshot = high_result.replay.snapshots[0]
        assert low_snapshot.score == high_snapshot.score
        assert low_snapshot.decision == high_snapshot.decision
        assert low_snapshot.outcomes != high_snapshot.outcomes


def test_suite_is_deterministic_under_input_and_variant_reordering() -> None:
    values = _inputs()
    bundles = _bundles(values)
    first = build_baseline_suite(values, bundles, _suite_policy())
    second = build_baseline_suite(
        tuple(reversed(values)),
        tuple(reversed(bundles)),
        _suite_policy(
            (
                ThresholdDeltaBaselineSpec("looser", -20.0),
                ThresholdDeltaBaselineSpec("stricter", 15.0),
            )
        ),
    )
    assert first == second


def test_baseline_import_and_engine_are_pure() -> None:
    code = (
        "import sys; import shreks_brain.baselines; "
        "assert 'pyarrow' not in sys.modules; assert 'sqlite3' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    source = inspect.getsource(baselines.engine)
    for banned in (
        "sqlite3",
        "pyarrow",
        "pathlib",
        "requests",
        "random",
        "time.time",
        "datetime.now",
        "open(",
    ):
        assert banned not in source
