use std::{
    collections::{BTreeMap, HashMap},
    fs::{self, OpenOptions},
    io::{BufWriter, Write},
    path::Path,
};

use serde::Serialize;
use sha2::{Digest, Sha256};
use shreks_core::{
    FastEvent, FastEventKind, FastMarketKey, FastMarketSnapshot, FastMarketState,
    FastReserveContext, FastWindowSummary, LifecycleEventKind, TokenLifecycleEvent, VenueId,
    DEFAULT_FAST_WINDOWS_MS,
};

use crate::{ShreksDb, StorageError, StoredFastEvent};

pub const FAST_TRAINING_FEATURE_SCHEMA_NAME: &str = "shreks.fast_lane_training_features";
pub const FAST_TRAINING_FEATURE_SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FastTrainingFeatureExportManifest {
    pub row_count: u64,
    pub min_decision_sequence: u64,
    pub max_decision_sequence: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum FastTrainingReserveContext {
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

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FastTrainingLifecycleEvent {
    pub kind: String,
    pub provider: String,
    pub mint: String,
    pub quote_mint: String,
    pub from_venue: String,
    pub to_venue: String,
    pub pool_address: String,
    pub signature: String,
    pub slot: u64,
    pub detected_at_unix_ms: i64,
    pub occurred_at_unix_ms: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FastTrainingWindowSummary {
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
    pub local_high_sequence: Option<u64>,
    pub local_high_observed_at_unix_ms: Option<i64>,
    pub local_low_price_quote: Option<f64>,
    pub local_low_sequence: Option<u64>,
    pub local_low_observed_at_unix_ms: Option<i64>,
    pub post_high_low_price_quote: Option<f64>,
    pub post_high_low_sequence: Option<u64>,
    pub post_high_low_observed_at_unix_ms: Option<i64>,
    pub last_price_quote: Option<f64>,
    pub drawdown_from_local_high: f64,
    pub recovery_from_local_low: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FastTrainingFeatureRecord {
    pub schema_name: &'static str,
    pub schema_version: u16,
    pub decision_signature: String,
    pub decision_ordinal: u32,
    pub decision_sequence: u64,
    pub mint: String,
    pub quote_mint: String,
    pub venue: String,
    pub decision_observed_at_unix_ms: i64,
    pub decision_provider: String,
    pub decision_source_observed_at_unix_ms: i64,
    pub decision_occurred_at_unix_ms: i64,
    pub decision_slot: u64,
    pub decision_event_kind: String,
    pub decision_actor: Option<String>,
    pub decision_executable_entry_price_quote: f64,
    pub decision_entry_total_quote: Option<f64>,
    pub snapshot_as_of_unix_ms: i64,
    pub snapshot_last_sequence: Option<u64>,
    pub snapshot_last_price_quote: Option<f64>,
    pub last_reserve_context: Option<FastTrainingReserveContext>,
    pub last_lifecycle_event: Option<FastTrainingLifecycleEvent>,
    pub windows: Vec<FastTrainingWindowSummary>,
}

#[derive(Debug, Clone)]
struct DecisionRow {
    signature: String,
    ordinal: u32,
    sequence: u64,
    market: FastMarketKey,
    observed_at_unix_ms: i64,
    entry_price_quote: f64,
    entry_total_quote: Option<f64>,
}

impl ShreksDb {
    /// Return one point-in-time Fast Lane feature row per unique FL4 decision.
    ///
    /// All window calculations are delegated to the sealed `FastMarketState`
    /// implementation. This exporter only selects canonical decisions, replays
    /// trusted source-backed events, and serializes the resulting snapshots.
    pub fn fast_training_feature_records(
        &self,
        label_version: u16,
    ) -> Result<Vec<FastTrainingFeatureRecord>, StorageError> {
        if label_version == 0 {
            return Err(StorageError::InvalidData(
                "training feature label_version must be positive".to_owned(),
            ));
        }

        let decisions = self.training_decisions(label_version)?;
        if decisions.is_empty() {
            return Ok(Vec::new());
        }

        let mut by_market: HashMap<FastMarketKey, Vec<DecisionRow>> = HashMap::new();
        for decision in decisions {
            by_market
                .entry(decision.market.clone())
                .or_default()
                .push(decision);
        }

        let mut records = Vec::new();
        for (market, mut market_decisions) in by_market {
            market_decisions.sort_by(|left, right| {
                (left.sequence, left.signature.as_str(), left.ordinal).cmp(&(
                    right.sequence,
                    right.signature.as_str(),
                    right.ordinal,
                ))
            });

            let events = self.fast_events_for_market_with_reserve_context(
                &market.mint,
                &market.quote_mint,
                market.venue,
            )?;
            let lifecycle_events = self.lifecycle_events_for_mint(&market.mint)?;
            let mut state = FastMarketState::with_default_windows(market.clone());
            let mut lifecycle_index = 0_usize;
            let mut decision_index = 0_usize;

            for stored in events {
                while lifecycle_index < lifecycle_events.len()
                    && lifecycle_events[lifecycle_index].detected_at_unix_ms
                        <= stored.event.observed_at_unix_ms
                {
                    let lifecycle = &lifecycle_events[lifecycle_index];
                    if lifecycle_matches_market(lifecycle, &market) {
                        state.apply_lifecycle(lifecycle.clone()).map_err(|error| {
                            StorageError::InvalidData(format!(
                                "training lifecycle replay failed: {error}"
                            ))
                        })?;
                    }
                    lifecycle_index += 1;
                }

                state.apply(stored.event.clone()).map_err(|error| {
                    StorageError::InvalidData(format!("training event replay failed: {error}"))
                })?;

                while decision_index < market_decisions.len()
                    && market_decisions[decision_index].sequence == stored.event.sequence
                {
                    let decision = &market_decisions[decision_index];
                    validate_decision_event(decision, &stored.event)?;
                    let snapshot = state
                        .snapshot(decision.observed_at_unix_ms)
                        .map_err(|error| {
                            StorageError::InvalidData(format!(
                                "training decision snapshot failed: {error}"
                            ))
                        })?;
                    records.push(record_from_snapshot(decision, &stored, &snapshot)?);
                    decision_index += 1;
                }
            }

            if decision_index != market_decisions.len() {
                let missing = &market_decisions[decision_index];
                return Err(StorageError::InvalidData(format!(
                    "training decision '{}' ordinal {} sequence {} was not found in canonical market replay",
                    missing.signature, missing.ordinal, missing.sequence
                )));
            }
        }

        records.sort_by(|left, right| {
            (
                left.decision_sequence,
                left.decision_signature.as_str(),
                left.decision_ordinal,
            )
                .cmp(&(
                    right.decision_sequence,
                    right.decision_signature.as_str(),
                    right.decision_ordinal,
                ))
        });
        Ok(records)
    }

    /// Write deterministic canonical JSONL to a newly-created path only.
    pub fn write_fast_training_feature_jsonl<P: AsRef<Path>>(
        &self,
        label_version: u16,
        output: P,
    ) -> Result<FastTrainingFeatureExportManifest, StorageError> {
        let rows = self.fast_training_feature_records(label_version)?;
        if rows.is_empty() {
            return Err(StorageError::InvalidData(
                "training feature export requires at least one FL4 decision".to_owned(),
            ));
        }

        let path = output.as_ref();
        if let Some(parent) = path.parent().filter(|value| !value.as_os_str().is_empty()) {
            fs::create_dir_all(parent)?;
        }
        let file = OpenOptions::new().write(true).create_new(true).open(path)?;
        let mut writer = BufWriter::new(file);
        let mut hasher = Sha256::new();

        for row in &rows {
            validate_record(row)?;
            let encoded = serde_json::to_vec(row).map_err(|error| {
                StorageError::InvalidData(format!(
                    "training feature row could not be serialized: {error}"
                ))
            })?;
            writer.write_all(&encoded)?;
            writer.write_all(b"\n")?;
            hasher.update(&encoded);
            hasher.update(b"\n");
        }
        writer.flush()?;

        Ok(FastTrainingFeatureExportManifest {
            row_count: u64::try_from(rows.len()).map_err(|_| {
                StorageError::InvalidData("training feature row count exceeds u64".to_owned())
            })?,
            min_decision_sequence: rows[0].decision_sequence,
            max_decision_sequence: rows[rows.len() - 1].decision_sequence,
            sha256: format!("{:x}", hasher.finalize()),
        })
    }

    fn training_decisions(&self, label_version: u16) -> Result<Vec<DecisionRow>, StorageError> {
        let mut statement = self.connection.prepare(
            r#"SELECT
                   decision_signature, decision_ordinal, decision_sequence,
                   decision_mint, decision_quote_mint, decision_venue,
                   decision_observed_at_unix_ms, decision_entry_price_quote,
                   decision_entry_total_quote
               FROM fast_future_path_labels
               WHERE label_version = ?1
               ORDER BY decision_sequence ASC, decision_signature ASC, decision_ordinal ASC,
                        horizon_ms ASC"#,
        )?;
        let raw = statement
            .query_map([i64::from(label_version)], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                    row.get::<_, i64>(6)?,
                    row.get::<_, f64>(7)?,
                    row.get::<_, Option<f64>>(8)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        type DecisionIdentity = (i64, String, String, String, i64, u64, Option<u64>);
        let mut seen = BTreeMap::<(String, i64), DecisionIdentity>::new();
        let mut decisions = Vec::new();

        for (signature, ordinal, sequence, mint, quote_mint, venue, observed_at, price, total) in raw {
            let ordinal_u32 = u32::try_from(ordinal).map_err(|_| {
                StorageError::InvalidData("training decision ordinal is outside u32".to_owned())
            })?;
            let sequence_u64 = u64::try_from(sequence).map_err(|_| {
                StorageError::InvalidData("training decision sequence is outside u64".to_owned())
            })?;
            if sequence_u64 == 0 {
                return Err(StorageError::InvalidData(
                    "training decision sequence must be positive".to_owned(),
                ));
            }
            if observed_at < 0 {
                return Err(StorageError::InvalidData(
                    "training decision timestamp must be non-negative".to_owned(),
                ));
            }
            validate_positive_finite(price, "training decision entry price")?;
            if let Some(value) = total {
                validate_positive_finite(value, "training decision entry total")?;
            }

            let venue_id = parse_training_venue(&venue)?;
            let market = FastMarketKey::new(mint.clone(), quote_mint.clone(), venue_id)
                .map_err(|error| {
                    StorageError::InvalidData(format!("invalid training decision market: {error}"))
                })?;
            let identity = (
                sequence,
                mint.clone(),
                quote_mint.clone(),
                venue.clone(),
                observed_at,
                price.to_bits(),
                total.map(f64::to_bits),
            );
            let key = (signature.clone(), ordinal);
            if let Some(previous) = seen.get(&key) {
                if previous != &identity {
                    return Err(StorageError::InvalidData(format!(
                        "training decision '{}' ordinal {} has contradictory FL4 identity/economics",
                        signature, ordinal
                    )));
                }
                continue;
            }
            seen.insert(key, identity);
            decisions.push(DecisionRow {
                signature,
                ordinal: ordinal_u32,
                sequence: sequence_u64,
                market,
                observed_at_unix_ms: observed_at,
                entry_price_quote: price,
                entry_total_quote: total,
            });
        }
        Ok(decisions)
    }
}

fn lifecycle_matches_market(event: &TokenLifecycleEvent, market: &FastMarketKey) -> bool {
    event.mint == market.mint
        && event.quote_mint == market.quote_mint
        && (event.from_venue == market.venue || event.to_venue == market.venue)
}

fn validate_decision_event(decision: &DecisionRow, event: &FastEvent) -> Result<(), StorageError> {
    if event.id.signature != decision.signature
        || event.id.ordinal != decision.ordinal
        || event.sequence != decision.sequence
        || event.market != decision.market
        || event.observed_at_unix_ms != decision.observed_at_unix_ms
        || event.price_quote.to_bits() != decision.entry_price_quote.to_bits()
    {
        return Err(StorageError::InvalidData(format!(
            "FL4 training decision '{}' ordinal {} does not match canonical FastEvent",
            decision.signature, decision.ordinal
        )));
    }
    Ok(())
}

fn record_from_snapshot(
    decision: &DecisionRow,
    stored: &StoredFastEvent,
    snapshot: &FastMarketSnapshot,
) -> Result<FastTrainingFeatureRecord, StorageError> {
    if snapshot.market != decision.market
        || snapshot.as_of_unix_ms != decision.observed_at_unix_ms
        || snapshot.last_sequence != Some(decision.sequence)
    {
        return Err(StorageError::InvalidData(
            "training snapshot identity/time does not match decision".to_owned(),
        ));
    }
    validate_default_windows(&snapshot.windows)?;

    let windows = snapshot
        .windows
        .iter()
        .map(window_from_summary)
        .collect::<Result<Vec<_>, _>>()?;
    let record = FastTrainingFeatureRecord {
        schema_name: FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version: FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature: decision.signature.clone(),
        decision_ordinal: decision.ordinal,
        decision_sequence: decision.sequence,
        mint: decision.market.mint.clone(),
        quote_mint: decision.market.quote_mint.clone(),
        venue: decision.market.venue.as_str().to_owned(),
        decision_observed_at_unix_ms: decision.observed_at_unix_ms,
        decision_provider: stored.event.provider.as_str().to_owned(),
        decision_source_observed_at_unix_ms: stored.source_observed_at_unix_ms,
        decision_occurred_at_unix_ms: stored.event.occurred_at_unix_ms,
        decision_slot: stored.event.slot,
        decision_event_kind: match stored.event.kind {
            FastEventKind::Buy => "buy",
            FastEventKind::Sell => "sell",
        }
        .to_owned(),
        decision_actor: stored.event.actor.clone(),
        decision_executable_entry_price_quote: decision.entry_price_quote,
        decision_entry_total_quote: decision.entry_total_quote,
        snapshot_as_of_unix_ms: snapshot.as_of_unix_ms,
        snapshot_last_sequence: snapshot.last_sequence,
        snapshot_last_price_quote: snapshot.last_price_quote,
        last_reserve_context: snapshot
            .last_reserve_context
            .as_ref()
            .map(reserve_from_context),
        last_lifecycle_event: snapshot
            .last_lifecycle_event
            .as_ref()
            .map(lifecycle_from_event),
        windows,
    };
    validate_record(&record)?;
    Ok(record)
}

fn validate_default_windows(windows: &[FastWindowSummary]) -> Result<(), StorageError> {
    if windows.len() != DEFAULT_FAST_WINDOWS_MS.len()
        || !windows
            .iter()
            .zip(DEFAULT_FAST_WINDOWS_MS)
            .all(|(window, expected)| window.window_ms == expected)
    {
        return Err(StorageError::InvalidData(
            "training snapshot does not contain the sealed default Fast Lane windows".to_owned(),
        ));
    }
    Ok(())
}

fn window_from_summary(
    value: &FastWindowSummary,
) -> Result<FastTrainingWindowSummary, StorageError> {
    for (number, name) in [
        (value.buy_arrival_rate_per_second, "buy arrival rate"),
        (value.sell_arrival_rate_per_second, "sell arrival rate"),
        (value.count_imbalance, "count imbalance"),
        (value.buy_base_quantity, "buy base quantity"),
        (value.sell_base_quantity, "sell base quantity"),
        (value.buy_quote_quantity, "buy quote quantity"),
        (value.sell_quote_quantity, "sell quote quantity"),
        (value.net_quote_quantity, "net quote quantity"),
        (value.quote_flow_imbalance, "quote flow imbalance"),
        (value.quote_flow_velocity_per_second, "quote flow velocity"),
        (
            value.quote_flow_acceleration_per_second2,
            "quote flow acceleration",
        ),
        (value.drawdown_from_local_high, "drawdown from high"),
        (value.recovery_from_local_low, "recovery from low"),
    ] {
        validate_finite(number, name)?;
    }
    for (number, name) in [
        (value.local_high_price_quote, "local high"),
        (value.local_low_price_quote, "local low"),
        (value.post_high_low_price_quote, "post-high low"),
        (value.last_price_quote, "window last price"),
    ] {
        if let Some(number) = number {
            validate_positive_finite(number, name)?;
        }
    }

    Ok(FastTrainingWindowSummary {
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
    })
}

fn reserve_from_context(value: &FastReserveContext) -> FastTrainingReserveContext {
    match value {
        FastReserveContext::PumpCurve {
            virtual_base_reserve_raw,
            virtual_quote_reserve_raw,
            real_base_reserve_raw,
            real_quote_reserve_raw,
            base_decimals,
            quote_decimals,
        } => FastTrainingReserveContext::PumpCurve {
            virtual_base_reserve_raw: *virtual_base_reserve_raw,
            virtual_quote_reserve_raw: *virtual_quote_reserve_raw,
            real_base_reserve_raw: *real_base_reserve_raw,
            real_quote_reserve_raw: *real_quote_reserve_raw,
            base_decimals: *base_decimals,
            quote_decimals: *quote_decimals,
        },
        FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw,
            pool_quote_reserve_raw,
            virtual_quote_reserve_raw,
            base_decimals,
            quote_decimals,
        } => FastTrainingReserveContext::PumpSwapPool {
            pool_base_reserve_raw: *pool_base_reserve_raw,
            pool_quote_reserve_raw: *pool_quote_reserve_raw,
            virtual_quote_reserve_raw: *virtual_quote_reserve_raw,
            base_decimals: *base_decimals,
            quote_decimals: *quote_decimals,
        },
    }
}

fn lifecycle_from_event(value: &TokenLifecycleEvent) -> FastTrainingLifecycleEvent {
    FastTrainingLifecycleEvent {
        kind: match value.kind {
            LifecycleEventKind::PumpGraduation => "pump_graduation",
        }
        .to_owned(),
        provider: value.provider.as_str().to_owned(),
        mint: value.mint.clone(),
        quote_mint: value.quote_mint.clone(),
        from_venue: value.from_venue.as_str().to_owned(),
        to_venue: value.to_venue.as_str().to_owned(),
        pool_address: value.pool_address.clone(),
        signature: value.signature.clone(),
        slot: value.slot,
        detected_at_unix_ms: value.detected_at_unix_ms,
        occurred_at_unix_ms: value.occurred_at_unix_ms,
    }
}

fn validate_record(value: &FastTrainingFeatureRecord) -> Result<(), StorageError> {
    if value.schema_name != FAST_TRAINING_FEATURE_SCHEMA_NAME
        || value.schema_version != FAST_TRAINING_FEATURE_SCHEMA_VERSION
        || value.decision_signature.trim().is_empty()
        || value.mint.trim().is_empty()
        || value.quote_mint.trim().is_empty()
        || value.venue.trim().is_empty()
        || value.decision_provider.trim().is_empty()
    {
        return Err(StorageError::InvalidData(
            "training feature record identity/schema is invalid".to_owned(),
        ));
    }
    if value.decision_observed_at_unix_ms < 0
        || value.snapshot_as_of_unix_ms != value.decision_observed_at_unix_ms
        || value.snapshot_last_sequence != Some(value.decision_sequence)
        || value.decision_source_observed_at_unix_ms < 0
        || value.decision_source_observed_at_unix_ms > value.decision_observed_at_unix_ms
        || value.decision_occurred_at_unix_ms < 0
        || value.decision_occurred_at_unix_ms > value.decision_observed_at_unix_ms
    {
        return Err(StorageError::InvalidData(
            "training feature record violates point-in-time decision clocks".to_owned(),
        ));
    }
    validate_positive_finite(
        value.decision_executable_entry_price_quote,
        "training executable entry price",
    )?;
    if let Some(number) = value.decision_entry_total_quote {
        validate_positive_finite(number, "training decision entry total")?;
    }
    if let Some(number) = value.snapshot_last_price_quote {
        validate_positive_finite(number, "training snapshot last price")?;
    }
    if value.windows.len() != DEFAULT_FAST_WINDOWS_MS.len()
        || !value
            .windows
            .iter()
            .zip(DEFAULT_FAST_WINDOWS_MS)
            .all(|(window, expected)| window.window_ms == expected)
    {
        return Err(StorageError::InvalidData(
            "training feature record window set differs from sealed defaults".to_owned(),
        ));
    }

    for window in &value.windows {
        for timestamp in [
            window.local_high_observed_at_unix_ms,
            window.local_low_observed_at_unix_ms,
            window.post_high_low_observed_at_unix_ms,
        ] {
            if timestamp.is_some_and(|at| at > value.decision_observed_at_unix_ms) {
                return Err(StorageError::InvalidData(
                    "training feature window contains future path timestamp".to_owned(),
                ));
            }
        }
        if window
            .local_high_sequence
            .into_iter()
            .chain(window.local_low_sequence)
            .chain(window.post_high_low_sequence)
            .any(|sequence| sequence > value.decision_sequence)
        {
            return Err(StorageError::InvalidData(
                "training feature window contains future sequence".to_owned(),
            ));
        }
    }

    if value
        .last_lifecycle_event
        .as_ref()
        .is_some_and(|event| event.detected_at_unix_ms > value.decision_observed_at_unix_ms)
    {
        return Err(StorageError::InvalidData(
            "training feature record contains future lifecycle evidence".to_owned(),
        ));
    }
    Ok(())
}

fn parse_training_venue(value: &str) -> Result<VenueId, StorageError> {
    match value {
        "pump_fun_bonding_curve" => Ok(VenueId::PumpFunBondingCurve),
        "pump_swap" => Ok(VenueId::PumpSwap),
        other => Err(StorageError::InvalidData(format!(
            "unsupported Fast Lane training venue '{other}'"
        ))),
    }
}

fn validate_finite(value: f64, name: &str) -> Result<(), StorageError> {
    if !value.is_finite() {
        return Err(StorageError::InvalidData(format!(
            "{name} must be finite for training export"
        )));
    }
    Ok(())
}

fn validate_positive_finite(value: f64, name: &str) -> Result<(), StorageError> {
    validate_finite(value, name)?;
    if value <= 0.0 {
        return Err(StorageError::InvalidData(format!(
            "{name} must be positive for training export"
        )));
    }
    Ok(())
}
