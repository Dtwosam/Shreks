use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::ProviderId;
use shreks_storage::{pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, ShreksDb};

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-solana-public-pumpswap-storage-{}-{nanos}",
        process::id()
    ))
}

#[test]
fn solana_public_pumpswap_evidence_round_trips_exact_provider_identity() {
    let root = unique_test_dir();
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let evidence = PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "swap-public".to_owned(),
        ordinal: pump_swap_event_ordinal(7).unwrap(),
        log_index: 7,
        slot: 900,
        observed_at_unix_ms: 1_777_000_000_100,
        pool: "pool-public".to_owned(),
        user: "wallet-public".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: 1_777_000_000,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    };

    assert!(db.record_pump_swap_trade_evidence(&evidence).unwrap());
    let rows = db
        .pump_swap_trade_evidence_for_signature("swap-public")
        .unwrap();
    assert_eq!(rows, vec![evidence]);

    drop(db);
    let _ = fs::remove_dir_all(root);
}
