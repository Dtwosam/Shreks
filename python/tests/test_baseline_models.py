from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest

from shreks_brain.backtest import (
    ReplayDecisionInput,
    ReplayOutcomeBundle,
    ReplayPolicySet,
    ReplaySetupKind,
    replay_entry_decisions,
)
from shreks_brain.baselines import (
    BASELINE_SUITE_SCHEMA_VERSION,
    BaselineKind,
    BaselineReplayResult,
    BaselineSuite,
    BaselineSuitePolicy,
    ThresholdDeltaBaselineSpec,
)
from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.features import FeatureVector, WalletFeatureVector
from shreks_brain.regime import MarketRegime, RegimeAssessment
from shreks_brain.research import (
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchOutcomeLabel,
    ResearchOutcomeLabelStatus,
)
from shreks_brain.safety import SafetyDecision
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import FRESH_LAUNCH_SETUP_NAME, FreshLaunchPolicy


AS_OF = 20_000_000
MINT = "mint-a"


def _market(*, as_of: int = AS_OF) -> FeatureVector:
    source = as_of - 1_000
    return FeatureVector(
        schema_version="b2-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        source_age_ms=1_000,
        safety_policy_version="safety-v1",
        safety_decision=SafetyDecision.PASS,
        token_age_seconds=300.0,
        price_usd=1.0,
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


def _outcomes(*, as_of: int = AS_OF) -> tuple[ResearchOutcomeLabel, ...]:
    values = []
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
        values.append(
            ResearchOutcomeLabel(
                horizon_seconds=horizon,
                baseline_observed_at_unix_ms=as_of,
                due_at_unix_ms=as_of + horizon * 1_000,
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
        )
    return tuple(values)


def _fresh_policy() -> FreshLaunchPolicy:
    return FreshLaunchPolicy(
        version="fresh-v1",
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


def _score_policy() -> ScorePolicy:
    return ScorePolicy(
        version="score-v1",
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
        version="decision-v1",
        required_score_policy_version="score-v1",
        setup_rules=(
            SetupDecisionRule(
                setup_name=FRESH_LAUNCH_SETUP_NAME,
                enabled=True,
                hot_min_score=50.0,
                normal_min_score=50.0,
                weak_min_score=60.0,
            ),
        ),
    )


def _replay_policy() -> ReplayPolicySet:
    return ReplayPolicySet(
        version="replay-v1",
        fresh_launch_policy=_fresh_policy(),
        graduation_breakout_policy=None,
        first_pullback_policy=None,
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
    )


def _run(*, mint: str = MINT, as_of: int = AS_OF):
    decision_input = ReplayDecisionInput(
        candidate_mint=mint,
        market_features=_market(as_of=as_of),
        wallet_features=_wallet(mint=mint, as_of=as_of),
        regime=_regime(as_of=as_of),
        setup_kind=ReplaySetupKind.FRESH_LAUNCH_CONTINUATION,
        graduation_context=None,
        pullback_context=None,
    )
    outcome = ReplayOutcomeBundle(
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        outcomes=_outcomes(as_of=as_of),
    )
    return replay_entry_decisions((decision_input,), (outcome,), _replay_policy())


def _result(
    name: str,
    kind: BaselineKind,
    *,
    delta: float | None = None,
    replay=None,
) -> BaselineReplayResult:
    if replay is None:
        replay = _run()
    return BaselineReplayResult(
        name=name,
        kind=kind,
        threshold_delta_points=delta,
        replay_policy_set_version=replay.policy_set_version,
        replay=replay,
    )


def test_baseline_schema_and_kind_values_are_exact() -> None:
    assert BASELINE_SUITE_SCHEMA_VERSION == "e2-baselines-v1"
    assert tuple(value.value for value in BaselineKind) == (
        "V0",
        "ZERO_SCORE_THRESHOLD",
        "THRESHOLD_DELTA",
    )


def test_threshold_delta_spec_is_frozen_and_accepts_signed_deltas() -> None:
    looser = ThresholdDeltaBaselineSpec(name="looser", delta_points=-10.0)
    stricter = ThresholdDeltaBaselineSpec(name="stricter", delta_points=10.0)
    assert looser.delta_points == -10.0
    assert stricter.delta_points == 10.0
    with pytest.raises(FrozenInstanceError):
        looser.delta_points = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [True, False, 0, 0.0, math.nan, math.inf, -math.inf, -100.0001, 100.0001],
)
def test_threshold_delta_spec_rejects_invalid_delta(value) -> None:
    with pytest.raises(ValueError, match="delta"):
        ThresholdDeltaBaselineSpec(name="variant", delta_points=value)


@pytest.mark.parametrize("name", ["", "   ", "v0", "zero_score_threshold"])
def test_threshold_delta_spec_rejects_empty_or_reserved_names(name: str) -> None:
    with pytest.raises(ValueError, match="name|reserved"):
        ThresholdDeltaBaselineSpec(name=name, delta_points=10.0)


def test_baseline_suite_policy_requires_exact_replay_policy_and_unique_tuple_variants() -> None:
    base = _replay_policy()
    variants = (
        ThresholdDeltaBaselineSpec("looser", -10.0),
        ThresholdDeltaBaselineSpec("stricter", 10.0),
    )
    value = BaselineSuitePolicy(
        version="suite-v1",
        base_replay_policies=base,
        threshold_variants=variants,
    )
    assert value.base_replay_policies is base

    with pytest.raises(FrozenInstanceError):
        value.version = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="ReplayPolicySet"):
        BaselineSuitePolicy("suite-v1", object(), variants)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tuple"):
        BaselineSuitePolicy("suite-v1", base, list(variants))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ThresholdDeltaBaselineSpec"):
        BaselineSuitePolicy("suite-v1", base, (object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate"):
        BaselineSuitePolicy(
            "suite-v1",
            base,
            (
                ThresholdDeltaBaselineSpec("same", -10.0),
                ThresholdDeltaBaselineSpec("same", 10.0),
            ),
        )


def test_baseline_replay_result_enforces_kind_name_delta_and_version_semantics() -> None:
    replay = _run()
    assert _result("v0", BaselineKind.V0, replay=replay).replay == replay
    assert _result(
        "zero_score_threshold",
        BaselineKind.ZERO_SCORE_THRESHOLD,
        replay=replay,
    ).replay == replay
    assert _result(
        "looser",
        BaselineKind.THRESHOLD_DELTA,
        delta=-10.0,
        replay=replay,
    ).replay == replay

    with pytest.raises(ValueError, match="v0"):
        _result("wrong", BaselineKind.V0, replay=replay)
    with pytest.raises(ValueError, match="delta"):
        _result("v0", BaselineKind.V0, delta=1.0, replay=replay)
    with pytest.raises(ValueError, match="zero_score_threshold"):
        _result("wrong", BaselineKind.ZERO_SCORE_THRESHOLD, replay=replay)
    with pytest.raises(ValueError, match="delta"):
        _result("looser", BaselineKind.THRESHOLD_DELTA, replay=replay)
    with pytest.raises(ValueError, match="version"):
        BaselineReplayResult(
            name="v0",
            kind=BaselineKind.V0,
            threshold_delta_points=None,
            replay_policy_set_version="wrong",
            replay=replay,
        )


def test_baseline_suite_accepts_canonical_results_and_rejects_bad_structure() -> None:
    replay = _run()
    v0 = _result("v0", BaselineKind.V0, replay=replay)
    zero = _result(
        "zero_score_threshold",
        BaselineKind.ZERO_SCORE_THRESHOLD,
        replay=replay,
    )
    looser = _result(
        "looser",
        BaselineKind.THRESHOLD_DELTA,
        delta=-10.0,
        replay=replay,
    )
    stricter = _result(
        "stricter",
        BaselineKind.THRESHOLD_DELTA,
        delta=10.0,
        replay=replay,
    )
    suite = BaselineSuite(
        schema_version=BASELINE_SUITE_SCHEMA_VERSION,
        policy_version="suite-v1",
        results=(v0, zero, looser, stricter),
    )
    assert tuple(result.name for result in suite.results) == (
        "v0",
        "zero_score_threshold",
        "looser",
        "stricter",
    )

    with pytest.raises(ValueError, match="schema_version"):
        BaselineSuite("wrong", "suite-v1", (v0, zero))
    with pytest.raises(ValueError, match="results"):
        BaselineSuite(BASELINE_SUITE_SCHEMA_VERSION, "suite-v1", ())
    with pytest.raises(ValueError, match="v0"):
        BaselineSuite(BASELINE_SUITE_SCHEMA_VERSION, "suite-v1", (zero, v0))
    with pytest.raises(ValueError, match="order"):
        BaselineSuite(
            BASELINE_SUITE_SCHEMA_VERSION,
            "suite-v1",
            (v0, zero, stricter, looser),
        )


def test_baseline_suite_rejects_population_mismatch() -> None:
    replay_a = _run(mint="mint-a")
    replay_b = _run(mint="mint-b")
    v0 = _result("v0", BaselineKind.V0, replay=replay_a)
    zero = _result(
        "zero_score_threshold",
        BaselineKind.ZERO_SCORE_THRESHOLD,
        replay=replay_b,
    )
    with pytest.raises(ValueError, match="identit|population"):
        BaselineSuite(
            schema_version=BASELINE_SUITE_SCHEMA_VERSION,
            policy_version="suite-v1",
            results=(v0, zero),
        )
