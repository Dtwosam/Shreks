from __future__ import annotations

import math

import pytest

from shreks_brain.features import (
    WalletFeatureInputs,
    WalletFeaturePolicy,
    WalletHistoricalStrengthState,
    build_wallet_feature_vector,
)
from shreks_brain.wallets import (
    WalletActionKind,
    WalletIndependenceAssessment,
    WalletObservation,
    WalletObservationEvidence,
    WalletProfile,
    WalletRelationshipDirection,
    WalletRelationshipEvidence,
    WalletRelationshipEvidenceQuality,
    WalletRelationshipPolicy,
    WalletTradeEpisode,
    WalletTradeEpisodeState,
    WalletTradeEvidenceQuality,
    WalletTradeReconstruction,
    assess_wallet_independence,
)

AS_OF = 10_000_000
MINT = "mint-a"


def _policy(**overrides: object) -> WalletFeaturePolicy:
    values: dict[str, object] = {
        "version": "d5-test-v1",
        "entry_window_ms": 300_000,
        "exit_window_ms": 300_000,
        "creator_activity_window_ms": 900_000,
        "minimum_effective_closed_sample_size": 5.0,
        "minimum_evidence_sample_confidence": 0.5,
        "minimum_median_return_pct": 10.0,
        "minimum_win_rate": 0.55,
        "maximum_rug_exposure_rate": 0.10,
        "maximum_median_drawdown_pct": 35.0,
    }
    values.update(overrides)
    return WalletFeaturePolicy(**values)  # type: ignore[arg-type]


def _profile(
    wallet: str,
    *,
    effective: float = 5.0,
    confidence: float = 0.5,
    median_return: float | None = 20.0,
    win_rate: float | None = 0.6,
    rug: float | None = 0.0,
    drawdown: float | None = 20.0,
    profile_policy_version: str = "d3-test-v1",
    context_version: str | None = "ctx-v1",
    as_of: int = AS_OF,
) -> WalletProfile:
    closed = max(5, math.ceil(effective))
    has_core = effective > 0.0
    rug_count = 1 if rug is not None else 0
    drawdown_count = 1 if drawdown is not None else 0
    if rug_count == 0 and drawdown_count == 0:
        context_version = None
    return WalletProfile(
        wallet=wallet,
        as_of_unix_ms=as_of,
        policy_version=profile_policy_version,
        context_version=context_version,
        reconstruction_count=closed,
        episode_count=closed,
        closed_episode_count=closed,
        open_episode_count=0,
        unresolved_episode_count=0,
        halted_reconstruction_count=0,
        direct_closed_episode_count=closed,
        mixed_closed_episode_count=0,
        inferred_closed_episode_count=0,
        effective_closed_sample_size=effective,
        evidence_sample_confidence=confidence if has_core else 0.0,
        confidence_weighted_median_return_pct=median_return if has_core else None,
        confidence_weighted_win_rate=win_rate if has_core else None,
        confidence_weighted_median_hold_ms=60_000.0 if has_core else None,
        aggregate_pnl_counter_asset_mint=None,
        aggregate_realized_pnl_counter_raw=None,
        entry_quality_sample_count=0,
        confidence_weighted_median_entry_quality_pct=None,
        entry_timing_sample_count=0,
        confidence_weighted_median_entry_delay_ms=None,
        drawdown_sample_count=drawdown_count,
        confidence_weighted_median_max_drawdown_pct=drawdown,
        rug_exposure_sample_count=rug_count,
        confidence_weighted_rug_exposure_rate=rug,
        regime_sample_count=0,
        regime_profiles=(),
    )


def _open_episode(wallet: str, *, index: int = 0, opened_at: int) -> WalletTradeEpisode:
    return WalletTradeEpisode(
        wallet=wallet,
        candidate_mint=MINT,
        episode_index=index,
        state=WalletTradeEpisodeState.OPEN,
        evidence_quality=WalletTradeEvidenceQuality.DIRECT,
        opened_at_unix_ms=opened_at,
        last_observed_at_unix_ms=AS_OF,
        closed_at_unix_ms=None,
        counter_asset_mint="SOL",
        total_bought_quantity_raw=100,
        total_sold_quantity_raw=0,
        remaining_quantity_raw=100,
        total_entry_cost_counter_raw=1_000,
        total_exit_proceeds_counter_raw=0,
        estimated_realized_pnl_counter_raw=None,
        estimated_return_pct=None,
        trade_observation_ids=(f"{wallet}-open-{index}",),
        findings=(),
    )


def _closed_episode(
    wallet: str,
    *,
    index: int = 0,
    opened_at: int,
    closed_at: int,
) -> WalletTradeEpisode:
    return WalletTradeEpisode(
        wallet=wallet,
        candidate_mint=MINT,
        episode_index=index,
        state=WalletTradeEpisodeState.CLOSED,
        evidence_quality=WalletTradeEvidenceQuality.DIRECT,
        opened_at_unix_ms=opened_at,
        last_observed_at_unix_ms=closed_at,
        closed_at_unix_ms=closed_at,
        counter_asset_mint="SOL",
        total_bought_quantity_raw=100,
        total_sold_quantity_raw=100,
        remaining_quantity_raw=0,
        total_entry_cost_counter_raw=1_000,
        total_exit_proceeds_counter_raw=1_200,
        estimated_realized_pnl_counter_raw=200,
        estimated_return_pct=20.0,
        trade_observation_ids=(f"{wallet}-closed-{index}",),
        findings=(),
    )


def _reconstruction(
    wallet: str,
    episodes: tuple[WalletTradeEpisode, ...],
    *,
    mint: str = MINT,
    as_of: int = AS_OF,
) -> WalletTradeReconstruction:
    return WalletTradeReconstruction(
        wallet=wallet,
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        episodes=episodes,
        findings=(),
        halted_on_uncertain_inventory=False,
    )


def _relationship_evidence(
    evidence_id: str,
    wallet_a: str,
    wallet_b: str,
    direction: WalletRelationshipDirection,
) -> WalletRelationshipEvidence:
    return WalletRelationshipEvidence(
        evidence_id=evidence_id,
        wallet_a=wallet_a,
        wallet_b=wallet_b,
        observed_at_unix_ms=AS_OF - 1,
        direction=direction,
        evidence_quality=WalletRelationshipEvidenceQuality.DIRECT,
        confidence=0.9,
        reason_code=f"reason-{evidence_id}",
    )


def _independence(
    wallets: tuple[str, ...],
    evidence: tuple[WalletRelationshipEvidence, ...] = (),
    *,
    as_of: int = AS_OF,
) -> WalletIndependenceAssessment:
    return assess_wallet_independence(
        wallets=wallets,
        evidence=evidence,
        as_of_unix_ms=as_of,
        policy=WalletRelationshipPolicy(
            version="d4-test-v1",
            direct_evidence_weight=1.0,
            inferred_evidence_weight=0.5,
            relationship_confidence_threshold=0.7,
        ),
    )


def _creator_observation(observed_at: int, *, action: WalletActionKind = WalletActionKind.CREATOR_ACTION) -> WalletObservation:
    return WalletObservation(
        provider="provider-a",
        wallet="creator-wallet",
        candidate_mint=MINT,
        action=action,
        evidence=WalletObservationEvidence.DIRECT,
        signature=f"sig-{observed_at}-{action.value}",
        event_index=0,
        slot=1,
        observed_at_unix_ms=observed_at,
        occurred_at_unix_ms=None,
        candidate_token_delta_raw=None,
        counter_asset_mint=None,
        counter_asset_delta_raw=None,
        venue=None,
        counterparty=None,
    )


def _inputs(
    reconstructions: tuple[WalletTradeReconstruction, ...],
    profiles: tuple[WalletProfile, ...],
    independence: WalletIndependenceAssessment,
    *,
    observations: tuple[WalletObservation, ...] = (),
    policy: WalletFeaturePolicy | None = None,
) -> WalletFeatureInputs:
    return WalletFeatureInputs(
        as_of_unix_ms=AS_OF,
        candidate_mint=MINT,
        reconstructions=reconstructions,
        profiles=profiles,
        independence=independence,
        observations=observations,
        policy=_policy() if policy is None else policy,
    )


def test_strength_classification_is_fail_closed_and_tri_state() -> None:
    wallets = ("wallet-a", "wallet-b", "wallet-c")
    reconstructions = tuple(
        _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))
        for wallet in wallets
    )
    profiles = (
        _profile("wallet-a"),
        _profile("wallet-b", effective=4.0),
        _profile("wallet-c", rug=None),
    )
    vector = build_wallet_feature_vector(
        _inputs(reconstructions, profiles, _independence(wallets))
    )
    states = {row.wallet: row for row in vector.strength_assessments}
    assert states["wallet-a"].state is WalletHistoricalStrengthState.STRONG
    assert states["wallet-b"].state is WalletHistoricalStrengthState.NOT_STRONG
    assert states["wallet-b"].failed_checks == ("effective_closed_sample_size",)
    assert states["wallet-c"].state is WalletHistoricalStrengthState.UNKNOWN
    assert states["wallet-c"].missing_checks == ("rug_exposure_rate",)


def test_known_failure_outranks_missing_optional_strength_metric() -> None:
    wallet = "wallet-a"
    reconstruction = _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))
    vector = build_wallet_feature_vector(
        _inputs(
            (reconstruction,),
            (_profile(wallet, effective=4.0, rug=None),),
            _independence((wallet,)),
        )
    )
    row = vector.strength_assessments[0]
    assert row.state is WalletHistoricalStrengthState.NOT_STRONG
    assert row.failed_checks == ("effective_closed_sample_size",)
    assert row.missing_checks == ("rug_exposure_rate",)


def test_optional_strength_thresholds_can_be_disabled_without_fabricating_context() -> None:
    wallet = "wallet-a"
    reconstruction = _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))
    policy = _policy(maximum_rug_exposure_rate=None, maximum_median_drawdown_pct=None)
    vector = build_wallet_feature_vector(
        _inputs(
            (reconstruction,),
            (_profile(wallet, rug=None, drawdown=None, context_version=None),),
            _independence((wallet,)),
            policy=policy,
        )
    )
    assert vector.strength_assessments[0].state is WalletHistoricalStrengthState.STRONG


def test_recent_entry_exit_boundaries_are_inclusive_and_churn_is_preserved() -> None:
    wallet = "wallet-a"
    episodes = (
        _closed_episode(
            wallet,
            index=0,
            opened_at=AS_OF - 600_000,
            closed_at=AS_OF - 300_000,
        ),
        _open_episode(wallet, index=1, opened_at=AS_OF - 300_000),
    )
    vector = build_wallet_feature_vector(
        _inputs(
            (_reconstruction(wallet, episodes),),
            (_profile(wallet),),
            _independence((wallet,)),
        )
    )
    assert vector.recent_entry_wallet_count == 1
    assert vector.recent_exit_wallet_count == 1
    assert vector.strong_entry_wallet_count == 1
    assert vector.strong_exit_wallet_count == 1
    assert vector.confidence_weighted_strong_entry_count == pytest.approx(0.5)
    assert vector.confidence_weighted_strong_exit_count == pytest.approx(0.5)


def test_older_activity_is_not_recent() -> None:
    wallet = "wallet-a"
    episode = _closed_episode(
        wallet,
        opened_at=AS_OF - 700_000,
        closed_at=AS_OF - 300_001,
    )
    vector = build_wallet_feature_vector(
        _inputs(
            (_reconstruction(wallet, (episode,)),),
            (_profile(wallet),),
            _independence((wallet,)),
        )
    )
    assert vector.recent_entry_wallet_count == 0
    assert vector.recent_exit_wallet_count == 0


def test_entry_quality_aggregates_are_confidence_weighted_and_deterministic() -> None:
    wallets = ("wallet-a", "wallet-b", "wallet-c")
    reconstructions = tuple(
        _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))
        for wallet in wallets
    )
    profiles = (
        _profile("wallet-a", confidence=1.0, median_return=10.0, win_rate=0.5),
        _profile("wallet-b", confidence=0.5, median_return=30.0, win_rate=0.7),
        _profile("wallet-c", confidence=0.25, median_return=100.0, win_rate=0.9),
    )
    vector = build_wallet_feature_vector(
        _inputs(
            tuple(reversed(reconstructions)),
            tuple(reversed(profiles)),
            _independence(wallets),
            policy=_policy(
                minimum_evidence_sample_confidence=0.1,
                minimum_median_return_pct=1.0,
                minimum_win_rate=0.0,
            ),
        )
    )
    assert vector.entry_quality_profile_sample_count == 3
    assert vector.confidence_weighted_entry_median_return_pct == 10.0
    expected_rate = ((1.0 * 0.5) + (0.5 * 0.7) + (0.25 * 0.9)) / 1.75
    assert vector.confidence_weighted_entry_win_rate == pytest.approx(expected_rate)
    assert tuple(row.wallet for row in vector.strength_assessments) == wallets


def test_no_recent_entrant_quality_remains_unknown_not_zero() -> None:
    wallet = "wallet-a"
    reconstruction = _reconstruction(
        wallet,
        (_open_episode(wallet, opened_at=AS_OF - 300_001),),
    )
    vector = build_wallet_feature_vector(
        _inputs((reconstruction,), (_profile(wallet),), _independence((wallet,)))
    )
    assert vector.entry_quality_profile_sample_count == 0
    assert vector.confidence_weighted_entry_median_return_pct is None
    assert vector.confidence_weighted_entry_win_rate is None
    assert "confidence_weighted_entry_median_return_pct" in vector.missing_features
    assert "confidence_weighted_entry_win_rate" in vector.missing_features


def test_strong_entry_independence_requires_explicit_pair_evidence() -> None:
    wallets = ("wallet-a", "wallet-b")
    reconstructions = tuple(
        _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))
        for wallet in wallets
    )
    profiles = tuple(_profile(wallet) for wallet in wallets)

    unknown = build_wallet_feature_vector(
        _inputs(reconstructions, profiles, _independence(wallets))
    )
    assert unknown.strong_entry_wallet_count == 2
    assert unknown.independently_strong_entry_wallet_count is None
    assert unknown.strong_entry_all_pairs_independent_under_evidence is None
    assert unknown.strong_entry_unknown_pair_count == 1

    explicit = build_wallet_feature_vector(
        _inputs(
            reconstructions,
            profiles,
            _independence(
                wallets,
                (_relationship_evidence(
                    "ev-ind",
                    "wallet-a",
                    "wallet-b",
                    WalletRelationshipDirection.INDEPENDENT,
                ),),
            ),
        )
    )
    assert explicit.independently_strong_entry_wallet_count == 2
    assert explicit.strong_entry_all_pairs_independent_under_evidence is True
    assert explicit.strong_entry_unknown_pair_count == 0


def test_linked_and_conflicting_strong_entry_pairs_fail_independence_closed() -> None:
    wallets = ("wallet-a", "wallet-b")
    reconstructions = tuple(
        _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))
        for wallet in wallets
    )
    profiles = tuple(_profile(wallet) for wallet in wallets)

    linked = build_wallet_feature_vector(
        _inputs(
            reconstructions,
            profiles,
            _independence(
                wallets,
                (_relationship_evidence(
                    "ev-link",
                    "wallet-a",
                    "wallet-b",
                    WalletRelationshipDirection.LINKED,
                ),),
            ),
        )
    )
    assert linked.independently_strong_entry_wallet_count is None
    assert linked.strong_entry_all_pairs_independent_under_evidence is False
    assert linked.strong_entry_linked_pair_count == 1
    assert linked.strong_entry_coordination_cluster_count == 1
    assert linked.strong_entry_max_independent_group_count_upper_bound == 1

    conflict_evidence = (
        _relationship_evidence(
            "ev-link",
            "wallet-a",
            "wallet-b",
            WalletRelationshipDirection.LINKED,
        ),
        _relationship_evidence(
            "ev-ind",
            "wallet-a",
            "wallet-b",
            WalletRelationshipDirection.INDEPENDENT,
        ),
    )
    conflict = build_wallet_feature_vector(
        _inputs(reconstructions, profiles, _independence(wallets, conflict_evidence))
    )
    assert conflict.strong_entry_all_pairs_independent_under_evidence is False
    assert conflict.strong_entry_conflicting_pair_count == 1


def test_nonentrant_bridge_preserves_coordination_component_for_strong_entrants() -> None:
    wallets = ("wallet-a", "wallet-b", "wallet-c")
    reconstructions = (
        _reconstruction("wallet-a", (_open_episode("wallet-a", opened_at=AS_OF - 1),)),
        _reconstruction("wallet-b", (_open_episode("wallet-b", opened_at=AS_OF - 400_000),)),
        _reconstruction("wallet-c", (_open_episode("wallet-c", opened_at=AS_OF - 1),)),
    )
    profiles = tuple(_profile(wallet) for wallet in wallets)
    evidence = (
        _relationship_evidence("ab", "wallet-a", "wallet-b", WalletRelationshipDirection.LINKED),
        _relationship_evidence("bc", "wallet-b", "wallet-c", WalletRelationshipDirection.LINKED),
    )
    vector = build_wallet_feature_vector(
        _inputs(reconstructions, profiles, _independence(wallets, evidence))
    )
    assert vector.strong_entry_wallet_count == 2
    assert vector.strong_entry_coordination_cluster_count == 1
    assert vector.strong_entry_max_independent_group_count_upper_bound == 1
    assert vector.strong_entry_unknown_pair_count == 1


def test_creator_deployer_activity_uses_local_inclusive_window_only() -> None:
    vector = build_wallet_feature_vector(
        _inputs(
            (),
            (),
            _independence(()),
            observations=(
                _creator_observation(AS_OF - 900_000),
                _creator_observation(AS_OF - 900_001),
                _creator_observation(AS_OF - 1, action=WalletActionKind.OTHER),
            ),
        )
    )
    assert vector.creator_deployer_action_observation_count == 1


def test_inputs_reject_cross_version_or_time_mismatches() -> None:
    wallet = "wallet-a"
    reconstruction = _reconstruction(wallet, (_open_episode(wallet, opened_at=AS_OF - 1),))

    with pytest.raises(ValueError, match="profile.*as_of"):
        _inputs(
            (reconstruction,),
            (_profile(wallet, as_of=AS_OF - 1),),
            _independence((wallet,)),
        )

    with pytest.raises(ValueError, match="wallet set"):
        _inputs(
            (reconstruction,),
            (_profile(wallet),),
            _independence(()),
        )

    second = _reconstruction("wallet-b", (_open_episode("wallet-b", opened_at=AS_OF - 1),))
    with pytest.raises(ValueError, match="policy"):
        _inputs(
            (reconstruction, second),
            (
                _profile(wallet, profile_policy_version="d3-a"),
                _profile("wallet-b", profile_policy_version="d3-b"),
            ),
            _independence((wallet, "wallet-b")),
        )
