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
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, ShreksDb, StorageError,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const SOURCE_OBSERVED_MS: i64 = 1_100;
const CANONICAL_OBSERVED_MS: i64 = 1_300;
const POOL: &str = "pool-a";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-pumpswap-fast-event-source-integrity-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(signature: &str, log_index: u32) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 900,
        observed_at_unix_ms: SOURCE_OBSERVED_MS,
        pool: POOL.to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: 1,
        pool_base_reserves_raw: 9_500_000_000,
        pool_quote_reserves_raw: 52_500_000_000,
    }
}

fn verified_market() -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::Helius,
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: POOL.to_owned(),
        signature: "migration-sig".to_owned(),
        slot: 899,
        detected_at_unix_ms: 900,
        occurred_at_unix_ms: Some(1_000),
    }
}

fn canonical_event(signature: &str, log_index: u32) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, pump_swap_event_ordinal(log_index).unwrap()).unwrap(),
        1,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpSwap).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        900,
        1_000,
        CANONICAL_OBSERVED_MS,
        500.0,
        2.5,
        0.005,
    )
    .unwrap()
}

fn assert_rejected(db: &ShreksDb, event: &FastEvent) {
    let error = db
        .record_fast_event(event, SOURCE_OBSERVED_MS, 6, 9)
        .expect_err("canonical payload that disagrees with raw PumpSwap truth must be rejected");
    assert!(matches!(error, StorageError::InvalidData(_)));
}

#[test]
fn first_canonical_append_must_match_immutable_pumpswap_source_truth() {
    let root = unique_test_dir("pumpswap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    db.record_pump_migration_signal("migration-sig", 899, 900)
        .unwrap();
    db.complete_pump_migration("migration-sig", 950, &[verified_market()])
        .unwrap();

    let mut cases = Vec::new();

    let signature = "wrong-provider";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 1))
        .unwrap();
    let mut event = canonical_event(signature, 1);
    event.provider = ProviderId::DexScreener;
    cases.push(event);

    let signature = "wrong-actor";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 2))
        .unwrap();
    let mut event = canonical_event(signature, 2);
    event.actor = Some("wallet-b".to_owned());
    cases.push(event);

    let signature = "wrong-slot";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 3))
        .unwrap();
    let mut event = canonical_event(signature, 3);
    event.slot = 901;
    cases.push(event);

    let signature = "wrong-side";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 4))
        .unwrap();
    let mut event = canonical_event(signature, 4);
    event.kind = FastEventKind::Sell;
    cases.push(event);

    let signature = "wrong-occurrence";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 5))
        .unwrap();
    let mut event = canonical_event(signature, 5);
    event.occurred_at_unix_ms = 1_001;
    cases.push(event);

    let signature = "wrong-market-quote-flow";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 6))
        .unwrap();
    let mut event = canonical_event(signature, 6);
    event.quote_quantity = 2.53;
    event.price_quote = 0.00506;
    cases.push(event);

    let signature = "wrong-base-economics";
    db.record_pump_swap_trade_evidence(&raw_trade(signature, 7))
        .unwrap();
    let mut event = canonical_event(signature, 7);
    event.base_quantity = 250.0;
    event.price_quote = 0.01;
    cases.push(event);

    for event in &cases {
        assert_rejected(&db, event);
    }

    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert_eq!(
        db.pending_pump_swap_trade_evidence(32).unwrap().len(),
        cases.len()
    );

    cleanup_dir(&root);
}
