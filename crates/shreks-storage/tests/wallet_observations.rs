use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    DiscoveredToken, ProviderId, VenueId, WalletActionKind, WalletObservation,
    WalletObservationEvidence,
};
use shreks_storage::{ShreksDb, WalletObservationWrite};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-wallet-observations-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms,
        source: ProviderId::Helius,
    }
}

fn observation(
    wallet: &str,
    mint: &str,
    signature: &str,
    event_index: u32,
    observed_at_unix_ms: i64,
) -> WalletObservation {
    let beyond_i64 = i128::from(i64::MAX) + 77;
    WalletObservation {
        provider: ProviderId::Helius,
        wallet: wallet.to_owned(),
        candidate_mint: mint.to_owned(),
        action: WalletActionKind::Buy,
        evidence: WalletObservationEvidence::Direct,
        signature: signature.to_owned(),
        event_index,
        slot: u64::MAX,
        observed_at_unix_ms,
        occurred_at_unix_ms: Some(observed_at_unix_ms.saturating_sub(100)),
        candidate_token_delta_raw: Some(beyond_i64),
        counter_asset_mint: Some("So11111111111111111111111111111111111111112".to_owned()),
        counter_asset_delta_raw: Some(-beyond_i64),
        venue: Some(VenueId::PumpSwap),
        counterparty: Some("Pool111".to_owned()),
    }
}

#[test]
fn insert_replay_preserves_earliest_local_observation_and_full_width_values() {
    let root = unique_test_dir("replay");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.upsert_candidate(&candidate("Mint111", 500)).unwrap();

    let original = observation("Wallet111", "Mint111", "Sig111", 0, 1_000);
    assert_eq!(
        db.record_wallet_observation(&original).unwrap(),
        WalletObservationWrite::Inserted
    );
    assert_eq!(
        db.record_wallet_observation(&original).unwrap(),
        WalletObservationWrite::AlreadyPresent
    );

    let mut later_replay = original.clone();
    later_replay.observed_at_unix_ms = 1_500;
    assert_eq!(
        db.record_wallet_observation(&later_replay).unwrap(),
        WalletObservationWrite::AlreadyPresent
    );

    let mut earlier_replay = original.clone();
    earlier_replay.observed_at_unix_ms = 900;
    assert_eq!(
        db.record_wallet_observation(&earlier_replay).unwrap(),
        WalletObservationWrite::AlreadyPresent
    );

    let rows = db
        .wallet_observations_for_mint("Mint111", 0, 2_000, 10)
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].observed_at_unix_ms, 900);
    assert_eq!(rows[0].slot, u64::MAX);
    assert_eq!(
        rows[0].candidate_token_delta_raw,
        Some(i128::from(i64::MAX) + 77)
    );
    assert_eq!(
        rows[0].counter_asset_delta_raw,
        Some(-(i128::from(i64::MAX) + 77))
    );

    cleanup_dir(&root);
}

#[test]
fn contradictory_replay_is_rejected_without_mutating_original_truth() {
    let root = unique_test_dir("contradiction");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.upsert_candidate(&candidate("Mint111", 0)).unwrap();

    let original = observation("Wallet111", "Mint111", "Sig111", 1, 1_000);
    db.record_wallet_observation(&original).unwrap();

    let mut contradictory = original.clone();
    contradictory.action = WalletActionKind::Sell;
    assert!(db.record_wallet_observation(&contradictory).is_err());

    let rows = db
        .wallet_observations_for_mint("Mint111", 0, 2_000, 10)
        .unwrap();
    assert_eq!(rows, vec![original]);

    cleanup_dir(&root);
}

#[test]
fn same_transaction_supports_distinct_event_indexes_and_queries_are_deterministic() {
    let root = unique_test_dir("query");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.upsert_candidate(&candidate("MintA", 0)).unwrap();
    db.upsert_candidate(&candidate("MintB", 0)).unwrap();

    let rows = [
        observation("WalletA", "MintA", "SigB", 1, 1_000),
        observation("WalletA", "MintA", "SigA", 1, 1_000),
        observation("WalletA", "MintA", "SigA", 0, 1_000),
        observation("WalletA", "MintB", "SigC", 0, 1_500),
        observation("WalletB", "MintA", "SigD", 0, 2_000),
    ];
    for row in &rows {
        assert_eq!(
            db.record_wallet_observation(row).unwrap(),
            WalletObservationWrite::Inserted
        );
    }

    let by_mint = db
        .wallet_observations_for_mint("MintA", 1_000, 2_000, 10)
        .unwrap();
    let mint_order: Vec<_> = by_mint
        .iter()
        .map(|row| (row.observed_at_unix_ms, row.signature.as_str(), row.event_index, row.wallet.as_str()))
        .collect();
    assert_eq!(
        mint_order,
        vec![
            (1_000, "SigA", 0, "WalletA"),
            (1_000, "SigA", 1, "WalletA"),
            (1_000, "SigB", 1, "WalletA"),
            (2_000, "SigD", 0, "WalletB"),
        ]
    );

    let by_wallet = db
        .wallet_observations_for_wallet("WalletA", 1_000, 1_500, 10)
        .unwrap();
    let wallet_order: Vec<_> = by_wallet
        .iter()
        .map(|row| (row.observed_at_unix_ms, row.signature.as_str(), row.event_index, row.candidate_mint.as_str()))
        .collect();
    assert_eq!(
        wallet_order,
        vec![
            (1_000, "SigA", 0, "MintA"),
            (1_000, "SigA", 1, "MintA"),
            (1_000, "SigB", 1, "MintA"),
            (1_500, "SigC", 0, "MintB"),
        ]
    );

    cleanup_dir(&root);
}

#[test]
fn invalid_inputs_and_unknown_candidates_fail_closed() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.upsert_candidate(&candidate("Mint111", 0)).unwrap();

    let unknown = observation("Wallet111", "UnknownMint", "SigU", 0, 1_000);
    assert!(db.record_wallet_observation(&unknown).is_err());

    let mut blank_wallet = observation("Wallet111", "Mint111", "Sig1", 0, 1_000);
    blank_wallet.wallet.clear();
    assert!(db.record_wallet_observation(&blank_wallet).is_err());

    let mut negative_time = observation("Wallet111", "Mint111", "Sig2", 0, 1_000);
    negative_time.observed_at_unix_ms = -1;
    assert!(db.record_wallet_observation(&negative_time).is_err());

    let mut negative_chain_time = observation("Wallet111", "Mint111", "Sig3", 0, 1_000);
    negative_chain_time.occurred_at_unix_ms = Some(-1);
    assert!(db.record_wallet_observation(&negative_chain_time).is_err());

    let mut missing_counter_mint = observation("Wallet111", "Mint111", "Sig4", 0, 1_000);
    missing_counter_mint.counter_asset_mint = None;
    assert!(db.record_wallet_observation(&missing_counter_mint).is_err());

    assert!(db
        .wallet_observations_for_mint("Mint111", 2_000, 1_000, 10)
        .is_err());
    assert!(db
        .wallet_observations_for_wallet("Wallet111", 0, 1_000, 0)
        .is_err());
    assert!(db
        .wallet_observations_for_wallet("Wallet111", 0, 1_000, 10_001)
        .is_err());

    cleanup_dir(&root);
}

#[test]
fn observations_survive_file_backed_restart_exactly() {
    let root = unique_test_dir("restart");
    let db_path = root.join("shreks.db");
    let expected = observation("Wallet111", "Mint111", "Sig111", 7, 5_000);

    {
        let db = ShreksDb::open(&db_path).unwrap();
        db.upsert_candidate(&candidate("Mint111", 0)).unwrap();
        db.record_wallet_observation(&expected).unwrap();
    }

    let reopened = ShreksDb::open(&db_path).unwrap();
    let rows = reopened
        .wallet_observations_for_wallet("Wallet111", 0, 10_000, 10)
        .unwrap();
    assert_eq!(rows, vec![expected]);

    cleanup_dir(&root);
}
