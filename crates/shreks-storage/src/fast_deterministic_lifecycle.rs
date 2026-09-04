use std::{
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
};

use shreks_core::{
    FastBaselineKind, FastBaselinePosture, FastLaneAction,
};

use crate::{
    evaluate_fast_baseline_campaign, FastBaselineCampaignAssessment, FastBaselineCampaignError,
    FastBaselineCampaignInput, FastTrainingFeatureRecord,
};

pub const FAST_DETERMINISTIC_LIFECYCLE_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FastDeterministicLifecyclePolicy {
    pub version: u16,
    pub entry_baseline_kind: FastBaselineKind,
    pub manager_baseline_kind: FastBaselineKind,
    pub entry_target_exposure_fraction: f64,
    pub reduce_remaining_fraction: f64,
}

#[derive(Debug, Clone, Copy)]
pub enum FastDeterministicLifecyclePostureInput<'a> {
    Flat {
        input: FastBaselineCampaignInput<'a>,
    },
    Open {
        current_exposure_fraction: f64,
        input: FastBaselineCampaignInput<'a>,
    },
}

impl FastDeterministicLifecyclePostureInput<'_> {
    pub const fn posture(&self) -> FastBaselinePosture {
        match self {
            Self::Flat { .. } => FastBaselinePosture::Flat,
            Self::Open { .. } => FastBaselinePosture::Open,
        }
    }

    pub const fn input(&self) -> FastBaselineCampaignInput<'_> {
        match self {
            Self::Flat { input } | Self::Open { input, .. } => *input,
        }
    }

    pub const fn current_exposure_fraction(&self) -> Option<f64> {
        match self {
            Self::Flat { .. } => None,
            Self::Open {
                current_exposure_fraction,
                ..
            } => Some(*current_exposure_fraction),
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct FastDeterministicLifecycleRequest<'a> {
    pub record: &'a FastTrainingFeatureRecord,
    pub posture: FastDeterministicLifecyclePostureInput<'a>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastDeterministicLifecycleDecision {
    pub version: u16,
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub component_kind: FastBaselineKind,
    pub component_version: u16,
    pub action: FastLaneAction,
    pub current_exposure_fraction: Option<f64>,
    pub target_exposure_fraction: f64,
    pub component: FastBaselineCampaignAssessment,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastDeterministicLifecycleBatchAssessment {
    pub version: u16,
    pub policy: FastDeterministicLifecyclePolicy,
    pub decisions: Vec<FastDeterministicLifecycleDecision>,
}

#[derive(Debug)]
pub enum FastDeterministicLifecycleError {
    InvalidPolicy(&'static str),
    EmptyBatch,
    InvalidCurrentExposure {
        index: usize,
        value: f64,
    },
    ComponentKindMismatch {
        index: usize,
        posture: FastBaselinePosture,
        expected: FastBaselineKind,
        actual: FastBaselineKind,
    },
    Component {
        index: usize,
        source: FastBaselineCampaignError,
    },
    UnexpectedComponentAction {
        index: usize,
        posture: FastBaselinePosture,
        action: Option<FastLaneAction>,
    },
    InvalidReduceTarget {
        index: usize,
    },
    DuplicateSourceEventId {
        source_event_id: String,
    },
    SequenceRegression {
        market_key: String,
        previous: u64,
        current: u64,
    },
    TimestampRegression {
        market_key: String,
        previous: i64,
        current: i64,
    },
}

impl fmt::Display for FastDeterministicLifecycleError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidPolicy(message) => {
                write!(formatter, "invalid deterministic lifecycle policy: {message}")
            }
            Self::EmptyBatch => {
                formatter.write_str("deterministic lifecycle batch must not be empty")
            }
            Self::InvalidCurrentExposure { index, value } => write!(
                formatter,
                "deterministic lifecycle current exposure at index {index} must be finite and within (0, 1]; got {value}"
            ),
            Self::ComponentKindMismatch {
                index,
                posture,
                expected,
                actual,
            } => write!(
                formatter,
                "deterministic lifecycle component baseline mismatch at index {index} for {posture:?}: expected {expected:?}, got {actual:?}"
            ),
            Self::Component { index, source } => write!(
                formatter,
                "deterministic lifecycle component evaluation failed at index {index}: {source}"
            ),
            Self::UnexpectedComponentAction {
                index,
                posture,
                action,
            } => write!(
                formatter,
                "deterministic lifecycle component returned invalid action at index {index} for {posture:?}: {action:?}"
            ),
            Self::InvalidReduceTarget { index } => write!(
                formatter,
                "deterministic lifecycle REDUCE target at index {index} is not finite, positive, and strictly below current exposure"
            ),
            Self::DuplicateSourceEventId { source_event_id } => write!(
                formatter,
                "deterministic lifecycle batch contains duplicate source event identity '{source_event_id}'"
            ),
            Self::SequenceRegression {
                market_key,
                previous,
                current,
            } => write!(
                formatter,
                "deterministic lifecycle source sequence regressed for market '{market_key}': previous {previous}, current {current}"
            ),
            Self::TimestampRegression {
                market_key,
                previous,
                current,
            } => write!(
                formatter,
                "deterministic lifecycle timestamp regressed for market '{market_key}': previous {previous}, current {current}"
            ),
        }
    }
}

impl Error for FastDeterministicLifecycleError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Component { source, .. } => Some(source),
            _ => None,
        }
    }
}

pub fn evaluate_fast_deterministic_lifecycle_batch(
    policy: &FastDeterministicLifecyclePolicy,
    requests: &[FastDeterministicLifecycleRequest<'_>],
) -> Result<FastDeterministicLifecycleBatchAssessment, FastDeterministicLifecycleError> {
    validate_policy(policy)?;
    if requests.is_empty() {
        return Err(FastDeterministicLifecycleError::EmptyBatch);
    }

    let mut seen_source_event_ids = HashSet::<String>::with_capacity(requests.len());
    let mut latest_by_market = HashMap::<String, (u64, i64)>::new();
    let mut decisions = Vec::with_capacity(requests.len());

    for (index, request) in requests.iter().enumerate() {
        let posture = request.posture.posture();
        let input = request.posture.input();
        let component_kind = input.baseline_kind();
        let expected_kind = match posture {
            FastBaselinePosture::Flat => policy.entry_baseline_kind,
            FastBaselinePosture::Open => policy.manager_baseline_kind,
        };
        if component_kind != expected_kind {
            return Err(FastDeterministicLifecycleError::ComponentKindMismatch {
                index,
                posture,
                expected: expected_kind,
                actual: component_kind,
            });
        }

        let current_exposure_fraction = request.posture.current_exposure_fraction();
        if let Some(value) = current_exposure_fraction {
            if !value.is_finite() || value <= 0.0 || value > 1.0 {
                return Err(FastDeterministicLifecycleError::InvalidCurrentExposure {
                    index,
                    value,
                });
            }
        }

        let component = evaluate_fast_baseline_campaign(request.record, posture, input)
            .map_err(|source| FastDeterministicLifecycleError::Component { index, source })?;
        let action = component.assessment.action().ok_or(
            FastDeterministicLifecycleError::UnexpectedComponentAction {
                index,
                posture,
                action: None,
            },
        )?;

        let target_exposure_fraction = match posture {
            FastBaselinePosture::Flat => match action {
                FastLaneAction::Buy => policy.entry_target_exposure_fraction,
                FastLaneAction::Skip => 0.0,
                FastLaneAction::Hold | FastLaneAction::Reduce | FastLaneAction::Sell => {
                    return Err(FastDeterministicLifecycleError::UnexpectedComponentAction {
                        index,
                        posture,
                        action: Some(action),
                    });
                }
            },
            FastBaselinePosture::Open => {
                let current = current_exposure_fraction.expect("OPEN exposure validated above");
                match action {
                    FastLaneAction::Hold => current,
                    FastLaneAction::Reduce => {
                        let target = current * policy.reduce_remaining_fraction;
                        if !target.is_finite() || target <= 0.0 || target >= current {
                            return Err(FastDeterministicLifecycleError::InvalidReduceTarget {
                                index,
                            });
                        }
                        target
                    }
                    FastLaneAction::Sell => 0.0,
                    FastLaneAction::Buy | FastLaneAction::Skip => {
                        return Err(FastDeterministicLifecycleError::UnexpectedComponentAction {
                            index,
                            posture,
                            action: Some(action),
                        });
                    }
                }
            }
        };

        if !seen_source_event_ids.insert(component.source_event_id.clone()) {
            return Err(FastDeterministicLifecycleError::DuplicateSourceEventId {
                source_event_id: component.source_event_id,
            });
        }

        if let Some((previous_sequence, previous_at)) =
            latest_by_market.get(&component.market_key).copied()
        {
            if component.source_sequence <= previous_sequence {
                return Err(FastDeterministicLifecycleError::SequenceRegression {
                    market_key: component.market_key,
                    previous: previous_sequence,
                    current: component.source_sequence,
                });
            }
            if component.as_of_unix_ms < previous_at {
                return Err(FastDeterministicLifecycleError::TimestampRegression {
                    market_key: component.market_key,
                    previous: previous_at,
                    current: component.as_of_unix_ms,
                });
            }
        }

        latest_by_market.insert(
            component.market_key.clone(),
            (component.source_sequence, component.as_of_unix_ms),
        );

        decisions.push(FastDeterministicLifecycleDecision {
            version: FAST_DETERMINISTIC_LIFECYCLE_VERSION,
            source_event_id: component.source_event_id.clone(),
            market_key: component.market_key.clone(),
            source_sequence: component.source_sequence,
            as_of_unix_ms: component.as_of_unix_ms,
            component_kind,
            component_version: component.baseline_version,
            action,
            current_exposure_fraction,
            target_exposure_fraction,
            component,
        });
    }

    Ok(FastDeterministicLifecycleBatchAssessment {
        version: FAST_DETERMINISTIC_LIFECYCLE_VERSION,
        policy: *policy,
        decisions,
    })
}

fn validate_policy(
    policy: &FastDeterministicLifecyclePolicy,
) -> Result<(), FastDeterministicLifecycleError> {
    if policy.version == 0 {
        return Err(FastDeterministicLifecycleError::InvalidPolicy(
            "version must be positive",
        ));
    }

    if !matches!(
        policy.entry_baseline_kind,
        FastBaselineKind::ImpulseScalp
            | FastBaselineKind::MicroPullback
            | FastBaselineKind::PreGraduation
            | FastBaselineKind::GraduationFlow
    ) {
        return Err(FastDeterministicLifecycleError::InvalidPolicy(
            "entry baseline must be FL6.1, FL6.2, FL6.3, or FL6.4",
        ));
    }

    if !matches!(
        policy.manager_baseline_kind,
        FastBaselineKind::WalletCohort | FastBaselineKind::LongerRunner
    ) {
        return Err(FastDeterministicLifecycleError::InvalidPolicy(
            "manager baseline must be FL6.5 or FL6.6",
        ));
    }

    if !policy.entry_target_exposure_fraction.is_finite()
        || policy.entry_target_exposure_fraction <= 0.0
        || policy.entry_target_exposure_fraction > 1.0
    {
        return Err(FastDeterministicLifecycleError::InvalidPolicy(
            "entry target exposure fraction must be finite and within (0, 1]",
        ));
    }

    if !policy.reduce_remaining_fraction.is_finite()
        || policy.reduce_remaining_fraction <= 0.0
        || policy.reduce_remaining_fraction >= 1.0
    {
        return Err(FastDeterministicLifecycleError::InvalidPolicy(
            "reduce remaining fraction must be finite and within (0, 1)",
        ));
    }

    Ok(())
}
