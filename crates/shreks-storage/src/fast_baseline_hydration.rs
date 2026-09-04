use shreks_core::{
    FastMarketKey, FastMarketSnapshot, FastReserveContext, FastWindowSummary, LifecycleEventKind,
    ProviderId, TokenLifecycleEvent, VenueId,
};

use crate::{
    training_features::{
        parse_training_venue, validate_record, FastTrainingFeatureRecord,
        FastTrainingLifecycleEvent, FastTrainingReserveContext, FastTrainingWindowSummary,
    },
    StorageError,
};

pub const FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq)]
pub struct FastBaselineSnapshotHydration {
    pub version: u16,
    pub source_event_id: String,
    pub market_key: String,
    pub source_sequence: u64,
    pub as_of_unix_ms: i64,
    pub decision_executable_entry_price_quote: f64,
    pub decision_entry_total_quote: Option<f64>,
    pub snapshot: FastMarketSnapshot,
}

pub fn hydrate_fast_baseline_snapshot(
    record: &FastTrainingFeatureRecord,
) -> Result<FastBaselineSnapshotHydration, StorageError> {
    validate_record(record)?;

    let venue = parse_training_venue(&record.venue)?;
    let market = FastMarketKey::new(record.mint.clone(), record.quote_mint.clone(), venue)
        .map_err(|error| {
            StorageError::InvalidData(format!(
                "invalid FL9 baseline hydration market identity: {error}"
            ))
        })?;

    let last_reserve_context = record
        .last_reserve_context
        .as_ref()
        .map(|value| hydrate_reserve_context(value, venue))
        .transpose()?;
    let last_lifecycle_event = record
        .last_lifecycle_event
        .as_ref()
        .map(|value| hydrate_lifecycle_event(value, &market, record.decision_observed_at_unix_ms))
        .transpose()?;

    let windows = record
        .windows
        .iter()
        .map(hydrate_window)
        .collect::<Vec<_>>();

    let snapshot = FastMarketSnapshot {
        market,
        as_of_unix_ms: record.snapshot_as_of_unix_ms,
        last_sequence: record.snapshot_last_sequence,
        last_price_quote: record.snapshot_last_price_quote,
        last_reserve_context,
        last_lifecycle_event,
        windows,
    };

    Ok(FastBaselineSnapshotHydration {
        version: FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
        source_event_id: format!(
            "{}:{}",
            record.decision_signature, record.decision_ordinal
        ),
        market_key: format!("{}:{}:{}", record.venue, record.mint, record.quote_mint),
        source_sequence: record.decision_sequence,
        as_of_unix_ms: record.decision_observed_at_unix_ms,
        decision_executable_entry_price_quote: record.decision_executable_entry_price_quote,
        decision_entry_total_quote: record.decision_entry_total_quote,
        snapshot,
    })
}

pub(crate) fn hydrate_window(value: &FastTrainingWindowSummary) -> FastWindowSummary {
    FastWindowSummary {
        window_ms: value.window_ms,
        buy_count: value.buy_count,
        sell_count: value.sell_count,
        unique_buy_actors: value.unique_buy_actors,
        unique_sell_actors: value.unique_sell_actors,
        buy_arrival_rate_per_second: value.buy_arrival_rate_per_second,
        sell_arrival_rate_per_second: value.sell_arrival_rate_per_second,
        count_imbalance: value.count_imbalance,
        buy_base_quantity: value.buy_base_quantity,
        sell_base_quantity: value.sell_base_quantity,
        buy_quote_quantity: value.buy_quote_quantity,
        sell_quote_quantity: value.sell_quote_quantity,
        net_quote_quantity: value.net_quote_quantity,
        quote_flow_imbalance: value.quote_flow_imbalance,
        quote_flow_velocity_per_second: value.quote_flow_velocity_per_second,
        quote_flow_acceleration_per_second2: value.quote_flow_acceleration_per_second2,
        local_high_price_quote: value.local_high_price_quote,
        local_high_sequence: value.local_high_sequence,
        local_high_observed_at_unix_ms: value.local_high_observed_at_unix_ms,
        local_low_price_quote: value.local_low_price_quote,
        local_low_sequence: value.local_low_sequence,
        local_low_observed_at_unix_ms: value.local_low_observed_at_unix_ms,
        post_high_low_price_quote: value.post_high_low_price_quote,
        post_high_low_sequence: value.post_high_low_sequence,
        post_high_low_observed_at_unix_ms: value.post_high_low_observed_at_unix_ms,
        last_price_quote: value.last_price_quote,
        drawdown_from_local_high: value.drawdown_from_local_high,
        recovery_from_local_low: value.recovery_from_local_low,
    }
}

pub(crate) fn hydrate_reserve_context(
    value: &FastTrainingReserveContext,
    venue: VenueId,
) -> Result<FastReserveContext, StorageError> {
    match (value, venue) {
        (
            FastTrainingReserveContext::PumpCurve {
                virtual_base_reserve_raw,
                virtual_quote_reserve_raw,
                real_base_reserve_raw,
                real_quote_reserve_raw,
                base_decimals,
                quote_decimals,
            },
            VenueId::PumpFunBondingCurve,
        ) => Ok(FastReserveContext::PumpCurve {
            virtual_base_reserve_raw: *virtual_base_reserve_raw,
            virtual_quote_reserve_raw: *virtual_quote_reserve_raw,
            real_base_reserve_raw: *real_base_reserve_raw,
            real_quote_reserve_raw: *real_quote_reserve_raw,
            base_decimals: *base_decimals,
            quote_decimals: *quote_decimals,
        }),
        (
            FastTrainingReserveContext::PumpSwapPool {
                pool_base_reserve_raw,
                pool_quote_reserve_raw,
                virtual_quote_reserve_raw,
                base_decimals,
                quote_decimals,
            },
            VenueId::PumpSwap,
        ) => Ok(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: *pool_base_reserve_raw,
            pool_quote_reserve_raw: *pool_quote_reserve_raw,
            virtual_quote_reserve_raw: *virtual_quote_reserve_raw,
            base_decimals: *base_decimals,
            quote_decimals: *quote_decimals,
        }),
        _ => Err(StorageError::InvalidData(
            "FL9 baseline hydration reserve context contradicts market venue".to_owned(),
        )),
    }
}

pub(crate) fn hydrate_lifecycle_event(
    value: &FastTrainingLifecycleEvent,
    market: &FastMarketKey,
    decision_at_unix_ms: i64,
) -> Result<TokenLifecycleEvent, StorageError> {
    if value.kind != "pump_graduation" {
        return Err(StorageError::InvalidData(format!(
            "unsupported FL9 baseline hydration lifecycle kind '{}'",
            value.kind
        )));
    }
    if value.mint != market.mint || value.quote_mint != market.quote_mint {
        return Err(StorageError::InvalidData(
            "FL9 baseline hydration lifecycle market identity does not match row market"
                .to_owned(),
        ));
    }
    for (field, item) in [
        ("mint", value.mint.as_str()),
        ("quote mint", value.quote_mint.as_str()),
        ("pool address", value.pool_address.as_str()),
        ("signature", value.signature.as_str()),
    ] {
        if item.trim().is_empty() {
            return Err(StorageError::InvalidData(format!(
                "FL9 baseline hydration lifecycle {field} must not be empty"
            )));
        }
    }

    let provider = parse_provider(&value.provider)?;
    let from_venue = parse_training_venue(&value.from_venue)?;
    let to_venue = parse_training_venue(&value.to_venue)?;
    if from_venue != VenueId::PumpFunBondingCurve || to_venue != VenueId::PumpSwap {
        return Err(StorageError::InvalidData(
            "FL9 baseline hydration lifecycle transition must be Pump.fun bonding curve -> PumpSwap"
                .to_owned(),
        ));
    }
    if market.venue != from_venue && market.venue != to_venue {
        return Err(StorageError::InvalidData(
            "FL9 baseline hydration lifecycle transition does not touch the row market venue"
                .to_owned(),
        ));
    }
    if value.detected_at_unix_ms < 0 || value.detected_at_unix_ms > decision_at_unix_ms {
        return Err(StorageError::InvalidData(
            "FL9 baseline hydration lifecycle detected clock is outside point-in-time evidence"
                .to_owned(),
        ));
    }
    if let Some(occurred_at_unix_ms) = value.occurred_at_unix_ms {
        if occurred_at_unix_ms < 0
            || occurred_at_unix_ms > value.detected_at_unix_ms
            || occurred_at_unix_ms > decision_at_unix_ms
        {
            return Err(StorageError::InvalidData(
                "FL9 baseline hydration lifecycle occurred clock is outside point-in-time evidence"
                    .to_owned(),
            ));
        }
    }

    Ok(TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider,
        mint: value.mint.clone(),
        quote_mint: value.quote_mint.clone(),
        from_venue,
        to_venue,
        pool_address: value.pool_address.clone(),
        signature: value.signature.clone(),
        slot: value.slot,
        detected_at_unix_ms: value.detected_at_unix_ms,
        occurred_at_unix_ms: value.occurred_at_unix_ms,
    })
}

pub(crate) fn parse_provider(value: &str) -> Result<ProviderId, StorageError> {
    match value {
        "dexscreener" => Ok(ProviderId::DexScreener),
        "helius" => Ok(ProviderId::Helius),
        "alchemy" => Ok(ProviderId::Alchemy),
        "chainstack" => Ok(ProviderId::Chainstack),
        "solana_public" => Ok(ProviderId::SolanaPublic),
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "unsupported FL9 baseline hydration lifecycle provider '{other}'"
        ))),
    }
}
