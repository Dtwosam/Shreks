use rusqlite::{params, OptionalExtension, Row};
use shreks_core::{
    ProviderId, VenueId, WalletActionKind, WalletObservation, WalletObservationEvidence,
};

use crate::{ShreksDb, StorageError};

const MAX_WALLET_OBSERVATION_QUERY_LIMIT: usize = 10_000;

/// Result of durably recording one normalized wallet observation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WalletObservationWrite {
    Inserted,
    AlreadyPresent,
}

impl ShreksDb {
    /// Record one normalized wallet action around a known candidate mint.
    ///
    /// Event identity is provider/signature/event-index/wallet/mint. Exact
    /// replays are idempotent and preserve the earliest local observation
    /// timestamp; contradictory replays fail closed without rewriting history.
    pub fn record_wallet_observation(
        &self,
        observation: &WalletObservation,
    ) -> Result<WalletObservationWrite, StorageError> {
        validate_wallet_observation(observation)?;
        ensure_candidate_mint_exists(self, &observation.candidate_mint)?;

        let event_index = i64::from(observation.event_index);
        let existing = self
            .connection
            .query_row(
                r#"SELECT
                       candidate_mint, provider, wallet, action, evidence, signature,
                       event_index, slot, observed_at_unix_ms, occurred_at_unix_ms,
                       candidate_token_delta_raw, counter_asset_mint,
                       counter_asset_delta_raw, venue, counterparty
                   FROM wallet_observations
                   WHERE provider = ?1
                     AND signature = ?2
                     AND event_index = ?3
                     AND wallet = ?4
                     AND candidate_mint = ?5"#,
                params![
                    observation.provider.as_str(),
                    observation.signature.as_str(),
                    event_index,
                    observation.wallet.as_str(),
                    observation.candidate_mint.as_str(),
                ],
                stored_wallet_observation_from_row,
            )
            .optional()?;

        if let Some(existing) = existing {
            let existing = existing.into_domain()?;
            if !same_immutable_event(&existing, observation) {
                return Err(StorageError::InvalidData(format!(
                    "wallet observation replay contradicts stored event {}:{}:{}:{}:{}",
                    observation.provider.as_str(),
                    observation.signature,
                    observation.event_index,
                    observation.wallet,
                    observation.candidate_mint
                )));
            }

            self.connection.execute(
                r#"UPDATE wallet_observations
                   SET observed_at_unix_ms = MIN(observed_at_unix_ms, ?6)
                   WHERE provider = ?1
                     AND signature = ?2
                     AND event_index = ?3
                     AND wallet = ?4
                     AND candidate_mint = ?5"#,
                params![
                    observation.provider.as_str(),
                    observation.signature.as_str(),
                    event_index,
                    observation.wallet.as_str(),
                    observation.candidate_mint.as_str(),
                    observation.observed_at_unix_ms,
                ],
            )?;
            return Ok(WalletObservationWrite::AlreadyPresent);
        }

        let slot = observation.slot.to_string();
        let candidate_token_delta_raw = observation
            .candidate_token_delta_raw
            .map(|value| value.to_string());
        let counter_asset_delta_raw = observation
            .counter_asset_delta_raw
            .map(|value| value.to_string());

        self.connection.execute(
            r#"INSERT INTO wallet_observations (
                   candidate_mint, provider, wallet, action, evidence, signature,
                   event_index, slot, observed_at_unix_ms, occurred_at_unix_ms,
                   candidate_token_delta_raw, counter_asset_mint,
                   counter_asset_delta_raw, venue, counterparty
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15
               )"#,
            params![
                observation.candidate_mint.as_str(),
                observation.provider.as_str(),
                observation.wallet.as_str(),
                observation.action.as_str(),
                observation.evidence.as_str(),
                observation.signature.as_str(),
                event_index,
                slot,
                observation.observed_at_unix_ms,
                observation.occurred_at_unix_ms,
                candidate_token_delta_raw,
                observation.counter_asset_mint.as_deref(),
                counter_asset_delta_raw,
                observation.venue.map(VenueId::as_str),
                observation.counterparty.as_deref(),
            ],
        )?;

        Ok(WalletObservationWrite::Inserted)
    }

    /// Load candidate-mint wallet observations in deterministic chronological order.
    pub fn wallet_observations_for_mint(
        &self,
        mint: &str,
        observed_from_unix_ms: i64,
        observed_through_unix_ms: i64,
        limit: usize,
    ) -> Result<Vec<WalletObservation>, StorageError> {
        validate_query("candidate mint", mint, observed_from_unix_ms, observed_through_unix_ms, limit)?;
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("wallet observation query limit is too large".to_owned())
        })?;
        let mut statement = self.connection.prepare(
            r#"SELECT
                   candidate_mint, provider, wallet, action, evidence, signature,
                   event_index, slot, observed_at_unix_ms, occurred_at_unix_ms,
                   candidate_token_delta_raw, counter_asset_mint,
                   counter_asset_delta_raw, venue, counterparty
               FROM wallet_observations
               WHERE candidate_mint = ?1
                 AND observed_at_unix_ms >= ?2
                 AND observed_at_unix_ms <= ?3
               ORDER BY observed_at_unix_ms ASC,
                        provider ASC,
                        signature ASC,
                        event_index ASC,
                        wallet ASC,
                        candidate_mint ASC
               LIMIT ?4"#,
        )?;
        let rows = statement.query_map(
            params![mint, observed_from_unix_ms, observed_through_unix_ms, limit],
            stored_wallet_observation_from_row,
        )?;
        collect_wallet_observations(rows)
    }

    /// Load wallet history in deterministic chronological order.
    pub fn wallet_observations_for_wallet(
        &self,
        wallet: &str,
        observed_from_unix_ms: i64,
        observed_through_unix_ms: i64,
        limit: usize,
    ) -> Result<Vec<WalletObservation>, StorageError> {
        validate_query("wallet", wallet, observed_from_unix_ms, observed_through_unix_ms, limit)?;
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("wallet observation query limit is too large".to_owned())
        })?;
        let mut statement = self.connection.prepare(
            r#"SELECT
                   candidate_mint, provider, wallet, action, evidence, signature,
                   event_index, slot, observed_at_unix_ms, occurred_at_unix_ms,
                   candidate_token_delta_raw, counter_asset_mint,
                   counter_asset_delta_raw, venue, counterparty
               FROM wallet_observations
               WHERE wallet = ?1
                 AND observed_at_unix_ms >= ?2
                 AND observed_at_unix_ms <= ?3
               ORDER BY observed_at_unix_ms ASC,
                        provider ASC,
                        signature ASC,
                        event_index ASC,
                        candidate_mint ASC,
                        wallet ASC
               LIMIT ?4"#,
        )?;
        let rows = statement.query_map(
            params![wallet, observed_from_unix_ms, observed_through_unix_ms, limit],
            stored_wallet_observation_from_row,
        )?;
        collect_wallet_observations(rows)
    }
}

#[derive(Debug)]
struct StoredWalletObservation {
    candidate_mint: String,
    provider: String,
    wallet: String,
    action: String,
    evidence: String,
    signature: String,
    event_index: i64,
    slot: String,
    observed_at_unix_ms: i64,
    occurred_at_unix_ms: Option<i64>,
    candidate_token_delta_raw: Option<String>,
    counter_asset_mint: Option<String>,
    counter_asset_delta_raw: Option<String>,
    venue: Option<String>,
    counterparty: Option<String>,
}

impl StoredWalletObservation {
    fn into_domain(self) -> Result<WalletObservation, StorageError> {
        let event_index = u32::try_from(self.event_index).map_err(|_| {
            StorageError::InvalidData("wallet observation event_index is out of u32 range".to_owned())
        })?;
        let observation = WalletObservation {
            provider: parse_provider(&self.provider)?,
            wallet: self.wallet,
            candidate_mint: self.candidate_mint,
            action: parse_action(&self.action)?,
            evidence: parse_evidence(&self.evidence)?,
            signature: self.signature,
            event_index,
            slot: parse_canonical_u64(&self.slot, "wallet observation slot")?,
            observed_at_unix_ms: self.observed_at_unix_ms,
            occurred_at_unix_ms: self.occurred_at_unix_ms,
            candidate_token_delta_raw: parse_optional_canonical_i128(
                self.candidate_token_delta_raw.as_deref(),
                "wallet observation candidate token delta",
            )?,
            counter_asset_mint: self.counter_asset_mint,
            counter_asset_delta_raw: parse_optional_canonical_i128(
                self.counter_asset_delta_raw.as_deref(),
                "wallet observation counter-asset delta",
            )?,
            venue: self.venue.as_deref().map(parse_venue).transpose()?,
            counterparty: self.counterparty,
        };
        validate_wallet_observation(&observation)?;
        Ok(observation)
    }
}

fn stored_wallet_observation_from_row(row: &Row<'_>) -> rusqlite::Result<StoredWalletObservation> {
    Ok(StoredWalletObservation {
        candidate_mint: row.get(0)?,
        provider: row.get(1)?,
        wallet: row.get(2)?,
        action: row.get(3)?,
        evidence: row.get(4)?,
        signature: row.get(5)?,
        event_index: row.get(6)?,
        slot: row.get(7)?,
        observed_at_unix_ms: row.get(8)?,
        occurred_at_unix_ms: row.get(9)?,
        candidate_token_delta_raw: row.get(10)?,
        counter_asset_mint: row.get(11)?,
        counter_asset_delta_raw: row.get(12)?,
        venue: row.get(13)?,
        counterparty: row.get(14)?,
    })
}

fn collect_wallet_observations(
    rows: rusqlite::MappedRows<'_, impl FnMut(&Row<'_>) -> rusqlite::Result<StoredWalletObservation>>,
) -> Result<Vec<WalletObservation>, StorageError> {
    let mut observations = Vec::new();
    for row in rows {
        observations.push(row?.into_domain()?);
    }
    Ok(observations)
}

fn validate_wallet_observation(observation: &WalletObservation) -> Result<(), StorageError> {
    require_non_blank("wallet observation wallet", &observation.wallet)?;
    require_non_blank("wallet observation candidate mint", &observation.candidate_mint)?;
    require_non_blank("wallet observation signature", &observation.signature)?;
    if observation.observed_at_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "wallet observation local timestamp must be nonnegative".to_owned(),
        ));
    }
    if observation
        .occurred_at_unix_ms
        .is_some_and(|value| value < 0)
    {
        return Err(StorageError::InvalidData(
            "wallet observation chain timestamp must be nonnegative when present".to_owned(),
        ));
    }
    if let Some(counter_asset_mint) = observation.counter_asset_mint.as_deref() {
        require_non_blank("wallet observation counter-asset mint", counter_asset_mint)?;
    }
    if observation.counter_asset_delta_raw.is_some() && observation.counter_asset_mint.is_none() {
        return Err(StorageError::InvalidData(
            "wallet observation counter-asset delta requires counter-asset mint".to_owned(),
        ));
    }
    if let Some(counterparty) = observation.counterparty.as_deref() {
        require_non_blank("wallet observation counterparty", counterparty)?;
    }
    Ok(())
}

fn validate_query(
    key_name: &str,
    key: &str,
    observed_from_unix_ms: i64,
    observed_through_unix_ms: i64,
    limit: usize,
) -> Result<(), StorageError> {
    require_non_blank(key_name, key)?;
    if observed_from_unix_ms < 0 || observed_through_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "wallet observation query timestamps must be nonnegative".to_owned(),
        ));
    }
    if observed_from_unix_ms > observed_through_unix_ms {
        return Err(StorageError::InvalidData(
            "wallet observation query start must not exceed end".to_owned(),
        ));
    }
    if !(1..=MAX_WALLET_OBSERVATION_QUERY_LIMIT).contains(&limit) {
        return Err(StorageError::InvalidData(format!(
            "wallet observation query limit must be within 1..={MAX_WALLET_OBSERVATION_QUERY_LIMIT}"
        )));
    }
    Ok(())
}

fn ensure_candidate_mint_exists(db: &ShreksDb, mint: &str) -> Result<(), StorageError> {
    let exists = db
        .connection
        .query_row(
            "SELECT 1 FROM token_candidates WHERE mint = ?1 LIMIT 1",
            [mint],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !exists {
        return Err(StorageError::InvalidData(format!(
            "wallet observation candidate mint '{mint}' is not known"
        )));
    }
    Ok(())
}

fn same_immutable_event(left: &WalletObservation, right: &WalletObservation) -> bool {
    left.provider == right.provider
        && left.wallet == right.wallet
        && left.candidate_mint == right.candidate_mint
        && left.action == right.action
        && left.evidence == right.evidence
        && left.signature == right.signature
        && left.event_index == right.event_index
        && left.slot == right.slot
        && left.occurred_at_unix_ms == right.occurred_at_unix_ms
        && left.candidate_token_delta_raw == right.candidate_token_delta_raw
        && left.counter_asset_mint == right.counter_asset_mint
        && left.counter_asset_delta_raw == right.counter_asset_delta_raw
        && left.venue == right.venue
        && left.counterparty == right.counterparty
}

fn require_non_blank(name: &str, value: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!(
            "{name} must not be blank"
        )));
    }
    Ok(())
}

fn parse_canonical_u64(value: &str, field: &str) -> Result<u64, StorageError> {
    let parsed = value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not a u64: {error}"))
    })?;
    if parsed.to_string() != value {
        return Err(StorageError::InvalidData(format!(
            "{field} is not canonical decimal text"
        )));
    }
    Ok(parsed)
}

fn parse_optional_canonical_i128(
    value: Option<&str>,
    field: &str,
) -> Result<Option<i128>, StorageError> {
    value
        .map(|value| {
            let parsed = value.parse::<i128>().map_err(|error| {
                StorageError::InvalidData(format!("{field} is not an i128: {error}"))
            })?;
            if parsed.to_string() != value {
                return Err(StorageError::InvalidData(format!(
                    "{field} is not canonical decimal text"
                )));
            }
            Ok(parsed)
        })
        .transpose()
}

fn parse_provider(value: &str) -> Result<ProviderId, StorageError> {
    match value {
        "dexscreener" => Ok(ProviderId::DexScreener),
        "helius" => Ok(ProviderId::Helius),
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "unknown wallet observation provider '{other}'"
        ))),
    }
}

fn parse_venue(value: &str) -> Result<VenueId, StorageError> {
    match value {
        "pump_fun_bonding_curve" => Ok(VenueId::PumpFunBondingCurve),
        "pump_swap" => Ok(VenueId::PumpSwap),
        "meteora_dlmm" => Ok(VenueId::MeteoraDlmm),
        "meteora_damm_v2" => Ok(VenueId::MeteoraDammV2),
        "other_solana" => Ok(VenueId::OtherSolana),
        other => Err(StorageError::InvalidData(format!(
            "unknown wallet observation venue '{other}'"
        ))),
    }
}

fn parse_action(value: &str) -> Result<WalletActionKind, StorageError> {
    match value {
        "buy" => Ok(WalletActionKind::Buy),
        "sell" => Ok(WalletActionKind::Sell),
        "transfer" => Ok(WalletActionKind::Transfer),
        "liquidity_event" => Ok(WalletActionKind::LiquidityEvent),
        "creator_action" => Ok(WalletActionKind::CreatorAction),
        "other" => Ok(WalletActionKind::Other),
        other => Err(StorageError::InvalidData(format!(
            "unknown wallet observation action '{other}'"
        ))),
    }
}

fn parse_evidence(value: &str) -> Result<WalletObservationEvidence, StorageError> {
    match value {
        "direct" => Ok(WalletObservationEvidence::Direct),
        "inferred" => Ok(WalletObservationEvidence::Inferred),
        other => Err(StorageError::InvalidData(format!(
            "unknown wallet observation evidence '{other}'"
        ))),
    }
}
