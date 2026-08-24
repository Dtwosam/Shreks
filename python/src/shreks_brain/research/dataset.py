from __future__ import annotations

import hashlib
import json
import math

from shreks_brain.features import WalletStrengthAssessment

from .models import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchOutcomeLabel,
    ResearchSnapshotInputs,
)


RESEARCH_FEATURE_COLUMNS = (
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

_LABEL_SUFFIXES = (
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

RESEARCH_LABEL_COLUMNS = tuple(
    f"label_{horizon}s_{suffix}"
    for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS
    for suffix in _LABEL_SUFFIXES
)

_RESEARCH_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS


def _strength_assessments_json(
    assessments: tuple[WalletStrengthAssessment, ...],
) -> str:
    values: list[dict[str, object]] = []
    for assessment in assessments:
        values.append(
            {
                "wallet": assessment.wallet,
                "state": assessment.state.value,
                "effective_closed_sample_size": assessment.effective_closed_sample_size,
                "evidence_sample_confidence": assessment.evidence_sample_confidence,
                "median_return_pct": assessment.median_return_pct,
                "win_rate": assessment.win_rate,
                "rug_exposure_rate": assessment.rug_exposure_rate,
                "median_drawdown_pct": assessment.median_drawdown_pct,
                "failed_checks": list(assessment.failed_checks),
                "missing_checks": list(assessment.missing_checks),
            }
        )
    return json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _label_values(label: ResearchOutcomeLabel) -> dict[str, object]:
    prefix = f"label_{label.horizon_seconds}s_"
    return {
        prefix + "status": label.status.value,
        prefix + "baseline_observed_at_unix_ms": label.baseline_observed_at_unix_ms,
        prefix + "due_at_unix_ms": label.due_at_unix_ms,
        prefix + "checkpoint_observed_at_unix_ms": label.checkpoint_observed_at_unix_ms,
        prefix + "completed_at_unix_ms": label.completed_at_unix_ms,
        prefix + "return_pct": label.return_pct,
        prefix + "mfe_pct": label.mfe_pct,
        prefix + "mae_pct": label.mae_pct,
        prefix + "liquidity_change_pct": label.liquidity_change_pct,
        prefix + "volume_m5_change_pct": label.volume_m5_change_pct,
        prefix + "buys_m5_change": label.buys_m5_change,
        prefix + "sells_m5_change": label.sells_m5_change,
        prefix + "rug_or_dead_pool": label.rug_or_dead_pool,
        prefix + "exitability": (
            None if label.exitability is None else label.exitability.value
        ),
    }


def build_research_row(inputs: ResearchSnapshotInputs) -> dict[str, object]:
    if type(inputs) is not ResearchSnapshotInputs:
        raise ValueError("inputs must be a ResearchSnapshotInputs value")

    market = inputs.market_features
    wallet = inputs.wallet_features
    regime = inputs.regime
    score = inputs.score
    decision = inputs.decision

    row: dict[str, object] = {
        "dataset_schema_version": RESEARCH_DATASET_SCHEMA_VERSION,
        "candidate_mint": inputs.candidate_mint,
        "as_of_unix_ms": market.as_of_unix_ms,
        "market_feature_schema_version": market.schema_version,
        "wallet_feature_schema_version": wallet.schema_version,
        "market_source_observed_at_unix_ms": market.source_observed_at_unix_ms,
        "market_source_age_ms": market.source_age_ms,
        "safety_policy_version": market.safety_policy_version,
        "wallet_feature_policy_version": wallet.wallet_feature_policy_version,
        "wallet_profile_policy_version": wallet.profile_policy_version,
        "wallet_profile_context_version": wallet.profile_context_version,
        "wallet_relationship_policy_version": wallet.relationship_policy_version,
        "regime_policy_version": regime.policy_version,
        "score_policy_version": score.policy_version,
        "decision_policy_version": decision.policy_version,
        "setup_name": score.setup_name,
        "setup_policy_version": score.setup_policy_version,
        "market_token_age_seconds": market.token_age_seconds,
        "market_price_usd": market.price_usd,
        "market_liquidity_usd": market.liquidity_usd,
        "market_liquidity_change_5m_pct": market.liquidity_change_5m_pct,
        "market_exit_price_impact_pct": market.exit_price_impact_pct,
        "market_volume_m5_usd": market.volume_m5_usd,
        "market_volume_h1_usd": market.volume_h1_usd,
        "market_volume_velocity_ratio": market.volume_velocity_ratio,
        "market_tx_count_m5": market.tx_count_m5,
        "market_tx_count_h1": market.tx_count_h1,
        "market_buy_fraction_m5": market.buy_fraction_m5,
        "market_buy_fraction_h1": market.buy_fraction_h1,
        "market_buy_sell_ratio_m5": market.buy_sell_ratio_m5,
        "market_buy_sell_ratio_h1": market.buy_sell_ratio_h1,
        "market_buy_pressure_acceleration": market.buy_pressure_acceleration,
        "market_return_1m_pct": market.return_1m_pct,
        "market_return_5m_pct": market.return_5m_pct,
        "market_return_15m_pct": market.return_15m_pct,
        "market_momentum_acceleration_1m_vs_5m": market.momentum_acceleration_1m_vs_5m,
        "market_distance_from_local_high_pct": market.distance_from_local_high_pct,
        "market_range_position_pct": market.range_position_pct,
        "market_safety_soft_finding_count": market.safety_soft_finding_count,
        "market_safety_liquidity_weak": market.safety_liquidity_weak,
        "market_safety_holder_concentration_elevated": market.safety_holder_concentration_elevated,
        "market_safety_creator_concentration_elevated": market.safety_creator_concentration_elevated,
        "market_safety_exit_price_impact_elevated": market.safety_exit_price_impact_elevated,
        "market_missing_features": tuple(market.missing_features),
        "wallet_count": wallet.wallet_count,
        "wallet_recent_entry_wallet_count": wallet.recent_entry_wallet_count,
        "wallet_recent_exit_wallet_count": wallet.recent_exit_wallet_count,
        "wallet_strong_wallet_count": wallet.strong_wallet_count,
        "wallet_unknown_strength_wallet_count": wallet.unknown_strength_wallet_count,
        "wallet_strong_entry_wallet_count": wallet.strong_entry_wallet_count,
        "wallet_strong_exit_wallet_count": wallet.strong_exit_wallet_count,
        "wallet_confidence_weighted_strong_entry_count": wallet.confidence_weighted_strong_entry_count,
        "wallet_confidence_weighted_strong_exit_count": wallet.confidence_weighted_strong_exit_count,
        "wallet_entry_quality_profile_sample_count": wallet.entry_quality_profile_sample_count,
        "wallet_confidence_weighted_entry_median_return_pct": wallet.confidence_weighted_entry_median_return_pct,
        "wallet_confidence_weighted_entry_win_rate": wallet.confidence_weighted_entry_win_rate,
        "wallet_independently_strong_entry_wallet_count": wallet.independently_strong_entry_wallet_count,
        "wallet_strong_entry_all_pairs_independent_under_evidence": wallet.strong_entry_all_pairs_independent_under_evidence,
        "wallet_strong_entry_linked_pair_count": wallet.strong_entry_linked_pair_count,
        "wallet_strong_entry_conflicting_pair_count": wallet.strong_entry_conflicting_pair_count,
        "wallet_strong_entry_unknown_pair_count": wallet.strong_entry_unknown_pair_count,
        "wallet_strong_entry_coordination_cluster_count": wallet.strong_entry_coordination_cluster_count,
        "wallet_strong_entry_max_independent_group_count_upper_bound": wallet.strong_entry_max_independent_group_count_upper_bound,
        "wallet_creator_deployer_action_observation_count": wallet.creator_deployer_action_observation_count,
        "wallet_missing_features": tuple(wallet.missing_features),
        "wallet_strength_assessments_json": _strength_assessments_json(
            wallet.strength_assessments
        ),
        "regime": regime.regime.value,
        "regime_base": regime.base_regime.value,
        "regime_source_observed_at_unix_ms": regime.source_observed_at_unix_ms,
        "regime_window_started_at_unix_ms": regime.window_started_at_unix_ms,
        "regime_source_age_ms": regime.source_age_ms,
        "regime_window_seconds": regime.window_seconds,
        "regime_candidate_count": regime.candidate_count,
        "regime_candidate_rate_per_hour": regime.candidate_rate_per_hour,
        "regime_executable_fraction": regime.executable_fraction,
        "regime_median_liquidity_usd": regime.median_liquidity_usd,
        "regime_median_volume_m5_usd": regime.median_volume_m5_usd,
        "regime_performance_sample_count": regime.performance_sample_count,
        "regime_performance_net_expectancy_after_costs_pct": regime.performance_net_expectancy_after_costs_pct,
        "regime_performance_applied": regime.performance_applied,
        "regime_reason_codes": tuple(finding.code.value for finding in regime.findings),
        "safety_decision": market.safety_decision.value,
        "setup_state": score.setup_state.value,
        "market_regime": score.market_regime.value,
        "score_safety_quality": score.safety_quality_score,
        "score_money_flow": score.money_flow_score,
        "score_setup_quality": score.setup_quality_score,
        "score_liquidity_executability": score.liquidity_executability_score,
        "total_score": score.total_score,
        "decision_action": decision.action.value,
        "required_score_threshold": decision.required_score_threshold,
        "score_reason_codes": tuple(finding.code.value for finding in score.findings),
        "decision_reason_codes": tuple(finding.code.value for finding in decision.findings),
    }
    for label in inputs.outcomes:
        row.update(_label_values(label))

    if tuple(row) != _RESEARCH_COLUMNS:
        raise RuntimeError("D6 row builder produced an unexpected physical column order")
    return row


def build_research_dataset(
    snapshots: tuple[ResearchSnapshotInputs, ...],
) -> tuple[dict[str, object], ...]:
    if not isinstance(snapshots, tuple):
        raise ValueError("snapshots must be a tuple")
    if not snapshots:
        raise ValueError("research dataset cannot be empty")
    if not all(type(value) is ResearchSnapshotInputs for value in snapshots):
        raise ValueError("snapshots must contain only ResearchSnapshotInputs values")

    identities: set[tuple[str, int]] = set()
    for snapshot in snapshots:
        identity = (
            snapshot.candidate_mint,
            snapshot.market_features.as_of_unix_ms,
        )
        if identity in identities:
            raise ValueError("duplicate research dataset identity")
        identities.add(identity)

    ordered = sorted(
        snapshots,
        key=lambda value: (
            value.market_features.as_of_unix_ms,
            value.candidate_mint,
        ),
    )
    return tuple(build_research_row(value) for value in ordered)


def _canonicalize(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("research dataset cannot contain non-finite floats")
        return value.hex()
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    raise TypeError(f"unsupported D6 logical fingerprint value: {type(value).__name__}")


def logical_dataset_fingerprint_sha256(
    rows: tuple[dict[str, object], ...],
) -> str:
    canonical = [
        [_canonicalize(row[column]) for column in _RESEARCH_COLUMNS]
        for row in rows
    ]
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
