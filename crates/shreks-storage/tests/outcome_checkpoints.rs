use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId,
};
use shreks_storage::{
    OutcomeCheckpointCompletion, OutcomeCheckpointStatus, ShreksDb, OUTCOME_HORIZONS_SECONDS,
};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-outcome-checkpoints-{label}-{}-{nanos}",
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

fn market_snapshot(mint: &str, pair: &str, observed_at_unix_ms: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: pair.to_owned(),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: Some("0.001".to_owned()),
        price_usd: Some("0.10".to_owned()),
        liquidity_usd: Some(10_000.0),
        volume_5m: Some(1_000.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 10,
            sells: 4,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(0),
        observed_at_unix_ms,
    }
}

fn snapshot_id(db_path: &Path, candidate_id: i64, pair: &str, observed_at: i64) -> i64 {
    Connection::open(db_path)
        .unwrap()
        .query_row(
            "SELECT id FROM market_snapshots WHERE candidate_id = ?1 AND pair_address = ?2 AND observed_at_unix_ms = ?3",
            (candidate_id, pair, observed_at),
            |row| row.get(0),
        )
        .unwrap()
}

#[test]
fn migration_four_schedules_the_exact_approved_horizons_idempotently() {
    let root = unique_test_dir("schema-schedule");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 11);

    let discovered_at = 1_000_000_i64;
    let candidate_id = db.upsert_candidate(&candidate("mint-a", discovered_at)).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, discovered_at).unwrap();

    let checkpoints = db.outcome_checkpoints(candidate_id).unwrap();
    assert_eq!(checkpoints.len(), 7);
    assert_eq!(OUTCOME_HORIZONS_SECONDS, [60, 300, 900, 1_800, 3_600, 14_400, 86_400]);

    let horizons: Vec<u32> = checkpoints.iter().map(|row| row.horizon_seconds).collect();
    assert_eq!(horizons, OUTCOME_HORIZONS_SECONDS);
    for checkpoint in &checkpoints {
        assert_eq!(checkpoint.status, OutcomeCheckpointStatus::Pending);
        assert_eq!(
            checkpoint.due_at_unix_ms,
            discovered_at + i64::from(checkpoint.horizon_seconds) * 1_000
        );
        assert_eq!(checkpoint.completed_at_unix_ms, None);
        assert_eq!(checkpoint.baseline_snapshot_id, None);
        assert_eq!(checkpoint.checkpoint_snapshot_id, None);
    }
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    reopened
        .ensure_outcome_checkpoints(candidate_id, discovered_at)
        .unwrap();
    assert_eq!(reopened.outcome_checkpoints(candidate_id).unwrap().len(), 7);

    cleanup_dir(&root);
}

#[test]
fn due_query_returns_only_arrived_pending_rows_in_deterministic_order() {
    let root = unique_test_dir("due-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first_id = db.upsert_candidate(&candidate("mint-first", 1_000)).unwrap();
    let second_id = db.upsert_candidate(&candidate("mint-second", 2_000)).unwrap();
    db.ensure_outcome_checkpoints(first_id, 1_000).unwrap();
    db.ensure_outcome_checkpoints(second_id, 2_000).unwrap();

    assert!(db.due_outcome_checkpoints(60_999, 50).unwrap().is_empty());

    let due = db.due_outcome_checkpoints(62_000, 50).unwrap();
    assert_eq!(due.len(), 2);
    assert_eq!(due[0].candidate_id, first_id);
    assert_eq!(due[0].mint, "mint-first");
    assert_eq!(due[0].horizon_seconds, 60);
    assert_eq!(due[0].due_at_unix_ms, 61_000);
    assert_eq!(due[1].candidate_id, second_id);
    assert_eq!(due[1].mint, "mint-second");
    assert_eq!(due[1].due_at_unix_ms, 62_000);

    let limited = db.due_outcome_checkpoints(62_000, 1).unwrap();
    assert_eq!(limited.len(), 1);
    assert_eq!(limited[0].candidate_id, first_id);

    cleanup_dir(&root);
}

#[test]
fn scheduling_rejects_timestamp_overflow_without_partial_rows() {
    let root = unique_test_dir("overflow");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db
        .upsert_candidate(&candidate("mint-overflow", i64::MAX - 1_000))
        .unwrap();

    let error = db
        .ensure_outcome_checkpoints(candidate_id, i64::MAX - 1_000)
        .unwrap_err();
    assert!(error.to_string().contains("overflow"));
    assert!(db.outcome_checkpoints(candidate_id).unwrap().is_empty());

    cleanup_dir(&root);
}

#[test]
fn completion_links_owned_snapshots_is_terminal_and_preserves_nullable_metrics() {
    let root = unique_test_dir("complete");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("mint-complete", 0)).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, 0).unwrap();

    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot("mint-complete", "baseline-pair", 1_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        candidate_id,
        &market_snapshot("mint-complete", "checkpoint-pair", 61_000),
    )
    .unwrap();
    let baseline_id = snapshot_id(&db_path, candidate_id, "baseline-pair", 1_000);
    let checkpoint_id = snapshot_id(&db_path, candidate_id, "checkpoint-pair", 61_000);

    let completion = OutcomeCheckpointCompletion {
        baseline_snapshot_id: baseline_id,
        checkpoint_snapshot_id: checkpoint_id,
        completed_at_unix_ms: 61_500,
        return_pct: Some(25.0),
        mfe_pct: None,
        mae_pct: None,
        liquidity_change_pct: None,
        volume_m5_change_pct: None,
        buys_m5_change: Some(3),
        sells_m5_change: Some(-1),
        rug_or_dead_pool: None,
        exitability: None,
    };
    db.complete_outcome_checkpoint(candidate_id, 60, &completion)
        .unwrap();

    let completed = db
        .outcome_checkpoints(candidate_id)
        .unwrap()
        .into_iter()
        .find(|row| row.horizon_seconds == 60)
        .unwrap();
    assert_eq!(completed.status, OutcomeCheckpointStatus::Completed);
    assert_eq!(completed.baseline_snapshot_id, Some(baseline_id));
    assert_eq!(completed.checkpoint_snapshot_id, Some(checkpoint_id));
    assert_eq!(completed.completed_at_unix_ms, Some(61_500));
    assert_eq!(completed.return_pct, Some(25.0));
    assert_eq!(completed.mfe_pct, None);
    assert_eq!(completed.mae_pct, None);
    assert_eq!(completed.buys_m5_change, Some(3));
    assert_eq!(completed.sells_m5_change, Some(-1));
    assert_eq!(completed.rug_or_dead_pool, None);
    assert_eq!(completed.exitability, None);
    assert!(db.due_outcome_checkpoints(100_000, 10).unwrap().is_empty());

    let error = db
        .complete_outcome_checkpoint(candidate_id, 60, &completion)
        .unwrap_err();
    assert!(error.to_string().contains("already completed"));

    cleanup_dir(&root);
}

#[test]
fn completion_rejects_snapshots_owned_by_another_candidate() {
    let root = unique_test_dir("ownership");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let first_id = db.upsert_candidate(&candidate("mint-owner-a", 0)).unwrap();
    let second_id = db.upsert_candidate(&candidate("mint-owner-b", 0)).unwrap();
    db.ensure_outcome_checkpoints(first_id, 0).unwrap();

    db.insert_market_snapshot(
        first_id,
        &market_snapshot("mint-owner-a", "owner-a-pair", 1_000),
    )
    .unwrap();
    db.insert_market_snapshot(
        second_id,
        &market_snapshot("mint-owner-b", "owner-b-pair", 61_000),
    )
    .unwrap();
    let baseline_id = snapshot_id(&db_path, first_id, "owner-a-pair", 1_000);
    let foreign_checkpoint_id = snapshot_id(&db_path, second_id, "owner-b-pair", 61_000);

    let completion = OutcomeCheckpointCompletion {
        baseline_snapshot_id: baseline_id,
        checkpoint_snapshot_id: foreign_checkpoint_id,
        completed_at_unix_ms: 61_500,
        return_pct: None,
        mfe_pct: None,
        mae_pct: None,
        liquidity_change_pct: None,
        volume_m5_change_pct: None,
        buys_m5_change: None,
        sells_m5_change: None,
        rug_or_dead_pool: None,
        exitability: None,
    };
    let error = db
        .complete_outcome_checkpoint(first_id, 60, &completion)
        .unwrap_err();
    assert!(error.to_string().contains("candidate"));

    let due = db.due_outcome_checkpoints(61_000, 10).unwrap();
    assert_eq!(due.len(), 1);
    assert_eq!(due[0].candidate_id, first_id);
    assert_eq!(due[0].horizon_seconds, 60);

    cleanup_dir(&root);
}
