use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{params, OptionalExtension};
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use shreks_core::{
    project_entry, project_exit, EntryProjectionError, ExitCapacityError, FastReserveContext,
    FuturePathCompleteness, VenueId,
};

use crate::{
    FastTrainingFeatureRecord, PumpSwapEffectiveFeeContext, PumpSwapEffectiveFeeContextValue,
    ShreksDb, StorageError, StoredFastEvent, StoredFuturePathLabel,
};

pub const FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME: &str =
    "shreks.fast_training_economics_overlay";
pub const FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FastTrainingEconomicsStatus {
    Available,
    UnsupportedVenue,
    NoEndpoint,
    EntryReserveUnavailable,
    ExitReserveUnavailable,
    EntryProjectionUnavailable,
    ExitProjectionUnavailable,
    EntryFeeMissing,
    EntryFeeStale,
    EntryFeeRateUnknown,
    ExitFeeMissing,
    ExitFeeStale,
    ExitFeeRateUnknown,
}

impl FastTrainingEconomicsStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Available => "available",
            Self::UnsupportedVenue => "unsupported_venue",
            Self::NoEndpoint => "no_endpoint",
            Self::EntryReserveUnavailable => "entry_reserve_unavailable",
            Self::ExitReserveUnavailable => "exit_reserve_unavailable",
            Self::EntryProjectionUnavailable => "entry_projection_unavailable",
            Self::ExitProjectionUnavailable => "exit_projection_unavailable",
            Self::EntryFeeMissing => "entry_fee_missing",
            Self::EntryFeeStale => "entry_fee_stale",
            Self::EntryFeeRateUnknown => "entry_fee_rate_unknown",
            Self::ExitFeeMissing => "exit_fee_missing",
            Self::ExitFeeStale => "exit_fee_stale",
            Self::ExitFeeRateUnknown => "exit_fee_rate_unknown",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FastTrainingEconomicsReserveProvenance {
    pub source_signature: String,
    pub source_ordinal: u32,
    pub source_sequence: u64,
    pub source_observed_at_unix_ms: i64,
    pub pool_base_reserve_raw: u64,
    pub pool_quote_reserve_raw: u64,
    pub virtual_quote_reserve_raw: i128,
    pub base_decimals: u8,
    pub quote_decimals: u8,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FastTrainingEconomicsEntryProjection {
    pub base_quantity_raw: u64,
    pub quote_input_raw: u64,
    pub base_quantity: f64,
    pub quote_input: f64,
    pub average_price_quote: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FastTrainingEconomicsExitProjection {
    pub base_quantity_raw: u64,
    pub quote_output_raw: u64,
    pub base_quantity: f64,
    pub quote_output: f64,
    pub average_price_quote: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FastTrainingEconomicsFeeProvenance {
    pub source_signature: String,
    pub source_ordinal: u32,
    pub source_sequence: u64,
    pub source_observed_at_unix_ms: i64,
    pub age_ms: u64,
    pub market_quote_amount_raw: u64,
    pub user_quote_amount_raw: u64,
    pub signed_user_cost_quote_raw: i128,
    pub effective_fee_bps: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FastTrainingEconomicsOverlayRow {
    pub decision_signature: String,
    pub decision_ordinal: u32,
    pub decision_sequence: u64,
    pub decision_observed_at_unix_ms: i64,
    pub mint: String,
    pub quote_mint: String,
    pub venue: String,
    pub horizon_ms: u64,
    pub future_path_label_version: u16,
    pub counterfactual_base_quantity: String,
    pub endpoint_signature: Option<String>,
    pub endpoint_ordinal: Option<u32>,
    pub endpoint_sequence: Option<u64>,
    pub endpoint_observed_at_unix_ms: Option<i64>,
    pub status: FastTrainingEconomicsStatus,
    pub requested_base_quantity_raw: Option<u64>,
    pub entry_reserve: Option<FastTrainingEconomicsReserveProvenance>,
    pub exit_reserve: Option<FastTrainingEconomicsReserveProvenance>,
    pub entry_projection: Option<FastTrainingEconomicsEntryProjection>,
    pub exit_projection: Option<FastTrainingEconomicsExitProjection>,
    pub entry_fee: Option<FastTrainingEconomicsFeeProvenance>,
    pub exit_fee: Option<FastTrainingEconomicsFeeProvenance>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FastTrainingEconomicsOverlayManifest {
    pub schema_name: String,
    pub schema_version: u16,
    pub row_count: u64,
    pub available_row_count: u64,
    pub status_counts: BTreeMap<String, u64>,
    pub feature_source_jsonl_sha256: String,
    pub future_path_logical_fingerprint_sha256: String,
    pub future_path_label_version: u16,
    pub counterfactual_base_quantity: String,
    pub pump_swap_fee_maximum_age_ms: u64,
    pub min_decision_observed_at_unix_ms: i64,
    pub max_decision_observed_at_unix_ms: i64,
    pub ordered_row_logical_fingerprint_sha256: String,
    pub manifest_fingerprint_sha256: String,
}

impl ShreksDb {
    pub fn fast_training_economics_overlay_rows(
        &self,
        features: &[FastTrainingFeatureRecord],
        label_version: u16,
        counterfactual_base_quantity: &str,
        pump_swap_fee_maximum_age_ms: u64,
    ) -> Result<Vec<FastTrainingEconomicsOverlayRow>, StorageError> {
        if label_version == 0 {
            return Err(StorageError::InvalidData(
                "training economics future-path label version must be positive".to_owned(),
            ));
        }
        validate_decimal_quantity_text(counterfactual_base_quantity)?;

        let expected_features = self.fast_training_feature_records(label_version)?;
        validate_feature_population(features, &expected_features)?;

        let mut labels =
            self.training_economics_labels_for_features(&expected_features, label_version)?;
        labels.sort_by(|left, right| {
            (
                left.decision.sequence,
                left.label.horizon_ms,
                left.decision.event_id.signature.as_str(),
                left.decision.event_id.ordinal,
            )
                .cmp(&(
                    right.decision.sequence,
                    right.label.horizon_ms,
                    right.decision.event_id.signature.as_str(),
                    right.decision.event_id.ordinal,
                ))
        });

        let mut rows = Vec::with_capacity(labels.len());
        let mut seen = BTreeSet::new();
        for stored in labels {
            let key = (
                stored.decision.event_id.signature.clone(),
                stored.decision.event_id.ordinal,
                stored.label.horizon_ms,
                stored.label.version,
            );
            if !seen.insert(key) {
                return Err(StorageError::InvalidData(
                    "training economics FL4 population contains duplicate decision/horizon identity"
                        .to_owned(),
                ));
            }
            self.validate_training_economics_canonical_sources(&stored)?;

            let endpoint_sequence = self.training_economics_endpoint_sequence(&stored)?;
            let mut row = base_overlay_row(
                &stored,
                endpoint_sequence,
                counterfactual_base_quantity,
            );

            if stored.decision.market.venue != VenueId::PumpSwap {
                row.status = FastTrainingEconomicsStatus::UnsupportedVenue;
                rows.push(row);
                continue;
            }

            let Some(endpoint_id) = stored.label.endpoint_event_id.as_ref() else {
                row.status = FastTrainingEconomicsStatus::NoEndpoint;
                rows.push(row);
                continue;
            };
            let endpoint_sequence = endpoint_sequence.ok_or_else(|| {
                StorageError::InvalidData(
                    "training economics endpoint identity is missing canonical sequence".to_owned(),
                )
            })?;

            let replay = self.fast_events_for_market_with_reserve_context(
                &stored.decision.market.mint,
                &stored.decision.market.quote_mint,
                VenueId::PumpSwap,
            )?;
            let decision_event = find_replay_event(
                &replay,
                &stored.decision.event_id.signature,
                stored.decision.event_id.ordinal,
                stored.decision.sequence,
                "decision",
            )?;
            let endpoint_event = find_replay_event(
                &replay,
                &endpoint_id.signature,
                endpoint_id.ordinal,
                endpoint_sequence,
                "endpoint",
            )?;

            let Some(entry_reserve) = pump_swap_reserve_provenance(decision_event)? else {
                row.status = FastTrainingEconomicsStatus::EntryReserveUnavailable;
                rows.push(row);
                continue;
            };
            let Some(exit_reserve) = pump_swap_reserve_provenance(endpoint_event)? else {
                row.status = FastTrainingEconomicsStatus::ExitReserveUnavailable;
                row.entry_reserve = Some(entry_reserve);
                rows.push(row);
                continue;
            };

            let requested_base_quantity_raw = decimal_quantity_to_raw(
                counterfactual_base_quantity,
                entry_reserve.base_decimals,
            )?;
            let exit_quantity_raw = decimal_quantity_to_raw(
                counterfactual_base_quantity,
                exit_reserve.base_decimals,
            )?;
            if requested_base_quantity_raw != exit_quantity_raw {
                return Err(StorageError::InvalidData(
                    "training economics decision/endpoint base decimals contradict requested quantity"
                        .to_owned(),
                ));
            }
            row.requested_base_quantity_raw = Some(requested_base_quantity_raw);
            row.entry_reserve = Some(entry_reserve.clone());
            row.exit_reserve = Some(exit_reserve.clone());

            let entry_context = reserve_context_from_provenance(&entry_reserve);
            let entry_projection = match project_entry(
                &entry_context,
                requested_base_quantity_raw,
            ) {
                Ok(value) => value,
                Err(
                    EntryProjectionError::PhysicalBaseReserveExhausted
                    | EntryProjectionError::BaseReserveExhausted,
                ) => {
                    row.status = FastTrainingEconomicsStatus::EntryProjectionUnavailable;
                    rows.push(row);
                    continue;
                }
                Err(error) => {
                    return Err(StorageError::InvalidData(format!(
                        "training economics entry projection failed closed: {error}"
                    )));
                }
            };
            row.entry_projection = Some(FastTrainingEconomicsEntryProjection {
                base_quantity_raw: entry_projection.base_quantity_raw,
                quote_input_raw: entry_projection.quote_input_raw,
                base_quantity: entry_projection.base_quantity,
                quote_input: entry_projection.quote_input,
                average_price_quote: entry_projection.average_price_quote,
            });

            let exit_context = reserve_context_from_provenance(&exit_reserve);
            let exit_projection = match project_exit(
                &exit_context,
                requested_base_quantity_raw,
            ) {
                Ok(value) => value,
                Err(ExitCapacityError::PhysicalQuoteReserveExhausted) => {
                    row.status = FastTrainingEconomicsStatus::ExitProjectionUnavailable;
                    rows.push(row);
                    continue;
                }
                Err(error) => {
                    return Err(StorageError::InvalidData(format!(
                        "training economics exit projection failed closed: {error}"
                    )));
                }
            };
            row.exit_projection = Some(FastTrainingEconomicsExitProjection {
                base_quantity_raw: exit_projection.base_quantity_raw,
                quote_output_raw: exit_projection.quote_output_raw,
                base_quantity: exit_projection.base_quantity,
                quote_output: exit_projection.quote_output,
                average_price_quote: exit_projection.average_price_quote,
            });

            match self.pump_swap_effective_fee_context(
                &stored.decision.market.mint,
                &stored.decision.market.quote_mint,
                true,
                stored.decision.sequence,
                stored.decision.observed_at_unix_ms,
                pump_swap_fee_maximum_age_ms,
            )? {
                PumpSwapEffectiveFeeContext::Missing => {
                    row.status = FastTrainingEconomicsStatus::EntryFeeMissing;
                    rows.push(row);
                    continue;
                }
                PumpSwapEffectiveFeeContext::Stale(_) => {
                    row.status = FastTrainingEconomicsStatus::EntryFeeStale;
                    rows.push(row);
                    continue;
                }
                PumpSwapEffectiveFeeContext::RateUnknown(_) => {
                    row.status = FastTrainingEconomicsStatus::EntryFeeRateUnknown;
                    rows.push(row);
                    continue;
                }
                PumpSwapEffectiveFeeContext::Available(value) => {
                    row.entry_fee = Some(fee_provenance(value)?);
                }
            }

            let endpoint_observed_at_unix_ms = stored
                .label
                .endpoint_observed_at_unix_ms
                .ok_or_else(|| {
                    StorageError::InvalidData(
                        "training economics endpoint identity is missing observation time"
                            .to_owned(),
                    )
                })?;
            match self.pump_swap_effective_fee_context(
                &stored.decision.market.mint,
                &stored.decision.market.quote_mint,
                false,
                endpoint_sequence,
                endpoint_observed_at_unix_ms,
                pump_swap_fee_maximum_age_ms,
            )? {
                PumpSwapEffectiveFeeContext::Missing => {
                    row.status = FastTrainingEconomicsStatus::ExitFeeMissing;
                    rows.push(row);
                    continue;
                }
                PumpSwapEffectiveFeeContext::Stale(_) => {
                    row.status = FastTrainingEconomicsStatus::ExitFeeStale;
                    rows.push(row);
                    continue;
                }
                PumpSwapEffectiveFeeContext::RateUnknown(_) => {
                    row.status = FastTrainingEconomicsStatus::ExitFeeRateUnknown;
                    rows.push(row);
                    continue;
                }
                PumpSwapEffectiveFeeContext::Available(value) => {
                    row.exit_fee = Some(fee_provenance(value)?);
                }
            }

            row.status = FastTrainingEconomicsStatus::Available;
            rows.push(row);
        }

        Ok(rows)
    }

    pub fn fast_training_future_path_logical_fingerprint_sha256(
        &self,
        label_version: u16,
    ) -> Result<String, StorageError> {
        if label_version == 0 {
            return Err(StorageError::InvalidData(
                "training economics future-path label version must be positive".to_owned(),
            ));
        }
        let features = self.fast_training_feature_records(label_version)?;
        let mut labels = self.training_economics_labels_for_features(&features, label_version)?;
        labels.sort_by(|left, right| {
            (
                left.decision.sequence,
                left.label.horizon_ms,
                left.decision.event_id.signature.as_str(),
                left.decision.event_id.ordinal,
            )
                .cmp(&(
                    right.decision.sequence,
                    right.label.horizon_ms,
                    right.decision.event_id.signature.as_str(),
                    right.decision.event_id.ordinal,
                ))
        });
        future_path_logical_fingerprint(&labels)
    }

    fn training_economics_labels_for_features(
        &self,
        features: &[FastTrainingFeatureRecord],
        label_version: u16,
    ) -> Result<Vec<StoredFuturePathLabel>, StorageError> {
        let mut labels = Vec::new();
        for feature in features {
            labels.extend(self.future_path_labels_for_decision(
                &feature.decision_signature,
                feature.decision_ordinal,
                label_version,
            )?);
        }
        if labels.is_empty() {
            return Err(StorageError::InvalidData(
                "training economics overlay requires at least one FL4 label".to_owned(),
            ));
        }
        Ok(labels)
    }

    fn validate_training_economics_canonical_sources(
        &self,
        stored: &StoredFuturePathLabel,
    ) -> Result<(), StorageError> {
        let decision = self
            .connection
            .query_row(
                r#"SELECT sequence, mint, quote_mint, venue, observed_at_unix_ms, price_quote
                   FROM fast_events
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![
                    stored.decision.event_id.signature,
                    i64::from(stored.decision.event_id.ordinal)
                ],
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
                StorageError::InvalidData(
                    "training economics canonical FL4 decision FastEvent is missing".to_owned(),
                )
            })?;

        let decision_sequence = u64::try_from(decision.0).map_err(|_| {
            StorageError::InvalidData(
                "training economics canonical decision sequence was negative".to_owned(),
            )
        })?;
        if decision_sequence != stored.decision.sequence
            || decision.1 != stored.decision.market.mint
            || decision.2 != stored.decision.market.quote_mint
            || decision.3 != stored.decision.market.venue.as_str()
            || decision.4 != stored.decision.observed_at_unix_ms
            || decision.5.to_bits() != stored.decision.executable_entry_price_quote.to_bits()
        {
            return Err(StorageError::InvalidData(
                "training economics FL4 decision does not match canonical FastEvent".to_owned(),
            ));
        }

        self.reject_training_economics_conflict(
            &stored.decision.event_id.signature,
            stored.decision.event_id.ordinal,
            stored.decision.market.venue,
            "decision",
        )?;

        if let Some(endpoint) = stored.label.endpoint_event_id.as_ref() {
            let canonical = self
                .connection
                .query_row(
                    r#"SELECT sequence, mint, quote_mint, venue, observed_at_unix_ms, price_quote
                       FROM fast_events
                       WHERE signature = ?1 AND ordinal = ?2"#,
                    params![endpoint.signature, i64::from(endpoint.ordinal)],
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
                    StorageError::InvalidData(
                        "training economics canonical FL4 endpoint FastEvent is missing".to_owned(),
                    )
                })?;

            let endpoint_sequence = u64::try_from(canonical.0).map_err(|_| {
                StorageError::InvalidData(
                    "training economics canonical endpoint sequence was negative".to_owned(),
                )
            })?;
            if endpoint_sequence <= stored.decision.sequence
                || canonical.1 != stored.decision.market.mint
                || canonical.2 != stored.decision.market.quote_mint
                || canonical.3 != stored.decision.market.venue.as_str()
                || Some(canonical.4) != stored.label.endpoint_observed_at_unix_ms
                || stored
                    .label
                    .endpoint_price_quote
                    .is_some_and(|value| canonical.5.to_bits() != value.to_bits())
            {
                return Err(StorageError::InvalidData(
                    "training economics FL4 endpoint does not match canonical FastEvent".to_owned(),
                ));
            }
            self.reject_training_economics_conflict(
                &endpoint.signature,
                endpoint.ordinal,
                stored.decision.market.venue,
                "endpoint",
            )?;
        }

        Ok(())
    }

    fn training_economics_endpoint_sequence(
        &self,
        stored: &StoredFuturePathLabel,
    ) -> Result<Option<u64>, StorageError> {
        let Some(endpoint) = stored.label.endpoint_event_id.as_ref() else {
            return Ok(None);
        };
        let sequence = self
            .connection
            .query_row(
                "SELECT sequence FROM fast_events WHERE signature = ?1 AND ordinal = ?2",
                params![endpoint.signature, i64::from(endpoint.ordinal)],
                |row| row.get::<_, i64>(0),
            )
            .optional()?
            .ok_or_else(|| {
                StorageError::InvalidData(
                    "training economics canonical endpoint FastEvent is missing".to_owned(),
                )
            })?;
        u64::try_from(sequence).map(Some).map_err(|_| {
            StorageError::InvalidData(
                "training economics canonical endpoint sequence was negative".to_owned(),
            )
        })
    }

    fn reject_training_economics_conflict(
        &self,
        signature: &str,
        ordinal: u32,
        venue: VenueId,
        role: &str,
    ) -> Result<(), StorageError> {
        let table = match venue {
            VenueId::PumpFunBondingCurve => "pump_trade_evidence_conflicts",
            VenueId::PumpSwap => "pump_swap_trade_evidence_conflicts",
            _ => {
                return Err(StorageError::InvalidData(format!(
                    "training economics unsupported canonical venue '{}'",
                    venue.as_str()
                )));
            }
        };
        let found = self
            .connection
            .query_row(
                &format!(
                    "SELECT 1 FROM {table} WHERE signature = ?1 AND ordinal = ?2 LIMIT 1"
                ),
                params![signature, i64::from(ordinal)],
                |_| Ok(()),
            )
            .optional()?;
        if found.is_some() {
            return Err(StorageError::InvalidData(format!(
                "training economics canonical {role} source is conflict-quarantined"
            )));
        }
        Ok(())
    }
}


fn base_overlay_row(
    stored: &StoredFuturePathLabel,
    endpoint_sequence: Option<u64>,
    counterfactual_base_quantity: &str,
) -> FastTrainingEconomicsOverlayRow {
    FastTrainingEconomicsOverlayRow {
        decision_signature: stored.decision.event_id.signature.clone(),
        decision_ordinal: stored.decision.event_id.ordinal,
        decision_sequence: stored.decision.sequence,
        decision_observed_at_unix_ms: stored.decision.observed_at_unix_ms,
        mint: stored.decision.market.mint.clone(),
        quote_mint: stored.decision.market.quote_mint.clone(),
        venue: stored.decision.market.venue.as_str().to_owned(),
        horizon_ms: stored.label.horizon_ms,
        future_path_label_version: stored.label.version,
        counterfactual_base_quantity: counterfactual_base_quantity.to_owned(),
        endpoint_signature: stored
            .label
            .endpoint_event_id
            .as_ref()
            .map(|value| value.signature.clone()),
        endpoint_ordinal: stored
            .label
            .endpoint_event_id
            .as_ref()
            .map(|value| value.ordinal),
        endpoint_sequence,
        endpoint_observed_at_unix_ms: stored.label.endpoint_observed_at_unix_ms,
        status: FastTrainingEconomicsStatus::UnsupportedVenue,
        requested_base_quantity_raw: None,
        entry_reserve: None,
        exit_reserve: None,
        entry_projection: None,
        exit_projection: None,
        entry_fee: None,
        exit_fee: None,
    }
}

fn find_replay_event<'a>(
    replay: &'a [StoredFastEvent],
    signature: &str,
    ordinal: u32,
    sequence: u64,
    role: &str,
) -> Result<&'a StoredFastEvent, StorageError> {
    replay
        .iter()
        .find(|stored| {
            stored.event.id.signature == signature
                && stored.event.id.ordinal == ordinal
                && stored.event.sequence == sequence
        })
        .ok_or_else(|| {
            StorageError::InvalidData(format!(
                "training economics canonical {role} event was not found in reserve-aware replay"
            ))
        })
}

fn pump_swap_reserve_provenance(
    stored: &StoredFastEvent,
) -> Result<Option<FastTrainingEconomicsReserveProvenance>, StorageError> {
    match stored.event.reserve_context.as_ref() {
        Some(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw,
            pool_quote_reserve_raw,
            virtual_quote_reserve_raw,
            base_decimals,
            quote_decimals,
        }) => {
            let Some(virtual_quote_reserve_raw) = virtual_quote_reserve_raw else {
                return Ok(None);
            };
            Ok(Some(FastTrainingEconomicsReserveProvenance {
                source_signature: stored.event.id.signature.clone(),
                source_ordinal: stored.event.id.ordinal,
                source_sequence: stored.event.sequence,
                source_observed_at_unix_ms: stored.source_observed_at_unix_ms,
                pool_base_reserve_raw: *pool_base_reserve_raw,
                pool_quote_reserve_raw: *pool_quote_reserve_raw,
                virtual_quote_reserve_raw: *virtual_quote_reserve_raw,
                base_decimals: *base_decimals,
                quote_decimals: *quote_decimals,
            }))
        }
        Some(other) => Err(StorageError::InvalidData(format!(
            "training economics PumpSwap event carried incompatible reserve context: {other:?}"
        ))),
        None => Err(StorageError::InvalidData(
            "training economics PumpSwap canonical replay omitted reserve context".to_owned(),
        )),
    }
}

fn reserve_context_from_provenance(
    value: &FastTrainingEconomicsReserveProvenance,
) -> FastReserveContext {
    FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: value.pool_base_reserve_raw,
        pool_quote_reserve_raw: value.pool_quote_reserve_raw,
        virtual_quote_reserve_raw: Some(value.virtual_quote_reserve_raw),
        base_decimals: value.base_decimals,
        quote_decimals: value.quote_decimals,
    }
}

fn fee_provenance(
    value: PumpSwapEffectiveFeeContextValue,
) -> Result<FastTrainingEconomicsFeeProvenance, StorageError> {
    let effective_fee_bps = value.evidence.effective_fee_bps.ok_or_else(|| {
        StorageError::InvalidData(
            "training economics available fee context omitted exact fee bps".to_owned(),
        )
    })?;
    Ok(FastTrainingEconomicsFeeProvenance {
        source_signature: value.evidence.signature,
        source_ordinal: value.evidence.ordinal,
        source_sequence: value.source_sequence,
        source_observed_at_unix_ms: value.source_observed_at_unix_ms,
        age_ms: value.age_ms,
        market_quote_amount_raw: value.evidence.market_quote_amount_raw,
        user_quote_amount_raw: value.evidence.user_quote_amount_raw,
        signed_user_cost_quote_raw: value.evidence.signed_user_cost_quote_raw,
        effective_fee_bps,
    })
}

#[derive(Debug, Clone, Copy)]
struct ParsedDecimalQuantity {
    coefficient: u128,
    scale10: i32,
}

fn validate_decimal_quantity_text(input: &str) -> Result<(), StorageError> {
    let parsed = parse_decimal_quantity(input)?;
    if parsed.coefficient == 0 {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity must be positive".to_owned(),
        ));
    }
    Ok(())
}

pub fn decimal_quantity_to_raw(
    input: &str,
    base_decimals: u8,
) -> Result<u64, StorageError> {
    let parsed = parse_decimal_quantity(input)?;
    if parsed.coefficient == 0 {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity must be positive".to_owned(),
        ));
    }

    let net_power = parsed
        .scale10
        .checked_add(i32::from(base_decimals))
        .ok_or_else(|| {
            StorageError::InvalidData(
                "training economics decimal quantity exponent overflowed".to_owned(),
            )
        })?;

    let raw = if net_power >= 0 {
        let factor = checked_pow10(u32::try_from(net_power).map_err(|_| {
            StorageError::InvalidData(
                "training economics decimal quantity exponent is outside u32".to_owned(),
            )
        })?)?;
        parsed.coefficient.checked_mul(factor).ok_or_else(|| {
            StorageError::InvalidData(
                "training economics decimal quantity raw conversion overflowed".to_owned(),
            )
        })?
    } else {
        let magnitude = net_power.checked_neg().ok_or_else(|| {
            StorageError::InvalidData(
                "training economics decimal quantity negative exponent overflowed".to_owned(),
            )
        })?;
        let divisor = checked_pow10(u32::try_from(magnitude).map_err(|_| {
            StorageError::InvalidData(
                "training economics decimal quantity exponent is outside u32".to_owned(),
            )
        })?)?;
        if parsed.coefficient % divisor != 0 {
            return Err(StorageError::InvalidData(
                "training economics counterfactual base quantity cannot be represented exactly in raw base units"
                    .to_owned(),
            ));
        }
        parsed.coefficient / divisor
    };

    if raw == 0 {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity rounds below one raw unit"
                .to_owned(),
        ));
    }
    u64::try_from(raw).map_err(|_| {
        StorageError::InvalidData(
            "training economics counterfactual base quantity exceeds u64 raw units".to_owned(),
        )
    })
}

fn parse_decimal_quantity(input: &str) -> Result<ParsedDecimalQuantity, StorageError> {
    if input.is_empty() || input != input.trim() {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity must be canonical decimal text"
                .to_owned(),
        ));
    }
    let input = input.strip_prefix('+').unwrap_or(input);
    if input.is_empty() || input.starts_with('-') {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity must be positive decimal text"
                .to_owned(),
        ));
    }

    let mut exponent_split = input.split(|character| character == 'e' || character == 'E');
    let mantissa = exponent_split.next().unwrap_or_default();
    let exponent_text = exponent_split.next();
    if exponent_split.next().is_some() {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity has multiple exponents".to_owned(),
        ));
    }
    let exponent = match exponent_text {
        Some(value) if !value.is_empty() => value.parse::<i32>().map_err(|_| {
            StorageError::InvalidData(
                "training economics counterfactual base quantity exponent is invalid".to_owned(),
            )
        })?,
        Some(_) => {
            return Err(StorageError::InvalidData(
                "training economics counterfactual base quantity exponent is empty".to_owned(),
            ));
        }
        None => 0,
    };

    let mut decimal_split = mantissa.split('.');
    let integer = decimal_split.next().unwrap_or_default();
    let fraction = decimal_split.next();
    if decimal_split.next().is_some() {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity has multiple decimal points"
                .to_owned(),
        ));
    }
    let fraction = fraction.unwrap_or("");
    if integer.is_empty() && fraction.is_empty() {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity has no digits".to_owned(),
        ));
    }
    if !integer.bytes().all(|value| value.is_ascii_digit())
        || !fraction.bytes().all(|value| value.is_ascii_digit())
    {
        return Err(StorageError::InvalidData(
            "training economics counterfactual base quantity must contain decimal digits only"
                .to_owned(),
        ));
    }

    let mut coefficient = 0_u128;
    for digit in integer.bytes().chain(fraction.bytes()) {
        coefficient = coefficient
            .checked_mul(10)
            .and_then(|value| value.checked_add(u128::from(digit - b'0')))
            .ok_or_else(|| {
                StorageError::InvalidData(
                    "training economics counterfactual base quantity coefficient overflowed"
                        .to_owned(),
                )
            })?;
    }
    let fractional_digits = i32::try_from(fraction.len()).map_err(|_| {
        StorageError::InvalidData(
            "training economics counterfactual base quantity has too many fractional digits"
                .to_owned(),
        )
    })?;
    let scale10 = exponent.checked_sub(fractional_digits).ok_or_else(|| {
        StorageError::InvalidData(
            "training economics counterfactual base quantity scale overflowed".to_owned(),
        )
    })?;
    Ok(ParsedDecimalQuantity {
        coefficient,
        scale10,
    })
}

fn checked_pow10(exponent: u32) -> Result<u128, StorageError> {
    let mut value = 1_u128;
    for _ in 0..exponent {
        value = value.checked_mul(10).ok_or_else(|| {
            StorageError::InvalidData(
                "training economics decimal quantity power-of-ten overflowed".to_owned(),
            )
        })?;
    }
    Ok(value)
}

fn validate_feature_population(
    supplied: &[FastTrainingFeatureRecord],
    expected: &[FastTrainingFeatureRecord],
) -> Result<(), StorageError> {
    if supplied.len() != expected.len() || supplied.is_empty() {
        return Err(StorageError::InvalidData(
            "training economics feature/FL4 decision identity mismatch".to_owned(),
        ));
    }

    let supplied_identities = supplied.iter().map(feature_identity).collect::<Vec<_>>();
    let expected_identities = expected.iter().map(feature_identity).collect::<Vec<_>>();
    if supplied_identities != expected_identities {
        return Err(StorageError::InvalidData(
            "training economics feature/FL4 decision identity mismatch".to_owned(),
        ));
    }
    Ok(())
}

fn feature_identity(
    value: &FastTrainingFeatureRecord,
) -> (String, u32, u64, String, String, String, i64) {
    (
        value.decision_signature.clone(),
        value.decision_ordinal,
        value.decision_sequence,
        value.mint.clone(),
        value.quote_mint.clone(),
        value.venue.clone(),
        value.decision_observed_at_unix_ms,
    )
}

fn future_path_logical_fingerprint(
    labels: &[StoredFuturePathLabel],
) -> Result<String, StorageError> {
    if labels.is_empty() {
        return Err(StorageError::InvalidData(
            "future-path training label dataset cannot be empty".to_owned(),
        ));
    }
    let payload = labels
        .iter()
        .map(future_path_fingerprint_row)
        .collect::<Result<Vec<_>, _>>()?;
    let encoded = serde_json::to_vec(&payload).map_err(|error| {
        StorageError::InvalidData(format!(
            "future-path logical fingerprint serialization failed: {error}"
        ))
    })?;
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

fn future_path_fingerprint_row(
    stored: &StoredFuturePathLabel,
) -> Result<BTreeMap<String, Value>, StorageError> {
    let mut row = BTreeMap::new();
    row.insert(
        "decision_signature".to_owned(),
        Value::String(stored.decision.event_id.signature.clone()),
    );
    row.insert(
        "decision_ordinal".to_owned(),
        Value::from(stored.decision.event_id.ordinal),
    );
    row.insert(
        "decision_sequence".to_owned(),
        Value::from(stored.decision.sequence),
    );
    row.insert(
        "decision_mint".to_owned(),
        Value::String(stored.decision.market.mint.clone()),
    );
    row.insert(
        "decision_quote_mint".to_owned(),
        Value::String(stored.decision.market.quote_mint.clone()),
    );
    row.insert(
        "decision_venue".to_owned(),
        Value::String(stored.decision.market.venue.as_str().to_owned()),
    );
    row.insert(
        "decision_observed_at_unix_ms".to_owned(),
        Value::from(stored.decision.observed_at_unix_ms),
    );
    row.insert(
        "decision_entry_price_quote".to_owned(),
        fingerprint_float(stored.decision.executable_entry_price_quote)?,
    );
    row.insert(
        "decision_entry_total_quote".to_owned(),
        fingerprint_optional_float(stored.decision.entry_total_quote)?,
    );
    row.insert(
        "coverage_complete_through_unix_ms".to_owned(),
        Value::from(stored.coverage.complete_through_unix_ms),
    );
    row.insert(
        "coverage_contiguous".to_owned(),
        Value::Bool(stored.coverage.contiguous),
    );
    row.insert("horizon_ms".to_owned(), Value::from(stored.label.horizon_ms));
    row.insert(
        "label_version".to_owned(),
        Value::from(stored.label.version),
    );
    row.insert(
        "completeness".to_owned(),
        Value::String(match stored.label.completeness {
            FuturePathCompleteness::Complete => "complete",
            FuturePathCompleteness::Incomplete => "incomplete",
        }
        .to_owned()),
    );
    row.insert("event_count".to_owned(), Value::from(stored.label.event_count));
    row.insert(
        "no_trade_events".to_owned(),
        Value::Bool(stored.label.no_trade_events),
    );
    row.insert(
        "endpoint_signature".to_owned(),
        stored
            .label
            .endpoint_event_id
            .as_ref()
            .map(|value| Value::String(value.signature.clone()))
            .unwrap_or(Value::Null),
    );
    row.insert(
        "endpoint_ordinal".to_owned(),
        stored
            .label
            .endpoint_event_id
            .as_ref()
            .map(|value| Value::from(value.ordinal))
            .unwrap_or(Value::Null),
    );
    row.insert(
        "endpoint_observed_at_unix_ms".to_owned(),
        stored
            .label
            .endpoint_observed_at_unix_ms
            .map(Value::from)
            .unwrap_or(Value::Null),
    );
    row.insert(
        "endpoint_price_quote".to_owned(),
        fingerprint_optional_float(stored.label.endpoint_price_quote)?,
    );
    row.insert(
        "endpoint_return_bps".to_owned(),
        fingerprint_optional_float(stored.label.endpoint_return_bps)?,
    );
    row.insert(
        "mfe_bps".to_owned(),
        fingerprint_optional_float(stored.label.mfe_bps)?,
    );
    row.insert(
        "mae_bps".to_owned(),
        fingerprint_optional_float(stored.label.mae_bps)?,
    );
    row.insert(
        "time_to_peak_ms".to_owned(),
        stored
            .label
            .time_to_peak_ms
            .map(Value::from)
            .unwrap_or(Value::Null),
    );
    row.insert(
        "time_to_trough_ms".to_owned(),
        stored
            .label
            .time_to_trough_ms
            .map(Value::from)
            .unwrap_or(Value::Null),
    );
    row.insert(
        "reversal_occurred".to_owned(),
        stored
            .label
            .reversal_occurred
            .map(Value::Bool)
            .unwrap_or(Value::Null),
    );
    row.insert(
        "first_reversal_after_ms".to_owned(),
        stored
            .label
            .first_reversal_after_ms
            .map(Value::from)
            .unwrap_or(Value::Null),
    );
    row.insert(
        "min_exit_capacity_base".to_owned(),
        fingerprint_optional_float(stored.label.min_exit_capacity_base)?,
    );
    row.insert(
        "endpoint_exit_capacity_base".to_owned(),
        fingerprint_optional_float(stored.label.endpoint_exit_capacity_base)?,
    );
    row.insert(
        "route_unavailability_observed".to_owned(),
        stored
            .label
            .route_unavailability_observed
            .map(Value::Bool)
            .unwrap_or(Value::Null),
    );
    row.insert(
        "best_cost_adjusted_return_bps".to_owned(),
        fingerprint_optional_float(stored.label.best_cost_adjusted_return_bps)?,
    );
    row.insert(
        "endpoint_cost_adjusted_return_bps".to_owned(),
        fingerprint_optional_float(stored.label.endpoint_cost_adjusted_return_bps)?,
    );
    Ok(row)
}

fn fingerprint_optional_float(value: Option<f64>) -> Result<Value, StorageError> {
    value.map(fingerprint_float).transpose().map(|value| value.unwrap_or(Value::Null))
}

fn fingerprint_float(value: f64) -> Result<Value, StorageError> {
    if !value.is_finite() {
        return Err(StorageError::InvalidData(
            "future-path logical fingerprint rejects non-finite floats".to_owned(),
        ));
    }
    let mut object = serde_json::Map::new();
    object.insert(
        "__float_hex__".to_owned(),
        Value::String(python_float_hex(value)?),
    );
    Ok(Value::Object(object))
}

pub fn python_float_hex(value: f64) -> Result<String, StorageError> {
    if !value.is_finite() {
        return Err(StorageError::InvalidData(
            "Python float.hex compatibility requires a finite value".to_owned(),
        ));
    }
    let bits = value.to_bits();
    let negative = bits >> 63 != 0;
    let exponent_bits = ((bits >> 52) & 0x7ff) as i32;
    let mantissa = bits & 0x000f_ffff_ffff_ffff;
    let sign = if negative { "-" } else { "" };

    if exponent_bits == 0 {
        if mantissa == 0 {
            return Ok(format!("{sign}0x0.0p+0"));
        }
        return Ok(format!("{sign}0x0.{mantissa:013x}p-1022"));
    }

    let exponent = exponent_bits - 1023;
    Ok(format!("{sign}0x1.{mantissa:013x}p{exponent:+}"))
}

#[cfg(test)]
mod tests {
    use super::python_float_hex;

    #[test]
    fn python_float_hex_matches_python_normal_and_zero_shapes() {
        assert_eq!(python_float_hex(1.0).unwrap(), "0x1.0000000000000p+0");
        assert_eq!(python_float_hex(0.5).unwrap(), "0x1.0000000000000p-1");
        assert_eq!(python_float_hex(-0.0).unwrap(), "-0x0.0p+0");
        assert_eq!(
            python_float_hex(f64::from_bits(1)).unwrap(),
            "0x0.0000000000001p-1022"
        );
    }
}
