use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{
    pump_realtime::PumpRealtimeNotification,
    pump_swap_trade::PumpSwapTradeEvidence,
    pump_trade::PumpTradeEvidence,
};
use shreks_storage::ShreksDb;
use tokio::sync::mpsc;

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-solana-public-realtime-writer-{}-{nanos}",
        process::id()
    ))
}

#[tokio::test]
async fn solana_public_realtime_writer_preserves_bonding_and_pumpswap_provenance() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let writer_db = ShreksDb::open(&db_path).unwrap();
    let (sender, receiver) = mpsc::channel(1);

    sender
        .send(PumpRealtimeNotification {
            provider: ProviderId::SolanaPublic,
            signature: "SolanaPublicRealtime111".to_owned(),
            slot: 1_234_567,
            lifecycle: None,
            trades: vec![PumpTradeEvidence {
                mint: "MintPublic111".to_owned(),
                quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
                user: "TraderPublic111".to_owned(),
                is_buy: true,
                token_amount_raw: 500_000_000,
                sol_amount_raw: 2_500_000_000,
                quote_amount_raw: 2_500_000_000,
                timestamp_unix_seconds: 1_777_000_000,
                virtual_sol_reserves_raw: 32_000_000_000,
                virtual_token_reserves_raw: 900_000_000_000_000,
                real_sol_reserves_raw: 10_000_000_000,
                real_token_reserves_raw: 600_000_000_000_000,
                virtual_quote_reserves_raw: 32_000_000_000,
                real_quote_reserves_raw: 10_000_000_000,
                ix_name: "buy".to_owned(),
            }],
            pump_swap_trades: vec![PumpSwapTradeEvidence {
                log_index: 17,
                pool: "PoolPublic111".to_owned(),
                user: "SwapTraderPublic111".to_owned(),
                is_buy: false,
                base_amount_raw: 700_000_000,
                quote_amount_raw: 3_500_000_000,
                user_quote_amount_raw: 3_460_000_000,
                timestamp_unix_seconds: 1_777_000_001,
                pool_base_reserves_raw: 800_000_000_000_000,
                pool_quote_reserves_raw: 42_000_000_000,
            }],
        })
        .await
        .unwrap();
    drop(sender);

    assert_eq!(
        Observer::run_pump_realtime_writer(writer_db, receiver)
            .await
            .expect("Solana public evidence must use the existing durable realtime writer"),
        2
    );

    let db = ShreksDb::open(&db_path).unwrap();
    let pump = db
        .pump_trade_evidence_for_signature("SolanaPublicRealtime111")
        .unwrap();
    let pumpswap = db
        .pump_swap_trade_evidence_for_signature("SolanaPublicRealtime111")
        .unwrap();
    assert_eq!(pump.len(), 1);
    assert_eq!(pumpswap.len(), 1);
    assert_eq!(pump[0].provider, ProviderId::SolanaPublic);
    assert_eq!(pumpswap[0].provider, ProviderId::SolanaPublic);

    drop(db);
    let _ = fs::remove_dir_all(root);
}
