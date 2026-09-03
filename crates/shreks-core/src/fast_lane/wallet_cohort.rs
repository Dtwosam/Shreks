use std::{error::Error, fmt};

use super::{FastLaneAction, FastMarketKey, FastMarketSnapshot};

pub const WALLET_COHORT_EVIDENCE_VERSION: u16 = 1;
pub const WALLET_COHORT_BASELINE_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortSideSummary {
    pub strong_wallet_count: u64,
    pub confidence_weighted_strong_count: f64,
    pub independently_strong_wallet_count: Option<u64>,
    pub all_pairs_independent_under_evidence: Option<bool>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortEvidence {
    pub version: u16,
    pub as_of_unix_ms: i64,
    pub candidate_mint: String,
    pub wallet_feature_policy_version: String,
    pub profile_policy_version: Option<String>,
    pub relationship_policy_version: String,
    pub support: WalletCohortSideSummary,
    pub exits: WalletCohortSideSummary,
    pub support_hold_horizon_wallet_weight: f64,
    pub confidence_weighted_support_median_hold_ms: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WalletCohortPositionInput {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub opened_at_unix_ms: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortPolicy {
    pub version: u16,
    pub min_support_wallet_count_for_ride: u64,
    pub min_confidence_weighted_support_for_ride: f64,
    pub min_independent_support_wallet_count_for_ride: u64,
    pub min_hold_horizon_wallet_weight_for_ride: f64,
    pub reduce_after_median_hold_ratio: f64,
    pub min_confidence_weighted_exit_for_reduce: f64,
    pub min_exit_pressure_ratio_for_reduce: f64,
    pub min_confidence_weighted_exit_for_sell: f64,
    pub min_exit_pressure_ratio_for_sell: f64,
    pub min_independent_exit_wallet_count_for_sell: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum WalletCohortPosture {
    Ride,
    Neutral,
    Fade,
}

impl WalletCohortPosture {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Ride => "ride",
            Self::Neutral => "neutral",
            Self::Fade => "fade",
        }
    }
}

impl fmt::Display for WalletCohortPosture {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum WalletCohortReason {
    WalletEvidenceUnavailable,
    SupportWalletCountBelowRideMinimum,
    SupportWeightBelowRideMinimum,
    SupportIndependenceUnknown,
    SupportIndependenceBelowRideMinimum,
    HoldHorizonUnavailable,
    HoldHorizonWeightBelowRideMinimum,
    HistoricalHoldHorizonExhausted,
    ExitWeightAtOrAboveReduceThreshold,
    ExitPressureAtOrAboveReduceThreshold,
    ExitWeightAtOrAboveSellThreshold,
    ExitPressureAtOrAboveSellThreshold,
    ExitIndependenceUnknown,
    ExitIndependenceBelowSellMinimum,
    RideConditionsMet,
    NeutralHold,
    ReduceConditionsMet,
    SellConditionsMet,
}

impl WalletCohortReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::WalletEvidenceUnavailable => "wallet_evidence_unavailable",
            Self::SupportWalletCountBelowRideMinimum => "support_wallet_count_below_ride_minimum",
            Self::SupportWeightBelowRideMinimum => "support_weight_below_ride_minimum",
            Self::SupportIndependenceUnknown => "support_independence_unknown",
            Self::SupportIndependenceBelowRideMinimum => {
                "support_independence_below_ride_minimum"
            }
            Self::HoldHorizonUnavailable => "hold_horizon_unavailable",
            Self::HoldHorizonWeightBelowRideMinimum => "hold_horizon_weight_below_ride_minimum",
            Self::HistoricalHoldHorizonExhausted => "historical_hold_horizon_exhausted",
            Self::ExitWeightAtOrAboveReduceThreshold => {
                "exit_weight_at_or_above_reduce_threshold"
            }
            Self::ExitPressureAtOrAboveReduceThreshold => {
                "exit_pressure_at_or_above_reduce_threshold"
            }
            Self::ExitWeightAtOrAboveSellThreshold => {
                "exit_weight_at_or_above_sell_threshold"
            }
            Self::ExitPressureAtOrAboveSellThreshold => {
                "exit_pressure_at_or_above_sell_threshold"
            }
            Self::ExitIndependenceUnknown => "exit_independence_unknown",
            Self::ExitIndependenceBelowSellMinimum => "exit_independence_below_sell_minimum",
            Self::RideConditionsMet => "ride_conditions_met",
            Self::NeutralHold => "neutral_hold",
            Self::ReduceConditionsMet => "reduce_conditions_met",
            Self::SellConditionsMet => "sell_conditions_met",
        }
    }
}

impl fmt::Display for WalletCohortReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCohortAssessment {
    pub version: u16,
    pub policy_version: u16,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub action: FastLaneAction,
    pub posture: WalletCohortPosture,
    pub reasons: Vec<WalletCohortReason>,
    pub position_age_ms: u64,
    pub evidence_version: Option<u16>,
    pub wallet_feature_policy_version: Option<String>,
    pub profile_policy_version: Option<String>,
    pub relationship_policy_version: Option<String>,
    pub support_strong_wallet_count: Option<u64>,
    pub support_confidence_weighted_strong_count: Option<f64>,
    pub support_independently_strong_wallet_count: Option<u64>,
    pub support_all_pairs_independent_under_evidence: Option<bool>,
    pub exit_strong_wallet_count: Option<u64>,
    pub exit_confidence_weighted_strong_count: Option<f64>,
    pub exit_independently_strong_wallet_count: Option<u64>,
    pub exit_all_pairs_independent_under_evidence: Option<bool>,
    pub exit_pressure_ratio: Option<f64>,
    pub support_hold_horizon_wallet_weight: Option<f64>,
    pub confidence_weighted_support_median_hold_ms: Option<f64>,
    pub ride_horizon_ms: Option<f64>,
    pub remaining_horizon_ms: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WalletCohortError {
    InvalidPolicy(&'static str),
    InvalidSnapshot(&'static str),
    InvalidEvidence(&'static str),
    InvalidPosition(&'static str),
    EvidenceMintMismatch,
    EvidenceTimestampMismatch { snapshot: i64, evidence: i64 },
    PositionMarketMismatch,
    PositionTimestampMismatch { snapshot: i64, position: i64 },
    PositionOpenedAfterDecision { opened: i64, as_of: i64 },
}

impl fmt::Display for WalletCohortError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(field) => {
                write!(formatter, "FL6.5 wallet cohort policy is invalid: {field}")
            }
            Self::InvalidSnapshot(field) => {
                write!(formatter, "FL6.5 wallet cohort snapshot is invalid: {field}")
            }
            Self::InvalidEvidence(field) => {
                write!(formatter, "FL6.5 wallet cohort evidence is invalid: {field}")
            }
            Self::InvalidPosition(field) => {
                write!(formatter, "FL6.5 wallet cohort position is invalid: {field}")
            }
            Self::EvidenceMintMismatch => formatter.write_str(
                "FL6.5 wallet evidence candidate mint does not match the snapshot market",
            ),
            Self::EvidenceTimestampMismatch { snapshot, evidence } => write!(
                formatter,
                "FL6.5 wallet evidence timestamp {evidence} does not match snapshot timestamp {snapshot}"
            ),
            Self::PositionMarketMismatch => formatter.write_str(
                "FL6.5 position market does not match the current snapshot market",
            ),
            Self::PositionTimestampMismatch { snapshot, position } => write!(
                formatter,
                "FL6.5 position timestamp {position} does not match snapshot timestamp {snapshot}"
            ),
            Self::PositionOpenedAfterDecision { opened, as_of } => write!(
                formatter,
                "FL6.5 position opened at {opened}, after decision timestamp {as_of}"
            ),
        }
    }
}

impl Error for WalletCohortError {}

pub fn assess_wallet_cohort_ride_fade(
    snapshot: &FastMarketSnapshot,
    evidence: Option<&WalletCohortEvidence>,
    position: &WalletCohortPositionInput,
    policy: &WalletCohortPolicy,
) -> Result<WalletCohortAssessment, WalletCohortError> {
    validate_policy(policy)?;
    validate_snapshot(snapshot)?;
    let position_age_ms = validate_position(snapshot, position)?;

    let Some(evidence) = evidence else {
        return Ok(WalletCohortAssessment {
            version: WALLET_COHORT_BASELINE_VERSION,
            policy_version: policy.version,
            market: snapshot.market.clone(),
            as_of_unix_ms: snapshot.as_of_unix_ms,
            action: FastLaneAction::Hold,
            posture: WalletCohortPosture::Neutral,
            reasons: vec![
                WalletCohortReason::WalletEvidenceUnavailable,
                WalletCohortReason::NeutralHold,
            ],
            position_age_ms,
            evidence_version: None,
            wallet_feature_policy_version: None,
            profile_policy_version: None,
            relationship_policy_version: None,
            support_strong_wallet_count: None,
            support_confidence_weighted_strong_count: None,
            support_independently_strong_wallet_count: None,
            support_all_pairs_independent_under_evidence: None,
            exit_strong_wallet_count: None,
            exit_confidence_weighted_strong_count: None,
            exit_independently_strong_wallet_count: None,
            exit_all_pairs_independent_under_evidence: None,
            exit_pressure_ratio: None,
            support_hold_horizon_wallet_weight: None,
            confidence_weighted_support_median_hold_ms: None,
            ride_horizon_ms: None,
            remaining_horizon_ms: None,
        });
    };

    validate_evidence(snapshot, evidence)?;

    let support_weight = evidence.support.confidence_weighted_strong_count;
    let exit_weight = evidence.exits.confidence_weighted_strong_count;
    let total_weight = support_weight + exit_weight;
    if !total_weight.is_finite() {
        return Err(WalletCohortError::InvalidEvidence(
            "combined support and exit weight must be finite",
        ));
    }
    let exit_pressure_ratio = if total_weight > 0.0 {
        exit_weight / total_weight
    } else {
        0.0
    };
    if !exit_pressure_ratio.is_finite() || !(0.0..=1.0).contains(&exit_pressure_ratio) {
        return Err(WalletCohortError::InvalidEvidence(
            "derived exit pressure ratio must be finite and in [0, 1]",
        ));
    }

    let horizon_weight_sufficient = evidence.support_hold_horizon_wallet_weight
        >= policy.min_hold_horizon_wallet_weight_for_ride;
    let (ride_horizon_ms, remaining_horizon_ms, horizon_exhausted) =
        if horizon_weight_sufficient {
            let median_hold = evidence
                .confidence_weighted_support_median_hold_ms
                .ok_or(WalletCohortError::InvalidEvidence(
                    "sufficient hold-horizon weight requires a median hold value",
                ))?;
            let horizon = median_hold * policy.reduce_after_median_hold_ratio;
            if !horizon.is_finite() || horizon < 0.0 {
                return Err(WalletCohortError::InvalidEvidence(
                    "derived ride horizon must be finite and non-negative",
                ));
            }
            let age = position_age_ms as f64;
            let remaining = (horizon - age).max(0.0);
            (Some(horizon), Some(remaining), age > horizon)
        } else {
            (None, None, false)
        };

    let exit_reduce_weight_met = exit_weight >= policy.min_confidence_weighted_exit_for_reduce;
    let exit_reduce_pressure_met =
        exit_pressure_ratio >= policy.min_exit_pressure_ratio_for_reduce;
    let moderate_exit_pressure = exit_reduce_weight_met && exit_reduce_pressure_met;

    let exit_sell_weight_met = exit_weight >= policy.min_confidence_weighted_exit_for_sell;
    let exit_sell_pressure_met = exit_pressure_ratio >= policy.min_exit_pressure_ratio_for_sell;
    let exact_exit_independent = evidence.exits.independently_strong_wallet_count;
    let exit_independence_proven = evidence.exits.all_pairs_independent_under_evidence == Some(true)
        && exact_exit_independent.is_some_and(|count| {
            count >= policy.min_independent_exit_wallet_count_for_sell
        });
    let sell_proven = exit_sell_weight_met && exit_sell_pressure_met && exit_independence_proven;

    let action = if sell_proven {
        FastLaneAction::Sell
    } else if moderate_exit_pressure || horizon_exhausted {
        FastLaneAction::Reduce
    } else {
        FastLaneAction::Hold
    };

    let support_count_met =
        evidence.support.strong_wallet_count >= policy.min_support_wallet_count_for_ride;
    let support_weight_met =
        support_weight >= policy.min_confidence_weighted_support_for_ride;
    let exact_support_independent = evidence.support.independently_strong_wallet_count;
    let support_independence_proven =
        evidence.support.all_pairs_independent_under_evidence == Some(true)
            && exact_support_independent.is_some_and(|count| {
                count >= policy.min_independent_support_wallet_count_for_ride
            });
    let ride_proven = action == FastLaneAction::Hold
        && support_count_met
        && support_weight_met
        && support_independence_proven
        && horizon_weight_sufficient
        && ride_horizon_ms.is_some()
        && !horizon_exhausted
        && exit_pressure_ratio < policy.min_exit_pressure_ratio_for_reduce;

    let posture = match action {
        FastLaneAction::Reduce | FastLaneAction::Sell => WalletCohortPosture::Fade,
        FastLaneAction::Hold if ride_proven => WalletCohortPosture::Ride,
        FastLaneAction::Hold => WalletCohortPosture::Neutral,
        FastLaneAction::Buy | FastLaneAction::Skip => unreachable!(
            "FL6.5 is open-position-only and cannot produce BUY or SKIP"
        ),
    };

    let mut reasons = Vec::new();
    if action == FastLaneAction::Hold && ride_proven {
        reasons.push(WalletCohortReason::RideConditionsMet);
    } else {
        if !support_count_met {
            reasons.push(WalletCohortReason::SupportWalletCountBelowRideMinimum);
        }
        if !support_weight_met {
            reasons.push(WalletCohortReason::SupportWeightBelowRideMinimum);
        }
        if evidence.support.strong_wallet_count >= 2
            && evidence.support.all_pairs_independent_under_evidence != Some(true)
        {
            reasons.push(WalletCohortReason::SupportIndependenceUnknown);
        } else if evidence.support.all_pairs_independent_under_evidence == Some(true)
            && exact_support_independent.is_some_and(|count| {
                count < policy.min_independent_support_wallet_count_for_ride
            })
        {
            reasons.push(WalletCohortReason::SupportIndependenceBelowRideMinimum);
        }

        if evidence.support_hold_horizon_wallet_weight == 0.0
            && evidence.confidence_weighted_support_median_hold_ms.is_none()
        {
            reasons.push(WalletCohortReason::HoldHorizonUnavailable);
        } else if !horizon_weight_sufficient {
            reasons.push(WalletCohortReason::HoldHorizonWeightBelowRideMinimum);
        }
        if horizon_exhausted {
            reasons.push(WalletCohortReason::HistoricalHoldHorizonExhausted);
        }

        if exit_reduce_weight_met {
            reasons.push(WalletCohortReason::ExitWeightAtOrAboveReduceThreshold);
        }
        if exit_reduce_pressure_met {
            reasons.push(WalletCohortReason::ExitPressureAtOrAboveReduceThreshold);
        }
        if exit_sell_weight_met {
            reasons.push(WalletCohortReason::ExitWeightAtOrAboveSellThreshold);
        }
        if exit_sell_pressure_met {
            reasons.push(WalletCohortReason::ExitPressureAtOrAboveSellThreshold);
        }
        if exit_sell_weight_met && exit_sell_pressure_met {
            if evidence.exits.strong_wallet_count >= 2
                && evidence.exits.all_pairs_independent_under_evidence != Some(true)
            {
                reasons.push(WalletCohortReason::ExitIndependenceUnknown);
            } else if evidence.exits.all_pairs_independent_under_evidence == Some(true)
                && exact_exit_independent.is_some_and(|count| {
                    count < policy.min_independent_exit_wallet_count_for_sell
                })
            {
                reasons.push(WalletCohortReason::ExitIndependenceBelowSellMinimum);
            }
        }

        reasons.push(match action {
            FastLaneAction::Hold => WalletCohortReason::NeutralHold,
            FastLaneAction::Reduce => WalletCohortReason::ReduceConditionsMet,
            FastLaneAction::Sell => WalletCohortReason::SellConditionsMet,
            FastLaneAction::Buy | FastLaneAction::Skip => unreachable!(
                "FL6.5 is open-position-only and cannot produce BUY or SKIP"
            ),
        });
        reasons.sort_by_key(|reason| reason_rank(*reason));
        reasons.dedup();
    }

    Ok(WalletCohortAssessment {
        version: WALLET_COHORT_BASELINE_VERSION,
        policy_version: policy.version,
        market: snapshot.market.clone(),
        as_of_unix_ms: snapshot.as_of_unix_ms,
        action,
        posture,
        reasons,
        position_age_ms,
        evidence_version: Some(evidence.version),
        wallet_feature_policy_version: Some(evidence.wallet_feature_policy_version.clone()),
        profile_policy_version: evidence.profile_policy_version.clone(),
        relationship_policy_version: Some(evidence.relationship_policy_version.clone()),
        support_strong_wallet_count: Some(evidence.support.strong_wallet_count),
        support_confidence_weighted_strong_count: Some(support_weight),
        support_independently_strong_wallet_count: evidence
            .support
            .independently_strong_wallet_count,
        support_all_pairs_independent_under_evidence: evidence
            .support
            .all_pairs_independent_under_evidence,
        exit_strong_wallet_count: Some(evidence.exits.strong_wallet_count),
        exit_confidence_weighted_strong_count: Some(exit_weight),
        exit_independently_strong_wallet_count: evidence.exits.independently_strong_wallet_count,
        exit_all_pairs_independent_under_evidence: evidence
            .exits
            .all_pairs_independent_under_evidence,
        exit_pressure_ratio: Some(exit_pressure_ratio),
        support_hold_horizon_wallet_weight: Some(evidence.support_hold_horizon_wallet_weight),
        confidence_weighted_support_median_hold_ms: evidence
            .confidence_weighted_support_median_hold_ms,
        ride_horizon_ms,
        remaining_horizon_ms,
    })
}

fn validate_policy(policy: &WalletCohortPolicy) -> Result<(), WalletCohortError> {
    if policy.version != WALLET_COHORT_BASELINE_VERSION {
        return Err(WalletCohortError::InvalidPolicy("unsupported version"));
    }
    if policy.min_support_wallet_count_for_ride == 0 {
        return Err(WalletCohortError::InvalidPolicy(
            "min_support_wallet_count_for_ride must be positive",
        ));
    }
    if policy.min_independent_support_wallet_count_for_ride == 0 {
        return Err(WalletCohortError::InvalidPolicy(
            "min_independent_support_wallet_count_for_ride must be positive",
        ));
    }
    if policy.min_independent_exit_wallet_count_for_sell == 0 {
        return Err(WalletCohortError::InvalidPolicy(
            "min_independent_exit_wallet_count_for_sell must be positive",
        ));
    }

    for (name, value) in [
        (
            "min_confidence_weighted_support_for_ride",
            policy.min_confidence_weighted_support_for_ride,
        ),
        (
            "min_hold_horizon_wallet_weight_for_ride",
            policy.min_hold_horizon_wallet_weight_for_ride,
        ),
        (
            "reduce_after_median_hold_ratio",
            policy.reduce_after_median_hold_ratio,
        ),
        (
            "min_confidence_weighted_exit_for_reduce",
            policy.min_confidence_weighted_exit_for_reduce,
        ),
        (
            "min_confidence_weighted_exit_for_sell",
            policy.min_confidence_weighted_exit_for_sell,
        ),
    ] {
        if !value.is_finite() || value <= 0.0 {
            return Err(WalletCohortError::InvalidPolicy(name));
        }
    }

    for (name, value) in [
        (
            "min_exit_pressure_ratio_for_reduce",
            policy.min_exit_pressure_ratio_for_reduce,
        ),
        (
            "min_exit_pressure_ratio_for_sell",
            policy.min_exit_pressure_ratio_for_sell,
        ),
    ] {
        if !value.is_finite() || !(0.0..=1.0).contains(&value) {
            return Err(WalletCohortError::InvalidPolicy(name));
        }
    }

    if policy.min_confidence_weighted_exit_for_sell
        < policy.min_confidence_weighted_exit_for_reduce
    {
        return Err(WalletCohortError::InvalidPolicy(
            "sell exit-weight threshold cannot be below reduce threshold",
        ));
    }
    if policy.min_exit_pressure_ratio_for_sell < policy.min_exit_pressure_ratio_for_reduce {
        return Err(WalletCohortError::InvalidPolicy(
            "sell exit-pressure threshold cannot be below reduce threshold",
        ));
    }

    Ok(())
}

fn validate_snapshot(snapshot: &FastMarketSnapshot) -> Result<(), WalletCohortError> {
    if snapshot.as_of_unix_ms < 0 {
        return Err(WalletCohortError::InvalidSnapshot(
            "decision timestamp must be non-negative",
        ));
    }
    Ok(())
}

fn validate_position(
    snapshot: &FastMarketSnapshot,
    position: &WalletCohortPositionInput,
) -> Result<u64, WalletCohortError> {
    if position.market != snapshot.market {
        return Err(WalletCohortError::PositionMarketMismatch);
    }
    if position.as_of_unix_ms != snapshot.as_of_unix_ms {
        return Err(WalletCohortError::PositionTimestampMismatch {
            snapshot: snapshot.as_of_unix_ms,
            position: position.as_of_unix_ms,
        });
    }
    if position.opened_at_unix_ms < 0 {
        return Err(WalletCohortError::InvalidPosition(
            "opened_at_unix_ms must be non-negative",
        ));
    }
    if position.opened_at_unix_ms > snapshot.as_of_unix_ms {
        return Err(WalletCohortError::PositionOpenedAfterDecision {
            opened: position.opened_at_unix_ms,
            as_of: snapshot.as_of_unix_ms,
        });
    }
    let age = snapshot
        .as_of_unix_ms
        .checked_sub(position.opened_at_unix_ms)
        .ok_or(WalletCohortError::InvalidPosition(
            "position age underflowed decision timestamp",
        ))?;
    u64::try_from(age).map_err(|_| {
        WalletCohortError::InvalidPosition("position age must fit in u64 milliseconds")
    })
}

fn validate_evidence(
    snapshot: &FastMarketSnapshot,
    evidence: &WalletCohortEvidence,
) -> Result<(), WalletCohortError> {
    if evidence.version != WALLET_COHORT_EVIDENCE_VERSION {
        return Err(WalletCohortError::InvalidEvidence(
            "unsupported evidence version",
        ));
    }
    if evidence.as_of_unix_ms < 0 {
        return Err(WalletCohortError::InvalidEvidence(
            "evidence timestamp must be non-negative",
        ));
    }
    if evidence.as_of_unix_ms != snapshot.as_of_unix_ms {
        return Err(WalletCohortError::EvidenceTimestampMismatch {
            snapshot: snapshot.as_of_unix_ms,
            evidence: evidence.as_of_unix_ms,
        });
    }
    if evidence.candidate_mint != snapshot.market.mint {
        return Err(WalletCohortError::EvidenceMintMismatch);
    }
    if evidence.wallet_feature_policy_version.trim().is_empty() {
        return Err(WalletCohortError::InvalidEvidence(
            "wallet feature policy version must not be empty",
        ));
    }
    if evidence.relationship_policy_version.trim().is_empty() {
        return Err(WalletCohortError::InvalidEvidence(
            "relationship policy version must not be empty",
        ));
    }
    if let Some(profile_version) = evidence.profile_policy_version.as_deref() {
        if profile_version.trim().is_empty() {
            return Err(WalletCohortError::InvalidEvidence(
                "profile policy version must not be empty when present",
            ));
        }
    }
    if (evidence.support.strong_wallet_count > 0 || evidence.exits.strong_wallet_count > 0)
        && evidence.profile_policy_version.is_none()
    {
        return Err(WalletCohortError::InvalidEvidence(
            "strong wallet evidence requires a profile policy version",
        ));
    }

    validate_side(&evidence.support, "support")?;
    validate_side(&evidence.exits, "exit")?;

    let horizon_weight = evidence.support_hold_horizon_wallet_weight;
    if !horizon_weight.is_finite()
        || horizon_weight < 0.0
        || horizon_weight > evidence.support.strong_wallet_count as f64
    {
        return Err(WalletCohortError::InvalidEvidence(
            "support hold-horizon wallet weight must be finite, non-negative, and bounded by support wallet count",
        ));
    }
    match (
        horizon_weight == 0.0,
        evidence.confidence_weighted_support_median_hold_ms,
    ) {
        (true, None) => {}
        (true, Some(_)) => {
            return Err(WalletCohortError::InvalidEvidence(
                "zero hold-horizon wallet weight cannot claim a median hold",
            ));
        }
        (false, None) => {
            return Err(WalletCohortError::InvalidEvidence(
                "positive hold-horizon wallet weight requires a median hold",
            ));
        }
        (false, Some(value)) if value.is_finite() && value >= 0.0 => {}
        (false, Some(_)) => {
            return Err(WalletCohortError::InvalidEvidence(
                "median hold must be finite and non-negative",
            ));
        }
    }

    Ok(())
}

fn validate_side(
    side: &WalletCohortSideSummary,
    label: &'static str,
) -> Result<(), WalletCohortError> {
    if !side.confidence_weighted_strong_count.is_finite()
        || side.confidence_weighted_strong_count < 0.0
        || side.confidence_weighted_strong_count > side.strong_wallet_count as f64
    {
        return Err(WalletCohortError::InvalidEvidence(match label {
            "support" => "support confidence-weighted count is invalid",
            _ => "exit confidence-weighted count is invalid",
        }));
    }

    match side.strong_wallet_count {
        0 => {
            if side.independently_strong_wallet_count != Some(0)
                || side.all_pairs_independent_under_evidence.is_some()
            {
                return Err(WalletCohortError::InvalidEvidence(match label {
                    "support" => "empty support side must use Some(0) independent count and unknown all-pairs state",
                    _ => "empty exit side must use Some(0) independent count and unknown all-pairs state",
                }));
            }
        }
        1 => {
            if side.independently_strong_wallet_count != Some(1)
                || side.all_pairs_independent_under_evidence != Some(true)
            {
                return Err(WalletCohortError::InvalidEvidence(match label {
                    "support" => "singleton support side must be exactly independently known",
                    _ => "singleton exit side must be exactly independently known",
                }));
            }
        }
        count => match side.all_pairs_independent_under_evidence {
            Some(true) => {
                if side.independently_strong_wallet_count != Some(count) {
                    return Err(WalletCohortError::InvalidEvidence(match label {
                        "support" => "proven independent support side must expose the exact raw independent count",
                        _ => "proven independent exit side must expose the exact raw independent count",
                    }));
                }
            }
            Some(false) | None => {
                if side.independently_strong_wallet_count.is_some() {
                    return Err(WalletCohortError::InvalidEvidence(match label {
                        "support" => "unproven support independence cannot expose an exact independent count",
                        _ => "unproven exit independence cannot expose an exact independent count",
                    }));
                }
            }
        },
    }

    Ok(())
}

const fn reason_rank(reason: WalletCohortReason) -> u8 {
    match reason {
        WalletCohortReason::WalletEvidenceUnavailable => 0,
        WalletCohortReason::SupportWalletCountBelowRideMinimum => 1,
        WalletCohortReason::SupportWeightBelowRideMinimum => 2,
        WalletCohortReason::SupportIndependenceUnknown => 3,
        WalletCohortReason::SupportIndependenceBelowRideMinimum => 4,
        WalletCohortReason::HoldHorizonUnavailable => 5,
        WalletCohortReason::HoldHorizonWeightBelowRideMinimum => 6,
        WalletCohortReason::HistoricalHoldHorizonExhausted => 7,
        WalletCohortReason::ExitWeightAtOrAboveReduceThreshold => 8,
        WalletCohortReason::ExitPressureAtOrAboveReduceThreshold => 9,
        WalletCohortReason::ExitWeightAtOrAboveSellThreshold => 10,
        WalletCohortReason::ExitPressureAtOrAboveSellThreshold => 11,
        WalletCohortReason::ExitIndependenceUnknown => 12,
        WalletCohortReason::ExitIndependenceBelowSellMinimum => 13,
        WalletCohortReason::RideConditionsMet => 14,
        WalletCohortReason::NeutralHold => 15,
        WalletCohortReason::ReduceConditionsMet => 16,
        WalletCohortReason::SellConditionsMet => 17,
    }
}
