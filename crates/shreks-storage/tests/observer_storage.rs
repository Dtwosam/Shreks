use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderHealthState, ProviderId, TokenMintState,
    TransactionWindow, VenueId,
};
use shreks_storage::{ShreksDb, StorageError};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn table_has_column(connection: &Connection, table: &str, column: &str) -> bool {
    let mut statement = connection
        .prepare(&format!("PRAGMA table_info({table})"))
        .unwrap();
    let found = statement
        .query_map([], |row| row.get::<_, String>(1))
        .unwrap()
        .map(Result::unwrap)
        .any(|name| name == column);
    found
}

fn pump_candidate() -> DiscoveredToken {
    DiscoveredToken {
        mint: "mint-a".to_owned(),
        pair_address: Some("pump-pair-a".to_owned()),
        dex_id: Some("pumpswap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms: 10,
        source: ProviderId::DexScreener,
    }
}

fn meteora_snapshot(observed_at_unix_ms: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::Meteora,
        venue: VenueId::MeteoraDlmm,
        chain_id: "solana".to_owned(),
        dex_id: "meteora_dlmm".to_owned(),
        pair_address: "meteora-pair-a".to_owned(),
        base_mint: "mint-a".to_owned(),
        base_name: Some("Token A".to_owned()),
        base_symbol: Some("TKA".to_owned()),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: Some("Wrapped SOL".to_owned()),
        quote_symbol: Some("SOL".to_owned()),
        price_native: Some("0.0035".to_owned()),
        price_usd: Some("0.42".to_owned()),
        liquidity_usd: Some(125_000.0),
        volume_5m: Some(4_500.0),
        volume_1h: Some(37_000.0),
        volume_6h: Some(120_000.0),
        volume_24h: Some(410_000.0),
        transactions: vec![
            TransactionWindow {
                window: "m5".to_owned(),
                buys: 31,
                sells: 12,
            },
            TransactionWindow {
                window: "h1".to_owned(),
                buys: 220,
                sells: 104,
            },
        ],
        fdv_usd: Some(420_000.0),
        market_cap_usd: Some(390_000.0),
        pair_created_at_unix_ms: Some(5),
        observed_at_unix_ms,
    }
}

#[test]
fn migration_two_adds_venue_aware_observer_schema() {
    let root = unique_test_dir("schema");
    let db_path = root.join("shreks.db");

    let db = ShreksDb::open(&db_path).unwrap();
    assert!(db.diagnostics().unwrap().schema_version >= 2);
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    assert!(table_has_column(&connection, "token_candidates", "venue"));

    for column in [
        "venue",
        "pair_address",
        "dex_id",
        "base_mint",
        "quote_mint",
        "price_native",
    ] {
        assert!(
            table_has_column(&connection, "market_snapshots", column),
            "market_snapshots missing normalized column {column}"
        );
    }

    let mint_state_table: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'token_mint_states'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(mint_state_table, 1);

    cleanup_dir(&root);
}

#[test]
fn market_snapshot_identity_allows_multiple_pairs_at_same_observation_time() {
    let root = unique_test_dir("pair-identity");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute(
            "INSERT INTO token_candidates (mint, pair_address, discovery_source, discovered_at_unix_ms, created_at_unix_ms) VALUES (?1, ?2, ?3, ?4, ?5)",
            ("mint-a", "", "dexscreener", 1_i64, 1_i64),
        )
        .unwrap();
    let candidate_id = connection.last_insert_rowid();

    for pair in ["pair-one", "pair-two"] {
        connection
            .execute(
                "INSERT INTO market_snapshots (candidate_id, observed_at_unix_ms, source, venue, pair_address, dex_id, base_mint, quote_mint) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                (
                    candidate_id,
                    10_i64,
                    "dexscreener",
                    "pump_swap",
                    pair,
                    "pumpswap",
                    "mint-a",
                    "sol",
                ),
            )
            .unwrap();
    }

    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM market_snapshots WHERE candidate_id = ?1 AND observed_at_unix_ms = 10",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 2);

    cleanup_dir(&root);
}

#[test]
fn provider_health_schema_accepts_rate_limited_state() {
    let root = unique_test_dir("rate-limit");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute(
            "INSERT INTO provider_health (provider, status, observed_at_unix_ms, consecutive_failures) VALUES (?1, ?2, ?3, ?4)",
            ("jupiter", "rate_limited", 1_i64, 1_i64),
        )
        .unwrap();

    let state: String = connection
        .query_row(
            "SELECT status FROM provider_health WHERE provider = 'jupiter'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(state, "rate_limited");

    cleanup_dir(&root);
}

#[test]
fn token_mint_states_reference_candidates_and_store_u64_fields_as_text() {
    let root = unique_test_dir("mint-states");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    let mut statement = connection
        .prepare("PRAGMA table_info(token_mint_states)")
        .unwrap();
    let columns: Vec<(String, String)> = statement
        .query_map([], |row| Ok((row.get(1)?, row.get(2)?)))
        .unwrap()
        .map(Result::unwrap)
        .collect();

    assert!(columns.iter().any(|(name, ty)| name == "candidate_id" && ty == "INTEGER"));
    assert!(columns.iter().any(|(name, ty)| name == "supply" && ty == "TEXT"));
    assert!(columns.iter().any(|(name, ty)| name == "slot" && ty == "TEXT"));

    let foreign_key_count: i64 = {
        let mut fk = connection
            .prepare("PRAGMA foreign_key_list(token_mint_states)")
            .unwrap();
        let count = fk
            .query_map([], |_| Ok(1_i64))
            .unwrap()
            .map(Result::unwrap)
            .sum();
        count
    };
    assert!(foreign_key_count >= 1);

    cleanup_dir(&root);
}

#[test]
fn upsert_candidate_is_idempotent_and_persists_venue() {
    let root = unique_test_dir("candidate-api");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate = pump_candidate();

    let first_id = db.upsert_candidate(&candidate).unwrap();
    let second_id = db.upsert_candidate(&candidate).unwrap();
    assert_eq!(first_id, second_id);

    let connection = Connection::open(&db_path).unwrap();
    let (count, venue): (i64, Option<String>) = connection
        .query_row(
            "SELECT COUNT(*), MAX(venue) FROM token_candidates WHERE mint = ?1 AND pair_address = ?2 AND discovery_source = ?3",
            (&candidate.mint, "pump-pair-a", "dexscreener"),
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(count, 1);
    assert_eq!(venue.as_deref(), Some("pump_swap"));

    cleanup_dir(&root);
}

#[test]
fn market_snapshot_api_persists_normalized_pair_and_flow_fields() {
    let root = unique_test_dir("market-api");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&pump_candidate()).unwrap();
    let snapshot = meteora_snapshot(100);

    db.insert_market_snapshot(candidate_id, &snapshot).unwrap();

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, String, String, String, String, Option<f64>, Option<i64>, Option<i64>) = connection
        .query_row(
            "SELECT venue, pair_address, dex_id, base_mint, quote_mint, price_usd, buys_m5, sells_h1 FROM market_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| Ok((
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                row.get(6)?,
                row.get(7)?,
            )),
        )
        .unwrap();

    assert_eq!(row.0, "meteora_dlmm");
    assert_eq!(row.1, "meteora-pair-a");
    assert_eq!(row.2, "meteora_dlmm");
    assert_eq!(row.3, "mint-a");
    assert_eq!(row.4, "So11111111111111111111111111111111111111112");
    assert_eq!(row.5, Some(0.42));
    assert_eq!(row.6, Some(31));
    assert_eq!(row.7, Some(104));

    cleanup_dir(&root);
}

#[test]
fn market_snapshot_api_rejects_invalid_numeric_price() {
    let root = unique_test_dir("invalid-price");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&pump_candidate()).unwrap();
    let mut snapshot = meteora_snapshot(101);
    snapshot.price_usd = Some("not-a-number".to_owned());

    let error = db.insert_market_snapshot(candidate_id, &snapshot).unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));

    cleanup_dir(&root);
}

#[test]
fn mint_state_api_preserves_full_u64_supply_and_slot() {
    let root = unique_test_dir("mint-api");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&pump_candidate()).unwrap();
    let state = TokenMintState {
        provider: ProviderId::Helius,
        mint: "mint-a".to_owned(),
        owner_program: "TokenProgram".to_owned(),
        supply: u64::MAX,
        decimals: 9,
        mint_authority: Some("mint-authority".to_owned()),
        freeze_authority: Some("freeze-authority".to_owned()),
        slot: u64::MAX,
        observed_at_unix_ms: 200,
    };

    db.insert_mint_state(candidate_id, &state).unwrap();

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, String, Option<String>, Option<String>) = connection
        .query_row(
            "SELECT supply, slot, mint_authority, freeze_authority FROM token_mint_states WHERE candidate_id = ?1",
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(row.0, u64::MAX.to_string());
    assert_eq!(row.1, u64::MAX.to_string());
    assert_eq!(row.2.as_deref(), Some("mint-authority"));
    assert_eq!(row.3.as_deref(), Some("freeze-authority"));

    cleanup_dir(&root);
}

#[test]
fn provider_health_and_checkpoint_apis_survive_restart() {
    let root = unique_test_dir("health-checkpoint");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.upsert_provider_health(
        ProviderId::Jupiter,
        ProviderHealthState::RateLimited,
        300,
        Some(25),
        Some("HTTP 429"),
        3,
    )
    .unwrap();
    db.set_ingestion_checkpoint(
        ProviderId::DexScreener,
        "profiles",
        Some("cursor-a"),
    )
    .unwrap();
    db.set_ingestion_checkpoint(
        ProviderId::DexScreener,
        "profiles",
        Some("cursor-b"),
    )
    .unwrap();
    assert_eq!(
        db.ingestion_checkpoint(ProviderId::DexScreener, "profiles")
            .unwrap()
            .as_deref(),
        Some("cursor-b")
    );
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened
            .ingestion_checkpoint(ProviderId::DexScreener, "profiles")
            .unwrap()
            .as_deref(),
        Some("cursor-b")
    );

    let connection = Connection::open(&db_path).unwrap();
    let health: (String, i64, Option<i64>) = connection
        .query_row(
            "SELECT status, consecutive_failures, latency_ms FROM provider_health WHERE provider = 'jupiter'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(health.0, "rate_limited");
    assert_eq!(health.1, 3);
    assert_eq!(health.2, Some(25));

    cleanup_dir(&root);
}
