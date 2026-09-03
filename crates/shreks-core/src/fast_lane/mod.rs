mod baseline;
mod capacity;
mod economics;
mod event;
mod future_path;
mod graduation_flow;
mod micro_pullback;
mod pre_graduation;
mod state;
mod wallet_cohort;

pub use baseline::{
    assess_impulse_scalp, FastLaneAction, ImpulseScalpAssessment, ImpulseScalpError,
    ImpulseScalpExecutionInput, ImpulseScalpPolicy, ImpulseScalpReason,
    IMPULSE_SCALP_BASELINE_VERSION,
};
pub use capacity::{
    maximum_exit_capacity, project_exit, ExitCapacity, ExitCapacityError, ExitProjection,
};
pub use economics::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError, ExecutionLegCostInput,
    ExecutionTradeInput, EXECUTION_ECONOMICS_VERSION,
};
pub use event::{
    FastEvent, FastEventError, FastEventId, FastEventKind, FastMarketKey, FastReserveContext,
};
pub use future_path::{
    label_future_paths, FuturePathCompleteness, FuturePathCoverage, FuturePathDecision,
    FuturePathLabel, FuturePathLabelError, FuturePathObservation, DEFAULT_FUTURE_PATH_HORIZONS_MS,
    FUTURE_PATH_LABEL_VERSION,
};
pub use graduation_flow::{
    assess_graduation_flow, GraduationBoostContext, GraduationFlowAssessment,
    GraduationFlowError, GraduationFlowExecutionInput, GraduationFlowPolicy, GraduationFlowReason,
    GRADUATION_FLOW_BASELINE_VERSION,
};
pub use micro_pullback::{
    assess_micro_pullback, MicroPullbackAssessment, MicroPullbackError,
    MicroPullbackExecutionInput, MicroPullbackPolicy, MicroPullbackReason,
    MICRO_PULLBACK_BASELINE_VERSION,
};
pub use pre_graduation::{
    assess_pre_graduation_acceleration, PreGraduationAssessment, PreGraduationError,
    PreGraduationExecutionInput, PreGraduationPolicy, PreGraduationReason,
    PRE_GRADUATION_BASELINE_VERSION,
};
pub use state::{
    FastMarketSnapshot, FastMarketState, FastStateError, FastWindowSummary,
    DEFAULT_FAST_WINDOWS_MS,
};
pub use wallet_cohort::{
    assess_wallet_cohort_ride_fade, WalletCohortAssessment, WalletCohortError,
    WalletCohortEvidence, WalletCohortPolicy, WalletCohortPositionInput, WalletCohortPosture,
    WalletCohortReason, WalletCohortSideSummary, WALLET_COHORT_BASELINE_VERSION,
    WALLET_COHORT_EVIDENCE_VERSION,
};
