use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, ProviderId, VenueId,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const SOURCE_OBSERVED_MS: i64 = 1_100;
const CANONICAL_OBSERVED_MS: i64 = 1_300;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-event-source-integrity-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms: SOURCE_OBSERVED_MS,
        mint: "mint-a".to_owned(),
        quote_mint: WSOL.to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw: 100_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 10_000_000_000,
        virtual_token_reserves_raw: 20_000_000_000,
        real_sol_reserves_raw: 5_000_000_000,
        real_token_reserves_raw: 10_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    }
}

fn canonical_event(signature: &str) -> FastEvent {
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        1,
        ProviderId::Helius,
        FastMarketKey::new("mint-a", WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some("wallet-a".to_owned()),
        55,
        1_000,
        CANONICAL_OBSERVED_MS,
        2.0,
        0.1,
        0.05,
    )
    .unwrap()
}

fn assert_rejected(db: &ShreksDb, event: &FastEvent) {
    let error = db
        .record_fast_event(event, SOURCE_OBSERVED_MS, 6, 9)
        .expect_err("canonical payload that disagrees with raw Pump truth must be rejected");
    assert!(matches!(error, StorageError::InvalidData(_)));
}

#[test]
fn first_canonical_append_must_match_immutable_pump_source_truth() {
    let root = unique_test_dir("bonding-curve");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let mut cases = Vec::new();

    let signature = "wrong-provider";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.provider = ProviderId::DexScreener;
    cases.push(event);

    let signature = "wrong-actor";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.actor = Some("wallet-b".to_owned());
    cases.push(event);

    let signature = "wrong-slot";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.slot = 56;
    cases.push(event);

    let signature = "wrong-side";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.kind = FastEventKind::Sell;
    cases.push(event);

    let signature = "wrong-occurrence";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.occurred_at_unix_ms = 1_001;
    cases.push(event);

    let signature = "wrong-market";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.market = FastMarketKey::new("mint-b", WSOL, VenueId::PumpFunBondingCurve).unwrap();
    cases.push(event);

    let signature = "wrong-base-economics";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.base_quantity = 4.0;
    event.price_quote = 0.025;
    cases.push(event);

    let signature = "wrong-quote-economics";
    db.record_pump_trade_evidence(&raw_trade(signature)).unwrap();
    let mut event = canonical_event(signature);
    event.quote_quantity = 0.2;
    event.price_quote = 0.1;
    cases.push(event);

    for event in &cases {
        assert_rejected(&db, event);
    }

    assert_eq!(db.next_fast_event_sequence().unwrap(), 1);
    assert_eq!(db.pending_pump_trade_evidence(32).unwrap().len(), cases.len());

    cleanup_dir(&root);
}
