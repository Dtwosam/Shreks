//! Shared domain primitives for Shreks.

mod fast_lane;
pub use fast_lane::{
    assess_continuous_action, assess_continuous_action_from_champion, assess_graduation_flow, assess_impulse_scalp, assess_longer_runner,
    assess_micro_pullback, assess_pre_graduation_acceleration, assess_wallet_cohort_ride_fade,
    label_future_paths, load_fast_forecast_champion_json, maximum_exit_capacity,
    predict_fast_forecast, project_exit, decode_fast_campaign_decision_batch_json,
    encode_fast_campaign_decision_results_json, evaluate_fast_campaign_decision_batch,
    ExecutionCostModel, ExecutionEconomics,
    ExecutionEconomicsError, ExecutionLegCostInput, ExecutionTradeInput, ExitCapacity,
    ExitCapacityError, ExitProjection, FastActionCandidateAssessment, FastActionConstraints,
    FastCampaignActionCandidateWire, FastCampaignActionConstraintsWire,
    FastCampaignContinuousActionPolicyWire, FastCampaignDecisionBatchWire,
    FastCampaignDecisionError, FastCampaignDecisionPositionWire,
    FastCampaignDecisionRequestWire, FastCampaignDecisionResultWire,
    FastCampaignDecisionResultsWire, FastCampaignHorizonEvidenceWire,
    FastCampaignReduceExecutionCostWire,
    FastActionForecastSet, FastActionPositionState, FastContinuousActionAssessment,
    FastContinuousActionError, FastContinuousActionPolicy, FastContinuousActionReason, FastEvent,
    FastEventError, FastEventId, FastEventKind, FastForecastArtifact, FastForecastChampion,
    FastForecastChampionMember, FastForecastChampionSelection, FastForecastFeatureTransform,
    FastForecastInferenceError, FastForecastModelFamily, FastForecastPrediction,
    FastForecastTarget, FastForecastTargetKind, FastHorizonActionEvidence, FastLaneAction,
    FastMarketKey, FastMarketSnapshot, FastMarketState, FastReduceExecutionCost,
    FastReserveContext, FastStateError, FastWindowSummary, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, FuturePathLabel, FuturePathLabelError,
    FuturePathObservation, GraduationBoostContext, GraduationFlowAssessment, GraduationFlowError,
    GraduationFlowExecutionInput, GraduationFlowPolicy, GraduationFlowReason,
    ImpulseScalpAssessment, ImpulseScalpError, ImpulseScalpExecutionInput, ImpulseScalpPolicy,
    ImpulseScalpReason, LongerRunnerAssessment, LongerRunnerContinuationEvidence,
    LongerRunnerError, LongerRunnerPolicy, LongerRunnerProtectiveState, LongerRunnerReason,
    MicroPullbackAssessment, MicroPullbackError, MicroPullbackExecutionInput, MicroPullbackPolicy,
    MicroPullbackReason, PreGraduationAssessment, PreGraduationError, PreGraduationExecutionInput,
    PreGraduationPolicy, PreGraduationReason, WalletCohortAssessment, WalletCohortError,
    WalletCohortEvidence, WalletCohortPolicy, WalletCohortPositionInput, WalletCohortPosture,
    WalletCohortReason, WalletCohortSideSummary, CONTINUOUS_ACTION_POLICY_VERSION,
    DEFAULT_FAST_WINDOWS_MS, DEFAULT_FUTURE_PATH_HORIZONS_MS, EXECUTION_ECONOMICS_VERSION,
    FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME, FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_SCHEMA_VERSION, FAST_FORECAST_FEATURE_COUNT,
    FAST_FORECAST_FEATURE_SCHEMA_VERSION, FUTURE_PATH_LABEL_VERSION,
    GRADUATION_FLOW_BASELINE_VERSION, IMPULSE_SCALP_BASELINE_VERSION,
    LONGER_RUNNER_BASELINE_VERSION, LONGER_RUNNER_EVIDENCE_VERSION,
    MICRO_PULLBACK_BASELINE_VERSION, PRE_GRADUATION_BASELINE_VERSION,
    WALLET_COHORT_BASELINE_VERSION, WALLET_COHORT_EVIDENCE_VERSION,
};
mod lifecycle;
pub use lifecycle::{LifecycleEventKind, TokenLifecycleEvent};
mod wallet;
pub use wallet::{WalletActionKind, WalletObservation, WalletObservationEvidence};

use std::{error::Error, fmt, str::FromStr};

/// Operating mode for the Shreks runtime.
///
/// Live execution is represented here as a state only. Permission to enter
/// `Live` will be guarded by later risk and promotion gates.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum RuntimeMode {
    #[default]
    Observe,
    Paper,
    Shadow,
    Live,
    Halted,
}

impl RuntimeMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Observe => "observe",
            Self::Paper => "paper",
            Self::Shadow => "shadow",
            Self::Live => "live",
            Self::Halted => "halted",
        }
    }
}

impl fmt::Display for RuntimeMode {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseRuntimeModeError {
    value: String,
}

impl ParseRuntimeModeError {
    fn new(value: &str) -> Self {
        Self {
            value: value.to_owned(),
        }
    }
}

impl fmt::Display for ParseRuntimeModeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "unsupported Shreks runtime mode '{}'; expected observe, paper, shadow, live, or halted",
            self.value
        )
    }
}

impl Error for ParseRuntimeModeError {}

impl FromStr for RuntimeMode {
    type Err = ParseRuntimeModeError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "observe" => Ok(Self::Observe),
            "paper" => Ok(Self::Paper),
            "shadow" => Ok(Self::Shadow),
            "live" => Ok(Self::Live),
            "halted" => Ok(Self::Halted),
            other => Err(ParseRuntimeModeError::new(other)),
        }
    }
}

/// External source identifier stored with every provider-derived observation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ProviderId {
    DexScreener,
    Helius,
    Alchemy,
    Chainstack,
    SolanaPublic,
    Jupiter,
    Meteora,
}

impl ProviderId {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::DexScreener => "dexscreener",
            Self::Helius => "helius",
            Self::Alchemy => "alchemy",
            Self::Chainstack => "chainstack",
            Self::SolanaPublic => "solana_public",
            Self::Jupiter => "jupiter",
            Self::Meteora => "meteora",
        }
    }
}

impl fmt::Display for ProviderId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Stable purpose attribution for read-only quote evidence.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum QuotePurpose {
    Entry,
    Exit,
}

impl QuotePurpose {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Entry => "entry",
            Self::Exit => "exit",
        }
    }
}

/// Economic venue where a token/pool/trade is occurring.
///
/// This is deliberately separate from `ProviderId`: DEX Screener may provide
/// an observation about a PumpSwap pair, while the venue remains PumpSwap.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum VenueId {
    PumpFunBondingCurve,
    PumpSwap,
    MeteoraDlmm,
    MeteoraDammV2,
    OtherSolana,
}

impl VenueId {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::PumpFunBondingCurve => "pump_fun_bonding_curve",
            Self::PumpSwap => "pump_swap",
            Self::MeteoraDlmm => "meteora_dlmm",
            Self::MeteoraDammV2 => "meteora_damm_v2",
            Self::OtherSolana => "other_solana",
        }
    }
}

impl fmt::Display for VenueId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Provider health vocabulary shared by observers and operational storage.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ProviderHealthState {
    Healthy,
    Degraded,
    RateLimited,
    Unavailable,
}

impl ProviderHealthState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Healthy => "healthy",
            Self::Degraded => "degraded",
            Self::RateLimited => "rate_limited",
            Self::Unavailable => "unavailable",
        }
    }
}

/// A token surfaced by one of Shreks' discovery sources.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveredToken {
    pub mint: String,
    pub pair_address: Option<String>,
    pub dex_id: Option<String>,
    pub venue: Option<VenueId>,
    pub discovered_at_unix_ms: i64,
    pub source: ProviderId,
}

/// Buy/sell transaction counts for one provider-defined time window.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TransactionWindow {
    pub window: String,
    pub buys: u64,
    pub sells: u64,
}

/// Provider-neutral market information for one DEX pair.
#[derive(Debug, Clone, PartialEq)]
pub struct PairMarketData {
    pub provider: ProviderId,
    pub venue: VenueId,
    pub chain_id: String,
    pub dex_id: String,
    pub pair_address: String,
    pub base_mint: String,
    pub base_name: Option<String>,
    pub base_symbol: Option<String>,
    pub quote_mint: String,
    pub quote_name: Option<String>,
    pub quote_symbol: Option<String>,
    pub price_native: Option<String>,
    pub price_usd: Option<String>,
    pub liquidity_usd: Option<f64>,
    pub volume_5m: Option<f64>,
    pub volume_1h: Option<f64>,
    pub volume_6h: Option<f64>,
    pub volume_24h: Option<f64>,
    pub transactions: Vec<TransactionWindow>,
    pub fdv_usd: Option<f64>,
    pub market_cap_usd: Option<f64>,
    pub pair_created_at_unix_ms: Option<i64>,
    pub observed_at_unix_ms: i64,
}

/// Parsed SPL-token mint state observed through a Solana RPC provider.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TokenMintState {
    pub provider: ProviderId,
    pub mint: String,
    pub owner_program: String,
    pub supply: u64,
    pub decimals: u8,
    pub mint_authority: Option<String>,
    pub freeze_authority: Option<String>,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
}

pub const MAX_TOKEN_DISTRIBUTION_PAGE_SIZE: usize = 1_000;

/// Bounded request for a read-only token-account distribution scan.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TokenDistributionRequest {
    pub mint: String,
    pub page_size: usize,
    pub max_pages: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TokenDistributionRequestError {
    EmptyMint,
    ZeroPageSize,
    PageSizeOutOfRange(usize),
    ZeroMaxPages,
}

impl fmt::Display for TokenDistributionRequestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyMint => formatter.write_str("distribution mint must not be empty"),
            Self::ZeroPageSize => formatter.write_str("distribution page size must be positive"),
            Self::PageSizeOutOfRange(value) => write!(
                formatter,
                "distribution page size must be <= {MAX_TOKEN_DISTRIBUTION_PAGE_SIZE}; got {value}"
            ),
            Self::ZeroMaxPages => formatter.write_str("distribution max pages must be positive"),
        }
    }
}

impl Error for TokenDistributionRequestError {}

impl TokenDistributionRequest {
    pub fn new(
        mint: impl Into<String>,
        page_size: usize,
        max_pages: usize,
    ) -> Result<Self, TokenDistributionRequestError> {
        let mint = mint.into();
        if mint.trim().is_empty() {
            return Err(TokenDistributionRequestError::EmptyMint);
        }
        if page_size == 0 {
            return Err(TokenDistributionRequestError::ZeroPageSize);
        }
        if page_size > MAX_TOKEN_DISTRIBUTION_PAGE_SIZE {
            return Err(TokenDistributionRequestError::PageSizeOutOfRange(page_size));
        }
        if max_pages == 0 {
            return Err(TokenDistributionRequestError::ZeroMaxPages);
        }
        Ok(Self {
            mint,
            page_size,
            max_pages,
        })
    }
}

/// Normalized owner-level concentration evidence from one coherent provider index point.
#[derive(Debug, Clone, PartialEq)]
pub struct TokenHolderDistribution {
    pub provider: ProviderId,
    pub mint: String,
    pub last_indexed_slot: u64,
    pub observed_at_unix_ms: i64,
    pub reported_total_accounts: u64,
    pub accounts_scanned: usize,
    pub unique_owners: usize,
    pub pages_scanned: usize,
    pub complete: bool,
    pub total_balance_raw: u64,
    pub largest_owner: Option<String>,
    pub largest_owner_balance_raw: Option<u64>,
    pub top_holder_concentration_pct: Option<f64>,
}

/// Validated request for a read-only executable Jupiter route/build quote.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuoteRequest {
    pub input_mint: String,
    pub output_mint: String,
    pub amount: u64,
    pub taker: String,
    pub slippage_bps: u16,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuoteRequestError {
    EmptyInputMint,
    EmptyOutputMint,
    IdenticalMints,
    ZeroAmount,
    EmptyTaker,
    SlippageOutOfRange(u16),
}

impl fmt::Display for QuoteRequestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyInputMint => formatter.write_str("input mint must not be empty"),
            Self::EmptyOutputMint => formatter.write_str("output mint must not be empty"),
            Self::IdenticalMints => formatter.write_str("input and output mints must differ"),
            Self::ZeroAmount => formatter.write_str("quote amount must be greater than zero"),
            Self::EmptyTaker => formatter.write_str("quote taker must not be empty"),
            Self::SlippageOutOfRange(value) => {
                write!(formatter, "slippage bps must be <= 10000; got {value}")
            }
        }
    }
}

impl Error for QuoteRequestError {}

impl QuoteRequest {
    pub fn new(
        input_mint: impl Into<String>,
        output_mint: impl Into<String>,
        amount: u64,
        taker: impl Into<String>,
        slippage_bps: u16,
    ) -> Result<Self, QuoteRequestError> {
        let input_mint = input_mint.into();
        let output_mint = output_mint.into();
        let taker = taker.into();

        if input_mint.trim().is_empty() {
            return Err(QuoteRequestError::EmptyInputMint);
        }
        if output_mint.trim().is_empty() {
            return Err(QuoteRequestError::EmptyOutputMint);
        }
        if input_mint == output_mint {
            return Err(QuoteRequestError::IdenticalMints);
        }
        if amount == 0 {
            return Err(QuoteRequestError::ZeroAmount);
        }
        if taker.trim().is_empty() {
            return Err(QuoteRequestError::EmptyTaker);
        }
        if slippage_bps > 10_000 {
            return Err(QuoteRequestError::SlippageOutOfRange(slippage_bps));
        }

        Ok(Self {
            input_mint,
            output_mint,
            amount,
            taker,
            slippage_bps,
        })
    }
}

/// Read-only route/build information. Instructions and signed transaction data
/// intentionally do not cross into the trading brain in Phase A.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuoteSnapshot {
    pub provider: ProviderId,
    pub input_mint: String,
    pub output_mint: String,
    pub input_amount: u64,
    pub output_amount: u64,
    pub minimum_output_amount: u64,
    pub slippage_bps: u16,
    pub price_impact_pct: Option<String>,
    pub route_labels: Vec<String>,
    pub route_available: bool,
    pub quoted_at_unix_ms: i64,
}
