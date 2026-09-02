use std::{error::Error, fmt};

use crate::{ProviderId, VenueId};

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct FastMarketKey {
    pub mint: String,
    pub quote_mint: String,
    pub venue: VenueId,
}

impl FastMarketKey {
    pub fn new(
        mint: impl Into<String>,
        quote_mint: impl Into<String>,
        venue: VenueId,
    ) -> Result<Self, FastEventError> {
        let mint = mint.into();
        let quote_mint = quote_mint.into();
        let mint = mint.trim();
        let quote_mint = quote_mint.trim();

        if mint.is_empty() {
            return Err(FastEventError::EmptyMint);
        }
        if quote_mint.is_empty() {
            return Err(FastEventError::EmptyQuoteMint);
        }

        Ok(Self {
            mint: mint.to_owned(),
            quote_mint: quote_mint.to_owned(),
            venue,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct FastEventId {
    pub signature: String,
    pub ordinal: u32,
}

impl FastEventId {
    pub fn new(
        signature: impl Into<String>,
        ordinal: u32,
    ) -> Result<Self, FastEventError> {
        let signature = signature.into();
        let signature = signature.trim();
        if signature.is_empty() {
            return Err(FastEventError::EmptySignature);
        }
        Ok(Self {
            signature: signature.to_owned(),
            ordinal,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FastEventKind {
    Buy,
    Sell,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum FastReserveContext {
    PumpCurve {
        virtual_base_reserve_raw: u64,
        virtual_quote_reserve_raw: u64,
        real_base_reserve_raw: u64,
        real_quote_reserve_raw: u64,
        base_decimals: u8,
        quote_decimals: u8,
    },
    PumpSwapPool {
        pool_base_reserve_raw: u64,
        pool_quote_reserve_raw: u64,
        virtual_quote_reserve_raw: Option<i128>,
        base_decimals: u8,
        quote_decimals: u8,
    },
}

impl FastReserveContext {
    fn matches_venue(&self, venue: &VenueId) -> bool {
        matches!(
            (self, venue),
            (
                Self::PumpCurve { .. },
                VenueId::PumpFunBondingCurve
            ) | (Self::PumpSwapPool { .. }, VenueId::PumpSwap)
        )
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastEvent {
    pub id: FastEventId,
    pub sequence: u64,
    pub provider: ProviderId,
    pub market: FastMarketKey,
    pub kind: FastEventKind,
    pub actor: Option<String>,
    pub slot: u64,
    pub occurred_at_unix_ms: i64,
    pub observed_at_unix_ms: i64,
    pub base_quantity: f64,
    pub quote_quantity: f64,
    pub price_quote: f64,
    pub reserve_context: Option<FastReserveContext>,
}

impl FastEvent {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        id: FastEventId,
        sequence: u64,
        provider: ProviderId,
        market: FastMarketKey,
        kind: FastEventKind,
        actor: Option<String>,
        slot: u64,
        occurred_at_unix_ms: i64,
        observed_at_unix_ms: i64,
        base_quantity: f64,
        quote_quantity: f64,
        price_quote: f64,
    ) -> Result<Self, FastEventError> {
        if occurred_at_unix_ms < 0 {
            return Err(FastEventError::NegativeOccurredAt(occurred_at_unix_ms));
        }
        if observed_at_unix_ms < 0 {
            return Err(FastEventError::NegativeObservedAt(observed_at_unix_ms));
        }
        if observed_at_unix_ms < occurred_at_unix_ms {
            return Err(FastEventError::ObservedBeforeOccurred {
                occurred: occurred_at_unix_ms,
                observed: observed_at_unix_ms,
            });
        }
        if !base_quantity.is_finite() || base_quantity <= 0.0 {
            return Err(FastEventError::InvalidBaseQuantity);
        }
        if !quote_quantity.is_finite() || quote_quantity <= 0.0 {
            return Err(FastEventError::InvalidQuoteQuantity);
        }
        if !price_quote.is_finite() || price_quote <= 0.0 {
            return Err(FastEventError::InvalidPriceQuote);
        }

        let actor = match actor {
            Some(actor) => {
                let actor = actor.trim();
                if actor.is_empty() {
                    return Err(FastEventError::EmptyActor);
                }
                Some(actor.to_owned())
            }
            None => None,
        };

        Ok(Self {
            id,
            sequence,
            provider,
            market,
            kind,
            actor,
            slot,
            occurred_at_unix_ms,
            observed_at_unix_ms,
            base_quantity,
            quote_quantity,
            price_quote,
            reserve_context: None,
        })
    }

    pub fn with_reserve_context(
        mut self,
        reserve_context: FastReserveContext,
    ) -> Result<Self, FastEventError> {
        if !reserve_context.matches_venue(&self.market.venue) {
            return Err(FastEventError::ReserveContextVenueMismatch);
        }
        self.reserve_context = Some(reserve_context);
        Ok(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastEventError {
    EmptyMint,
    EmptyQuoteMint,
    EmptySignature,
    EmptyActor,
    NegativeOccurredAt(i64),
    NegativeObservedAt(i64),
    ObservedBeforeOccurred { occurred: i64, observed: i64 },
    InvalidBaseQuantity,
    InvalidQuoteQuantity,
    InvalidPriceQuote,
    ReserveContextVenueMismatch,
}

impl fmt::Display for FastEventError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyMint => formatter.write_str("fast-lane mint must not be empty"),
            Self::EmptyQuoteMint => formatter.write_str("fast-lane quote mint must not be empty"),
            Self::EmptySignature => formatter.write_str("fast-lane signature must not be empty"),
            Self::EmptyActor => formatter.write_str("fast-lane actor must not be empty when present"),
            Self::NegativeOccurredAt(value) => write!(
                formatter,
                "fast-lane occurrence timestamp must be non-negative; got {value}"
            ),
            Self::NegativeObservedAt(value) => write!(
                formatter,
                "fast-lane observation timestamp must be non-negative; got {value}"
            ),
            Self::ObservedBeforeOccurred { occurred, observed } => write!(
                formatter,
                "fast-lane observation timestamp {observed} precedes occurrence timestamp {occurred}"
            ),
            Self::InvalidBaseQuantity => {
                formatter.write_str("fast-lane base quantity must be positive and finite")
            }
            Self::InvalidQuoteQuantity => {
                formatter.write_str("fast-lane quote quantity must be positive and finite")
            }
            Self::InvalidPriceQuote => {
                formatter.write_str("fast-lane quote price must be positive and finite")
            }
            Self::ReserveContextVenueMismatch => formatter.write_str(
                "fast-lane reserve context does not match the event market venue",
            ),
        }
    }
}

impl Error for FastEventError {}
