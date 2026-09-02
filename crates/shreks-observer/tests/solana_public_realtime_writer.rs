use std::{
    fs,
    path::PathBuf,
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_observer::Observer;
use shreks_providers::{
    pump_realtime::PumpRealtimeNotification,
    pump_swap_trade::{PumpSwapCurrentEconomicsEvidence, PumpSwapTradeEvidence},
    pump_trade::PumpTradeEvidence,
};
use shreks_storage::{pump_swap_event_ordinal, ShreksDb};
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
                fee_recipient: "FeeRecipientPublic111".to_owned(),
                fee_basis_points: 95,
                fee_raw: 23_750_000,
                creator: "CreatorPublic111".to_owned(),
                creator_fee_basis_points: 30,
                creator_fee_raw: 7_500_000,
                cashback_fee_basis_points: 5,
                cashback_raw: 1_250_000,
                buyback_fee_basis_points: 7,
                buyback_fee_raw: 1_750_000,
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
                lp_fee_basis_points: 20,
                lp_fee_raw: 7_000_000,
                protocol_fee_basis_points: 93,
                protocol_fee_raw: 32_550_000,
                quote_amount_with_or_without_lp_fee_raw: 3_507_000_000,
                current_economics: Some(PumpSwapCurrentEconomicsEvidence {
                    coin_creator: "SwapCreatorPublic111".to_owned(),
                    coin_creator_fee_basis_points: 30,
                    coin_creator_fee_raw: 10_500_000,
                    cashback_fee_basis_points: 5,
                    cashback_raw: 1_750_000,
                    buyback_fee_basis_points: 7,
                    buyback_fee_raw: 2_450_000,
                    virtual_quote_reserves_raw: 4_000_000_000,
                    can_boost: true,
                    base_supply_raw: 1_000_000_000_000_000,
                }),
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

    let pump_economics = db
        .pump_trade_execution_economics("SolanaPublicRealtime111", 0)
        .unwrap()
        .expect("Pump fee evidence must survive the realtime storage boundary");
    assert_eq!(pump_economics.fee_basis_points, 95);
    assert_eq!(pump_economics.fee_raw, 23_750_000);
    assert_eq!(pump_economics.creator_fee_raw, 7_500_000);
    assert_eq!(pump_economics.cashback_raw, 1_250_000);
    assert_eq!(pump_economics.buyback_fee_raw, 1_750_000);

    let swap_ordinal = pump_swap_event_ordinal(17).unwrap();
    let pumpswap_economics = db
        .pump_swap_execution_economics("SolanaPublicRealtime111", swap_ordinal)
        .unwrap()
        .expect("PumpSwap fee evidence must survive the realtime storage boundary");
    assert_eq!(pumpswap_economics.lp_fee_raw, 7_000_000);
    assert_eq!(pumpswap_economics.protocol_fee_raw, 32_550_000);
    assert_eq!(
        pumpswap_economics.virtual_quote_reserves_raw,
        Some(4_000_000_000)
    );
    assert_eq!(pumpswap_economics.can_boost, Some(true));

    drop(db);
    let _ = fs::remove_dir_all(root);
}
