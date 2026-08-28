use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, LifecycleEventKind, ProviderId,
    TokenLifecycleEvent, VenueId,
};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapMarket, PumpSwapTradeEvidenceWrite, ShreksDb, StorageError,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pumpswap-evidence-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw(signature: &str, log_index: u32, observed_at_unix_ms: i64) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms,
        pool: "pool-a".to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: 1_777_000_000,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

fn migration(
    signature: &str,
    mint: &str,
    quote_mint: &str,
    pool: &str,
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
        slot: 850,
        detected_at_unix_ms: 1_776_999_900_000,
        occurred_at_unix_ms: Some(1_776_999_899_000),
    }
}

#[test]
fn pumpswap_raw_evidence_is_immutable_restart_safe_and_namespace_separated() {
    let root = unique_test_dir("raw");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(db.diagnostics().unwrap().schema_version, 12);

    assert_eq!(pump_swap_event_ordinal(0).unwrap(), 0x8000_0000);
    assert_eq!(pump_swap_event_ordinal(17).unwrap(), 0x8000_0011);
    assert!(pump_swap_event_ordinal(0x8000_0000).is_err());

    let first = raw("swap-a", 17, 1_777_000_000_100);
    assert!(db.record_pump_swap_trade_evidence(&first).unwrap());

    let mut replay = first.clone();
    replay.observed_at_unix_ms += 500;
    assert!(!db.record_pump_swap_trade_evidence(&replay).unwrap());

    let rows = db.pump_swap_trade_evidence_for_signature("swap-a").unwrap();
    assert_eq!(rows, vec![first.clone()]);

    let mut conflict = first.clone();
    conflict.quote_amount_raw += 1;
    assert!(matches!(
        db.record_pump_swap_trade_evidence(&conflict).unwrap_err(),
        StorageError::InvalidData(_)
    ));

    drop(db);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened
            .pending_pump_swap_trade_evidence(10)
            .unwrap()
            .first()
            .unwrap(),
        &first
    );

    cleanup_dir(&root);
}

#[test]
fn pumpswap_pool_resolution_is_verified_and_canonical_source_integrity_is_venue_aware() {
    let root = unique_test_dir("market");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    assert_eq!(db.pump_swap_market_for_pool("pool-a").unwrap(), None);

    db.record_pump_migration_signal("migration-a", 850, 1_776_999_900_000)
        .unwrap();
    db.complete_pump_migration(
        "migration-a",
        1_776_999_900_100,
        &[migration("migration-a", "mint-a", WSOL, "pool-a")],
    )
    .unwrap();

    assert_eq!(
        db.pump_swap_market_for_pool("pool-a").unwrap(),
        Some(PumpSwapMarket {
            mint: "mint-a".to_owned(),
            quote_mint: WSOL.to_owned(),
            pool_address: "pool-a".to_owned(),
        })
    );

    let raw = raw("swap-a", 17, 1_777_000_000_100);
    db.record_pump_swap_trade_evidence(&raw).unwrap();
    let event = FastEvent::new(
        FastEventId::new("swap-a", raw.ordinal).unwrap(),
        1,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpSwap).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        900,
        1_777_000_000_000,
        1_777_000_000_200,
        500.0,
        2.5,
        0.005,
    )
    .unwrap();
    assert!(db
        .record_fast_event(&event, raw.observed_at_unix_ms, 6, 9)
        .unwrap());
    assert!(db.pending_pump_swap_trade_evidence(10).unwrap().is_empty());

    db.record_pump_migration_signal("migration-b", 851, 1_776_999_901_000)
        .unwrap();
    db.complete_pump_migration(
        "migration-b",
        1_776_999_901_100,
        &[migration("migration-b", "mint-other", WSOL, "pool-a")],
    )
    .unwrap();
    assert!(matches!(
        db.pump_swap_market_for_pool("pool-a").unwrap_err(),
        StorageError::InvalidData(_)
    ));

    cleanup_dir(&root);
}
