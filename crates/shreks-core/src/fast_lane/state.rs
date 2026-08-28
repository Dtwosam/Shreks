use std::{collections::VecDeque, error::Error, fmt};

use super::{FastEvent, FastEventKind, FastMarketKey};

pub const DEFAULT_FAST_WINDOWS_MS: [u64; 7] = [100, 250, 500, 1_000, 2_000, 5_000, 10_000];

#[derive(Debug, Clone, PartialEq)]
pub struct FastWindowSummary {
    pub window_ms: u64,
    pub buy_count: u64,
    pub sell_count: u64,
    pub buy_base_quantity: f64,
    pub sell_base_quantity: f64,
    pub buy_quote_quantity: f64,
    pub sell_quote_quantity: f64,
    pub net_quote_quantity: f64,
}

impl FastWindowSummary {
    fn empty(window_ms: u64) -> Self {
        Self {
            window_ms,
            buy_count: 0,
            sell_count: 0,
            buy_base_quantity: 0.0,
            sell_base_quantity: 0.0,
            buy_quote_quantity: 0.0,
            sell_quote_quantity: 0.0,
            net_quote_quantity: 0.0,
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
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastMarketSnapshot {
    pub market: FastMarketKey,
    pub as_of_unix_ms: i64,
    pub last_sequence: Option<u64>,
    pub last_price_quote: Option<f64>,
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
            let mut summary = FastWindowSummary::empty(*window_ms);
            for event in &self.events {
                if event.observed_at_unix_ms >= cutoff
                    && event.observed_at_unix_ms <= as_of_unix_ms
                {
                    summary.apply(event);
                }
            }
            windows.push(summary);
        }

        Ok(FastMarketSnapshot {
            market: self.market.clone(),
            as_of_unix_ms,
            last_sequence: self.last_sequence,
            last_price_quote: self.last_price_quote,
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
