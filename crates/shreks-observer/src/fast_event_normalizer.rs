use std::{error::Error, fmt};

use shreks_core::ProviderId;
use shreks_providers::{
    pump_quote::{pump_quote_is_sol, SOL_QUOTE_DECIMALS},
    pump_trade::{pump_trade_evidence_to_fast_event, PumpTradeEvidence},
    ProviderError,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct FastEventNormalizationReport {
    pub scanned: usize,
    pub normalized: usize,
    pub unresolved_decimals: usize,
}

#[derive(Debug)]
pub enum FastEventNormalizationError {
    Storage(StorageError),
    Provider(ProviderError),
    InvalidSourceProvider(ProviderId),
}

impl fmt::Display for FastEventNormalizationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Storage(error) => write!(formatter, "FastEvent normalization storage error: {error}"),
            Self::Provider(error) => write!(formatter, "FastEvent normalization provider error: {error}"),
            Self::InvalidSourceProvider(provider) => write!(
                formatter,
                "FastEvent normalization rejected non-Helius Pump evidence provider {provider}"
            ),
        }
    }
}

impl Error for FastEventNormalizationError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Storage(error) => Some(error),
            Self::Provider(error) => Some(error),
            Self::InvalidSourceProvider(_) => None,
        }
    }
}

impl From<StorageError> for FastEventNormalizationError {
    fn from(error: StorageError) -> Self {
        Self::Storage(error)
    }
}

impl From<ProviderError> for FastEventNormalizationError {
    fn from(error: ProviderError) -> Self {
        Self::Provider(error)
    }
}

pub fn normalize_pending_pump_trade_evidence_at(
    db: &ShreksDb,
    limit: usize,
    accepted_at_unix_ms: i64,
) -> Result<FastEventNormalizationReport, FastEventNormalizationError> {
    let pending = db.pending_pump_trade_evidence(limit)?;
    let mut report = FastEventNormalizationReport {
        scanned: pending.len(),
        ..FastEventNormalizationReport::default()
    };

    for raw in pending {
        if raw.provider != ProviderId::Helius {
            return Err(FastEventNormalizationError::InvalidSourceProvider(
                raw.provider,
            ));
        }

        let Some(base_decimals) = db.verified_mint_decimals(&raw.mint)? else {
            report.unresolved_decimals += 1;
            continue;
        };
        let quote_decimals = if pump_quote_is_sol(&raw.quote_mint) {
            SOL_QUOTE_DECIMALS
        } else {
            let Some(decimals) = db.verified_mint_decimals(&raw.quote_mint)? else {
                report.unresolved_decimals += 1;
                continue;
            };
            decimals
        };

        let sequence = db.next_fast_event_sequence()?;
        let evidence = as_provider_evidence(&raw);
        let event = pump_trade_evidence_to_fast_event(
            &evidence,
            &raw.signature,
            raw.ordinal,
            sequence,
            raw.slot,
            accepted_at_unix_ms,
            base_decimals,
            quote_decimals,
        )?;

        if db.record_fast_event(
            &event,
            raw.observed_at_unix_ms,
            base_decimals,
            quote_decimals,
        )? {
            report.normalized += 1;
        }
    }

    Ok(report)
}

fn as_provider_evidence(raw: &PumpTradeEvidenceWrite) -> PumpTradeEvidence {
    PumpTradeEvidence {
        mint: raw.mint.clone(),
        quote_mint: raw.quote_mint.clone(),
        user: raw.user.clone(),
        is_buy: raw.is_buy,
        token_amount_raw: raw.token_amount_raw,
        sol_amount_raw: raw.sol_amount_raw,
        quote_amount_raw: raw.quote_amount_raw,
        timestamp_unix_seconds: raw.timestamp_unix_seconds,
        virtual_sol_reserves_raw: raw.virtual_sol_reserves_raw,
        virtual_token_reserves_raw: raw.virtual_token_reserves_raw,
        real_sol_reserves_raw: raw.real_sol_reserves_raw,
        real_token_reserves_raw: raw.real_token_reserves_raw,
        virtual_quote_reserves_raw: raw.virtual_quote_reserves_raw,
        real_quote_reserves_raw: raw.real_quote_reserves_raw,
        ix_name: raw.ix_name.clone(),
    }
}
