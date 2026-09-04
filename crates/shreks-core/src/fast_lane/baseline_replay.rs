use std::{error::Error, fmt};

use super::{
    assess_graduation_flow, assess_impulse_scalp, assess_longer_runner, assess_micro_pullback,
    assess_pre_graduation_acceleration, assess_wallet_cohort_ride_fade, FastLaneAction,
    FastMarketKey, FastMarketSnapshot, GraduationBoostContext, GraduationFlowAssessment,
    GraduationFlowError, GraduationFlowExecutionInput, GraduationFlowPolicy, ImpulseScalpAssessment,
    ImpulseScalpError, ImpulseScalpExecutionInput, ImpulseScalpPolicy, LongerRunnerAssessment,
    LongerRunnerContinuationEvidence, LongerRunnerError, LongerRunnerPolicy,
    LongerRunnerProtectiveState, MicroPullbackAssessment, MicroPullbackError,
    MicroPullbackExecutionInput, MicroPullbackPolicy, PreGraduationAssessment, PreGraduationError,
    PreGraduationExecutionInput, PreGraduationPolicy, WalletCohortAssessment, WalletCohortError,
    WalletCohortEvidence, WalletCohortPolicy, WalletCohortPositionInput,
    GRADUATION_FLOW_BASELINE_VERSION, IMPULSE_SCALP_BASELINE_VERSION,
    LONGER_RUNNER_BASELINE_VERSION, MICRO_PULLBACK_BASELINE_VERSION,
    PRE_GRADUATION_BASELINE_VERSION, WALLET_COHORT_BASELINE_VERSION,
};

pub const FAST_BASELINE_REPLAY_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FastBaselineKind {
    ImpulseScalp,
    MicroPullback,
    PreGraduation,
    GraduationFlow,
    WalletCohort,
    LongerRunner,
}

impl FastBaselineKind {
    pub const fn baseline_version(self) -> u16 {
        match self {
            Self::ImpulseScalp => IMPULSE_SCALP_BASELINE_VERSION,
            Self::MicroPullback => MICRO_PULLBACK_BASELINE_VERSION,
            Self::PreGraduation => PRE_GRADUATION_BASELINE_VERSION,
            Self::GraduationFlow => GRADUATION_FLOW_BASELINE_VERSION,
            Self::WalletCohort => WALLET_COHORT_BASELINE_VERSION,
            Self::LongerRunner => LONGER_RUNNER_BASELINE_VERSION,
        }
    }

    pub const fn required_posture(self) -> FastBaselinePosture {
        match self {
            Self::ImpulseScalp
            | Self::MicroPullback
            | Self::PreGraduation
            | Self::GraduationFlow => FastBaselinePosture::Flat,
            Self::WalletCohort | Self::LongerRunner => FastBaselinePosture::Open,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FastBaselinePosture {
    Flat,
    Open,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastBaselineNotApplicable {
    pub version: u16,
    pub baseline_kind: FastBaselineKind,
    pub baseline_version: u16,
    pub actual_posture: FastBaselinePosture,
    pub required_posture: FastBaselinePosture,
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
}

#[derive(Debug, Clone, Copy)]
pub enum FastBaselineReplayInput<'a> {
    ImpulseScalp {
        snapshot: &'a FastMarketSnapshot,
        execution: Option<&'a ImpulseScalpExecutionInput>,
        policy: &'a ImpulseScalpPolicy,
    },
    MicroPullback {
        snapshot: &'a FastMarketSnapshot,
        execution: Option<&'a MicroPullbackExecutionInput>,
        policy: &'a MicroPullbackPolicy,
    },
    PreGraduation {
        snapshot: &'a FastMarketSnapshot,
        execution: Option<&'a PreGraduationExecutionInput>,
        policy: &'a PreGraduationPolicy,
    },
    GraduationFlow {
        pre_snapshot: &'a FastMarketSnapshot,
        post_snapshot: &'a FastMarketSnapshot,
        boost_context: Option<&'a GraduationBoostContext>,
        execution: Option<&'a GraduationFlowExecutionInput>,
        policy: &'a GraduationFlowPolicy,
    },
    WalletCohort {
        snapshot: &'a FastMarketSnapshot,
        evidence: Option<&'a WalletCohortEvidence>,
        position: &'a WalletCohortPositionInput,
        policy: &'a WalletCohortPolicy,
    },
    LongerRunner {
        snapshot: &'a FastMarketSnapshot,
        protective: &'a LongerRunnerProtectiveState,
        continuation: Option<&'a LongerRunnerContinuationEvidence>,
        policy: &'a LongerRunnerPolicy,
    },
}

impl FastBaselineReplayInput<'_> {
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

    pub fn market(&self) -> &FastMarketKey {
        match self {
            Self::ImpulseScalp { snapshot, .. }
            | Self::MicroPullback { snapshot, .. }
            | Self::PreGraduation { snapshot, .. }
            | Self::WalletCohort { snapshot, .. }
            | Self::LongerRunner { snapshot, .. } => &snapshot.market,
            Self::GraduationFlow { post_snapshot, .. } => &post_snapshot.market,
        }
    }

    pub const fn as_of_unix_ms(&self) -> i64 {
        match self {
            Self::ImpulseScalp { snapshot, .. }
            | Self::MicroPullback { snapshot, .. }
            | Self::PreGraduation { snapshot, .. }
            | Self::WalletCohort { snapshot, .. }
            | Self::LongerRunner { snapshot, .. } => snapshot.as_of_unix_ms,
            Self::GraduationFlow { post_snapshot, .. } => post_snapshot.as_of_unix_ms,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum FastBaselineReplayAssessment {
    NotApplicable(FastBaselineNotApplicable),
    ImpulseScalp(ImpulseScalpAssessment),
    MicroPullback(MicroPullbackAssessment),
    PreGraduation(PreGraduationAssessment),
    GraduationFlow(GraduationFlowAssessment),
    WalletCohort(WalletCohortAssessment),
    LongerRunner(LongerRunnerAssessment),
}

impl FastBaselineReplayAssessment {
    pub const fn version(&self) -> u16 {
        FAST_BASELINE_REPLAY_VERSION
    }

    pub const fn baseline_kind(&self) -> FastBaselineKind {
        match self {
            Self::NotApplicable(value) => value.baseline_kind,
            Self::ImpulseScalp(_) => FastBaselineKind::ImpulseScalp,
            Self::MicroPullback(_) => FastBaselineKind::MicroPullback,
            Self::PreGraduation(_) => FastBaselineKind::PreGraduation,
            Self::GraduationFlow(_) => FastBaselineKind::GraduationFlow,
            Self::WalletCohort(_) => FastBaselineKind::WalletCohort,
            Self::LongerRunner(_) => FastBaselineKind::LongerRunner,
        }
    }

    pub const fn baseline_version(&self) -> u16 {
        self.baseline_kind().baseline_version()
    }

    pub const fn action(&self) -> Option<FastLaneAction> {
        match self {
            Self::NotApplicable(_) => None,
            Self::ImpulseScalp(value) => Some(value.action),
            Self::MicroPullback(value) => Some(value.action),
            Self::PreGraduation(value) => Some(value.action),
            Self::GraduationFlow(value) => Some(value.action),
            Self::WalletCohort(value) => Some(value.action),
            Self::LongerRunner(value) => Some(value.action),
        }
    }

    pub fn market(&self) -> &FastMarketKey {
        match self {
            Self::NotApplicable(value) => &value.market,
            Self::ImpulseScalp(value) => &value.market,
            Self::MicroPullback(value) => &value.market,
            Self::PreGraduation(value) => &value.market,
            Self::GraduationFlow(value) => &value.market,
            Self::WalletCohort(value) => &value.market,
            Self::LongerRunner(value) => &value.market,
        }
    }

    pub const fn as_of_unix_ms(&self) -> i64 {
        match self {
            Self::NotApplicable(value) => value.as_of_unix_ms,
            Self::ImpulseScalp(value) => value.as_of_unix_ms,
            Self::MicroPullback(value) => value.as_of_unix_ms,
            Self::PreGraduation(value) => value.as_of_unix_ms,
            Self::GraduationFlow(value) => value.as_of_unix_ms,
            Self::WalletCohort(value) => value.as_of_unix_ms,
            Self::LongerRunner(value) => value.as_of_unix_ms,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum FastBaselineReplayError {
    ImpulseScalp(ImpulseScalpError),
    MicroPullback(MicroPullbackError),
    PreGraduation(PreGraduationError),
    GraduationFlow(GraduationFlowError),
    WalletCohort(WalletCohortError),
    LongerRunner(LongerRunnerError),
}

impl fmt::Display for FastBaselineReplayError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ImpulseScalp(error) => write!(formatter, "impulse scalp replay failed: {error}"),
            Self::MicroPullback(error) => write!(formatter, "micro pullback replay failed: {error}"),
            Self::PreGraduation(error) => {
                write!(formatter, "pre-graduation replay failed: {error}")
            }
            Self::GraduationFlow(error) => {
                write!(formatter, "graduation flow replay failed: {error}")
            }
            Self::WalletCohort(error) => {
                write!(formatter, "wallet cohort replay failed: {error}")
            }
            Self::LongerRunner(error) => {
                write!(formatter, "longer runner replay failed: {error}")
            }
        }
    }
}

impl Error for FastBaselineReplayError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::ImpulseScalp(error) => Some(error),
            Self::MicroPullback(error) => Some(error),
            Self::PreGraduation(error) => Some(error),
            Self::GraduationFlow(error) => Some(error),
            Self::WalletCohort(error) => Some(error),
            Self::LongerRunner(error) => Some(error),
        }
    }
}

pub fn replay_fast_baseline(
    posture: FastBaselinePosture,
    input: FastBaselineReplayInput<'_>,
) -> Result<FastBaselineReplayAssessment, FastBaselineReplayError> {
    let baseline_kind = input.baseline_kind();
    let required_posture = baseline_kind.required_posture();
    if posture != required_posture {
        return Ok(FastBaselineReplayAssessment::NotApplicable(
            FastBaselineNotApplicable {
                version: FAST_BASELINE_REPLAY_VERSION,
                baseline_kind,
                baseline_version: baseline_kind.baseline_version(),
                actual_posture: posture,
                required_posture,
                market: input.market().clone(),
                as_of_unix_ms: input.as_of_unix_ms(),
            },
        ));
    }

    match input {
        FastBaselineReplayInput::ImpulseScalp {
            snapshot,
            execution,
            policy,
        } => assess_impulse_scalp(snapshot, execution, policy)
            .map(FastBaselineReplayAssessment::ImpulseScalp)
            .map_err(FastBaselineReplayError::ImpulseScalp),
        FastBaselineReplayInput::MicroPullback {
            snapshot,
            execution,
            policy,
        } => assess_micro_pullback(snapshot, execution, policy)
            .map(FastBaselineReplayAssessment::MicroPullback)
            .map_err(FastBaselineReplayError::MicroPullback),
        FastBaselineReplayInput::PreGraduation {
            snapshot,
            execution,
            policy,
        } => assess_pre_graduation_acceleration(snapshot, execution, policy)
            .map(FastBaselineReplayAssessment::PreGraduation)
            .map_err(FastBaselineReplayError::PreGraduation),
        FastBaselineReplayInput::GraduationFlow {
            pre_snapshot,
            post_snapshot,
            boost_context,
            execution,
            policy,
        } => assess_graduation_flow(
            pre_snapshot,
            post_snapshot,
            boost_context,
            execution,
            policy,
        )
        .map(FastBaselineReplayAssessment::GraduationFlow)
        .map_err(FastBaselineReplayError::GraduationFlow),
        FastBaselineReplayInput::WalletCohort {
            snapshot,
            evidence,
            position,
            policy,
        } => assess_wallet_cohort_ride_fade(snapshot, evidence, position, policy)
            .map(FastBaselineReplayAssessment::WalletCohort)
            .map_err(FastBaselineReplayError::WalletCohort),
        FastBaselineReplayInput::LongerRunner {
            snapshot,
            protective,
            continuation,
            policy,
        } => assess_longer_runner(snapshot, protective, continuation, policy)
            .map(FastBaselineReplayAssessment::LongerRunner)
            .map_err(FastBaselineReplayError::LongerRunner),
    }
}
