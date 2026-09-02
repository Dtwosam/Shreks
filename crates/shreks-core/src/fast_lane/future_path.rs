use std::{error::Error, fmt};

use super::{FastEvent, FastEventId, FastMarketKey};

pub const FUTURE_PATH_LABEL_VERSION: u16 = 1;
pub const DEFAULT_FUTURE_PATH_HORIZONS_MS: [u64; 12] = [
    250, 500, 1_000, 3_000, 5_000, 10_000, 30_000, 60_000, 300_000, 900_000, 1_800_000,
    3_600_000,
];

#[derive(Debug, Clone, PartialEq)]
pub struct FuturePathDecision {
    pub market: FastMarketKey,
    pub event_id: FastEventId,
    pub sequence: u64,
    pub observed_at_unix_ms: i64,
    pub executable_entry_price_quote: f64,
    pub entry_total_quote: Option<f64>,
}

impl FuturePathDecision {
    pub fn new(
        market: FastMarketKey,
        event_id: FastEventId,
        sequence: u64,
        observed_at_unix_ms: i64,
        executable_entry_price_quote: f64,
    ) -> Result<Self, FuturePathLabelError> {
        if observed_at_unix_ms < 0 {
            return Err(FuturePathLabelError::NegativeDecisionTimestamp(
                observed_at_unix_ms,
            ));
        }
        if !executable_entry_price_quote.is_finite() || executable_entry_price_quote <= 0.0 {
            return Err(FuturePathLabelError::InvalidDecisionPrice);
        }
        Ok(Self {
            market,
            event_id,
            sequence,
            observed_at_unix_ms,
            executable_entry_price_quote,
            entry_total_quote: None,
        })
    }

    pub fn with_entry_total_quote(
        mut self,
        entry_total_quote: f64,
    ) -> Result<Self, FuturePathLabelError> {
        if !entry_total_quote.is_finite() || entry_total_quote <= 0.0 {
            return Err(FuturePathLabelError::InvalidEntryTotalQuote);
        }
        self.entry_total_quote = Some(entry_total_quote);
        Ok(self)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FuturePathObservation {
    pub event: FastEvent,
    pub route_available: Option<bool>,
    pub exit_capacity_base: Option<f64>,
    pub executable_exit_net_quote: Option<f64>,
}

impl FuturePathObservation {
    pub fn from_event(event: FastEvent) -> Self {
        Self {
            event,
            route_available: None,
            exit_capacity_base: None,
            executable_exit_net_quote: None,
        }
    }

    pub fn with_route_available(mut self, route_available: bool) -> Self {
        self.route_available = Some(route_available);
        self
    }

    pub fn with_exit_capacity_base(
        mut self,
        exit_capacity_base: f64,
    ) -> Result<Self, FuturePathLabelError> {
        if !exit_capacity_base.is_finite() || exit_capacity_base < 0.0 {
            return Err(FuturePathLabelError::InvalidExitCapacityBase);
        }
        self.exit_capacity_base = Some(exit_capacity_base);
        Ok(self)
    }

    pub fn with_executable_exit_net_quote(
        mut self,
        executable_exit_net_quote: f64,
    ) -> Result<Self, FuturePathLabelError> {
        if !executable_exit_net_quote.is_finite() || executable_exit_net_quote < 0.0 {
            return Err(FuturePathLabelError::InvalidExecutableExitNetQuote);
        }
        self.executable_exit_net_quote = Some(executable_exit_net_quote);
        Ok(self)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FuturePathCoverage {
    pub complete_through_unix_ms: i64,
    pub contiguous: bool,
}

impl FuturePathCoverage {
    pub fn new(
        complete_through_unix_ms: i64,
        contiguous: bool,
    ) -> Result<Self, FuturePathLabelError> {
        if complete_through_unix_ms < 0 {
            return Err(FuturePathLabelError::NegativeCoverageTimestamp(
                complete_through_unix_ms,
            ));
        }
        Ok(Self {
            complete_through_unix_ms,
            contiguous,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FuturePathCompleteness {
    Complete,
    Incomplete,
}

impl FuturePathCompleteness {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Complete => "complete",
            Self::Incomplete => "incomplete",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FuturePathLabel {
    pub version: u16,
    pub horizon_ms: u64,
    pub completeness: FuturePathCompleteness,
    pub event_count: u64,
    pub no_trade_events: bool,
    pub endpoint_event_id: Option<FastEventId>,
    pub endpoint_observed_at_unix_ms: Option<i64>,
    pub endpoint_price_quote: Option<f64>,
    pub endpoint_return_bps: Option<f64>,
    pub mfe_bps: Option<f64>,
    pub mae_bps: Option<f64>,
    pub time_to_peak_ms: Option<u64>,
    pub time_to_trough_ms: Option<u64>,
    pub reversal_occurred: Option<bool>,
    pub first_reversal_after_ms: Option<u64>,
    pub min_exit_capacity_base: Option<f64>,
    pub endpoint_exit_capacity_base: Option<f64>,
    pub route_unavailability_observed: Option<bool>,
    pub best_cost_adjusted_return_bps: Option<f64>,
    pub endpoint_cost_adjusted_return_bps: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FuturePathLabelError {
    NegativeDecisionTimestamp(i64),
    InvalidDecisionPrice,
    InvalidEntryTotalQuote,
    InvalidExitCapacityBase,
    InvalidExecutableExitNetQuote,
    NegativeCoverageTimestamp(i64),
    InvalidHorizons,
    ObservationMarketMismatch,
    ObservationSequenceNotAfterDecision { decision: u64, incoming: u64 },
    ObservationTimeNotAfterDecision { decision: i64, incoming: i64 },
    NonMonotonicObservationSequence { last: u64, incoming: u64 },
    ObservationTimeMovedBackward { last: i64, incoming: i64 },
    HorizonTimestampOverflow,
    EventCountOverflow,
}

impl fmt::Display for FuturePathLabelError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NegativeDecisionTimestamp(value) => write!(
                formatter,
                "future-path decision timestamp must be non-negative; got {value}"
            ),
            Self::InvalidDecisionPrice => formatter.write_str(
                "future-path decision executable entry price must be positive and finite",
            ),
            Self::InvalidEntryTotalQuote => formatter.write_str(
                "future-path entry total quote must be positive and finite when present",
            ),
            Self::InvalidExitCapacityBase => formatter.write_str(
                "future-path exit capacity must be finite and non-negative when present",
            ),
            Self::InvalidExecutableExitNetQuote => formatter.write_str(
                "future-path executable exit net quote must be finite and non-negative when present",
            ),
            Self::NegativeCoverageTimestamp(value) => write!(
                formatter,
                "future-path coverage timestamp must be non-negative; got {value}"
            ),
            Self::InvalidHorizons => formatter.write_str(
                "future-path horizons must be non-empty, strictly increasing, and non-zero",
            ),
            Self::ObservationMarketMismatch => formatter.write_str(
                "future-path observation market does not match decision market",
            ),
            Self::ObservationSequenceNotAfterDecision { decision, incoming } => write!(
                formatter,
                "future-path observation sequence {incoming} is not after decision sequence {decision}"
            ),
            Self::ObservationTimeNotAfterDecision { decision, incoming } => write!(
                formatter,
                "future-path observation time {incoming} is not after decision time {decision}"
            ),
            Self::NonMonotonicObservationSequence { last, incoming } => write!(
                formatter,
                "future-path observation sequence must strictly increase; last {last}, incoming {incoming}"
            ),
            Self::ObservationTimeMovedBackward { last, incoming } => write!(
                formatter,
                "future-path canonical observation time moved backward; last {last}, incoming {incoming}"
            ),
            Self::HorizonTimestampOverflow => {
                formatter.write_str("future-path horizon timestamp overflowed")
            }
            Self::EventCountOverflow => {
                formatter.write_str("future-path event count exceeds u64")
            }
        }
    }
}

impl Error for FuturePathLabelError {}

pub fn label_future_paths(
    decision: &FuturePathDecision,
    observations: &[FuturePathObservation],
    coverage: FuturePathCoverage,
    horizons_ms: &[u64],
) -> Result<Vec<FuturePathLabel>, FuturePathLabelError> {
    validate_horizons(horizons_ms)?;
    validate_observations(decision, observations)?;

    horizons_ms
        .iter()
        .copied()
        .map(|horizon_ms| label_horizon(decision, observations, coverage, horizon_ms))
        .collect()
}

fn validate_horizons(horizons_ms: &[u64]) -> Result<(), FuturePathLabelError> {
    if horizons_ms.is_empty() || horizons_ms[0] == 0 {
        return Err(FuturePathLabelError::InvalidHorizons);
    }
    if horizons_ms
        .windows(2)
        .any(|window| window[0] == 0 || window[1] <= window[0])
    {
        return Err(FuturePathLabelError::InvalidHorizons);
    }
    Ok(())
}

fn validate_observations(
    decision: &FuturePathDecision,
    observations: &[FuturePathObservation],
) -> Result<(), FuturePathLabelError> {
    let mut last_sequence = decision.sequence;
    let mut last_observed_at = decision.observed_at_unix_ms;

    for observation in observations {
        let event = &observation.event;
        if event.market != decision.market {
            return Err(FuturePathLabelError::ObservationMarketMismatch);
        }
        if event.sequence <= decision.sequence {
            return Err(FuturePathLabelError::ObservationSequenceNotAfterDecision {
                decision: decision.sequence,
                incoming: event.sequence,
            });
        }
        if event.observed_at_unix_ms <= decision.observed_at_unix_ms {
            return Err(FuturePathLabelError::ObservationTimeNotAfterDecision {
                decision: decision.observed_at_unix_ms,
                incoming: event.observed_at_unix_ms,
            });
        }
        if event.sequence <= last_sequence {
            return Err(FuturePathLabelError::NonMonotonicObservationSequence {
                last: last_sequence,
                incoming: event.sequence,
            });
        }
        if event.observed_at_unix_ms < last_observed_at {
            return Err(FuturePathLabelError::ObservationTimeMovedBackward {
                last: last_observed_at,
                incoming: event.observed_at_unix_ms,
            });
        }
        last_sequence = event.sequence;
        last_observed_at = event.observed_at_unix_ms;
    }
    Ok(())
}

fn label_horizon(
    decision: &FuturePathDecision,
    observations: &[FuturePathObservation],
    coverage: FuturePathCoverage,
    horizon_ms: u64,
) -> Result<FuturePathLabel, FuturePathLabelError> {
    let horizon_i64 = i64::try_from(horizon_ms)
        .map_err(|_| FuturePathLabelError::HorizonTimestampOverflow)?;
    let horizon_end = decision
        .observed_at_unix_ms
        .checked_add(horizon_i64)
        .ok_or(FuturePathLabelError::HorizonTimestampOverflow)?;

    let complete = coverage.contiguous && coverage.complete_through_unix_ms >= horizon_end;
    if !complete {
        return Ok(empty_label(horizon_ms, FuturePathCompleteness::Incomplete, false));
    }

    let future: Vec<&FuturePathObservation> = observations
        .iter()
        .take_while(|observation| observation.event.observed_at_unix_ms <= horizon_end)
        .collect();
    if future.is_empty() {
        return Ok(empty_label(horizon_ms, FuturePathCompleteness::Complete, true));
    }

    let event_count = u64::try_from(future.len()).map_err(|_| FuturePathLabelError::EventCountOverflow)?;
    let endpoint = *future.last().expect("future path prefix is non-empty");

    let mut max_return_bps = 0.0_f64;
    let mut min_return_bps = 0.0_f64;
    let mut peak_time_ms = 0_u64;
    let mut trough_time_ms = 0_u64;
    let mut direction: i8 = 0;
    let mut reversal_occurred = false;
    let mut first_reversal_after_ms = None;
    let mut min_exit_capacity_base: Option<f64> = None;
    let mut any_route_evidence = false;
    let mut route_unavailability_observed = false;
    let mut best_cost_adjusted_return_bps: Option<f64> = None;

    for observation in &future {
        let elapsed_ms = u64::try_from(
            observation.event.observed_at_unix_ms - decision.observed_at_unix_ms,
        )
        .map_err(|_| FuturePathLabelError::HorizonTimestampOverflow)?;
        let return_bps = price_return_bps(
            decision.executable_entry_price_quote,
            observation.event.price_quote,
        );
        if return_bps > max_return_bps {
            max_return_bps = return_bps;
            peak_time_ms = elapsed_ms;
        }
        if return_bps < min_return_bps {
            min_return_bps = return_bps;
            trough_time_ms = elapsed_ms;
        }

        if direction == 0 {
            direction = if observation.event.price_quote > decision.executable_entry_price_quote {
                1
            } else if observation.event.price_quote < decision.executable_entry_price_quote {
                -1
            } else {
                0
            };
        } else if !reversal_occurred {
            let crossed = (direction > 0
                && observation.event.price_quote <= decision.executable_entry_price_quote)
                || (direction < 0
                    && observation.event.price_quote >= decision.executable_entry_price_quote);
            if crossed {
                reversal_occurred = true;
                first_reversal_after_ms = Some(elapsed_ms);
            }
        }

        if let Some(capacity) = observation.exit_capacity_base {
            min_exit_capacity_base = Some(
                min_exit_capacity_base.map_or(capacity, |current| current.min(capacity)),
            );
        }
        if let Some(route_available) = observation.route_available {
            any_route_evidence = true;
            route_unavailability_observed |= !route_available;
        }
        if let (Some(entry_total), Some(exit_net)) = (
            decision.entry_total_quote,
            observation.executable_exit_net_quote,
        ) {
            let economic_return = economic_return_bps(entry_total, exit_net);
            best_cost_adjusted_return_bps = Some(
                best_cost_adjusted_return_bps
                    .map_or(economic_return, |current| current.max(economic_return)),
            );
        }
    }

    let endpoint_return_bps = price_return_bps(
        decision.executable_entry_price_quote,
        endpoint.event.price_quote,
    );
    let endpoint_cost_adjusted_return_bps = match (
        decision.entry_total_quote,
        endpoint.executable_exit_net_quote,
    ) {
        (Some(entry_total), Some(exit_net)) => Some(economic_return_bps(entry_total, exit_net)),
        _ => None,
    };

    Ok(FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: FuturePathCompleteness::Complete,
        event_count,
        no_trade_events: false,
        endpoint_event_id: Some(endpoint.event.id.clone()),
        endpoint_observed_at_unix_ms: Some(endpoint.event.observed_at_unix_ms),
        endpoint_price_quote: Some(endpoint.event.price_quote),
        endpoint_return_bps: Some(endpoint_return_bps),
        mfe_bps: Some(max_return_bps),
        mae_bps: Some(min_return_bps),
        time_to_peak_ms: Some(peak_time_ms),
        time_to_trough_ms: Some(trough_time_ms),
        reversal_occurred: Some(reversal_occurred),
        first_reversal_after_ms,
        min_exit_capacity_base,
        endpoint_exit_capacity_base: endpoint.exit_capacity_base,
        route_unavailability_observed: any_route_evidence.then_some(route_unavailability_observed),
        best_cost_adjusted_return_bps,
        endpoint_cost_adjusted_return_bps,
    })
}

fn empty_label(
    horizon_ms: u64,
    completeness: FuturePathCompleteness,
    no_trade_events: bool,
) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness,
        event_count: 0,
        no_trade_events,
        endpoint_event_id: None,
        endpoint_observed_at_unix_ms: None,
        endpoint_price_quote: None,
        endpoint_return_bps: None,
        mfe_bps: None,
        mae_bps: None,
        time_to_peak_ms: None,
        time_to_trough_ms: None,
        reversal_occurred: None,
        first_reversal_after_ms: None,
        min_exit_capacity_base: None,
        endpoint_exit_capacity_base: None,
        route_unavailability_observed: None,
        best_cost_adjusted_return_bps: None,
        endpoint_cost_adjusted_return_bps: None,
    }
}

fn price_return_bps(entry_price: f64, exit_price: f64) -> f64 {
    (exit_price / entry_price - 1.0) * 10_000.0
}

fn economic_return_bps(entry_total_quote: f64, exit_net_quote: f64) -> f64 {
    (exit_net_quote / entry_total_quote - 1.0) * 10_000.0
}
