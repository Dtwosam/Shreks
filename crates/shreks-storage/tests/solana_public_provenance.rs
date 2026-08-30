use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::ProviderId;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const WSOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-solana-public-provenance-{}-{nanos}",
        process::id()
    ))
}

#[test]
fn solana_public_raw_pump_provenance_round_trips_from_storage() {
    let root = unique_test_dir();
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let row = PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "sig-public".to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms: 1_100,
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
    };

    assert!(db.record_pump_trade_evidence(&row).unwrap());
    let pending = db.pending_pump_trade_evidence(1).unwrap();
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].provider, ProviderId::SolanaPublic);

    drop(db);
    let _ = fs::remove_dir_all(root);
}
