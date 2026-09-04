//! Operational SQLite storage for Shreks.

mod conflict_quarantine;
mod execution_economics;
mod fast_baseline_batch;
mod fast_baseline_campaign;
mod fast_baseline_hydration;
mod fast_deterministic_candidate_manifest;
mod fast_deterministic_lifecycle;
mod fast_deterministic_lifecycle_wire;
mod fast_lane;
mod fast_lane_metadata;
mod future_path_generation;
mod fast_population_parity;
mod future_path_labels;
mod lifecycle;
mod outcomes;
mod pump_swap_fast_lane;
mod reserve_context;
mod safety_evidence;
mod training_features;
mod wallet;
pub use conflict_quarantine::EvidenceWriteOutcome;
pub use execution_economics::{
    PumpSwapExecutionEconomicsWrite, PumpTradeExecutionEconomicsWrite,
};
pub use fast_baseline_batch::{
    evaluate_fast_baseline_campaign_batch, FastBaselineCampaignBatchAssessment,
    FastBaselineCampaignBatchError, FastBaselineCampaignRequest,
    FAST_BASELINE_CAMPAIGN_BATCH_VERSION,
};
pub use fast_baseline_campaign::{
    evaluate_fast_baseline_campaign, FastBaselineCampaignAssessment, FastBaselineCampaignError,
    FastBaselineCampaignInput, FAST_BASELINE_CAMPAIGN_VERSION,
};
pub use fast_baseline_hydration::{
    hydrate_fast_baseline_snapshot, FastBaselineSnapshotHydration,
    FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
};
pub use fast_deterministic_candidate_manifest::{
    build_fast_deterministic_candidate_manifest,
    decode_fast_deterministic_candidate_manifest_json,
    encode_fast_deterministic_candidate_manifest_json,
    FastDeterministicCandidateManifestError, FastDeterministicCandidateManifestWire,
    FastDeterministicComponentPolicyWire, FastDeterministicEntryPolicyRef,
    FastDeterministicManagerPolicyRef,
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION,
    FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY,
};
pub use fast_deterministic_lifecycle::{
    evaluate_fast_deterministic_lifecycle_batch, FastDeterministicLifecycleBatchAssessment,
    FastDeterministicLifecycleDecision, FastDeterministicLifecycleError,
    FastDeterministicLifecyclePolicy, FastDeterministicLifecyclePostureInput,
    FastDeterministicLifecycleRequest, FAST_DETERMINISTIC_LIFECYCLE_VERSION,
};
pub use fast_deterministic_lifecycle_wire::{
    decode_fast_deterministic_lifecycle_results_json,
    encode_fast_deterministic_lifecycle_results_json, fast_deterministic_lifecycle_to_wire,
    FastDeterministicLifecycleDecisionWire, FastDeterministicLifecyclePolicyWire,
    FastDeterministicLifecycleResultsWire, FastDeterministicLifecycleWireError,
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME,
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
};
pub use fast_lane::{PumpTradeEvidenceWrite, StoredFastEvent};
pub use future_path_labels::StoredFuturePathLabel;
pub use fast_population_parity::{
    prove_fast_baseline_population_parity, FastBaselinePopulationParityError,
    FastBaselinePopulationParityProof, FAST_BASELINE_POPULATION_PARITY_VERSION,
};
pub use lifecycle::PumpMigrationSignalRecord;
pub use outcomes::{
    DueOutcomeCheckpoint, OutcomeCheckpointCompletion, OutcomeCheckpointRecord,
    OutcomeCheckpointStatus, OUTCOME_HORIZONS_SECONDS,
};
pub use pump_swap_fast_lane::{
    pump_swap_event_ordinal, PumpSwapMarket, PumpSwapTradeEvidenceWrite,
};
pub use reserve_context::{
    pump_reserve_context_from_source, pump_swap_reserve_context_from_source,
};
pub use training_features::{
    decode_fast_training_feature_record_json, FastTrainingFeatureExportManifest,
    FastTrainingFeatureRecord, FastTrainingLifecycleEvent,
    FastTrainingReserveContext, FastTrainingWindowSummary, FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
};
pub use wallet::WalletObservationWrite;

use std::{
    error::Error,
    fmt, fs,
    path::Path,
    time::{Duration, SystemTime, SystemTimeError, UNIX_EPOCH},
};

use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderHealthState, ProviderId, TokenMintState,
    TransactionWindow,
};

const BUSY_TIMEOUT_MS: u64 = 5_000;

struct Migration {
    version: i64,
    name: &'static str,
    sql: &'static str,
}

const MIGRATIONS: &[Migration] = &[
    Migration {
        version: 1,
        name: "operational",
        sql: include_str!("../migrations/0001_operational.sql"),
    },
    Migration {
        version: 2,
        name: "observer_normalization",
        sql: include_str!("../migrations/0002_observer_normalization.sql"),
    },
    Migration {
        version: 3,
        name: "pump_launch_signals",
        sql: include_str!("../migrations/0003_pump_launch_signals.sql"),
    },
    Migration {
        version: 4,
        name: "candidate_outcome_checkpoints",
        sql: include_str!("../migrations/0004_candidate_outcome_checkpoints.sql"),
    },
    Migration {
        version: 5,
        name: "pump_graduation_lifecycle",
        sql: include_str!("../migrations/0005_pump_graduation_lifecycle.sql"),
    },
    Migration {
        version: 6,
        name: "paper_loop_checkpoints",
        sql: include_str!("../migrations/0006_paper_loop_checkpoints.sql"),
    },
    Migration {
        version: 7,
        name: "wallet_observations",
        sql: include_str!("../migrations/0007_wallet_observations.sql"),
    },
    Migration {
        version: 8,
        name: "safety_evidence",
        sql: include_str!("../migrations/0008_safety_evidence.sql"),
    },
    Migration {
        version: 9,
        name: "paper_quote_purpose",
        sql: include_str!("../migrations/0009_paper_quote_purpose.sql"),
    },
    Migration {
        version: 10,
        name: "fast_lane_pump_trade_evidence",
        sql: include_str!("../migrations/0010_fast_lane_pump_trade_evidence.sql"),
    },
    Migration {
        version: 11,
        name: "fast_lane_canonical_events",
        sql: include_str!("../migrations/0011_fast_lane_canonical_events.sql"),
    },
    Migration {
        version: 12,
        name: "fast_lane_pumpswap_evidence",
        sql: include_str!("../migrations/0012_fast_lane_pumpswap_evidence.sql"),
    },
    Migration {
        version: 13,
        name: "fast_lane_conflict_quarantine",
        sql: include_str!("../migrations/0013_fast_lane_conflict_quarantine.sql"),
    },
    Migration {
        version: 14,
        name: "fast_lane_pumpswap_pool_lookup",
        sql: include_str!("../migrations/0014_fast_lane_pumpswap_pool_lookup.sql"),
    },
    Migration {
        version: 15,
        name: "fl3_execution_economics",
        sql: include_str!("../migrations/0015_fl3_execution_economics.sql"),
    },
    Migration {
        version: 16,
        name: "fast_future_path_labels",
        sql: include_str!("../migrations/0016_fast_future_path_labels.sql"),
    },
    Migration {
        version: 17,
        name: "fast_paper_skip_records",
        sql: include_str!("../migrations/0017_fast_paper_skip_records.sql"),
    },
];

/// Read-only operational diagnostics for a Shreks database connection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DatabaseDiagnostics {
    pub journal_mode: String,
    pub foreign_keys_enabled: bool,
    pub schema_version: i64,
}

/// Durable state of a Pump launch signal after it has entered the local inbox.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PumpSignalStatus {
    Pending,
    Verified,
    Rejected,
}

impl PumpSignalStatus {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Verified => "verified",
            Self::Rejected => "rejected",
        }
    }

    fn parse(value: &str) -> Result<Self, StorageError> {
        match value {
            "pending" => Ok(Self::Pending),
            "verified" => Ok(Self::Verified),
            "rejected" => Ok(Self::Rejected),
            other => Err(StorageError::InvalidData(format!(
                "unknown Pump signal status '{other}'"
            ))),
        }
    }
}

/// One durable Pump launch signal. Slots remain unsigned in memory and are
/// stored as decimal text so the full Solana u64 range is preserved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSignalRecord {
    pub signature: String,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
    pub status: PumpSignalStatus,
    pub attempt_count: u64,
    pub last_attempt_at_unix_ms: Option<i64>,
    pub candidate_id: Option<i64>,
    pub last_error: Option<String>,
}

/// Errors produced while opening, validating, migrating, or writing Shreks
/// operational storage.
#[derive(Debug)]
pub enum StorageError {
    Io(std::io::Error),
    Sqlite(rusqlite::Error),
    Clock(SystemTimeError),
    InvalidData(String),
}

impl fmt::Display for StorageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "storage filesystem error: {error}"),
            Self::Sqlite(error) => write!(formatter, "storage SQLite error: {error}"),
            Self::Clock(error) => write!(formatter, "storage clock error: {error}"),
            Self::InvalidData(message) => write!(formatter, "storage rejected invalid data: {message}"),
        }
    }
}

impl Error for StorageError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Sqlite(error) => Some(error),
            Self::Clock(error) => Some(error),
            Self::InvalidData(_) => None,
        }
    }
}

impl From<std::io::Error> for StorageError {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<rusqlite::Error> for StorageError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Sqlite(error)
    }
}

impl From<SystemTimeError> for StorageError {
    fn from(error: SystemTimeError) -> Self {
        Self::Clock(error)
    }
}

/// Owns one configured connection to the operational Shreks SQLite database.
pub struct ShreksDb {
    connection: Connection,
}

impl ShreksDb {
    /// Open or create a file-backed Shreks database and bring it to the latest
    /// known schema version before returning it to the caller.
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self, StorageError> {
        let path = path.as_ref();
        if let Some(parent) = path.parent().filter(|parent| !parent.as_os_str().is_empty()) {
            fs::create_dir_all(parent)?;
        }

        let mut connection = Connection::open(path)?;
        configure_connection(&connection)?;
        apply_migrations(&mut connection)?;

        Ok(Self { connection })
    }

    /// Open an existing current-schema database without creating, migrating,
    /// or mutating it. This is the only storage open path used by FL8 research
    /// exporters so historical feature generation cannot become operational
    /// database authority.
    pub fn open_existing_read_only<P: AsRef<Path>>(path: P) -> Result<Self, StorageError> {
        let path = path.as_ref();
        if !path.is_file() {
            return Err(StorageError::InvalidData(format!(
                "read-only Shreks database does not exist as a file: {}",
                path.display()
            )));
        }

        let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
        configure_read_only_connection(&connection)?;
        validate_current_schema(&connection)?;
        Ok(Self { connection })
    }

    /// Report configuration and migration state without exposing the raw
    /// SQLite connection to callers.
    pub fn diagnostics(&self) -> Result<DatabaseDiagnostics, StorageError> {
        let journal_mode = self
            .connection
            .query_row("PRAGMA journal_mode", [], |row| row.get::<_, String>(0))?;
        let foreign_keys: i64 = self
            .connection
            .query_row("PRAGMA foreign_keys", [], |row| row.get(0))?;
        let schema_version: i64 = self.connection.query_row(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
            [],
            |row| row.get(0),
        )?;

        Ok(DatabaseDiagnostics {
            journal_mode,
            foreign_keys_enabled: foreign_keys == 1,
            schema_version,
        })
    }

    /// Persist a discovered candidate without creating duplicate rows for the
    /// same mint/pair/source identity. The earliest discovery timestamp wins;
    /// later venue information may enrich an existing row.
    pub fn upsert_candidate(&self, candidate: &DiscoveredToken) -> Result<i64, StorageError> {
        if candidate.mint.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "candidate mint must not be empty".to_owned(),
            ));
        }

        let pair_address = candidate.pair_address.as_deref().unwrap_or("");
        let venue = candidate.venue.map(|value| value.as_str());
        let created_at = unix_time_ms()?;

        self.connection.execute(
            r#"INSERT INTO token_candidates (
                   mint, pair_address, discovery_source, discovered_at_unix_ms, created_at_unix_ms, venue
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
               ON CONFLICT(mint, pair_address, discovery_source) DO UPDATE SET
                   venue = COALESCE(excluded.venue, token_candidates.venue),
                   discovered_at_unix_ms = MIN(token_candidates.discovered_at_unix_ms, excluded.discovered_at_unix_ms)"#,
            params![
                candidate.mint,
                pair_address,
                candidate.source.as_str(),
                candidate.discovered_at_unix_ms,
                created_at,
                venue,
            ],
        )?;

        let id = self.connection.query_row(
            "SELECT id FROM token_candidates WHERE mint = ?1 AND pair_address = ?2 AND discovery_source = ?3",
            params![candidate.mint, pair_address, candidate.source.as_str()],
            |row| row.get(0),
        )?;
        Ok(id)
    }

    /// Durably accept one Pump log signal before any transaction fetch occurs.
    /// Duplicate signatures never reset terminal state and preserve the first
    /// local observation timestamp.
    pub fn record_pump_launch_signal(
        &self,
        signature: &str,
        slot: u64,
        observed_at_unix_ms: i64,
    ) -> Result<(), StorageError> {
        if signature.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "Pump launch signature must not be empty".to_owned(),
            ));
        }

        self.connection.execute(
            r#"INSERT INTO pump_launch_signals (
                   signature, slot, observed_at_unix_ms, status
               ) VALUES (?1, ?2, ?3, ?4)
               ON CONFLICT(signature) DO UPDATE SET
                   observed_at_unix_ms = MIN(
                       pump_launch_signals.observed_at_unix_ms,
                       excluded.observed_at_unix_ms
                   )"#,
            params![
                signature,
                slot.to_string(),
                observed_at_unix_ms,
                PumpSignalStatus::Pending.as_str(),
            ],
        )?;
        Ok(())
    }

    /// Return the oldest pending Pump signals for deterministic restart replay.
    pub fn pending_pump_launch_signals(
        &self,
        limit: usize,
    ) -> Result<Vec<PumpSignalRecord>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("Pump pending-signal limit exceeds i64".to_owned())
        })?;

        let mut statement = self.connection.prepare(
            r#"SELECT
                   signature, slot, observed_at_unix_ms, status, attempt_count,
                   last_attempt_at_unix_ms, candidate_id, last_error
               FROM pump_launch_signals
               WHERE status = 'pending'
               ORDER BY observed_at_unix_ms ASC, signature ASC
               LIMIT ?1"#,
        )?;
        let raw = statement
            .query_map([limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, i64>(4)?,
                    row.get::<_, Option<i64>>(5)?,
                    row.get::<_, Option<i64>>(6)?,
                    row.get::<_, Option<String>>(7)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        raw.into_iter()
            .map(
                |(
                    signature,
                    slot,
                    observed_at_unix_ms,
                    status,
                    attempt_count,
                    last_attempt_at_unix_ms,
                    candidate_id,
                    last_error,
                )| {
                    let slot = slot.parse::<u64>().map_err(|error| {
                        StorageError::InvalidData(format!(
                            "Pump signal slot is not u64 decimal text: {error}"
                        ))
                    })?;
                    let attempt_count = u64::try_from(attempt_count).map_err(|_| {
                        StorageError::InvalidData(
                            "Pump signal attempt count was negative".to_owned(),
                        )
                    })?;
                    Ok(PumpSignalRecord {
                        signature,
                        slot,
                        observed_at_unix_ms,
                        status: PumpSignalStatus::parse(&status)?,
                        attempt_count,
                        last_attempt_at_unix_ms,
                        candidate_id,
                        last_error,
                    })
                },
            )
            .collect()
    }

    /// Record one verification attempt while leaving the signal pending.
    pub fn record_pump_launch_attempt(
        &self,
        signature: &str,
        attempted_at_unix_ms: i64,
        error: Option<&str>,
    ) -> Result<(), StorageError> {
        validate_pump_signature(signature)?;
        let changed = self.connection.execute(
            r#"UPDATE pump_launch_signals
               SET attempt_count = attempt_count + 1,
                   last_attempt_at_unix_ms = ?2,
                   last_error = ?3
               WHERE signature = ?1 AND status = 'pending'"#,
            params![signature, attempted_at_unix_ms, error],
        )?;
        ensure_pump_signal_changed(changed, signature, "record attempt")
    }

    /// Mark a verified Pump signal and link it to the normalized token row.
    pub fn mark_pump_launch_verified(
        &self,
        signature: &str,
        candidate_id: i64,
    ) -> Result<(), StorageError> {
        validate_pump_signature(signature)?;
        let changed = self.connection.execute(
            r#"UPDATE pump_launch_signals
               SET status = 'verified', candidate_id = ?2, last_error = NULL
               WHERE signature = ?1 AND status = 'pending'"#,
            params![signature, candidate_id],
        )?;
        ensure_pump_signal_changed(changed, signature, "mark verified")
    }

    /// Permanently reject a signal that was fetched successfully but did not
    /// verify as a Pump Create/CreateV2 transaction. The reason stays auditable.
    pub fn mark_pump_launch_rejected(
        &self,
        signature: &str,
        rejected_at_unix_ms: i64,
        reason: &str,
    ) -> Result<(), StorageError> {
        validate_pump_signature(signature)?;
        if reason.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "Pump rejection reason must not be empty".to_owned(),
            ));
        }
        let changed = self.connection.execute(
            r#"UPDATE pump_launch_signals
               SET status = 'rejected',
                   last_attempt_at_unix_ms = ?2,
                   last_error = ?3
               WHERE signature = ?1 AND status = 'pending'"#,
            params![signature, rejected_at_unix_ms, reason],
        )?;
        ensure_pump_signal_changed(changed, signature, "mark rejected")
    }

    /// Persist one provider-neutral pair snapshot. Duplicate observations of
    /// the same candidate/provider/pair/timestamp are ignored safely.
    pub fn insert_market_snapshot(
        &self,
        candidate_id: i64,
        snapshot: &PairMarketData,
    ) -> Result<(), StorageError> {
        if snapshot.chain_id != "solana" {
            return Err(StorageError::InvalidData(format!(
                "market snapshot chain must be solana; got {}",
                snapshot.chain_id
            )));
        }
        if snapshot.pair_address.trim().is_empty()
            || snapshot.base_mint.trim().is_empty()
            || snapshot.quote_mint.trim().is_empty()
        {
            return Err(StorageError::InvalidData(
                "market snapshot requires pair, base mint, and quote mint".to_owned(),
            ));
        }

        validate_optional_decimal_text(snapshot.price_native.as_deref(), "price_native")?;
        let price_usd = parse_optional_decimal_text(snapshot.price_usd.as_deref(), "price_usd")?;
        let liquidity_usd = validate_optional_nonnegative_f64(snapshot.liquidity_usd, "liquidity_usd")?;
        let volume_5m = validate_optional_nonnegative_f64(snapshot.volume_5m, "volume_5m")?;
        let volume_1h = validate_optional_nonnegative_f64(snapshot.volume_1h, "volume_1h")?;
        let volume_6h = validate_optional_nonnegative_f64(snapshot.volume_6h, "volume_6h")?;
        let volume_24h = validate_optional_nonnegative_f64(snapshot.volume_24h, "volume_24h")?;
        let fdv_usd = validate_optional_nonnegative_f64(snapshot.fdv_usd, "fdv_usd")?;
        let market_cap_usd =
            validate_optional_nonnegative_f64(snapshot.market_cap_usd, "market_cap_usd")?;

        let m5 = transaction_window(&snapshot.transactions, "m5");
        let h1 = transaction_window(&snapshot.transactions, "h1");
        let buys_m5 = optional_u64_as_i64(m5.map(|window| window.buys), "buys_m5")?;
        let sells_m5 = optional_u64_as_i64(m5.map(|window| window.sells), "sells_m5")?;
        let buys_h1 = optional_u64_as_i64(h1.map(|window| window.buys), "buys_h1")?;
        let sells_h1 = optional_u64_as_i64(h1.map(|window| window.sells), "sells_h1")?;

        self.connection.execute(
            r#"INSERT OR IGNORE INTO market_snapshots (
                   candidate_id, observed_at_unix_ms, source, source_observed_at_unix_ms,
                   venue, pair_address, dex_id, base_mint, quote_mint, price_native, price_usd,
                   market_cap_usd, fdv_usd, liquidity_usd, volume_m5_usd, volume_h1_usd,
                   volume_h6_usd, volume_h24_usd, buys_m5, sells_m5, buys_h1, sells_h1,
                   pair_created_at_unix_ms
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15,
                   ?16, ?17, ?18, ?19, ?20, ?21, ?22, ?23
               )"#,
            params![
                candidate_id,
                snapshot.observed_at_unix_ms,
                snapshot.provider.as_str(),
                snapshot.observed_at_unix_ms,
                snapshot.venue.as_str(),
                snapshot.pair_address,
                snapshot.dex_id,
                snapshot.base_mint,
                snapshot.quote_mint,
                snapshot.price_native,
                price_usd,
                market_cap_usd,
                fdv_usd,
                liquidity_usd,
                volume_5m,
                volume_1h,
                volume_6h,
                volume_24h,
                buys_m5,
                sells_m5,
                buys_h1,
                sells_h1,
                snapshot.pair_created_at_unix_ms,
            ],
        )?;
        Ok(())
    }

    /// Persist parsed Solana mint state while preserving full unsigned values
    /// as decimal text instead of narrowing them into SQLite's signed INTEGER.
    pub fn insert_mint_state(
        &self,
        candidate_id: i64,
        state: &TokenMintState,
    ) -> Result<(), StorageError> {
        if state.mint.trim().is_empty() || state.owner_program.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "mint state requires mint and owner program".to_owned(),
            ));
        }

        self.connection.execute(
            r#"INSERT OR IGNORE INTO token_mint_states (
                   candidate_id, provider, owner_program, supply, decimals, mint_authority,
                   freeze_authority, slot, observed_at_unix_ms
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)"#,
            params![
                candidate_id,
                state.provider.as_str(),
                state.owner_program,
                state.supply.to_string(),
                i64::from(state.decimals),
                state.mint_authority,
                state.freeze_authority,
                state.slot.to_string(),
                state.observed_at_unix_ms,
            ],
        )?;
        Ok(())
    }

    /// Upsert the latest health state for one provider.
    pub fn upsert_provider_health(
        &self,
        provider: ProviderId,
        state: ProviderHealthState,
        observed_at_unix_ms: i64,
        latency_ms: Option<u64>,
        detail: Option<&str>,
        consecutive_failures: u64,
    ) -> Result<(), StorageError> {
        let latency_ms = optional_u64_as_i64(latency_ms, "provider latency_ms")?;
        let consecutive_failures = u64_as_i64(consecutive_failures, "provider consecutive_failures")?;

        self.connection.execute(
            r#"INSERT INTO provider_health (
                   provider, status, observed_at_unix_ms, latency_ms, detail, consecutive_failures
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
               ON CONFLICT(provider) DO UPDATE SET
                   status = excluded.status,
                   observed_at_unix_ms = excluded.observed_at_unix_ms,
                   latency_ms = excluded.latency_ms,
                   detail = excluded.detail,
                   consecutive_failures = excluded.consecutive_failures"#,
            params![
                provider.as_str(),
                state.as_str(),
                observed_at_unix_ms,
                latency_ms,
                detail,
                consecutive_failures,
            ],
        )?;
        Ok(())
    }

    /// Replace a provider stream checkpoint atomically.
    pub fn set_ingestion_checkpoint(
        &self,
        provider: ProviderId,
        stream: &str,
        cursor: Option<&str>,
    ) -> Result<(), StorageError> {
        if stream.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "ingestion checkpoint stream must not be empty".to_owned(),
            ));
        }

        self.connection.execute(
            r#"INSERT INTO ingestion_checkpoints (provider, stream, cursor, updated_at_unix_ms)
               VALUES (?1, ?2, ?3, ?4)
               ON CONFLICT(provider, stream) DO UPDATE SET
                   cursor = excluded.cursor,
                   updated_at_unix_ms = excluded.updated_at_unix_ms"#,
            params![provider.as_str(), stream, cursor, unix_time_ms()?],
        )?;
        Ok(())
    }

    /// Load a previously persisted provider stream checkpoint.
    pub fn ingestion_checkpoint(
        &self,
        provider: ProviderId,
        stream: &str,
    ) -> Result<Option<String>, StorageError> {
        if stream.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "ingestion checkpoint stream must not be empty".to_owned(),
            ));
        }

        let cursor = self
            .connection
            .query_row(
                "SELECT cursor FROM ingestion_checkpoints WHERE provider = ?1 AND stream = ?2",
                params![provider.as_str(), stream],
                |row| row.get::<_, Option<String>>(0),
            )
            .optional()?;
        Ok(cursor.flatten())
    }
}

fn configure_connection(connection: &Connection) -> Result<(), StorageError> {
    connection.query_row("PRAGMA journal_mode = WAL", [], |row| row.get::<_, String>(0))?;
    connection.busy_timeout(Duration::from_millis(BUSY_TIMEOUT_MS))?;
    connection.execute_batch(
        "PRAGMA foreign_keys = ON;\
\
         PRAGMA synchronous = NORMAL;",
    )?;

    Ok(())
}

fn configure_read_only_connection(connection: &Connection) -> Result<(), StorageError> {
    connection.busy_timeout(Duration::from_millis(BUSY_TIMEOUT_MS))?;
    connection.execute_batch(
        "PRAGMA foreign_keys = ON;\
\
         PRAGMA query_only = ON;",
    )?;
    Ok(())
}

fn validate_current_schema(connection: &Connection) -> Result<(), StorageError> {
    let mut statement = connection.prepare(
        "SELECT version, name FROM schema_migrations ORDER BY version ASC",
    )?;
    let applied = statement
        .query_map([], |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)))?
        .collect::<Result<Vec<_>, _>>()?;

    if applied.len() != MIGRATIONS.len() {
        return Err(StorageError::InvalidData(format!(
            "read-only Shreks database schema history has {} migrations; expected {}",
            applied.len(),
            MIGRATIONS.len()
        )));
    }
    for (actual, expected) in applied.iter().zip(MIGRATIONS) {
        if actual.0 != expected.version || actual.1 != expected.name {
            return Err(StorageError::InvalidData(format!(
                "read-only Shreks database schema history diverges at version {}",
                expected.version
            )));
        }
    }
    Ok(())
}

fn apply_migrations(connection: &mut Connection) -> Result<(), StorageError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_migrations (\
\
             version INTEGER PRIMARY KEY,\
\
             name TEXT NOT NULL,\
\
             applied_at_unix_ms INTEGER NOT NULL\
\
         );",
    )?;

    for migration in MIGRATIONS {
        let applied: i64 = connection.query_row(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?1",
            [migration.version],
            |row| row.get(0),
        )?;

        if applied != 0 {
            continue;
        }

        let transaction = connection.transaction()?;
        transaction.execute_batch(migration.sql)?;
        transaction.execute(
            "INSERT INTO schema_migrations (version, name, applied_at_unix_ms) VALUES (?1, ?2, ?3)",
            params![migration.version, migration.name, unix_time_ms()?],
        )?;
        transaction.commit()?;
    }

    Ok(())
}

fn validate_pump_signature(signature: &str) -> Result<(), StorageError> {
    if signature.trim().is_empty() {
        return Err(StorageError::InvalidData(
            "Pump launch signature must not be empty".to_owned(),
        ));
    }
    Ok(())
}

fn ensure_pump_signal_changed(
    changed: usize,
    signature: &str,
    operation: &str,
) -> Result<(), StorageError> {
    if changed == 0 {
        return Err(StorageError::InvalidData(format!(
            "cannot {operation} Pump signal '{signature}': signal is missing or no longer pending"
        )));
    }
    Ok(())
}

fn transaction_window<'a>(
    windows: &'a [TransactionWindow],
    name: &str,
) -> Option<&'a TransactionWindow> {
    windows.iter().find(|window| window.window == name)
}

fn validate_optional_decimal_text(value: Option<&str>, field: &str) -> Result<(), StorageError> {
    if let Some(value) = value {
        let parsed = parse_decimal_text(value, field)?;
        if parsed < 0.0 {
            return Err(StorageError::InvalidData(format!(
                "{field} must not be negative"
            )));
        }
    }
    Ok(())
}

fn parse_optional_decimal_text(
    value: Option<&str>,
    field: &str,
) -> Result<Option<f64>, StorageError> {
    value
        .map(|value| {
            let parsed = parse_decimal_text(value, field)?;
            if parsed < 0.0 {
                return Err(StorageError::InvalidData(format!(
                    "{field} must not be negative"
                )));
            }
            Ok(parsed)
        })
        .transpose()
}

fn parse_decimal_text(value: &str, field: &str) -> Result<f64, StorageError> {
    let parsed = value.parse::<f64>().map_err(|error| {
        StorageError::InvalidData(format!("{field} is not numeric: {error}"))
    })?;
    if !parsed.is_finite() {
        return Err(StorageError::InvalidData(format!(
            "{field} must be finite"
        )));
    }
    Ok(parsed)
}

fn validate_optional_nonnegative_f64(
    value: Option<f64>,
    field: &str,
) -> Result<Option<f64>, StorageError> {
    if let Some(value) = value {
        if !value.is_finite() || value < 0.0 {
            return Err(StorageError::InvalidData(format!(
                "{field} must be finite and nonnegative"
            )));
        }
    }
    Ok(value)
}

fn optional_u64_as_i64(value: Option<u64>, field: &str) -> Result<Option<i64>, StorageError> {
    value.map(|value| u64_as_i64(value, field)).transpose()
}

fn u64_as_i64(value: u64, field: &str) -> Result<i64, StorageError> {
    i64::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!("{field} exceeds SQLite signed integer range"))
    })
}

fn unix_time_ms() -> Result<i64, StorageError> {
    let elapsed = SystemTime::now().duration_since(UNIX_EPOCH)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| {
        StorageError::InvalidData("system clock exceeds i64 milliseconds".to_owned())
    })
}

#[cfg(test)]
mod tests {
    use super::BUSY_TIMEOUT_MS;

    #[test]
    fn busy_timeout_is_five_seconds() {
        assert_eq!(BUSY_TIMEOUT_MS, 5_000);
    }
}
