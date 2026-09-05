mod action_policy;
mod baseline;
mod baseline_replay;
mod capacity;
mod campaign;
mod economics;
mod event;
mod forecast;
mod future_path;
mod graduation_flow;
mod longer_runner;
mod micro_pullback;
mod pre_graduation;
mod state;
mod wallet_cohort;

pub use action_policy::{
    assess_continuous_action, FastActionCandidateAssessment, FastActionConstraints,
    FastActionForecastSet, FastActionPositionState, FastContinuousActionAssessment,
    FastContinuousActionError, FastContinuousActionPolicy, FastContinuousActionReason,
    FastHorizonActionEvidence, FastReduceExecutionCost, CONTINUOUS_ACTION_POLICY_VERSION,
};
pub use baseline::{
    assess_impulse_scalp, FastLaneAction, ImpulseScalpAssessment, ImpulseScalpError,
    ImpulseScalpExecutionInput, ImpulseScalpPolicy, ImpulseScalpReason,
    IMPULSE_SCALP_BASELINE_VERSION,
};
pub use baseline_replay::{
    replay_fast_baseline, FastBaselineKind, FastBaselineNotApplicable, FastBaselinePosture,
    FastBaselineReplayAssessment, FastBaselineReplayError, FastBaselineReplayInput,
    FAST_BASELINE_REPLAY_VERSION,
};
pub use capacity::{
    maximum_exit_capacity, project_entry, project_exit, EntryProjection, EntryProjectionError,
    ExitCapacity, ExitCapacityError, ExitProjection,
};
pub use campaign::{
    assess_continuous_action_from_champion, decode_fast_campaign_decision_batch_json,
    encode_fast_campaign_decision_results_json, evaluate_fast_campaign_decision_batch,
    FastCampaignActionCandidateWire, FastCampaignActionConstraintsWire,
    FastCampaignContinuousActionPolicyWire, FastCampaignDecisionBatchWire,
    FastCampaignDecisionError, FastCampaignDecisionPositionWire,
    FastCampaignDecisionRequestWire, FastCampaignDecisionResultWire,
    FastCampaignDecisionResultsWire, FastCampaignHorizonEvidenceWire,
    FastCampaignReduceExecutionCostWire, FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME, FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
};
pub use economics::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError, ExecutionLegCostInput,
    ExecutionTradeInput, EXECUTION_ECONOMICS_VERSION,
};
pub use event::{
    FastEvent, FastEventError, FastEventId, FastEventKind, FastMarketKey, FastReserveContext,
};
pub use forecast::{
    load_fast_forecast_champion_json, predict_fast_forecast, FastForecastArtifact,
    FastForecastChampion, FastForecastChampionMember, FastForecastChampionSelection,
    FastForecastFeatureTransform, FastForecastInferenceError, FastForecastModelFamily,
    FastForecastPrediction, FastForecastTarget, FastForecastTargetKind,
    FAST_FORECAST_FEATURE_COUNT, FAST_FORECAST_FEATURE_SCHEMA_VERSION,
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
pub use longer_runner::{
    assess_longer_runner, LongerRunnerAssessment, LongerRunnerContinuationEvidence,
    LongerRunnerError, LongerRunnerPolicy, LongerRunnerProtectiveState, LongerRunnerReason,
    LONGER_RUNNER_BASELINE_VERSION, LONGER_RUNNER_EVIDENCE_VERSION,
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
