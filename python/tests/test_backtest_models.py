from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from shreks_brain.backtest import (
    BACKTEST_REPLAY_SCHEMA_VERSION,
    ReplayDecisionInput,
    ReplayOutcomeBundle,
    ReplayPolicySet,
    ReplayRun,
    ReplaySetupKind,
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
from shreks_brain.setups import (
    FRESH_LAUNCH_SETUP_NAME,
    FreshLaunchPolicy,
    GraduationContext,
    PullbackContext,
)

AS_OF = 5_000_000
SOURCE = 4_999_000
MINT = "mint-a"


def _market(*, as_of: int = AS_OF, source: int = SOURCE, source_age: int | None = None, schema: str = "b2-v1") -> FeatureVector:
    return FeatureVector(
        schema_version=schema,
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=source,
        source_age_ms=as_of - source if source_age is None else source_age,
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


def _wallet(*, mint: str = MINT, as_of: int = AS_OF, schema: str = "d5-wallet-v1") -> WalletFeatureVector:
    return WalletFeatureVector(
        schema_version=schema,
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
    return RegimeAssessment(
        policy_version="regime-v1",
        as_of_unix_ms=as_of,
        source_observed_at_unix_ms=SOURCE,
        window_started_at_unix_ms=SOURCE - 3_600_000,
        source_age_ms=as_of - SOURCE,
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


def _graduation(*, mint: str = MINT, detected_at: int = AS_OF - 60_000) -> GraduationContext:
    return GraduationContext(
        event_type="pump_graduation",
        provider="provider-a",
        mint=mint,
        quote_mint="So11111111111111111111111111111111111111112",
        from_venue="pump_fun_bonding_curve",
        to_venue="pump_swap",
        pool_address="pool-a",
        signature="sig-a",
        slot=1,
        detected_at_unix_ms=detected_at,
        occurred_at_unix_ms=None,
    )


def _pullback(*, trough_at: int = SOURCE - 1_000) -> PullbackContext:
    return PullbackContext(
        impulse_started_at_unix_ms=trough_at - 30_000,
        peak_at_unix_ms=trough_at - 10_000,
        trough_at_unix_ms=trough_at,
        impulse_start_price_usd=1.0,
        peak_price_usd=1.5,
        trough_price_usd=1.2,
        peak_liquidity_usd=100_000.0,
        trough_liquidity_usd=90_000.0,
        trough_buy_fraction_m5=0.55,
        sample_count=5,
    )


def _decision_input(**changes: object) -> ReplayDecisionInput:
    values: dict[str, object] = {
        "candidate_mint": MINT,
        "market_features": _market(),
        "wallet_features": _wallet(),
        "regime": _regime(),
        "setup_kind": ReplaySetupKind.FRESH_LAUNCH_CONTINUATION,
        "graduation_context": None,
        "pullback_context": None,
    }
    values.update(changes)
    return ReplayDecisionInput(**values)  # type: ignore[arg-type]


def _label(horizon: int, *, baseline: int = AS_OF) -> ResearchOutcomeLabel:
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


def _outcomes(*, baseline: int = AS_OF) -> tuple[ResearchOutcomeLabel, ...]:
    return tuple(_label(value, baseline=baseline) for value in RESEARCH_OUTCOME_HORIZONS_SECONDS)


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


def _score_policy(*, version: str = "score-v1") -> ScorePolicy:
    return ScorePolicy(
        version=version,
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


def _decision_policy(*, required_score: str = "score-v1") -> DecisionPolicy:
    return DecisionPolicy(
        version="decision-v1",
        required_score_policy_version=required_score,
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


def test_replay_schema_and_setup_kind_values_are_exact() -> None:
    assert BACKTEST_REPLAY_SCHEMA_VERSION == "e1-replay-v1"
    assert tuple(value.value for value in ReplaySetupKind) == (
        "fresh_launch_continuation",
        "graduation_breakout",
        "first_pullback",
    )


def test_replay_decision_input_is_frozen_and_accepts_all_context_shapes() -> None:
    value = _decision_input()
    with pytest.raises(FrozenInstanceError):
        value.candidate_mint = "other"  # type: ignore[misc]

    graduation = _decision_input(
        setup_kind=ReplaySetupKind.GRADUATION_BREAKOUT,
        graduation_context=_graduation(),
    )
    assert graduation.graduation_context is not None

    pullback = _decision_input(
        setup_kind=ReplaySetupKind.FIRST_PULLBACK,
        pullback_context=_pullback(),
    )
    assert pullback.pullback_context is not None


def test_replay_decision_input_rejects_cross_domain_mismatch() -> None:
    with pytest.raises(ValueError, match="candidate"):
        _decision_input(wallet_features=_wallet(mint="mint-b"))
    with pytest.raises(ValueError, match="as_of"):
        _decision_input(wallet_features=_wallet(as_of=AS_OF + 1))
    with pytest.raises(ValueError, match="as_of"):
        _decision_input(regime=_regime(as_of=AS_OF + 1))
    with pytest.raises(ValueError, match="market feature schema"):
        _decision_input(market_features=_market(schema="other"))
    with pytest.raises(ValueError, match="d5-wallet-v1"):
        _wallet(schema="other")


def test_replay_decision_input_rejects_future_or_incoherent_source_data() -> None:
    with pytest.raises(ValueError, match="source"):
        _decision_input(market_features=_market(source=AS_OF + 1, source_age=0))
    with pytest.raises(ValueError, match="source_age"):
        _decision_input(market_features=_market(source_age=999))


def test_setup_context_must_match_setup_kind_and_historical_availability() -> None:
    with pytest.raises(ValueError, match="Fresh"):
        _decision_input(graduation_context=_graduation())
    with pytest.raises(ValueError, match="graduation"):
        _decision_input(
            setup_kind=ReplaySetupKind.GRADUATION_BREAKOUT,
            graduation_context=_graduation(mint="mint-b"),
        )
    with pytest.raises(ValueError, match="future"):
        _decision_input(
            setup_kind=ReplaySetupKind.GRADUATION_BREAKOUT,
            graduation_context=_graduation(detected_at=AS_OF + 1),
        )
    with pytest.raises(ValueError, match="pullback"):
        _decision_input(
            setup_kind=ReplaySetupKind.FIRST_PULLBACK,
            graduation_context=_graduation(),
        )
    with pytest.raises(ValueError, match="market source"):
        _decision_input(
            setup_kind=ReplaySetupKind.FIRST_PULLBACK,
            pullback_context=_pullback(trough_at=SOURCE + 1),
        )


def test_outcome_bundle_requires_exact_decision_anchored_horizons() -> None:
    bundle = ReplayOutcomeBundle(
        candidate_mint=MINT,
        as_of_unix_ms=AS_OF,
        outcomes=_outcomes(),
    )
    assert tuple(value.horizon_seconds for value in bundle.outcomes) == RESEARCH_OUTCOME_HORIZONS_SECONDS
    with pytest.raises(FrozenInstanceError):
        bundle.as_of_unix_ms = 0  # type: ignore[misc]

    with pytest.raises(ValueError, match="outcomes"):
        ReplayOutcomeBundle(MINT, AS_OF, _outcomes()[:-1])
    with pytest.raises(ValueError, match="order"):
        ReplayOutcomeBundle(MINT, AS_OF, tuple(reversed(_outcomes())))
    with pytest.raises(ValueError, match="baseline"):
        ReplayOutcomeBundle(MINT, AS_OF, _outcomes(baseline=AS_OF - 1))


def test_replay_policy_set_is_explicit_and_compatible() -> None:
    policies = ReplayPolicySet(
        version="replay-policy-v1",
        fresh_launch_policy=_fresh_policy(),
        graduation_breakout_policy=None,
        first_pullback_policy=None,
        score_policy=_score_policy(),
        decision_policy=_decision_policy(),
    )
    assert policies.version == "replay-policy-v1"

    with pytest.raises(ValueError, match="setup policy"):
        ReplayPolicySet(
            version="replay-policy-v1",
            fresh_launch_policy=None,
            graduation_breakout_policy=None,
            first_pullback_policy=None,
            score_policy=_score_policy(),
            decision_policy=_decision_policy(),
        )
    with pytest.raises(ValueError, match="score policy"):
        ReplayPolicySet(
            version="replay-policy-v1",
            fresh_launch_policy=_fresh_policy(),
            graduation_breakout_policy=None,
            first_pullback_policy=None,
            score_policy=_score_policy(),
            decision_policy=_decision_policy(required_score="other-score"),
        )


def test_replay_run_rejects_empty_snapshot_set() -> None:
    with pytest.raises(ValueError, match="snapshots"):
        ReplayRun(
            schema_version=BACKTEST_REPLAY_SCHEMA_VERSION,
            policy_set_version="replay-policy-v1",
            score_policy_version="score-v1",
            decision_policy_version="decision-v1",
            snapshots=(),
            reject_count=0,
            watch_count=0,
            enter_count=0,
            min_as_of_unix_ms=0,
            max_as_of_unix_ms=0,
        )
