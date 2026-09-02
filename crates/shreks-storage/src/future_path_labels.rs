use rusqlite::{params, OptionalExtension};
use shreks_core::{
    FastEventId, FastMarketKey, FuturePathCompleteness, FuturePathCoverage, FuturePathDecision,
    FuturePathLabel, VenueId, FUTURE_PATH_LABEL_VERSION,
};

use super::{ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq)]
pub struct StoredFuturePathLabel {
    pub decision: FuturePathDecision,
    pub coverage: FuturePathCoverage,
    pub label: FuturePathLabel,
}

#[derive(Debug)]
struct RawFuturePathRow {
    decision_signature: String,
    decision_ordinal: i64,
    decision_sequence: i64,
    decision_mint: String,
    decision_quote_mint: String,
    decision_venue: String,
    decision_observed_at_unix_ms: i64,
    decision_entry_price_quote: f64,
    decision_entry_total_quote: Option<f64>,
    coverage_complete_through_unix_ms: i64,
    coverage_contiguous: i64,
    horizon_ms: i64,
    label_version: i64,
    completeness: String,
    event_count: i64,
    no_trade_events: i64,
    endpoint_signature: Option<String>,
    endpoint_ordinal: Option<i64>,
    endpoint_observed_at_unix_ms: Option<i64>,
    endpoint_price_quote: Option<f64>,
    endpoint_return_bps: Option<f64>,
    mfe_bps: Option<f64>,
    mae_bps: Option<f64>,
    time_to_peak_ms: Option<i64>,
    time_to_trough_ms: Option<i64>,
    reversal_occurred: Option<i64>,
    first_reversal_after_ms: Option<i64>,
    min_exit_capacity_base: Option<f64>,
    endpoint_exit_capacity_base: Option<f64>,
    route_unavailability_observed: Option<i64>,
    best_cost_adjusted_return_bps: Option<f64>,
    endpoint_cost_adjusted_return_bps: Option<f64>,
}

impl ShreksDb {
    pub fn record_future_path_label(
        &self,
        decision: &FuturePathDecision,
        coverage: FuturePathCoverage,
        label: &FuturePathLabel,
    ) -> Result<bool, StorageError> {
        validate_future_path_label(decision, coverage, label)?;
        self.validate_future_path_decision_source(decision)?;
        self.validate_future_path_endpoint_source(decision, label)?;

        let decision_ordinal = i64::from(decision.event_id.ordinal);
        let decision_sequence = i64::try_from(decision.sequence).map_err(|_| {
            StorageError::InvalidData(
                "future-path decision sequence exceeds SQLite signed integer range".to_owned(),
            )
        })?;
        let horizon_ms = i64::try_from(label.horizon_ms).map_err(|_| {
            StorageError::InvalidData(
                "future-path horizon exceeds SQLite signed integer range".to_owned(),
            )
        })?;
        let label_version = i64::from(label.version);
        let event_count = i64::try_from(label.event_count).map_err(|_| {
            StorageError::InvalidData(
                "future-path event count exceeds SQLite signed integer range".to_owned(),
            )
        })?;
        let endpoint_signature = label
            .endpoint_event_id
            .as_ref()
            .map(|identity| identity.signature.as_str());
        let endpoint_ordinal = label
            .endpoint_event_id
            .as_ref()
            .map(|identity| i64::from(identity.ordinal));

        let changed = self.connection.execute(
            r#"INSERT OR IGNORE INTO fast_future_path_labels (
                   decision_signature, decision_ordinal, decision_sequence,
                   decision_mint, decision_quote_mint, decision_venue,
                   decision_observed_at_unix_ms, decision_entry_price_quote,
                   decision_entry_total_quote,
                   coverage_complete_through_unix_ms, coverage_contiguous,
                   horizon_ms, label_version, completeness, event_count, no_trade_events,
                   endpoint_signature, endpoint_ordinal, endpoint_observed_at_unix_ms,
                   endpoint_price_quote, endpoint_return_bps, mfe_bps, mae_bps,
                   time_to_peak_ms, time_to_trough_ms, reversal_occurred,
                   first_reversal_after_ms, min_exit_capacity_base,
                   endpoint_exit_capacity_base, route_unavailability_observed,
                   best_cost_adjusted_return_bps, endpoint_cost_adjusted_return_bps
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8,
                   ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16,
                   ?17, ?18, ?19, ?20, ?21, ?22, ?23, ?24,
                   ?25, ?26, ?27, ?28, ?29, ?30, ?31, ?32
               )"#,
            params![
                decision.event_id.signature,
                decision_ordinal,
                decision_sequence,
                decision.market.mint,
                decision.market.quote_mint,
                decision.market.venue.as_str(),
                decision.observed_at_unix_ms,
                decision.executable_entry_price_quote,
                decision.entry_total_quote,
                coverage.complete_through_unix_ms,
                bool_i64(coverage.contiguous),
                horizon_ms,
                label_version,
                label.completeness.as_str(),
                event_count,
                bool_i64(label.no_trade_events),
                endpoint_signature,
                endpoint_ordinal,
                label.endpoint_observed_at_unix_ms,
                label.endpoint_price_quote,
                label.endpoint_return_bps,
                label.mfe_bps,
                label.mae_bps,
                option_u64_i64(label.time_to_peak_ms, "future-path time_to_peak_ms")?,
                option_u64_i64(label.time_to_trough_ms, "future-path time_to_trough_ms")?,
                label.reversal_occurred.map(bool_i64),
                option_u64_i64(
                    label.first_reversal_after_ms,
                    "future-path first_reversal_after_ms",
                )?,
                label.min_exit_capacity_base,
                label.endpoint_exit_capacity_base,
                label.route_unavailability_observed.map(bool_i64),
                label.best_cost_adjusted_return_bps,
                label.endpoint_cost_adjusted_return_bps,
            ],
        )?;

        if changed == 1 {
            return Ok(true);
        }

        let existing = self
            .future_path_label_by_key(
                &decision.event_id.signature,
                decision.event_id.ordinal,
                label.horizon_ms,
                label.version,
            )?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "future-path label '{}' ordinal {} horizon {} version {} disappeared after duplicate insert",
                    decision.event_id.signature,
                    decision.event_id.ordinal,
                    label.horizon_ms,
                    label.version
                ))
            })?;

        let incoming = StoredFuturePathLabel {
            decision: decision.clone(),
            coverage,
            label: label.clone(),
        };
        if existing == incoming {
            return Ok(false);
        }

        Err(StorageError::InvalidData(format!(
            "conflicting future-path label for '{}' ordinal {} horizon {} version {}",
            decision.event_id.signature,
            decision.event_id.ordinal,
            label.horizon_ms,
            label.version
        )))
    }

    pub fn future_path_labels_for_decision(
        &self,
        decision_signature: &str,
        decision_ordinal: u32,
        label_version: u16,
    ) -> Result<Vec<StoredFuturePathLabel>, StorageError> {
        if decision_signature.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "future-path decision signature must not be empty".to_owned(),
            ));
        }
        if label_version == 0 {
            return Err(StorageError::InvalidData(
                "future-path label version must be positive".to_owned(),
            ));
        }

        let mut statement = self.connection.prepare(&format!(
            "{} WHERE decision_signature = ?1 AND decision_ordinal = ?2 AND label_version = ?3 ORDER BY horizon_ms ASC",
            future_path_select_sql()
        ))?;
        let rows = statement
            .query_map(
                params![
                    decision_signature,
                    i64::from(decision_ordinal),
                    i64::from(label_version)
                ],
                decode_raw_future_path_row,
            )?
            .collect::<Result<Vec<_>, _>>()?;
        rows.into_iter().map(decode_future_path_row).collect()
    }

    fn future_path_label_by_key(
        &self,
        decision_signature: &str,
        decision_ordinal: u32,
        horizon_ms: u64,
        label_version: u16,
    ) -> Result<Option<StoredFuturePathLabel>, StorageError> {
        let horizon_ms = i64::try_from(horizon_ms).map_err(|_| {
            StorageError::InvalidData(
                "future-path horizon exceeds SQLite signed integer range".to_owned(),
            )
        })?;
        let mut statement = self.connection.prepare(&format!(
            "{} WHERE decision_signature = ?1 AND decision_ordinal = ?2 AND horizon_ms = ?3 AND label_version = ?4",
            future_path_select_sql()
        ))?;
        let raw = statement
            .query_row(
                params![
                    decision_signature,
                    i64::from(decision_ordinal),
                    horizon_ms,
                    i64::from(label_version)
                ],
                decode_raw_future_path_row,
            )
            .optional()?;
        raw.map(decode_future_path_row).transpose()
    }

    fn validate_future_path_decision_source(
        &self,
        decision: &FuturePathDecision,
    ) -> Result<(), StorageError> {
        let source = self
            .connection
            .query_row(
                r#"SELECT sequence, mint, quote_mint, venue, observed_at_unix_ms
                   FROM fast_events
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![decision.event_id.signature, i64::from(decision.event_id.ordinal)],
                |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, i64>(4)?,
                    ))
                },
            )
            .optional()?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "future-path decision FastEvent '{}' ordinal {} is missing",
                    decision.event_id.signature, decision.event_id.ordinal
                ))
            })?;

        let expected_sequence = i64::try_from(decision.sequence).map_err(|_| {
            StorageError::InvalidData(
                "future-path decision sequence exceeds SQLite signed integer range".to_owned(),
            )
        })?;
        if source.0 != expected_sequence
            || source.1 != decision.market.mint
            || source.2 != decision.market.quote_mint
            || source.3 != decision.market.venue.as_str()
            || source.4 != decision.observed_at_unix_ms
        {
            return Err(StorageError::InvalidData(format!(
                "future-path decision does not match canonical FastEvent '{}' ordinal {}",
                decision.event_id.signature, decision.event_id.ordinal
            )));
        }
        Ok(())
    }

    fn validate_future_path_endpoint_source(
        &self,
        decision: &FuturePathDecision,
        label: &FuturePathLabel,
    ) -> Result<(), StorageError> {
        let Some(identity) = label.endpoint_event_id.as_ref() else {
            return Ok(());
        };
        let source = self
            .connection
            .query_row(
                r#"SELECT sequence, mint, quote_mint, venue, observed_at_unix_ms, price_quote
                   FROM fast_events
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![identity.signature, i64::from(identity.ordinal)],
                |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, i64>(4)?,
                        row.get::<_, f64>(5)?,
                    ))
                },
            )
            .optional()?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "future-path endpoint FastEvent '{}' ordinal {} is missing",
                    identity.signature, identity.ordinal
                ))
            })?;
        if source.0 <= i64::try_from(decision.sequence).unwrap_or(i64::MAX)
            || source.1 != decision.market.mint
            || source.2 != decision.market.quote_mint
            || source.3 != decision.market.venue.as_str()
            || Some(source.4) != label.endpoint_observed_at_unix_ms
            || Some(source.5) != label.endpoint_price_quote
        {
            return Err(StorageError::InvalidData(format!(
                "future-path endpoint does not match canonical FastEvent '{}' ordinal {}",
                identity.signature, identity.ordinal
            )));
        }
        Ok(())
    }
}

fn validate_future_path_label(
    decision: &FuturePathDecision,
    coverage: FuturePathCoverage,
    label: &FuturePathLabel,
) -> Result<(), StorageError> {
    if decision.event_id.signature.trim().is_empty()
        || decision.market.mint.trim().is_empty()
        || decision.market.quote_mint.trim().is_empty()
        || decision.observed_at_unix_ms < 0
        || !decision.executable_entry_price_quote.is_finite()
        || decision.executable_entry_price_quote <= 0.0
    {
        return Err(StorageError::InvalidData(
            "future-path decision contains invalid canonical identity/economics".to_owned(),
        ));
    }
    if let Some(entry_total_quote) = decision.entry_total_quote {
        validate_positive_finite(entry_total_quote, "future-path decision entry total quote")?;
    }
    if coverage.complete_through_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "future-path coverage timestamp must be non-negative".to_owned(),
        ));
    }
    if label.version != FUTURE_PATH_LABEL_VERSION || label.horizon_ms == 0 {
        return Err(StorageError::InvalidData(format!(
            "future-path storage only accepts label version {FUTURE_PATH_LABEL_VERSION} with positive horizons"
        )));
    }

    let horizon = i64::try_from(label.horizon_ms).map_err(|_| {
        StorageError::InvalidData(
            "future-path horizon exceeds SQLite signed integer range".to_owned(),
        )
    })?;
    let horizon_end = decision
        .observed_at_unix_ms
        .checked_add(horizon)
        .ok_or_else(|| StorageError::InvalidData("future-path horizon timestamp overflowed".to_owned()))?;
    let expected_complete = coverage.contiguous && coverage.complete_through_unix_ms >= horizon_end;
    match (expected_complete, label.completeness) {
        (true, FuturePathCompleteness::Complete)
        | (false, FuturePathCompleteness::Incomplete) => {}
        _ => {
            return Err(StorageError::InvalidData(
                "future-path label completeness contradicts supplied coverage".to_owned(),
            ));
        }
    }

    for (value, name) in [
        (label.endpoint_price_quote, "future-path endpoint price"),
        (label.endpoint_return_bps, "future-path endpoint return"),
        (label.mfe_bps, "future-path MFE"),
        (label.mae_bps, "future-path MAE"),
        (label.min_exit_capacity_base, "future-path minimum exit capacity"),
        (label.endpoint_exit_capacity_base, "future-path endpoint exit capacity"),
        (
            label.best_cost_adjusted_return_bps,
            "future-path best cost-adjusted return",
        ),
        (
            label.endpoint_cost_adjusted_return_bps,
            "future-path endpoint cost-adjusted return",
        ),
    ] {
        if let Some(value) = value {
            validate_finite(value, name)?;
        }
    }
    if label.endpoint_price_quote.is_some_and(|value| value <= 0.0)
        || label.min_exit_capacity_base.is_some_and(|value| value < 0.0)
        || label.endpoint_exit_capacity_base.is_some_and(|value| value < 0.0)
    {
        return Err(StorageError::InvalidData(
            "future-path price/capacity values violate positivity constraints".to_owned(),
        ));
    }

    let has_any_path_metric = label.endpoint_event_id.is_some()
        || label.endpoint_observed_at_unix_ms.is_some()
        || label.endpoint_price_quote.is_some()
        || label.endpoint_return_bps.is_some()
        || label.mfe_bps.is_some()
        || label.mae_bps.is_some()
        || label.time_to_peak_ms.is_some()
        || label.time_to_trough_ms.is_some()
        || label.reversal_occurred.is_some()
        || label.first_reversal_after_ms.is_some()
        || label.min_exit_capacity_base.is_some()
        || label.endpoint_exit_capacity_base.is_some()
        || label.route_unavailability_observed.is_some()
        || label.best_cost_adjusted_return_bps.is_some()
        || label.endpoint_cost_adjusted_return_bps.is_some();

    match label.completeness {
        FuturePathCompleteness::Incomplete => {
            if label.event_count != 0 || label.no_trade_events || has_any_path_metric {
                return Err(StorageError::InvalidData(
                    "incomplete future-path labels must expose no path metrics".to_owned(),
                ));
            }
        }
        FuturePathCompleteness::Complete if label.event_count == 0 => {
            if !label.no_trade_events || has_any_path_metric {
                return Err(StorageError::InvalidData(
                    "complete no-trade future-path labels must keep path metrics unknown".to_owned(),
                ));
            }
        }
        FuturePathCompleteness::Complete => {
            if label.no_trade_events
                || label.endpoint_event_id.is_none()
                || label.endpoint_observed_at_unix_ms.is_none()
                || label.endpoint_price_quote.is_none()
                || label.endpoint_return_bps.is_none()
                || label.mfe_bps.is_none()
                || label.mae_bps.is_none()
                || label.time_to_peak_ms.is_none()
                || label.time_to_trough_ms.is_none()
                || label.reversal_occurred.is_none()
            {
                return Err(StorageError::InvalidData(
                    "complete future-path labels with events require endpoint/path metrics".to_owned(),
                ));
            }
            let endpoint_observed = label.endpoint_observed_at_unix_ms.unwrap();
            if endpoint_observed <= decision.observed_at_unix_ms || endpoint_observed > horizon_end {
                return Err(StorageError::InvalidData(
                    "future-path endpoint time is outside the decision horizon".to_owned(),
                ));
            }
            if label.time_to_peak_ms.unwrap() > label.horizon_ms
                || label.time_to_trough_ms.unwrap() > label.horizon_ms
                || label
                    .first_reversal_after_ms
                    .is_some_and(|value| value > label.horizon_ms)
            {
                return Err(StorageError::InvalidData(
                    "future-path timing metric exceeds its horizon".to_owned(),
                ));
            }
            match (label.reversal_occurred, label.first_reversal_after_ms) {
                (Some(true), Some(_)) | (Some(false), None) => {}
                _ => {
                    return Err(StorageError::InvalidData(
                        "future-path reversal timing contradicts reversal occurrence".to_owned(),
                    ));
                }
            }
        }
    }

    Ok(())
}

fn future_path_select_sql() -> &'static str {
    r#"SELECT
           decision_signature, decision_ordinal, decision_sequence,
           decision_mint, decision_quote_mint, decision_venue,
           decision_observed_at_unix_ms, decision_entry_price_quote,
           decision_entry_total_quote,
           coverage_complete_through_unix_ms, coverage_contiguous,
           horizon_ms, label_version, completeness, event_count, no_trade_events,
           endpoint_signature, endpoint_ordinal, endpoint_observed_at_unix_ms,
           endpoint_price_quote, endpoint_return_bps, mfe_bps, mae_bps,
           time_to_peak_ms, time_to_trough_ms, reversal_occurred,
           first_reversal_after_ms, min_exit_capacity_base,
           endpoint_exit_capacity_base, route_unavailability_observed,
           best_cost_adjusted_return_bps, endpoint_cost_adjusted_return_bps
       FROM fast_future_path_labels"#
}

fn decode_raw_future_path_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RawFuturePathRow> {
    Ok(RawFuturePathRow {
        decision_signature: row.get(0)?,
        decision_ordinal: row.get(1)?,
        decision_sequence: row.get(2)?,
        decision_mint: row.get(3)?,
        decision_quote_mint: row.get(4)?,
        decision_venue: row.get(5)?,
        decision_observed_at_unix_ms: row.get(6)?,
        decision_entry_price_quote: row.get(7)?,
        decision_entry_total_quote: row.get(8)?,
        coverage_complete_through_unix_ms: row.get(9)?,
        coverage_contiguous: row.get(10)?,
        horizon_ms: row.get(11)?,
        label_version: row.get(12)?,
        completeness: row.get(13)?,
        event_count: row.get(14)?,
        no_trade_events: row.get(15)?,
        endpoint_signature: row.get(16)?,
        endpoint_ordinal: row.get(17)?,
        endpoint_observed_at_unix_ms: row.get(18)?,
        endpoint_price_quote: row.get(19)?,
        endpoint_return_bps: row.get(20)?,
        mfe_bps: row.get(21)?,
        mae_bps: row.get(22)?,
        time_to_peak_ms: row.get(23)?,
        time_to_trough_ms: row.get(24)?,
        reversal_occurred: row.get(25)?,
        first_reversal_after_ms: row.get(26)?,
        min_exit_capacity_base: row.get(27)?,
        endpoint_exit_capacity_base: row.get(28)?,
        route_unavailability_observed: row.get(29)?,
        best_cost_adjusted_return_bps: row.get(30)?,
        endpoint_cost_adjusted_return_bps: row.get(31)?,
    })
}

fn decode_future_path_row(raw: RawFuturePathRow) -> Result<StoredFuturePathLabel, StorageError> {
    let venue = parse_venue(&raw.decision_venue)?;
    let market = FastMarketKey::new(raw.decision_mint, raw.decision_quote_mint, venue)
        .map_err(|error| StorageError::InvalidData(format!("invalid stored future-path market: {error}")))?;
    let event_id = FastEventId::new(raw.decision_signature, u32_value(raw.decision_ordinal, "decision ordinal")?)
        .map_err(|error| StorageError::InvalidData(format!("invalid stored future-path identity: {error}")))?;
    let mut decision = FuturePathDecision::new(
        market,
        event_id,
        u64_value(raw.decision_sequence, "decision sequence")?,
        raw.decision_observed_at_unix_ms,
        raw.decision_entry_price_quote,
    )
    .map_err(|error| StorageError::InvalidData(format!("invalid stored future-path decision: {error}")))?;
    if let Some(entry_total_quote) = raw.decision_entry_total_quote {
        decision = decision.with_entry_total_quote(entry_total_quote).map_err(|error| {
            StorageError::InvalidData(format!("invalid stored future-path entry total: {error}"))
        })?;
    }
    let coverage = FuturePathCoverage::new(
        raw.coverage_complete_through_unix_ms,
        bool_value(raw.coverage_contiguous, "coverage contiguous")?,
    )
    .map_err(|error| StorageError::InvalidData(format!("invalid stored future-path coverage: {error}")))?;
    let completeness = match raw.completeness.as_str() {
        "complete" => FuturePathCompleteness::Complete,
        "incomplete" => FuturePathCompleteness::Incomplete,
        other => {
            return Err(StorageError::InvalidData(format!(
                "unknown stored future-path completeness '{other}'"
            )));
        }
    };
    let endpoint_event_id = match (raw.endpoint_signature, raw.endpoint_ordinal) {
        (None, None) => None,
        (Some(signature), Some(ordinal)) => Some(
            FastEventId::new(signature, u32_value(ordinal, "endpoint ordinal")?).map_err(|error| {
                StorageError::InvalidData(format!("invalid stored future-path endpoint identity: {error}"))
            })?,
        ),
        _ => {
            return Err(StorageError::InvalidData(
                "stored future-path endpoint identity is partial".to_owned(),
            ));
        }
    };
    let label = FuturePathLabel {
        version: u16_value(raw.label_version, "label version")?,
        horizon_ms: u64_value(raw.horizon_ms, "horizon_ms")?,
        completeness,
        event_count: u64_value(raw.event_count, "event_count")?,
        no_trade_events: bool_value(raw.no_trade_events, "no_trade_events")?,
        endpoint_event_id,
        endpoint_observed_at_unix_ms: raw.endpoint_observed_at_unix_ms,
        endpoint_price_quote: raw.endpoint_price_quote,
        endpoint_return_bps: raw.endpoint_return_bps,
        mfe_bps: raw.mfe_bps,
        mae_bps: raw.mae_bps,
        time_to_peak_ms: option_u64(raw.time_to_peak_ms, "time_to_peak_ms")?,
        time_to_trough_ms: option_u64(raw.time_to_trough_ms, "time_to_trough_ms")?,
        reversal_occurred: option_bool(raw.reversal_occurred, "reversal_occurred")?,
        first_reversal_after_ms: option_u64(
            raw.first_reversal_after_ms,
            "first_reversal_after_ms",
        )?,
        min_exit_capacity_base: raw.min_exit_capacity_base,
        endpoint_exit_capacity_base: raw.endpoint_exit_capacity_base,
        route_unavailability_observed: option_bool(
            raw.route_unavailability_observed,
            "route_unavailability_observed",
        )?,
        best_cost_adjusted_return_bps: raw.best_cost_adjusted_return_bps,
        endpoint_cost_adjusted_return_bps: raw.endpoint_cost_adjusted_return_bps,
    };
    validate_future_path_label(&decision, coverage, &label)?;
    Ok(StoredFuturePathLabel {
        decision,
        coverage,
        label,
    })
}

fn parse_venue(value: &str) -> Result<VenueId, StorageError> {
    match value {
        "pump_fun_bonding_curve" => Ok(VenueId::PumpFunBondingCurve),
        "pump_swap" => Ok(VenueId::PumpSwap),
        "meteora_dlmm" => Ok(VenueId::MeteoraDlmm),
        "meteora_damm_v2" => Ok(VenueId::MeteoraDammV2),
        "other_solana" => Ok(VenueId::OtherSolana),
        other => Err(StorageError::InvalidData(format!(
            "unknown stored future-path venue '{other}'"
        ))),
    }
}

fn validate_positive_finite(value: f64, field: &str) -> Result<(), StorageError> {
    validate_finite(value, field)?;
    if value <= 0.0 {
        return Err(StorageError::InvalidData(format!("{field} must be positive")));
    }
    Ok(())
}

fn validate_finite(value: f64, field: &str) -> Result<(), StorageError> {
    if !value.is_finite() {
        return Err(StorageError::InvalidData(format!("{field} must be finite")));
    }
    Ok(())
}

fn bool_i64(value: bool) -> i64 {
    if value { 1 } else { 0 }
}

fn bool_value(value: i64, field: &str) -> Result<bool, StorageError> {
    match value {
        0 => Ok(false),
        1 => Ok(true),
        other => Err(StorageError::InvalidData(format!(
            "{field} must be stored as 0 or 1; got {other}"
        ))),
    }
}

fn option_bool(value: Option<i64>, field: &str) -> Result<Option<bool>, StorageError> {
    value.map(|value| bool_value(value, field)).transpose()
}

fn option_u64_i64(value: Option<u64>, field: &str) -> Result<Option<i64>, StorageError> {
    value
        .map(|value| {
            i64::try_from(value).map_err(|_| {
                StorageError::InvalidData(format!(
                    "{field} exceeds SQLite signed integer range"
                ))
            })
        })
        .transpose()
}

fn option_u64(value: Option<i64>, field: &str) -> Result<Option<u64>, StorageError> {
    value.map(|value| u64_value(value, field)).transpose()
}

fn u64_value(value: i64, field: &str) -> Result<u64, StorageError> {
    u64::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!("stored future-path {field} was negative"))
    })
}

fn u32_value(value: i64, field: &str) -> Result<u32, StorageError> {
    u32::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!(
            "stored future-path {field} was outside u32 range"
        ))
    })
}

fn u16_value(value: i64, field: &str) -> Result<u16, StorageError> {
    u16::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!(
            "stored future-path {field} was outside u16 range"
        ))
    })
}
