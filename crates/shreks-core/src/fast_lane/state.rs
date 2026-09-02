use std::{
    collections::{HashSet, VecDeque},
    error::Error,
    fmt,
};

use super::{FastEvent, FastEventKind, FastMarketKey, FastReserveContext};

pub const DEFAULT_FAST_WINDOWS_MS: [u64; 7] = [100, 250, 500, 1_000, 2_000, 5_000, 10_000];

#[derive(Debug, Clone, PartialEq)]
pub struct FastWindowSummary {
    pub window_ms: u64,
    pub buy_count: u64,
    pub sell_count: u64,
    pub unique_buy_actors: u64,
    pub unique_sell_actors: u64,
    pub buy_arrival_rate_per_second: f64,
    pub sell_arrival_rate_per_second: f64,
    pub count_imbalance: f64,
    pub buy_base_quantity: f64,
    pub sell_base_quantity: f64,
    pub buy_quote_quantity: f64,
    pub sell_quote_quantity: f64,
    pub net_quote_quantity: f64,
    pub quote_flow_imbalance: f64,
    pub quote_flow_velocity_per_second: f64,
    pub quote_flow_acceleration_per_second2: f64,
    pub local_high_price_quote: Option<f64>,
    pub local_low_price_quote: Option<f64>,
    pub last_price_quote: Option<f64>,
    pub drawdown_from_local_high: f64,
    pub recovery_from_local_low: f64,
}

impl FastWindowSummary {
    fn empty(window_ms: u64) -> Self {
        Self {
            window_ms,
            buy_count: 0,
            sell_count: 0,
            unique_buy_actors: 0,
            unique_sell_actors: 0,
            buy_arrival_rate_per_second: 0.0,
            sell_arrival_rate_per_second: 0.0,
            count_imbalance: 0.0,
            buy_base_quantity: 0.0,
            sell_base_quantity: 0.0,
            buy_quote_quantity: 0.0,
            sell_quote_quantity: 0.0,
            net_quote_quantity: 0.0,
            quote_flow_imbalance: 0.0,
            quote_flow_velocity_per_second: 0.0,
            quote_flow_acceleration_per_second2: 0.0,
            local_high_price_quote: None,
            local_low_price_quote: None,
            last_price_quote: None,
            drawdown_from_local_high: 0.0,
            recovery_from_local_low: 0.0,
        }
    }

    fn apply(&mut self, event: &FastEvent) {
        match event.kind {
            FastEventKind::Buy => {
                self.buy_count = self.buy_count.saturating_add(1);
                self.buy_base_quantity += event.base_quantity;
                self.buy_quote_quantity += event.quote_quantity;
            }
            FastEventKind::Sell => {
                self.sell_count = self.sell_count.saturating_add(1);
                self.sell_base_quantity += event.base_quantity;
                self.sell_quote_quantity += event.quote_quantity;
            }
        }
        self.net_quote_quantity = self.buy_quote_quantity - self.sell_quote_quantity;
        self.local_high_price_quote = Some(
            self.local_high_price_quote
                .map_or(event.price_quote, |high| high.max(event.price_quote)),
        );
        self.local_low_price_quote = Some(
            self.local_low_price_quote
                .map_or(event.price_quote, |low| low.min(event.price_quote)),
        );
        self.last_price_quote = Some(event.price_quote);
    }

    fn finish(
        &mut self,
        unique_buy_actors: usize,
        unique_sell_actors: usize,
        older_half_net_quote: f64,
        recent_half_net_quote: f64,
    ) {
        self.unique_buy_actors = unique_buy_actors as u64;
        self.unique_sell_actors = unique_sell_actors as u64;

        if self.window_ms > 0 {
            let window_seconds = self.window_ms as f64 / 1_000.0;
            self.buy_arrival_rate_per_second = self.buy_count as f64 / window_seconds;
            self.sell_arrival_rate_per_second = self.sell_count as f64 / window_seconds;
            self.quote_flow_velocity_per_second = self.net_quote_quantity / window_seconds;

            let half_window_seconds = window_seconds / 2.0;
            if half_window_seconds > 0.0 {
                let older_velocity = older_half_net_quote / half_window_seconds;
                let recent_velocity = recent_half_net_quote / half_window_seconds;
                self.quote_flow_acceleration_per_second2 =
                    (recent_velocity - older_velocity) / half_window_seconds;
            }
        }

        let total_count = self.buy_count.saturating_add(self.sell_count);
        if total_count > 0 {
            self.count_imbalance =
                (self.buy_count as f64 - self.sell_count as f64) / total_count as f64;
        }

        let total_quote = self.buy_quote_quantity + self.sell_quote_quantity;
        if total_quote > 0.0 {
            self.quote_flow_imbalance = self.net_quote_quantity / total_quote;
        }

        if let (Some(high), Some(low), Some(last)) = (
            self.local_high_price_quote,
            self.local_low_price_quote,
            self.last_price_quote,
        ) {
            self.drawdown_from_local_high = (high - last) / high;
            self.recovery_from_local_low = (last - low) / low;
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastMarketSnapshot {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub last_sequence: Option<u64>,
    pub last_price_quote: Option<f64>,
    pub last_reserve_context: Option<FastReserveContext>,
    pub windows: Vec<FastWindowSummary>,
}

impl FastMarketSnapshot {
    pub fn window(&self, window_ms: u64) -> Option<&FastWindowSummary> {
        self.windows.iter().find(|window| window.window_ms == window_ms)
    }
}

#[derive(Debug, Clone)]
pub struct FastMarketState {
    market: FastMarketKey,
    windows_ms: Vec<u64>,
    events: VecDeque<FastEvent>,
    last_sequence: Option<u64>,
    last_observed_at_unix_ms: Option<i64>,
    last_price_quote: Option<f64>,
    last_reserve_context: Option<FastReserveContext>,
}

impl FastMarketState {
    pub fn with_default_windows(market: FastMarketKey) -> Self {
        Self {
            market,
            windows_ms: DEFAULT_FAST_WINDOWS_MS.to_vec(),
            events: VecDeque::new(),
            last_sequence: None,
            last_observed_at_unix_ms: None,
            last_price_quote: None,
            last_reserve_context: None,
        }
    }

    pub fn apply(&mut self, event: FastEvent) -> Result<(), FastStateError> {
        if event.market != self.market {
            return Err(FastStateError::MarketMismatch);
        }
        if let Some(last) = self.last_sequence {
            if event.sequence <= last {
                return Err(FastStateError::NonMonotonicSequence {
                    last,
                    incoming: event.sequence,
                });
            }
        }
        if let Some(last) = self.last_observed_at_unix_ms {
            if event.observed_at_unix_ms < last {
                return Err(FastStateError::ObservationTimeMovedBackward {
                    last,
                    incoming: event.observed_at_unix_ms,
                });
            }
        }

        let observed_at_unix_ms = event.observed_at_unix_ms;
        self.last_sequence = Some(event.sequence);
        self.last_observed_at_unix_ms = Some(observed_at_unix_ms);
        self.last_price_quote = Some(event.price_quote);
        self.last_reserve_context = event.reserve_context.clone();
        self.events.push_back(event);

        let max_window_ms = self.windows_ms.iter().copied().max().unwrap_or(0) as i64;
        let cutoff = observed_at_unix_ms.saturating_sub(max_window_ms);
        while self
            .events
            .front()
            .is_some_and(|front| front.observed_at_unix_ms < cutoff)
        {
            self.events.pop_front();
        }

        Ok(())
    }

    pub fn snapshot(&self, as_of_unix_ms: i64) -> Result<FastMarketSnapshot, FastStateError> {
        if as_of_unix_ms < 0 {
            return Err(FastStateError::NegativeAsOf(as_of_unix_ms));
        }
        if let Some(last_observed_at_unix_ms) = self.last_observed_at_unix_ms {
            if as_of_unix_ms < last_observed_at_unix_ms {
                return Err(FastStateError::SnapshotBeforeLastObservation {
                    last_observed_at_unix_ms,
                    as_of_unix_ms,
                });
            }
        }

        let mut windows = Vec::with_capacity(self.windows_ms.len());
        for window_ms in &self.windows_ms {
            let cutoff = as_of_unix_ms.saturating_sub(*window_ms as i64);
            let midpoint = cutoff.saturating_add((*window_ms / 2) as i64);
            let mut summary = FastWindowSummary::empty(*window_ms);
            let mut unique_buy_actors = HashSet::new();
            let mut unique_sell_actors = HashSet::new();
            let mut older_half_net_quote = 0.0;
            let mut recent_half_net_quote = 0.0;

            for event in &self.events {
                if event.observed_at_unix_ms < cutoff
                    || event.observed_at_unix_ms > as_of_unix_ms
                {
                    continue;
                }

                summary.apply(event);

                if let Some(actor) = event.actor.as_deref() {
                    match event.kind {
                        FastEventKind::Buy => {
                            unique_buy_actors.insert(actor);
                        }
                        FastEventKind::Sell => {
                            unique_sell_actors.insert(actor);
                        }
                    }
                }

                let signed_quote = match event.kind {
                    FastEventKind::Buy => event.quote_quantity,
                    FastEventKind::Sell => -event.quote_quantity,
                };
                if event.observed_at_unix_ms < midpoint {
                    older_half_net_quote += signed_quote;
                } else {
                    recent_half_net_quote += signed_quote;
                }
            }

            summary.finish(
                unique_buy_actors.len(),
                unique_sell_actors.len(),
                older_half_net_quote,
                recent_half_net_quote,
            );
            windows.push(summary);
        }

        Ok(FastMarketSnapshot {
            market: self.market.clone(),
            as_of_unix_ms,
            last_sequence: self.last_sequence,
            last_price_quote: self.last_price_quote,
            last_reserve_context: self.last_reserve_context.clone(),
            windows,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastStateError {
    MarketMismatch,
    NonMonotonicSequence { last: u64, incoming: u64 },
    ObservationTimeMovedBackward { last: i64, incoming: i64 },
    NegativeAsOf(i64),
    SnapshotBeforeLastObservation {
        last_observed_at_unix_ms: i64,
        as_of_unix_ms: i64,
    },
}

impl fmt::Display for FastStateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MarketMismatch => {
                formatter.write_str("fast-lane event market does not match state market")
            }
            Self::NonMonotonicSequence { last, incoming } => write!(
                formatter,
                "fast-lane event sequence must strictly increase; last {last}, incoming {incoming}"
            ),
            Self::ObservationTimeMovedBackward { last, incoming } => write!(
                formatter,
                "fast-lane event observation time moved backward; last {last}, incoming {incoming}"
            ),
            Self::NegativeAsOf(value) => write!(
                formatter,
                "fast-lane snapshot timestamp must be non-negative; got {value}"
            ),
            Self::SnapshotBeforeLastObservation {
                last_observed_at_unix_ms,
                as_of_unix_ms,
            } => write!(
                formatter,
                "fast-lane snapshot timestamp {as_of_unix_ms} precedes latest observation {last_observed_at_unix_ms}"
            ),
        }
    }
}

impl Error for FastStateError {}
