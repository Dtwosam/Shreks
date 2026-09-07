use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, LifecycleEventKind, PairMarketData, ProviderId, TokenLifecycleEvent, VenueId,
};
use shreks_storage::{PumpSignalStatus, ShreksDb};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pump-migration-storage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str, source: ProviderId, discovered_at_unix_ms: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: None,
        discovered_at_unix_ms,
        source,
    }
}

fn market_snapshot(mint: &str, observed_at_unix_ms: i64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pump_swap".to_owned(),
        pair_address: format!("pair-{mint}"),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some("1.0".to_owned()),
        liquidity_usd: Some(10_000.0),
        volume_5m: Some(1_000.0),
        volume_1h: Some(2_000.0),
        volume_6h: Some(3_000.0),
        volume_24h: Some(4_000.0),
        transactions: Vec::new(),
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(0),
        observed_at_unix_ms,
    }
}

fn event(
    signature: &str,
    mint: &str,
    quote_mint: &str,
    pool: &str,
    detected_at_unix_ms: i64,
) -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: mint.to_owned(),
        quote_mint: quote_mint.to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: pool.to_owned(),
        signature: signature.to_owned(),
        slot: u64::MAX,
        detected_at_unix_ms,
        occurred_at_unix_ms: Some(1_770_000_000_000),
    }
}

#[test]
fn lifecycle_event_kind_string_is_stable() {
    assert_eq!(LifecycleEventKind::PumpGraduation.as_str(), "pump_graduation");
}

#[test]
fn migration_five_adds_inbox_and_normalized_lifecycle_tables() {
    let root = unique_test_dir("schema");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 18);
    drop(db);

    let connection = Connection::open(&db_path).unwrap();
    for table in ["pump_migration_signals", "token_lifecycle_events"] {
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?1",
                [table],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 1, "missing table {table}");
    }

    let slot_type: String = connection
        .query_row(
            "SELECT type FROM pragma_table_info('pump_migration_signals') WHERE name='slot'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(slot_type, "TEXT");

    cleanup_dir(&root);
}

#[test]
fn migration_signal_is_idempotent_restart_safe_and_oldest_first() {
    let root = unique_test_dir("restart-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-late", 3, 300).unwrap();
    db.record_pump_migration_signal("sig-first", u64::MAX, 100)
        .unwrap();
    db.record_pump_migration_signal("sig-middle", 2, 200).unwrap();
    db.record_pump_migration_signal("sig-first", u64::MAX, 150)
        .unwrap();

    let pending = db.pending_pump_migration_signals(2).unwrap();
    assert_eq!(pending.len(), 2);
    assert_eq!(pending[0].signature, "sig-first");
    assert_eq!(pending[0].slot, u64::MAX);
    assert_eq!(pending[0].observed_at_unix_ms, 100);
    assert_eq!(pending[0].status, PumpSignalStatus::Pending);
    assert_eq!(pending[1].signature, "sig-middle");
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    let pending = reopened.pending_pump_migration_signals(10).unwrap();
    assert_eq!(pending.len(), 3);
    assert_eq!(pending[0].signature, "sig-first");
    assert_eq!(pending[0].slot, u64::MAX);

    cleanup_dir(&root);
}

#[test]
fn migration_attempts_remain_pending_and_record_retry_state() {
    let root = unique_test_dir("attempts");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-retry", 42, 100).unwrap();
    db.record_pump_migration_attempt("sig-retry", 150, Some("not available"))
        .unwrap();
    db.record_pump_migration_attempt("sig-retry", 175, None)
        .unwrap();

    let pending = db.pending_pump_migration_signals(10).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].attempt_count, 2);
    assert_eq!(pending[0].last_attempt_at_unix_ms, Some(175));
    assert_eq!(pending[0].last_error, None);

    cleanup_dir(&root);
}

#[test]
fn completion_is_atomic_normalized_and_identical_replay_is_noop() {
    let root = unique_test_dir("complete");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("sig-ok", u64::MAX, 100)
        .unwrap();

    let first = event("sig-ok", "mint-a", "quote-a", "pool-a", 100);
    let second = event("sig-ok", "mint-b", "quote-b", "pool-b", 100);
    let inserted = db
        .complete_pump_migration("sig-ok", 180, &[first.clone(), second.clone()])
        .unwrap();
    assert_eq!(inserted, 2);
    assert!(db.pending_pump_migration_signals(10).unwrap().is_empty());

    let replayed = db
        .complete_pump_migration("sig-ok", 190, &[first.clone(), second.clone()])
        .unwrap();
    assert_eq!(replayed, 0);

    assert_eq!(db.lifecycle_events_for_mint("mint-a").unwrap(), vec![first]);
    assert_eq!(db.lifecycle_events_for_mint("mint-b").unwrap(), vec![second]);

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<i64>, Option<String>) = connection
        .query_row(
            "SELECT status, attempt_count, last_attempt_at_unix_ms, last_error FROM pump_migration_signals WHERE signature='sig-ok'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(row.0, "verified");
    assert_eq!(row.1, 1);
    assert_eq!(row.2, Some(180));
    assert_eq!(row.3, None);

    cleanup_dir(&root);
}

#[test]
fn verified_replay_cannot_append_or_mutate_lifecycle_truth() {
    let root = unique_test_dir("immutable-terminal");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("sig-ok", 9, 100).unwrap();

    let original = event("sig-ok", "mint-a", "quote-a", "pool-a", 100);
    db.complete_pump_migration("sig-ok", 180, std::slice::from_ref(&original))
        .unwrap();

    let changed = event("sig-ok", "mint-a", "quote-a", "pool-changed", 100);
    assert!(db
        .complete_pump_migration("sig-ok", 190, &[original.clone(), changed])
        .is_err());
    assert_eq!(db.lifecycle_events_for_mint("mint-a").unwrap(), vec![original]);

    db.record_pump_migration_signal("sig-ok", 9, 50).unwrap();
    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64) = connection
        .query_row(
            "SELECT status, observed_at_unix_ms FROM pump_migration_signals WHERE signature='sig-ok'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(row.0, "verified");
    assert_eq!(row.1, 50);

    cleanup_dir(&root);
}

#[test]
fn lifecycle_lookup_is_deterministic_by_detection_signature_and_pool() {
    let root = unique_test_dir("lookup-order");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for (signature, detected, pool) in [
        ("sig-c", 300, "pool-c"),
        ("sig-b", 100, "pool-z"),
        ("sig-a", 100, "pool-a"),
    ] {
        db.record_pump_migration_signal(signature, 1, detected).unwrap();
        let row = event(signature, "mint-one", "quote", pool, detected);
        db.complete_pump_migration(signature, detected + 1, &[row])
            .unwrap();
    }

    let rows = db.lifecycle_events_for_mint("mint-one").unwrap();
    let order: Vec<_> = rows
        .iter()
        .map(|row| (row.detected_at_unix_ms, row.signature.as_str(), row.pool_address.as_str()))
        .collect();
    assert_eq!(
        order,
        vec![
            (100, "sig-a", "pool-a"),
            (100, "sig-b", "pool-z"),
            (300, "sig-c", "pool-c"),
        ]
    );

    cleanup_dir(&root);
}

#[test]
fn rejection_is_terminal_auditable_and_duplicate_signal_does_not_reset_it() {
    let root = unique_test_dir("reject");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-bad", 7, 100).unwrap();
    db.mark_pump_migration_rejected("sig-bad", 180, "not a verified migration")
        .unwrap();
    db.record_pump_migration_signal("sig-bad", 7, 90).unwrap();

    assert!(db.pending_pump_migration_signals(10).unwrap().is_empty());
    assert!(db
        .complete_pump_migration(
            "sig-bad",
            190,
            &[event("sig-bad", "mint", "quote", "pool", 90)],
        )
        .is_err());

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, i64, Option<String>, Option<i64>) = connection
        .query_row(
            "SELECT status, observed_at_unix_ms, last_error, last_attempt_at_unix_ms FROM pump_migration_signals WHERE signature='sig-bad'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(row.0, "rejected");
    assert_eq!(row.1, 90);
    assert_eq!(row.2.as_deref(), Some("not a verified migration"));
    assert_eq!(row.3, Some(180));

    cleanup_dir(&root);
}

#[test]
fn invalid_completion_inputs_fail_closed_without_partial_event_rows() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    assert!(db.record_pump_migration_signal("", 1, 100).is_err());
    assert!(db.record_pump_migration_signal("sig-negative", 1, -1).is_err());
    assert!(db
        .complete_pump_migration("unknown", 100, &[event("unknown", "m", "q", "p", 100)])
        .is_err());

    db.record_pump_migration_signal("sig-empty", 1, 100).unwrap();
    assert!(db.complete_pump_migration("sig-empty", 120, &[]).is_err());

    let mut invalid = event("sig-empty", "mint", "quote", "pool", 100);
    invalid.pool_address.clear();
    assert!(db
        .complete_pump_migration("sig-empty", 120, &[invalid])
        .is_err());

    let mut wrong_signature = event("other", "mint", "quote", "pool", 100);
    wrong_signature.occurred_at_unix_ms = None;
    assert!(db
        .complete_pump_migration("sig-empty", 120, &[wrong_signature])
        .is_err());

    let connection = Connection::open(&db_path).unwrap();
    let events: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_lifecycle_events", [], |row| row.get(0))
        .unwrap();
    assert_eq!(events, 0);

    cleanup_dir(&root);
}


#[test]
fn lifecycle_storage_round_trips_every_supported_provider_id() {
    let root = unique_test_dir("provider-round-trip");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let providers = [
        ProviderId::DexScreener,
        ProviderId::Helius,
        ProviderId::Alchemy,
        ProviderId::Chainstack,
        ProviderId::SolanaPublic,
        ProviderId::Jupiter,
        ProviderId::Meteora,
    ];

    for (index, provider) in providers.into_iter().enumerate() {
        let signature = format!("sig-provider-{index}");
        let mint = format!("mint-provider-{index}");
        db.record_pump_migration_signal(
            &signature,
            u64::try_from(index + 1).unwrap(),
            1_000 + i64::try_from(index).unwrap(),
        )
        .unwrap();

        let mut lifecycle = event(
            &signature,
            &mint,
            "quote",
            &format!("pool-provider-{index}"),
            1_000 + i64::try_from(index).unwrap(),
        );
        lifecycle.provider = provider;

        db.complete_pump_migration(
            &signature,
            2_000 + i64::try_from(index).unwrap(),
            std::slice::from_ref(&lifecycle),
        )
        .unwrap();

        assert_eq!(
            db.lifecycle_events_for_mint(&mint).unwrap(),
            vec![lifecycle],
        );
    }

    cleanup_dir(&root);
}

#[test]
fn verified_migration_sampling_targets_are_bounded_and_deduplicated_by_mint() {
    let root = unique_test_dir("sampling-targets");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("sig-target", 1, 1_000).unwrap();
    let row = event(
        "sig-target",
        "mint-target",
        "So11111111111111111111111111111111111111112",
        "pool-target",
        1_000,
    );
    db.complete_pump_migration("sig-target", 1_100, std::slice::from_ref(&row))
        .unwrap();

    let before = db.verified_pump_swap_sampling_targets(0, 999).unwrap();
    assert!(before.is_empty());

    let selected = db
        .verified_pump_swap_sampling_targets(1_000, 2_000)
        .unwrap();
    assert_eq!(selected.len(), 1);
    assert_eq!(selected[0].mint, "mint-target");
    assert_eq!(selected[0].pool_address, "pool-target");
    assert_eq!(selected[0].detected_at_unix_ms, 1_000);
    assert_eq!(selected[0].provider, ProviderId::Helius);

    cleanup_dir(&root);
}

#[test]
fn migration_sampling_candidate_reuses_sole_candidate_without_snapshots() {
    let root = unique_test_dir("sampling-sole-candidate");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let expected = db
        .upsert_candidate(&candidate("mint-sole", ProviderId::SolanaPublic, 100))
        .unwrap();

    let resolved = db
        .migration_sampling_candidate_for_mint("mint-sole")
        .unwrap()
        .unwrap();
    assert_eq!(resolved.candidate_id, expected);
    assert_eq!(resolved.mint, "mint-sole");

    cleanup_dir(&root);
}

#[test]
fn migration_sampling_candidate_prefers_unique_snapshot_owner() {
    let root = unique_test_dir("sampling-snapshot-owner");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let _empty = db
        .upsert_candidate(&candidate("mint-owner", ProviderId::SolanaPublic, 100))
        .unwrap();
    let owner = db
        .upsert_candidate(&candidate("mint-owner", ProviderId::DexScreener, 120))
        .unwrap();
    db.insert_market_snapshot(owner, &market_snapshot("mint-owner", 130))
        .unwrap();

    let resolved = db
        .migration_sampling_candidate_for_mint("mint-owner")
        .unwrap()
        .unwrap();
    assert_eq!(resolved.candidate_id, owner);

    cleanup_dir(&root);
}

#[test]
fn migration_sampling_candidate_prefers_unique_dexscreener_identity_without_snapshots() {
    let root = unique_test_dir("sampling-dexscreener-ownerless");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let _chain = db
        .upsert_candidate(&candidate(
            "mint-dexscreener-ownerless",
            ProviderId::SolanaPublic,
            100,
        ))
        .unwrap();
    let expected = db
        .upsert_candidate(&candidate(
            "mint-dexscreener-ownerless",
            ProviderId::DexScreener,
            120,
        ))
        .unwrap();

    let resolved = db
        .migration_sampling_candidate_for_mint("mint-dexscreener-ownerless")
        .unwrap()
        .unwrap();

    assert_eq!(resolved.candidate_id, expected);
    assert_eq!(resolved.mint, "mint-dexscreener-ownerless");

    cleanup_dir(&root);
}

#[test]
fn migration_sampling_candidate_rejects_multiple_dexscreener_identities_without_snapshots() {
    let root = unique_test_dir("sampling-multiple-dexscreener-ownerless");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.upsert_candidate(&candidate(
        "mint-multiple-dex",
        ProviderId::SolanaPublic,
        100,
    ))
    .unwrap();
    db.upsert_candidate(&candidate(
        "mint-multiple-dex",
        ProviderId::DexScreener,
        120,
    ))
    .unwrap();
    db.upsert_candidate(&DiscoveredToken {
        mint: "mint-multiple-dex".to_owned(),
        pair_address: Some("pair-alt".to_owned()),
        dex_id: Some("pump_swap".to_owned()),
        venue: Some(VenueId::PumpSwap),
        discovered_at_unix_ms: 130,
        source: ProviderId::DexScreener,
    })
    .unwrap();

    let error = db
        .migration_sampling_candidate_for_mint("mint-multiple-dex")
        .unwrap_err();

    assert!(
        error
            .to_string()
            .contains("0 snapshot owners and 2 DexScreener candidates")
    );

    cleanup_dir(&root);
}

#[test]
fn migration_sampling_candidate_rejects_multiple_snapshot_owners() {
    let root = unique_test_dir("sampling-ambiguous-owners");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first = db
        .upsert_candidate(&candidate("mint-ambiguous", ProviderId::SolanaPublic, 100))
        .unwrap();
    let second = db
        .upsert_candidate(&candidate("mint-ambiguous", ProviderId::DexScreener, 120))
        .unwrap();
    db.insert_market_snapshot(first, &market_snapshot("mint-ambiguous", 130))
        .unwrap();
    db.insert_market_snapshot(second, &market_snapshot("mint-ambiguous", 140))
        .unwrap();

    let error = db
        .migration_sampling_candidate_for_mint("mint-ambiguous")
        .unwrap_err();
    assert!(error.to_string().contains("ambiguous"));

    cleanup_dir(&root);
}

