use std::{error::Error, fmt};

use shreks_core::{
    replay_fast_baseline, FastBaselineKind, FastBaselinePosture, FastBaselineReplayAssessment,
    FastBaselineReplayError, FastBaselineReplayInput, FastMarketSnapshot, GraduationBoostContext,
    GraduationFlowExecutionInput, GraduationFlowPolicy, ImpulseScalpExecutionInput,
    ImpulseScalpPolicy, LongerRunnerContinuationEvidence, LongerRunnerPolicy,
    LongerRunnerProtectiveState, MicroPullbackExecutionInput, MicroPullbackPolicy,
    PreGraduationExecutionInput, PreGraduationPolicy, WalletCohortEvidence, WalletCohortPolicy,
    WalletCohortPositionInput,
};

use crate::{
    hydrate_fast_baseline_snapshot, FastTrainingFeatureRecord, StorageError,
    FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
};

pub const FAST_BASELINE_CAMPAIGN_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy)]
pub enum FastBaselineCampaignInput<'a> {
    ImpulseScalp {
        execution: Option<&'a ImpulseScalpExecutionInput>,
        policy: &'a ImpulseScalpPolicy,
    },
    MicroPullback {
        execution: Option<&'a MicroPullbackExecutionInput>,
        policy: &'a MicroPullbackPolicy,
    },
    PreGraduation {
        execution: Option<&'a PreGraduationExecutionInput>,
        policy: &'a PreGraduationPolicy,
    },
    GraduationFlow {
        pre_snapshot: &'a FastMarketSnapshot,
        boost_context: Option<&'a GraduationBoostContext>,
        execution: Option<&'a GraduationFlowExecutionInput>,
        policy: &'a GraduationFlowPolicy,
    },
    WalletCohort {
        evidence: Option<&'a WalletCohortEvidence>,
        position: &'a WalletCohortPositionInput,
        policy: &'a WalletCohortPolicy,
    },
    LongerRunner {
        protective: &'a LongerRunnerProtectiveState,
        continuation: Option<&'a LongerRunnerContinuationEvidence>,
        policy: &'a LongerRunnerPolicy,
    },
}

impl FastBaselineCampaignInput<'_> {
    pub const fn baseline_kind(&self) -> FastBaselineKind {
        match self {
            Self::ImpulseScalp { .. } => FastBaselineKind::ImpulseScalp,
            Self::MicroPullback { .. } => FastBaselineKind::MicroPullback,
            Self::PreGraduation { .. } => FastBaselineKind::PreGraduation,
            Self::GraduationFlow { .. } => FastBaselineKind::GraduationFlow,
            Self::WalletCohort { .. } => FastBaselineKind::WalletCohort,
            Self::LongerRunner { .. } => FastBaselineKind::LongerRunner,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastBaselineCampaignAssessment {
    pub version: u16,
    pub hydration_version: u16,
    pub replay_version: u16,
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub posture: FastBaselinePosture,
    pub baseline_kind: FastBaselineKind,
    pub baseline_version: u16,
    pub assessment: FastBaselineReplayAssessment,
}

#[derive(Debug)]
pub enum FastBaselineCampaignError {
    Hydration(StorageError),
    Replay(FastBaselineReplayError),
    Invariant(&'static str),
}

impl fmt::Display for FastBaselineCampaignError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Hydration(error) => write!(formatter, "FL9 baseline campaign hydration failed: {error}"),
            Self::Replay(error) => write!(formatter, "FL9 baseline campaign replay failed: {error}"),
            Self::Invariant(message) => {
                write!(formatter, "FL9 baseline campaign invariant failed: {message}")
            }
        }
    }
}

impl Error for FastBaselineCampaignError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Hydration(error) => Some(error),
            Self::Replay(error) => Some(error),
            Self::Invariant(_) => None,
        }
    }
}

impl From<StorageError> for FastBaselineCampaignError {
    fn from(error: StorageError) -> Self {
        Self::Hydration(error)
    }
}

impl From<FastBaselineReplayError> for FastBaselineCampaignError {
    fn from(error: FastBaselineReplayError) -> Self {
        Self::Replay(error)
    }
}

pub fn evaluate_fast_baseline_campaign(
    record: &FastTrainingFeatureRecord,
    posture: FastBaselinePosture,
    input: FastBaselineCampaignInput<'_>,
) -> Result<FastBaselineCampaignAssessment, FastBaselineCampaignError> {
    let hydration = hydrate_fast_baseline_snapshot(record)?;
    if hydration.version != FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION {
        return Err(FastBaselineCampaignError::Invariant(
            "snapshot hydration version changed unexpectedly",
        ));
    }

    let baseline_kind = input.baseline_kind();
    let assessment = match input {
        FastBaselineCampaignInput::ImpulseScalp { execution, policy } => replay_fast_baseline(
            posture,
            FastBaselineReplayInput::ImpulseScalp {
                snapshot: &hydration.snapshot,
                execution,
                policy,
            },
        )?,
        FastBaselineCampaignInput::MicroPullback { execution, policy } => replay_fast_baseline(
            posture,
            FastBaselineReplayInput::MicroPullback {
                snapshot: &hydration.snapshot,
                execution,
                policy,
            },
        )?,
        FastBaselineCampaignInput::PreGraduation { execution, policy } => replay_fast_baseline(
            posture,
            FastBaselineReplayInput::PreGraduation {
                snapshot: &hydration.snapshot,
                execution,
                policy,
            },
        )?,
        FastBaselineCampaignInput::GraduationFlow {
            pre_snapshot,
            boost_context,
            execution,
            policy,
        } => replay_fast_baseline(
            posture,
            FastBaselineReplayInput::GraduationFlow {
                pre_snapshot,
                post_snapshot: &hydration.snapshot,
                boost_context,
                execution,
                policy,
            },
        )?,
        FastBaselineCampaignInput::WalletCohort {
            evidence,
            position,
            policy,
        } => replay_fast_baseline(
            posture,
            FastBaselineReplayInput::WalletCohort {
                snapshot: &hydration.snapshot,
                evidence,
                position,
                policy,
            },
        )?,
        FastBaselineCampaignInput::LongerRunner {
            protective,
            continuation,
            policy,
        } => replay_fast_baseline(
            posture,
            FastBaselineReplayInput::LongerRunner {
                snapshot: &hydration.snapshot,
                protective,
                continuation,
                policy,
            },
        )?,
    };

    if assessment.market() != &hydration.snapshot.market {
        return Err(FastBaselineCampaignError::Invariant(
            "replay market diverged from hydrated current snapshot",
        ));
    }
    if assessment.as_of_unix_ms() != hydration.snapshot.as_of_unix_ms {
        return Err(FastBaselineCampaignError::Invariant(
            "replay timestamp diverged from hydrated current snapshot",
        ));
    }
    if assessment.baseline_kind() != baseline_kind {
        return Err(FastBaselineCampaignError::Invariant(
            "replay baseline kind diverged from requested baseline",
        ));
    }

    Ok(FastBaselineCampaignAssessment {
        version: FAST_BASELINE_CAMPAIGN_VERSION,
        hydration_version: hydration.version,
        replay_version: assessment.version(),
        source_event_id: hydration.source_event_id,
        market_key: hydration.market_key,
        source_sequence: hydration.source_sequence,
        as_of_unix_ms: hydration.as_of_unix_ms,
        posture,
        baseline_kind,
        baseline_version: assessment.baseline_version(),
        assessment,
    })
}
