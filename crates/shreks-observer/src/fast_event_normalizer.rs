use std::{error::Error, fmt};

use shreks_core::ProviderId;
use shreks_providers::{
    pump::WRAPPED_SOL_MINT,
    pump_quote::{pump_quote_is_sol, SOL_QUOTE_DECIMALS},
    pump_swap_trade::{pump_swap_trade_evidence_to_fast_event, PumpSwapTradeEvidence},
    pump_trade::{pump_trade_evidence_to_fast_event, PumpTradeEvidence},
    ProviderError,
};
use shreks_storage::{
    PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb, StorageError,
};

const MAX_BLOCKED_FRONTIER_SCAN_MULTIPLIER: usize = 8;

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
                "FastEvent normalization rejected non-realtime Pump evidence provider {provider}"
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

enum PendingEvidence {
    Pump(PumpTradeEvidenceWrite),
    PumpSwap(PumpSwapTradeEvidenceWrite),
}

impl PendingEvidence {
    fn observed_at_unix_ms(&self) -> i64 {
        match self {
            Self::Pump(row) => row.observed_at_unix_ms,
            Self::PumpSwap(row) => row.observed_at_unix_ms,
        }
    }

    fn signature(&self) -> &str {
        match self {
            Self::Pump(row) => &row.signature,
            Self::PumpSwap(row) => &row.signature,
        }
    }

    fn ordinal(&self) -> u32 {
        match self {
            Self::Pump(row) => row.ordinal,
            Self::PumpSwap(row) => row.ordinal,
        }
    }

    fn source_rank(&self) -> u8 {
        match self {
            Self::Pump(_) => 0,
            Self::PumpSwap(_) => 1,
        }
    }
}

pub fn normalize_pending_pump_trade_evidence_at(
    db: &ShreksDb,
    limit: usize,
    accepted_at_unix_ms: i64,
) -> Result<FastEventNormalizationReport, FastEventNormalizationError> {
    if limit == 0 {
        return Ok(FastEventNormalizationReport::default());
    }

    let max_scan_limit = limit
        .saturating_mul(MAX_BLOCKED_FRONTIER_SCAN_MULTIPLIER)
        .max(limit);
    let mut scan_limit = limit;

    loop {
        let mut pending = db
            .pending_unambiguous_pump_trade_evidence(scan_limit)?
            .into_iter()
            .map(PendingEvidence::Pump)
            .chain(
                db.pending_unambiguous_pump_swap_trade_evidence(scan_limit)?
                    .into_iter()
                    .map(PendingEvidence::PumpSwap),
            )
            .collect::<Vec<_>>();

        pending.sort_by(|left, right| {
            left.observed_at_unix_ms()
                .cmp(&right.observed_at_unix_ms())
                .then_with(|| left.signature().cmp(right.signature()))
                .then_with(|| left.ordinal().cmp(&right.ordinal()))
                .then_with(|| left.source_rank().cmp(&right.source_rank()))
        });
        pending.truncate(scan_limit);

        let exhausted = pending.len() < scan_limit;
        let mut report = FastEventNormalizationReport {
            scanned: pending.len(),
            ..FastEventNormalizationReport::default()
        };

        for pending in pending {
            if report.normalized >= limit {
                break;
            }

            match pending {
                PendingEvidence::Pump(raw) => {
                    normalize_bonding_curve_row(db, raw, accepted_at_unix_ms, &mut report)?;
                }
                PendingEvidence::PumpSwap(raw) => {
                    normalize_pump_swap_row(db, raw, accepted_at_unix_ms, &mut report)?;
                }
            }
        }

        if report.normalized > 0 || exhausted {
            return Ok(report);
        }

        if scan_limit >= max_scan_limit {
            return normalize_ready_pump_fallback(db, limit, accepted_at_unix_ms, report);
        }

        let next_scan_limit = scan_limit.saturating_mul(2).min(max_scan_limit);
        if next_scan_limit == scan_limit {
            return Ok(report);
        }
        scan_limit = next_scan_limit;
    }
}

fn normalize_ready_pump_fallback(
    db: &ShreksDb,
    limit: usize,
    accepted_at_unix_ms: i64,
    mut report: FastEventNormalizationReport,
) -> Result<FastEventNormalizationReport, FastEventNormalizationError> {
    let ready = db.pending_normalizable_pump_trade_evidence(limit)?;
    report.scanned = report.scanned.saturating_add(ready.len());

    for raw in ready {
        if report.normalized >= limit {
            break;
        }
        normalize_bonding_curve_row(db, raw, accepted_at_unix_ms, &mut report)?;
    }

    Ok(report)
}

fn normalize_bonding_curve_row(
    db: &ShreksDb,
    raw: PumpTradeEvidenceWrite,
    accepted_at_unix_ms: i64,
    report: &mut FastEventNormalizationReport,
) -> Result<(), FastEventNormalizationError> {
    require_realtime_provider(raw.provider)?;

    let Some(base_decimals) = db.verified_mint_decimals(&raw.mint)? else {
        report.unresolved_decimals += 1;
        return Ok(());
    };
    let quote_decimals = if pump_quote_is_sol(&raw.quote_mint) {
        SOL_QUOTE_DECIMALS
    } else {
        let Some(decimals) = db.verified_mint_decimals(&raw.quote_mint)? else {
            report.unresolved_decimals += 1;
            return Ok(());
        };
        decimals
    };

    let sequence = db.next_fast_event_sequence()?;
    let evidence = as_provider_evidence(&raw);
    let mut event = pump_trade_evidence_to_fast_event(
        &evidence,
        &raw.signature,
        raw.ordinal,
        sequence,
        raw.slot,
        accepted_at_unix_ms,
        base_decimals,
        quote_decimals,
    )?;
    event.provider = raw.provider;

    if db.record_fast_event(
        &event,
        raw.observed_at_unix_ms,
        base_decimals,
        quote_decimals,
    )? {
        report.normalized += 1;
    }
    Ok(())
}

fn normalize_pump_swap_row(
    db: &ShreksDb,
    raw: PumpSwapTradeEvidenceWrite,
    accepted_at_unix_ms: i64,
    report: &mut FastEventNormalizationReport,
) -> Result<(), FastEventNormalizationError> {
    require_realtime_provider(raw.provider)?;

    let Some(market) = db.pump_swap_market_for_pool(&raw.pool)? else {
        // A direct PumpSwap trade may arrive before its verified migration has
        // been normalized. Keep the immutable raw row pending rather than
        // guessing mint identity or fetching a transaction on the hot path.
        return Ok(());
    };

    let Some(base_decimals) = db.verified_mint_decimals(&market.mint)? else {
        report.unresolved_decimals += 1;
        return Ok(());
    };

    let (quote_mint, quote_decimals) = if pump_quote_is_sol(&market.quote_mint) {
        (WRAPPED_SOL_MINT.to_owned(), SOL_QUOTE_DECIMALS)
    } else {
        let Some(decimals) = db.verified_mint_decimals(&market.quote_mint)? else {
            report.unresolved_decimals += 1;
            return Ok(());
        };
        (market.quote_mint.clone(), decimals)
    };

    let sequence = db.next_fast_event_sequence()?;
    let evidence = as_provider_pump_swap_evidence(&raw);
    let mut event = pump_swap_trade_evidence_to_fast_event(
        &evidence,
        &raw.signature,
        raw.ordinal,
        sequence,
        raw.slot,
        accepted_at_unix_ms,
        &market.mint,
        &quote_mint,
        base_decimals,
        quote_decimals,
    )?;
    event.provider = raw.provider;

    if db.record_fast_event(
        &event,
        raw.observed_at_unix_ms,
        base_decimals,
        quote_decimals,
    )? {
        report.normalized += 1;
    }
    Ok(())
}

fn require_realtime_provider(provider: ProviderId) -> Result<(), FastEventNormalizationError> {
    if !matches!(
        provider,
        ProviderId::Helius | ProviderId::Chainstack | ProviderId::Alchemy | ProviderId::SolanaPublic
    ) {
        return Err(FastEventNormalizationError::InvalidSourceProvider(provider));
    }
    Ok(())
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

fn as_provider_pump_swap_evidence(raw: &PumpSwapTradeEvidenceWrite) -> PumpSwapTradeEvidence {
    PumpSwapTradeEvidence {
        log_index: raw.log_index,
        pool: raw.pool.clone(),
        user: raw.user.clone(),
        is_buy: raw.is_buy,
        base_amount_raw: raw.base_amount_raw,
        quote_amount_raw: raw.quote_amount_raw,
        user_quote_amount_raw: raw.user_quote_amount_raw,
        timestamp_unix_seconds: raw.timestamp_unix_seconds,
        pool_base_reserves_raw: raw.pool_base_reserves_raw,
        pool_quote_reserves_raw: raw.pool_quote_reserves_raw,
    }
}
