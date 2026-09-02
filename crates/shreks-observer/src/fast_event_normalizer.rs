use std::{collections::HashMap, error::Error, fmt};

use shreks_core::ProviderId;
use shreks_providers::{
    pump::WRAPPED_SOL_MINT,
    pump_quote::{pump_quote_is_sol, SOL_QUOTE_DECIMALS},
    pump_swap_trade::{pump_swap_trade_evidence_to_fast_event, PumpSwapTradeEvidence},
    pump_trade::{pump_trade_evidence_to_fast_event, PumpTradeEvidence},
    ProviderError,
};
use shreks_storage::{
    PumpSwapMarket, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb, StorageError,
};

const MAX_BLOCKED_FRONTIER_SCAN_MULTIPLIER: usize = 8;
const MAX_FAST_EVENT_WRITE_TRANSACTION_ROWS: usize = 64;

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct FastEventNormalizationReport {
    pub scanned: usize,
    pub normalized: usize,
    pub unresolved_decimals: usize,
    pub invalid_economics: usize,
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
            Self::Storage(error) => {
                write!(formatter, "FastEvent normalization storage error: {error}")
            }
            Self::Provider(error) => {
                write!(formatter, "FastEvent normalization provider error: {error}")
            }
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

struct NormalizationChunkCache {
    next_sequence: u64,
    verified_decimals: HashMap<String, Option<u8>>,
    pump_swap_markets: HashMap<String, Option<PumpSwapMarket>>,
}

impl NormalizationChunkCache {
    fn new(db: &ShreksDb) -> Result<Self, FastEventNormalizationError> {
        Ok(Self {
            next_sequence: db.next_fast_event_sequence()?,
            verified_decimals: HashMap::new(),
            pump_swap_markets: HashMap::new(),
        })
    }

    fn verified_decimals(
        &mut self,
        db: &ShreksDb,
        mint: &str,
    ) -> Result<Option<u8>, FastEventNormalizationError> {
        if let Some(value) = self.verified_decimals.get(mint) {
            return Ok(*value);
        }
        let value = db.verified_mint_decimals(mint)?;
        self.verified_decimals.insert(mint.to_owned(), value);
        Ok(value)
    }

    fn pump_swap_market(
        &mut self,
        db: &ShreksDb,
        pool: &str,
    ) -> Result<Option<PumpSwapMarket>, FastEventNormalizationError> {
        if let Some(value) = self.pump_swap_markets.get(pool) {
            return Ok(value.clone());
        }
        let value = db.pump_swap_market_for_pool(pool)?;
        self.pump_swap_markets
            .insert(pool.to_owned(), value.clone());
        Ok(value)
    }

    fn sequence(&self) -> u64 {
        self.next_sequence
    }

    fn accepted_insert(&mut self) -> Result<(), FastEventNormalizationError> {
        self.next_sequence = self.next_sequence.checked_add(1).ok_or_else(|| {
            StorageError::InvalidData("FastEvent sequence exhausted u64 range".to_owned())
        })?;
        Ok(())
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

    // Small diagnostic/test batches keep the historical oldest-first contract.
    // Production-sized bursts reserve at most one quarter for deterministic
    // historical progress, but advance that debt lane through durable bounded
    // keyset pages instead of re-running absolute-oldest metadata/market scans.
    // Every unused debt slot is still returned to newest ready evidence.
    if limit < 4 {
        return normalize_oldest_capacity(db, limit, accepted_at_unix_ms);
    }

    let debt_target = (limit / 4).max(1);
    let mut report = normalize_paged_debt_capacity(db, debt_target, accepted_at_unix_ms)?;
    let fresh_capacity = limit.saturating_sub(report.normalized);

    if fresh_capacity > 0 {
        let fresh = recent_ready_rows(db, fresh_capacity, accepted_at_unix_ms)?;
        report.scanned = report.scanned.saturating_add(fresh.len());
        normalize_pending_rows(db, fresh, limit, accepted_at_unix_ms, &mut report)?;
    }

    Ok(report)
}

fn normalize_paged_debt_capacity(
    db: &ShreksDb,
    limit: usize,
    accepted_at_unix_ms: i64,
) -> Result<FastEventNormalizationReport, FastEventNormalizationError> {
    if limit == 0 {
        return Ok(FastEventNormalizationReport::default());
    }

    // Each venue gets at most one bounded keyset page of the full debt reserve.
    // We then choose the globally-oldest `limit` rows. This keeps total raw
    // inspection bounded at 2x the debt reserve while ensuring an empty or
    // sparse venue cannot waste the production 25% historical allocation.
    // Rows paged past but not selected remain authoritative pending evidence and
    // are revisited when that venue's durable cursor wraps.
    let mut pending = db
        .paged_normalizer_pump_debt_evidence(limit)?
        .into_iter()
        .map(PendingEvidence::Pump)
        .chain(
            db.paged_normalizer_pumpswap_debt_evidence(limit)?
                .into_iter()
                .map(PendingEvidence::PumpSwap),
        )
        .collect::<Vec<_>>();

    sort_pending(&mut pending);
    pending.dedup_by(|left, right| {
        left.source_rank() == right.source_rank()
            && left.signature() == right.signature()
            && left.ordinal() == right.ordinal()
    });
    pending.truncate(limit);

    let mut report = FastEventNormalizationReport {
        scanned: pending.len(),
        ..FastEventNormalizationReport::default()
    };
    normalize_pending_rows(db, pending, limit, accepted_at_unix_ms, &mut report)?;
    Ok(report)
}

fn normalize_oldest_capacity(
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

        sort_pending(&mut pending);
        pending.truncate(scan_limit);

        let exhausted = pending.len() < scan_limit;
        let mut report = FastEventNormalizationReport {
            scanned: pending.len(),
            ..FastEventNormalizationReport::default()
        };

        normalize_pending_rows(db, pending, limit, accepted_at_unix_ms, &mut report)?;

        if report.normalized >= limit || exhausted {
            return Ok(report);
        }

        if report.normalized > 0 {
            return normalize_ready_fallback(db, limit, accepted_at_unix_ms, report);
        }

        if scan_limit >= max_scan_limit {
            return normalize_ready_fallback(db, limit, accepted_at_unix_ms, report);
        }

        let next_scan_limit = scan_limit.saturating_mul(2).min(max_scan_limit);
        if next_scan_limit == scan_limit {
            return Ok(report);
        }
        scan_limit = next_scan_limit;
    }
}

fn normalize_ready_fallback(
    db: &ShreksDb,
    limit: usize,
    accepted_at_unix_ms: i64,
    mut report: FastEventNormalizationReport,
) -> Result<FastEventNormalizationReport, FastEventNormalizationError> {
    let remaining = limit.saturating_sub(report.normalized);
    if remaining == 0 {
        return Ok(report);
    }

    let mut ready = db
        .pending_normalizable_pump_trade_evidence(remaining)?
        .into_iter()
        .map(PendingEvidence::Pump)
        .chain(
            db.pending_normalizable_pump_swap_trade_evidence(remaining)?
                .into_iter()
                .map(PendingEvidence::PumpSwap),
        )
        .collect::<Vec<_>>();

    sort_pending(&mut ready);
    ready.truncate(remaining);
    report.scanned = report.scanned.saturating_add(ready.len());
    normalize_pending_rows(db, ready, limit, accepted_at_unix_ms, &mut report)?;

    Ok(report)
}

fn recent_ready_rows(
    db: &ShreksDb,
    limit: usize,
    accepted_at_unix_ms: i64,
) -> Result<Vec<PendingEvidence>, FastEventNormalizationError> {
    if limit == 0 {
        return Ok(Vec::new());
    }

    let mut ready = db
        .recent_normalizable_pump_trade_evidence(limit, accepted_at_unix_ms)?
        .into_iter()
        .map(PendingEvidence::Pump)
        .chain(
            db.recent_normalizable_pump_swap_trade_evidence(limit, accepted_at_unix_ms)?
                .into_iter()
                .map(PendingEvidence::PumpSwap),
        )
        .collect::<Vec<_>>();

    sort_pending_recent(&mut ready);
    ready.truncate(limit);
    Ok(ready)
}

fn sort_pending(pending: &mut [PendingEvidence]) {
    pending.sort_by(|left, right| {
        left.observed_at_unix_ms()
            .cmp(&right.observed_at_unix_ms())
            .then_with(|| left.signature().cmp(right.signature()))
            .then_with(|| left.ordinal().cmp(&right.ordinal()))
            .then_with(|| left.source_rank().cmp(&right.source_rank()))
    });
}

fn sort_pending_recent(pending: &mut [PendingEvidence]) {
    pending.sort_by(|left, right| {
        right
            .observed_at_unix_ms()
            .cmp(&left.observed_at_unix_ms())
            .then_with(|| right.signature().cmp(left.signature()))
            .then_with(|| right.ordinal().cmp(&left.ordinal()))
            .then_with(|| left.source_rank().cmp(&right.source_rank()))
    });
}

fn normalize_pending_rows(
    db: &ShreksDb,
    pending: Vec<PendingEvidence>,
    limit: usize,
    accepted_at_unix_ms: i64,
    report: &mut FastEventNormalizationReport,
) -> Result<(), FastEventNormalizationError> {
    let mut pending = pending.into_iter();

    while report.normalized < limit {
        let chunk = pending
            .by_ref()
            .take(MAX_FAST_EVENT_WRITE_TRANSACTION_ROWS)
            .collect::<Vec<_>>();
        if chunk.is_empty() {
            break;
        }

        db.with_fast_event_write_transaction(|| -> Result<(), FastEventNormalizationError> {
            // The cache lifetime is exactly one IMMEDIATE transaction. Reusing
            // sequence/metadata/source prerequisites therefore cannot mask a
            // concurrent writer: the snapshot is fixed until this chunk commits.
            let mut cache = NormalizationChunkCache::new(db)?;

            for pending in chunk {
                if report.normalized >= limit {
                    break;
                }

                // `accepted_at_unix_ms` is the canonical acceptance snapshot
                // for this normalization burst. Raw ingestion runs concurrently,
                // so a pending query can discover a row observed just after that
                // snapshot was taken. Leave it pending for the next burst rather
                // than weakening the storage ordering invariant.
                if pending.observed_at_unix_ms() > accepted_at_unix_ms {
                    continue;
                }

                match pending {
                    PendingEvidence::Pump(raw) => {
                        normalize_bonding_curve_row(
                            db,
                            raw,
                            accepted_at_unix_ms,
                            report,
                            &mut cache,
                        )?;
                    }
                    PendingEvidence::PumpSwap(raw) => {
                        normalize_pump_swap_row(db, raw, accepted_at_unix_ms, report, &mut cache)?;
                    }
                }
            }
            Ok(())
        })?;
    }
    Ok(())
}

fn normalize_bonding_curve_row(
    db: &ShreksDb,
    raw: PumpTradeEvidenceWrite,
    accepted_at_unix_ms: i64,
    report: &mut FastEventNormalizationReport,
    cache: &mut NormalizationChunkCache,
) -> Result<(), FastEventNormalizationError> {
    require_realtime_provider(raw.provider)?;

    // Direct program logs are immutable source evidence, not guaranteed
    // canonical economics. A successful on-chain transaction can still emit a
    // tradeEvent with zero executed base/quote quantity. Keep that raw row for
    // audit, but do not let one non-economic event terminate the mandatory
    // normalizer task or consume a canonical sequence number.
    if !pump_trade_has_positive_economics(&raw) {
        report.invalid_economics = report.invalid_economics.saturating_add(1);
        return Ok(());
    }

    let Some(base_decimals) = cache.verified_decimals(db, &raw.mint)? else {
        report.unresolved_decimals += 1;
        return Ok(());
    };
    let quote_decimals = if pump_quote_is_sol(&raw.quote_mint) {
        SOL_QUOTE_DECIMALS
    } else {
        let Some(decimals) = cache.verified_decimals(db, &raw.quote_mint)? else {
            report.unresolved_decimals += 1;
            return Ok(());
        };
        decimals
    };

    let evidence = as_provider_evidence(&raw);
    let mut event = pump_trade_evidence_to_fast_event(
        &evidence,
        &raw.signature,
        raw.ordinal,
        cache.sequence(),
        raw.slot,
        accepted_at_unix_ms,
        base_decimals,
        quote_decimals,
    )?;
    event.provider = raw.provider;

    if db.record_pump_fast_event_from_source(&event, &raw, base_decimals, quote_decimals)? {
        report.normalized += 1;
        cache.accepted_insert()?;
    }
    Ok(())
}

fn pump_trade_has_positive_economics(raw: &PumpTradeEvidenceWrite) -> bool {
    if raw.token_amount_raw == 0 {
        return false;
    }

    if pump_quote_is_sol(&raw.quote_mint) {
        raw.sol_amount_raw > 0
    } else {
        raw.quote_amount_raw > 0
    }
}

fn normalize_pump_swap_row(
    db: &ShreksDb,
    raw: PumpSwapTradeEvidenceWrite,
    accepted_at_unix_ms: i64,
    report: &mut FastEventNormalizationReport,
    cache: &mut NormalizationChunkCache,
) -> Result<(), FastEventNormalizationError> {
    require_realtime_provider(raw.provider)?;

    let Some(market) = cache.pump_swap_market(db, &raw.pool)? else {
        // A direct PumpSwap trade may arrive before its verified migration has
        // been normalized. Keep the immutable raw row pending rather than
        // guessing mint identity or fetching a transaction on the hot path.
        return Ok(());
    };

    let Some(base_decimals) = cache.verified_decimals(db, &market.mint)? else {
        report.unresolved_decimals += 1;
        return Ok(());
    };

    let (quote_mint, quote_decimals) = if pump_quote_is_sol(&market.quote_mint) {
        (WRAPPED_SOL_MINT.to_owned(), SOL_QUOTE_DECIMALS)
    } else {
        let Some(decimals) = cache.verified_decimals(db, &market.quote_mint)? else {
            report.unresolved_decimals += 1;
            return Ok(());
        };
        (market.quote_mint.clone(), decimals)
    };

    let evidence = as_provider_pump_swap_evidence(&raw);
    let mut event = pump_swap_trade_evidence_to_fast_event(
        &evidence,
        &raw.signature,
        raw.ordinal,
        cache.sequence(),
        raw.slot,
        accepted_at_unix_ms,
        &market.mint,
        &quote_mint,
        base_decimals,
        quote_decimals,
    )?;
    event.provider = raw.provider;

    if db.record_pump_swap_fast_event_from_source(
        &event,
        &raw,
        &market,
        base_decimals,
        quote_decimals,
    )? {
        report.normalized += 1;
        cache.accepted_insert()?;
    }
    Ok(())
}

fn require_realtime_provider(provider: ProviderId) -> Result<(), FastEventNormalizationError> {
    if !matches!(
        provider,
        ProviderId::Helius
            | ProviderId::Chainstack
            | ProviderId::Alchemy
            | ProviderId::SolanaPublic
    ) {
        return Err(FastEventNormalizationError::InvalidSourceProvider(provider));
    }
    Ok(())
}

// FL1 canonical FastEvent reconstruction intentionally does not carry FL3 fee authority.
// The provider conversion functions consume only the FL1 amount/reserve fields below;
// these neutral placeholders are never an FL3 economics source. FL3 decisions must load
// exact fee evidence from the durable execution-economics sidecar tables instead.
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
        fee_recipient: String::new(),
        fee_basis_points: 0,
        fee_raw: 0,
        creator: String::new(),
        creator_fee_basis_points: 0,
        creator_fee_raw: 0,
        cashback_fee_basis_points: 0,
        cashback_raw: 0,
        buyback_fee_basis_points: 0,
        buyback_fee_raw: 0,
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
        lp_fee_basis_points: 0,
        lp_fee_raw: 0,
        protocol_fee_basis_points: 0,
        protocol_fee_raw: 0,
        quote_amount_with_or_without_lp_fee_raw: 0,
        current_economics: None,
    }
}
