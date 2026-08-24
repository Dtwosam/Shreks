from __future__ import annotations

import math

from shreks_brain.wallets import (
    WalletActionKind,
    WalletProfile,
    WalletRelationshipState,
    WalletTradeEpisodeState,
)

from .wallet_models import (
    WALLET_FEATURE_SCHEMA_VERSION,
    WalletFeatureInputs,
    WalletFeaturePolicy,
    WalletFeatureVector,
    WalletHistoricalStrengthState,
    WalletStrengthAssessment,
)


def build_wallet_feature_vector(inputs: WalletFeatureInputs) -> WalletFeatureVector:
    if type(inputs) is not WalletFeatureInputs:
        raise ValueError("inputs must be a WalletFeatureInputs")

    profiles_by_wallet = {profile.wallet: profile for profile in inputs.profiles}
    strength_assessments = tuple(
        _assess_wallet_strength(profile, inputs.policy)
        for profile in sorted(inputs.profiles, key=lambda value: value.wallet)
    )
    strong_wallets = {
        row.wallet
        for row in strength_assessments
        if row.state is WalletHistoricalStrengthState.STRONG
    }

    recent_entry_wallets, recent_exit_wallets = _recent_activity_wallets(inputs)
    strong_entry_wallets = strong_wallets & recent_entry_wallets
    strong_exit_wallets = strong_wallets & recent_exit_wallets

    confidence_weighted_strong_entry_count = math.fsum(
        profiles_by_wallet[wallet].evidence_sample_confidence
        for wallet in sorted(strong_entry_wallets)
    )
    confidence_weighted_strong_exit_count = math.fsum(
        profiles_by_wallet[wallet].evidence_sample_confidence
        for wallet in sorted(strong_exit_wallets)
    )

    (
        entry_quality_profile_sample_count,
        confidence_weighted_entry_median_return_pct,
        confidence_weighted_entry_win_rate,
    ) = _entry_quality_aggregates(
        recent_entry_wallets=recent_entry_wallets,
        profiles_by_wallet=profiles_by_wallet,
    )

    (
        independently_strong_entry_wallet_count,
        strong_entry_all_pairs_independent_under_evidence,
        strong_entry_linked_pair_count,
        strong_entry_conflicting_pair_count,
        strong_entry_unknown_pair_count,
        strong_entry_coordination_cluster_count,
        strong_entry_max_independent_group_count_upper_bound,
    ) = _strong_entry_relationship_features(
        strong_entry_wallets=strong_entry_wallets,
        inputs=inputs,
    )

    creator_deployer_action_observation_count = sum(
        observation.action is WalletActionKind.CREATOR_ACTION
        and observation.observed_at_unix_ms
        >= inputs.as_of_unix_ms - inputs.policy.creator_activity_window_ms
        for observation in inputs.observations
    )

    profile_policy_version = (
        None if not inputs.profiles else inputs.profiles[0].policy_version
    )
    profile_context_version = next(
        (
            profile.context_version
            for profile in sorted(inputs.profiles, key=lambda value: value.wallet)
            if profile.context_version is not None
        ),
        None,
    )

    nullable_features = (
        (
            "confidence_weighted_entry_median_return_pct",
            confidence_weighted_entry_median_return_pct,
        ),
        (
            "confidence_weighted_entry_win_rate",
            confidence_weighted_entry_win_rate,
        ),
        (
            "independently_strong_entry_wallet_count",
            independently_strong_entry_wallet_count,
        ),
        (
            "strong_entry_all_pairs_independent_under_evidence",
            strong_entry_all_pairs_independent_under_evidence,
        ),
    )
    missing_features = tuple(
        name for name, value in nullable_features if value is None
    )

    return WalletFeatureVector(
        schema_version=WALLET_FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=inputs.as_of_unix_ms,
        candidate_mint=inputs.candidate_mint,
        wallet_feature_policy_version=inputs.policy.version,
        profile_policy_version=profile_policy_version,
        profile_context_version=profile_context_version,
        relationship_policy_version=inputs.independence.policy_version,
        wallet_count=len(inputs.profiles),
        recent_entry_wallet_count=len(recent_entry_wallets),
        recent_exit_wallet_count=len(recent_exit_wallets),
        strong_wallet_count=len(strong_wallets),
        unknown_strength_wallet_count=sum(
            row.state is WalletHistoricalStrengthState.UNKNOWN
            for row in strength_assessments
        ),
        strong_entry_wallet_count=len(strong_entry_wallets),
        strong_exit_wallet_count=len(strong_exit_wallets),
        confidence_weighted_strong_entry_count=confidence_weighted_strong_entry_count,
        confidence_weighted_strong_exit_count=confidence_weighted_strong_exit_count,
        entry_quality_profile_sample_count=entry_quality_profile_sample_count,
        confidence_weighted_entry_median_return_pct=(
            confidence_weighted_entry_median_return_pct
        ),
        confidence_weighted_entry_win_rate=confidence_weighted_entry_win_rate,
        independently_strong_entry_wallet_count=(
            independently_strong_entry_wallet_count
        ),
        strong_entry_all_pairs_independent_under_evidence=(
            strong_entry_all_pairs_independent_under_evidence
        ),
        strong_entry_linked_pair_count=strong_entry_linked_pair_count,
        strong_entry_conflicting_pair_count=strong_entry_conflicting_pair_count,
        strong_entry_unknown_pair_count=strong_entry_unknown_pair_count,
        strong_entry_coordination_cluster_count=(
            strong_entry_coordination_cluster_count
        ),
        strong_entry_max_independent_group_count_upper_bound=(
            strong_entry_max_independent_group_count_upper_bound
        ),
        creator_deployer_action_observation_count=(
            creator_deployer_action_observation_count
        ),
        strength_assessments=strength_assessments,
        missing_features=missing_features,
    )


def _assess_wallet_strength(
    profile: WalletProfile,
    policy: WalletFeaturePolicy,
) -> WalletStrengthAssessment:
    failed_checks: list[str] = []
    missing_checks: list[str] = []

    if (
        profile.effective_closed_sample_size
        < policy.minimum_effective_closed_sample_size
    ):
        failed_checks.append("effective_closed_sample_size")

    if (
        profile.evidence_sample_confidence
        < policy.minimum_evidence_sample_confidence
    ):
        failed_checks.append("evidence_sample_confidence")

    median_return = profile.confidence_weighted_median_return_pct
    if median_return is None:
        missing_checks.append("median_return_pct")
    elif median_return < policy.minimum_median_return_pct:
        failed_checks.append("median_return_pct")

    win_rate = profile.confidence_weighted_win_rate
    if win_rate is None:
        missing_checks.append("win_rate")
    elif win_rate < policy.minimum_win_rate:
        failed_checks.append("win_rate")

    rug_exposure_rate = profile.confidence_weighted_rug_exposure_rate
    if policy.maximum_rug_exposure_rate is not None:
        if rug_exposure_rate is None:
            missing_checks.append("rug_exposure_rate")
        elif rug_exposure_rate > policy.maximum_rug_exposure_rate:
            failed_checks.append("rug_exposure_rate")

    median_drawdown = profile.confidence_weighted_median_max_drawdown_pct
    if policy.maximum_median_drawdown_pct is not None:
        if median_drawdown is None:
            missing_checks.append("median_drawdown_pct")
        elif median_drawdown > policy.maximum_median_drawdown_pct:
            failed_checks.append("median_drawdown_pct")

    if failed_checks:
        state = WalletHistoricalStrengthState.NOT_STRONG
    elif missing_checks:
        state = WalletHistoricalStrengthState.UNKNOWN
    else:
        state = WalletHistoricalStrengthState.STRONG

    return WalletStrengthAssessment(
        wallet=profile.wallet,
        state=state,
        effective_closed_sample_size=profile.effective_closed_sample_size,
        evidence_sample_confidence=profile.evidence_sample_confidence,
        median_return_pct=median_return,
        win_rate=win_rate,
        rug_exposure_rate=rug_exposure_rate,
        median_drawdown_pct=median_drawdown,
        failed_checks=tuple(failed_checks),
        missing_checks=tuple(missing_checks),
    )


def _recent_activity_wallets(
    inputs: WalletFeatureInputs,
) -> tuple[set[str], set[str]]:
    entry_cutoff = inputs.as_of_unix_ms - inputs.policy.entry_window_ms
    exit_cutoff = inputs.as_of_unix_ms - inputs.policy.exit_window_ms
    recent_entries: set[str] = set()
    recent_exits: set[str] = set()

    for reconstruction in inputs.reconstructions:
        for episode in reconstruction.episodes:
            if (
                episode.state is not WalletTradeEpisodeState.UNRESOLVED
                and episode.opened_at_unix_ms >= entry_cutoff
            ):
                recent_entries.add(reconstruction.wallet)
            if (
                episode.state is WalletTradeEpisodeState.CLOSED
                and episode.closed_at_unix_ms is not None
                and episode.closed_at_unix_ms >= exit_cutoff
            ):
                recent_exits.add(reconstruction.wallet)

    return recent_entries, recent_exits


def _entry_quality_aggregates(
    *,
    recent_entry_wallets: set[str],
    profiles_by_wallet: dict[str, WalletProfile],
) -> tuple[int, float | None, float | None]:
    usable: list[tuple[str, WalletProfile]] = []
    for wallet in sorted(recent_entry_wallets):
        profile = profiles_by_wallet[wallet]
        if (
            profile.evidence_sample_confidence > 0.0
            and profile.confidence_weighted_median_return_pct is not None
            and profile.confidence_weighted_win_rate is not None
        ):
            usable.append((wallet, profile))

    if not usable:
        return 0, None, None

    total_weight = math.fsum(
        profile.evidence_sample_confidence for _, profile in usable
    )
    if total_weight <= 0.0:
        return 0, None, None

    weighted_median_return = _weighted_median(
        (
            profile.confidence_weighted_median_return_pct,
            profile.evidence_sample_confidence,
            wallet,
        )
        for wallet, profile in usable
        if profile.confidence_weighted_median_return_pct is not None
    )
    weighted_win_rate = (
        math.fsum(
            profile.evidence_sample_confidence
            * profile.confidence_weighted_win_rate
            for _, profile in usable
            if profile.confidence_weighted_win_rate is not None
        )
        / total_weight
    )
    return len(usable), weighted_median_return, weighted_win_rate


def _weighted_median(rows) -> float:
    ordered = sorted(rows, key=lambda value: (value[0], value[2]))
    total_weight = math.fsum(value[1] for value in ordered)
    midpoint = total_weight / 2.0
    cumulative = 0.0
    for metric, weight, _wallet in ordered:
        cumulative += weight
        if cumulative >= midpoint:
            return metric
    return ordered[-1][0]


def _strong_entry_relationship_features(
    *,
    strong_entry_wallets: set[str],
    inputs: WalletFeatureInputs,
) -> tuple[int | None, bool | None, int, int, int, int, int]:
    strong_count = len(strong_entry_wallets)
    if strong_count == 0:
        return 0, None, 0, 0, 0, 0, 0

    pair_rows = tuple(
        row
        for row in inputs.independence.pair_relationships
        if row.wallet_a in strong_entry_wallets
        and row.wallet_b in strong_entry_wallets
    )
    linked_pair_count = sum(
        row.state is WalletRelationshipState.LINKED for row in pair_rows
    )
    conflicting_pair_count = sum(
        row.state is WalletRelationshipState.CONFLICTING for row in pair_rows
    )
    unknown_pair_count = sum(
        row.state is WalletRelationshipState.UNKNOWN for row in pair_rows
    )

    coordination_cluster_count = 0
    max_independent_group_count_upper_bound = 0
    for cluster in inputs.independence.clusters:
        strong_members = strong_entry_wallets.intersection(cluster.wallets)
        if strong_members:
            max_independent_group_count_upper_bound += 1
        if len(strong_members) >= 2:
            coordination_cluster_count += 1

    if strong_count == 1:
        return (
            1,
            True,
            linked_pair_count,
            conflicting_pair_count,
            unknown_pair_count,
            coordination_cluster_count,
            max_independent_group_count_upper_bound,
        )

    if linked_pair_count > 0 or conflicting_pair_count > 0:
        exact_independent_count = None
        all_pairs_independent = False
    elif unknown_pair_count > 0:
        exact_independent_count = None
        all_pairs_independent = None
    else:
        exact_independent_count = strong_count
        all_pairs_independent = True

    return (
        exact_independent_count,
        all_pairs_independent,
        linked_pair_count,
        conflicting_pair_count,
        unknown_pair_count,
        coordination_cluster_count,
        max_independent_group_count_upper_bound,
    )
